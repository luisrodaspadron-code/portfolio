from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.database import get_risk_rules
from app.services.advisor_intelligence import TOOL_INVENTORY, build_advisor_packet, store_decision_packet, _stable_json
from app.services.ai_service import (
    _call_openai_response,
    _effective_openai_api_key,
    _extract_output_text,
    _usage,
    ai_failure_state,
    ai_run_record,
    ai_runtime_settings,
    insert_ai_run,
    json_schema_text_format,
    parse_model_json_object,
    user_safe_ai_error,
)
from app.services.copilot_service import ask_copilot
from app.services.data_service import compute_universe_features
from app.services.advisor_math import build_add_plan, build_trim_plan, cap_distance, data_quality_from_price
from app.services.risk import evaluate_candidate, target_weight_for_candidate
from app.services.policy_engine import RiskPolicy, selected_risk_policy, threshold_for_state, PolicyState
from app.services.trade_impact import evaluate_trade_impact
from app.services.llm_review_packet import build_llm_review_packet
from app.services.llm_review_output import (
    LLM_REVIEW_OUTPUT_SCHEMA,
    detect_decision_conflict,
    detect_forbidden_claims,
)
from app.services.specialist_agents import run_specialist_agents
from app.services.universe_service import universe_status
from app.services.data_service import latest_fundamentals


DECISION_FIELDS = [
    "portfolio_verdict",
    "holding_decisions",
    "opportunity_decisions",
    "execution_plan",
    "staggering_guidance",
    "entry_conditions",
    "risks",
    "data_used",
    "missing_data",
    "what_would_change_my_mind",
]

ALLOWED_DECISIONS = {"Hold", "Add", "Trim", "Rotate", "Stagger Entry", "Avoid", "Wait For Data"}

DECISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": DECISION_FIELDS,
    "additionalProperties": False,
    "properties": {
        "portfolio_verdict": {"type": "string"},
        "holding_decisions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "opportunity_decisions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "execution_plan": {"type": "array", "items": {"type": "string"}},
        "staggering_guidance": {"type": "array", "items": {"type": "string"}},
        "entry_conditions": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "data_used": {"type": "array", "items": {"type": "string"}},
        "missing_data": {"type": "array", "items": {"type": "string"}},
        "what_would_change_my_mind": {"type": "array", "items": {"type": "string"}},
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text_list(value: Any, limit: int = 8) -> list[str]:
    return [str(item) for item in _as_list(value)[:limit]]


def _decision_label(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip().title()
    aliases = {
        "Stagger": "Stagger Entry",
        "Wait": "Wait For Data",
        "Wait For More Data": "Wait For Data",
        "Do Nothing": "Hold",
        "Keep": "Hold",
        "Reduce": "Trim",
        "Sell": "Trim",
        "Buy": "Add",
    }
    text = aliases.get(text, text)
    return text if text in ALLOWED_DECISIONS else fallback


def _confidence_label(confidence: float, data_confidence: str, eligible: bool) -> str:
    if not eligible:
        return "Not eligible now"
    if data_confidence != "fresh":
        return "Data limited"
    if confidence >= 0.72:
        return "High conviction"
    if confidence >= 0.58:
        return "Constructive"
    return "Needs confirmation"


def _candidate_source(item: dict[str, Any] | None) -> str:
    if not item:
        return "missing"
    source = item.get("price_source", "unknown")
    age = int(item.get("source_data_age_days") or 0)
    if source == "sample":
        return "sample-only"
    return "fresh" if age <= 7 else f"stale {age}d"


def _evidence(item: dict[str, Any] | None) -> list[str]:
    if not item:
        return ["No sufficient price history is available yet."]
    factors = item.get("factor_breakdown") or {}
    return [
        f"Composite score {item.get('score', 0):.2f}.",
        f"Cross-sectional momentum {factors.get('cross_section_momentum', 0):.2f}.",
        f"Time-series momentum {factors.get('time_series_momentum', 0):.2f}.",
        f"Quality/profitability {factors.get('quality_profitability', 0):.2f}.",
        f"Risk score {item.get('risk_score', 0):.2f}; max drawdown {item.get('max_drawdown', 0):.1%}.",
        f"Source {_candidate_source(item)}.",
    ]


def _position_data_quality(
    position: dict[str, Any],
    feature: dict[str, Any] | None,
    *,
    policy: RiskPolicy | None = None,
    fundamentals_symbols: set[str] | None = None,
) -> dict[str, Any]:
    if position.get("valuation_status") == "missing_price":
        return {
            "provider": "missing",
            "sourceTimestamp": "",
            "receivedAt": _now(),
            "ageSeconds": 999_999_999,
            "freshness": "missing",
            "coverage": "missing",
            "confidence": 0,
            "warnings": ["No local price or imported average cost is available."],
        }
    if feature:
        quality = data_quality_from_price(
            provider=str(feature.get("price_source") or "unknown"),
            source_timestamp=str(feature.get("latest_date") or ""),
            asset_class=str(position.get("asset_class") or "stock"),
            coverage="complete",
            sample=feature.get("price_source") == "sample",
            policy=policy,
        )
        symbol = str(position.get("symbol") or "").upper()
        if fundamentals_symbols is not None and symbol and symbol not in fundamentals_symbols:
            if str(position.get("asset_class") or "").lower() == "stock":
                quality["coverage"] = "partial"
                warnings = list(quality.get("warnings") or [])
                warnings.append("Fundamentals coverage incomplete.")
                quality["warnings"] = warnings
                quality["confidence"] = min(float(quality.get("confidence") or 0), 0.72)
        return quality
    quality = {
        "provider": "imported_cost_basis" if position.get("valuation_status") == "proxy" else "local_price",
        "sourceTimestamp": "",
        "receivedAt": _now(),
        "ageSeconds": 999_999_999,
        "freshness": "stale" if position.get("valuation_status") == "proxy" else "missing",
        "coverage": "insufficient",
        "confidence": 0.35,
        "warnings": [position.get("valuation_note") or "Insufficient market history for full signal generation."],
    }
    symbol = str(position.get("symbol") or "").upper()
    if fundamentals_symbols is not None and symbol and symbol not in fundamentals_symbols:
        if str(position.get("asset_class") or "").lower() == "stock":
            quality["coverage"] = "partial"
            warnings = list(quality.get("warnings") or [])
            warnings.append("Fundamentals coverage incomplete.")
            quality["warnings"] = warnings
            quality["confidence"] = min(float(quality.get("confidence") or 0), 0.72)
    return quality


def _sector_weights_from_holdings(holdings: list[dict[str, Any]]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for position in holdings:
        sector = str(position.get("sector") or "Unknown")
        weights[sector] = weights.get(sector, 0.0) + float(position.get("weight") or 0)
    return weights


def _is_broad_etf(position: dict[str, Any]) -> bool:
    if str(position.get("asset_class") or "").upper() != "ETF":
        return False
    theme = str(position.get("theme") or position.get("sector") or "").lower()
    name = str(position.get("name") or "").lower()
    if theme in {"thematic", "leveraged", "inverse"} or "leveraged" in name or "2x" in name or "3x" in name:
        return False
    return True


def _holding_cap_payload(position: dict[str, Any], rules: dict[str, Any], policy: RiskPolicy) -> dict[str, Any]:
    current_weight = float(position.get("weight") or 0)
    legacy_cap = rules["max_etf_weight"] if position.get("asset_class") == "ETF" else rules["max_single_stock_weight"]
    if _is_broad_etf(position) and policy.broad_etf.exempt_from_single_stock_cap:
        payload = cap_distance(current_weight, policy.broad_etf.max_single_broad_etf)
        breached = bool(payload.get("breached"))
        payload["state"] = "hard_buy_block" if breached else "ok"
        payload["blocksNewBuys"] = breached
        payload["requiresTrimPlan"] = breached
        return payload
    return cap_distance(current_weight, legacy_cap, single_stock=policy.single_stock)


def _trim_policy_state(state: str) -> PolicyState:
    if state in {"extreme", "urgent_review", "hard_buy_block", "warning", "ok"}:
        return state  # type: ignore[return-value]
    return "urgent_review"


def _portfolio_snapshot(holdings: list[dict[str, Any]], total_value: float, sector_weights: dict[str, float]) -> dict[str, Any]:
    return {
        "totalValue": total_value,
        "positions": [
            {
                "symbol": position["symbol"],
                "weight": float(position.get("weight") or 0),
                "sector": str(position.get("sector") or "Unknown"),
                "assetClass": str(position.get("asset_class") or "").lower(),
                "isBroadEtf": _is_broad_etf(position),
                "isThematicEtf": str(position.get("asset_class") or "").upper() == "ETF" and not _is_broad_etf(position),
            }
            for position in holdings
        ],
        "sectorWeights": dict(sector_weights),
    }


def _holding_decision(
    position: dict[str, Any],
    feature: dict[str, Any] | None,
    rules: dict[str, Any],
    total_value: float,
    sector_weights: dict[str, float],
    policy: RiskPolicy,
    fundamentals_symbols: set[str] | None = None,
) -> dict[str, Any]:
    current_weight = float(position.get("weight") or 0)
    cap = rules["max_etf_weight"] if position.get("asset_class") == "ETF" else rules["max_single_stock_weight"]
    source = _candidate_source(feature)
    cap_payload = _holding_cap_payload(position, rules, policy)
    state = str(cap_payload.get("state") or "ok")
    hard_cap_breach = state in {"urgent_review", "extreme"} or bool(cap_payload.get("requiresTrimPlan"))
    buy_blocked = bool(cap_payload.get("blocksNewBuys")) or state in {"hard_buy_block", "urgent_review", "extreme"}
    reason_code = "HOLD_WITHIN_POLICY"
    if position.get("valuation_status") == "missing_price":
        decision = "Wait For Data"
        target = min(current_weight, cap)
        reason = "Signal PM needs a usable price before sizing this holding."
        eligible = False
        reason_code = "PRICE_MISSING"
    elif state == "extreme":
        decision = "Trim"
        target = policy.single_stock.warning
        reason = (
            f"{position['symbol']} is in extreme concentration ({current_weight:.1%}); trim toward the warning level."
        )
        eligible = True
        reason_code = "SINGLE_NAME_EXTREME" if position.get("asset_class") != "ETF" else "ETF_CAP_BREACH"
    elif state == "urgent_review":
        decision = "Trim"
        target = policy.single_stock.warning
        reason = (
            f"{position['symbol']} is in urgent-review concentration ({current_weight:.1%}); trim toward the warning level."
        )
        eligible = True
        reason_code = "SINGLE_NAME_URGENT_REVIEW" if position.get("asset_class") != "ETF" else "ETF_CAP_BREACH"
    elif hard_cap_breach:
        # Legacy fallback when ETF asset class produces a different cap path.
        decision = "Trim"
        target = cap
        reason = f"{position['symbol']} is above the configured risk cap; trim toward the cap."
        eligible = True
        reason_code = "ETF_CAP_BREACH" if position.get("asset_class") == "ETF" else "SINGLE_NAME_CAP_BREACH"
    elif state == "hard_buy_block":
        decision = "Hold"
        target = min(current_weight, cap)
        reason = (
            f"{position['symbol']} is in hard buy-block concentration ({current_weight:.1%}); new buys are blocked but no forced trim yet."
        )
        eligible = True
        reason_code = "SINGLE_NAME_HARD_BUY_BLOCK"
    elif feature is None:
        decision = "Wait For Data"
        target = min(current_weight, cap)
        reason = "Signal PM cannot make a confident add-or-rotate decision until this holding has usable market history."
        eligible = False
        reason_code = "INSUFFICIENT_HISTORY"
    elif (feature["score"] < -0.08 and current_weight > cap * 0.5) or (feature["risk_score"] > 0.68 and current_weight > cap * 0.5):
        decision = "Trim"
        target = max(0.01, min(current_weight * 0.65, cap))
        reason = "The holding is large enough and weak enough on the current risk-adjusted evidence to justify a trim."
        eligible = True
        reason_code = "WEAK_RISK_ADJUSTED_SIGNAL"
    elif feature["score"] > 0.12 and current_weight < cap * 0.75 and source == "fresh" and not buy_blocked:
        decision = "Add"
        target = min(target_weight_for_candidate(feature, rules), cap)
        reason = "The holding already fits the portfolio and has strong current quant evidence without breaching size rules."
        eligible = True
        reason_code = "ADD_ELIGIBLE"
    elif state == "warning":
        decision = "Hold"
        target = min(current_weight, cap)
        reason = (
            f"{position['symbol']} is in the warning band ({current_weight:.1%}); hold and watch for risk-reducing rebalance opportunities."
        )
        eligible = True
        reason_code = "SINGLE_NAME_WARNING"
    else:
        decision = "Hold"
        target = min(max(current_weight, 0.01), cap)
        reason = "The holding is not forcing a change right now; monitor it through the next advisor cycle."
        eligible = True
    data_confidence = "sample_only" if source == "sample-only" else "stale" if source.startswith("stale") else "fresh" if source == "fresh" else "missing"
    confidence = float(feature.get("confidence", 0.25) if feature else 0.15)
    confidence_label = "Risk breach" if hard_cap_breach and eligible else _confidence_label(confidence, data_confidence, eligible)
    detail_payload: dict[str, Any] = {
        "advisoryOnly": True,
        "reasonCode": reason_code,
        "capDistance": cap_payload,
        "policyState": state,
        "blocksNewBuys": buy_blocked,
        "dataQuality": _position_data_quality(position, feature, policy=policy, fundamentals_symbols=fundamentals_symbols),
        "blockers": [] if eligible else [reason],
        "trimPlan": None,
        "addPlan": None,
    }
    latest_price = float(position.get("latest_price") or 0)
    if decision == "Trim" and latest_price > 0 and total_value > 0:
        trim_state = _trim_policy_state(state)
        policy_threshold = threshold_for_state(policy.single_stock, trim_state)
        detail_payload["trimPlan"] = build_trim_plan(
            total_portfolio_value=total_value,
            current_position_value=float(position.get("market_value") or 0),
            target_weight=float(target),
            live_price=latest_price,
            price_timestamp=str((feature or {}).get("latest_date") or ""),
            quantity=float(position.get("quantity") or 0),
            avg_cost=float(position.get("avg_cost") or 0),
            fractional_shares=True,
            compliance_mode="strict_below_threshold",
            policy_threshold=float(policy_threshold),
        )
    if decision == "Add" and total_value > 0:
        sector = str(position.get("sector") or "Unknown")
        detail_payload["addPlan"] = build_add_plan(
            total_portfolio_value=total_value,
            target_weight=float(target),
            current_sector_weight=float(sector_weights.get(sector, 0)),
            sector_cap=float(rules["max_sector_weight"]),
        )
    return {
        "symbol": position["symbol"],
        "item_type": "holding",
        "decision": decision,
        "plain_action": f"{decision} {position['symbol']}",
        "reason": reason,
        "target_weight": round(target, 4),
        "current_weight": round(current_weight, 4),
        "confidence_label": confidence_label,
        "confidence_score": round(confidence, 4),
        "eligibility": "eligible" if eligible else "needs_data",
        "risk_check": "Hard risk cap checked; no automatic trade is placed.",
        "quant_evidence": _evidence(feature),
        "source_freshness": source,
        "reason_code": reason_code,
        "detail_payload": detail_payload,
        "ai_commentary": "",
    }


def _opportunity_decision(
    candidate: dict[str, Any],
    rules: dict[str, Any],
    *,
    total_value: float,
    sector_weights: dict[str, float],
    policy: RiskPolicy,
    holdings: list[dict[str, Any]],
) -> dict[str, Any]:
    target = target_weight_for_candidate(candidate, rules)
    sector = str(candidate.get("sector") or "Unknown")
    current_sector_weight = float(sector_weights.get(sector, 0))
    status, flags = evaluate_candidate(
        candidate, target, rules, current_sector_weight=current_sector_weight, policy=policy
    )
    source = _candidate_source(candidate)
    score = float(candidate.get("score") or 0)
    impact = evaluate_trade_impact(
        _portfolio_snapshot(holdings, total_value, sector_weights),
        {
            "symbol": candidate.get("symbol", ""),
            "side": "buy",
            "weightDelta": target,
            "sector": sector,
            "assetClass": str(candidate.get("asset_class") or "").lower(),
            "isBroadEtf": bool(candidate.get("is_broad_etf") or (candidate.get("asset_class") == "ETF" and not candidate.get("is_thematic_etf"))),
            "isThematicEtf": bool(candidate.get("is_thematic_etf")),
        },
        policy,
    )
    if impact.blocked:
        flags.extend(reason for reason in impact.reasons if reason not in flags)
        status = "fail"
    if status == "fail":
        decision = "Avoid"
        if any("sector" in flag.lower() for flag in flags):
            reason = "The idea is blocked because portfolio sector exposure is already at or above the configured cap."
            reason_code = "SECTOR_CAP_BLOCKED"
        else:
            reason = "The idea is not eligible now because hard risk or liquidity gates failed."
            reason_code = "RISK_GATE_FAILED"
    elif source != "fresh":
        decision = "Wait For Data" if candidate.get("price_source") == "sample" else "Stagger Entry"
        reason = "The idea has interesting signals, but confidence is reduced until live/recent data confirms the setup."
        reason_code = "DATA_LIMITED"
    elif score > 0.16 and float(candidate.get("risk_score") or 0) < 0.34:
        decision = "Add"
        reason = "This is one of the strongest eligible ideas after momentum, quality, liquidity, drawdown, and risk checks."
        reason_code = "ADD_ELIGIBLE"
    elif score > 0.08:
        decision = "Stagger Entry"
        reason = "The idea is constructive, but staged exposure is more appropriate than a single lump-sum move."
        reason_code = "STAGGER_ENTRY_ELIGIBLE"
    else:
        decision = "Hold"
        reason = "The evidence is not strong enough to displace current portfolio capital right now."
        reason_code = "NOT_COMPETITIVE_ENOUGH"
    data_confidence = "sample_only" if source == "sample-only" else "stale" if source.startswith("stale") else "fresh"
    confidence = float(candidate.get("confidence") or 0.25)
    blockers = flags if status == "fail" else []
    add_plan = None
    if decision in {"Add", "Stagger Entry"} and total_value > 0:
        add_plan = build_add_plan(
            total_portfolio_value=total_value,
            target_weight=float(target),
            current_sector_weight=current_sector_weight,
            sector_cap=float(rules["max_sector_weight"]),
            blockers=flags,
        )
    return {
        "symbol": candidate["symbol"],
        "item_type": "opportunity",
        "decision": decision,
        "plain_action": f"{decision} {candidate['symbol']}",
        "reason": reason,
        "target_weight": round(target, 4),
        "current_weight": 0,
        "confidence_label": _confidence_label(confidence, data_confidence, status != "fail"),
        "confidence_score": round(confidence, 4),
        "eligibility": status,
        "risk_check": "; ".join(flags) if flags else "Passed deterministic risk gates.",
        "quant_evidence": _evidence(candidate),
        "source_freshness": source,
        "reason_code": reason_code,
        "detail_payload": {
            "advisoryOnly": True,
            "reasonCode": reason_code,
            "dataQuality": data_quality_from_price(
                provider=str(candidate.get("price_source") or "unknown"),
                source_timestamp=str(candidate.get("latest_date") or ""),
                asset_class=str(candidate.get("asset_class") or "stock"),
                coverage="complete",
                sample=candidate.get("price_source") == "sample",
                policy=policy,
            ),
            "blockers": blockers,
            "addPlan": add_plan,
            "trimPlan": None,
        },
        "ai_commentary": "",
    }


def _deterministic_decision(conn, packet: dict[str, Any]) -> dict[str, Any]:
    rules = get_risk_rules(conn)
    policy = selected_risk_policy(conn)
    features = compute_universe_features(conn)
    by_symbol = {item["symbol"]: item for item in features}
    real = packet["portfolio"]["real"]
    holdings = real.get("positions", [])
    total_value = float(real.get("total_value") or 0)
    sector_weights = _sector_weights_from_holdings(holdings)
    holding_symbols = {item["symbol"] for item in holdings}
    fundamentals_symbols = set(latest_fundamentals(conn).keys())
    holding_items = [
        _holding_decision(position, by_symbol.get(position["symbol"]), rules, total_value, sector_weights, policy, fundamentals_symbols)
        for position in holdings
    ]
    opportunities = []
    for candidate in features:
        if candidate["symbol"] in holding_symbols:
            continue
        opportunities.append(
            _opportunity_decision(
                candidate,
                rules,
                total_value=total_value,
                sector_weights=sector_weights,
                policy=policy,
                holdings=holdings,
            )
        )
        if len(opportunities) >= 10:
            break
    urgent_trims = [item for item in holding_items if item["decision"] == "Trim"]
    add_items = [item for item in [*holding_items, *opportunities] if item["decision"] in {"Add", "Stagger Entry"}]
    execution_plan = [
        "No real trades are placed by Signal PM.",
        "Address hard concentration trims before adding similar exposure.",
        "For long-term adds, prefer 3 to 5 tranches over several weeks unless the next data refresh changes the signal.",
    ]
    if urgent_trims:
        execution_plan.insert(1, f"Prioritize {urgent_trims[0]['symbol']} and other concentration trims before initiating any new adds.")
        execution_plan.append("New single-stock adds are blocked until hard concentration breaches are remediated.")
    if any(item.get("reason_code") == "SECTOR_CAP_BLOCKED" for item in opportunities):
        execution_plan.append("Adds in overweight sectors are blocked until sector exposure is reduced.")
    if not holdings:
        verdict = "Import real holdings before trusting portfolio-specific decisions."
    elif urgent_trims:
        verdict = f"Review concentration first: {urgent_trims[0]['symbol']} is the highest-priority trim candidate."
    elif add_items:
        verdict = f"Portfolio can stay mostly intact; the strongest incremental idea is {add_items[0]['symbol']}."
    else:
        verdict = "Keep the portfolio broadly as-is for now; no eligible idea is strong enough to force a change."
    sample_only = packet["data_quality"]["sample_only"]
    return {
        "portfolio_verdict": verdict,
        "holding_decisions": holding_items,
        "opportunity_decisions": opportunities,
        "execution_plan": execution_plan,
        "staggering_guidance": [
            "Use staged entries for volatile or sample-data ideas.",
            "Use a single allocation only when data is fresh, risk gates pass, and the target weight is small relative to portfolio value.",
        ],
        "entry_conditions": [
            "Fresh provider data confirms the score and source age is seven days or less.",
            "The idea remains above the portfolio's current weakest holding after risk and turnover penalties.",
            "For IPO/special-situation names, wait for tradeable status, seasoning, filings, and liquidity before any add decision.",
        ],
        "risks": [
            packet["data_quality"]["message"],
            *packet["risk_breaches"][:4],
        ],
        "data_used": [
            f"{packet['provider_freshness']['provider_mode']} price mode",
            f"{universe_status(conn)['included_assets']} included universe assets",
            "momentum, quality, value proxy, drawdown, liquidity, macro regime, and risk gates",
        ],
        "missing_data": ["Live provider data is required before treating sample-only ideas as high confidence."] if sample_only else [],
        "what_would_change_my_mind": [
            "A holding moves from risk breach to within cap after market movement or a staged trim.",
            "A candidate loses trend/quality leadership in the next walk-forward snapshot.",
            "SEC fundamentals materially weaken or live data becomes stale/rate-limited.",
        ],
    }


def _parse_llm_review(output_text: str) -> dict[str, Any]:
    parsed = parse_model_json_object(output_text)
    if not isinstance(parsed, dict):
        raise ValueError("LLM review response was not a JSON object.")
    for field in LLM_REVIEW_OUTPUT_SCHEMA["required"]:
        if field not in parsed:
            raise ValueError(f"LLM review missing field: {field}")
    return parsed


def _apply_llm_review(
    review: dict[str, Any],
    deterministic: dict[str, Any],
    review_packet: dict[str, Any],
) -> dict[str, Any]:
    first_action = review_packet.get("deterministicFirstAction") or {}
    conflict = detect_decision_conflict(
        review,
        first_action.get("symbol"),
        first_action.get("decision"),
    )
    narrative_blob = " ".join(
        str(review.get(key) or "")
        for key in ("headline", "executiveSummary", "userExplanation", "confidenceNarrative", "advisoryOnlyDisclosure")
    )
    forbidden = detect_forbidden_claims(narrative_blob)

    holding_items = [dict(item) for item in deterministic["holding_decisions"]]
    opportunity_items = [dict(item) for item in deterministic["opportunity_decisions"]]
    commentary = str(review.get("userExplanation") or review.get("executiveSummary") or "").strip()
    first_symbol = first_action.get("symbol")
    if first_symbol and commentary:
        for item in [*holding_items, *opportunity_items]:
            if item["symbol"] == first_symbol:
                item["ai_commentary"] = commentary
                break

    risks = _text_list(review.get("keyRisks") or deterministic.get("risks"), 8)
    if conflict:
        risks.insert(0, f"LLM conflict (logged, not merged): {conflict}")
    if forbidden:
        risks.append(f"Forbidden LLM phrasing flagged: {', '.join(forbidden)}")

    execution_plan = _text_list(deterministic.get("execution_plan"), 8)
    alternatives = _text_list(review.get("whyNotAlternatives"), 4)
    if alternatives:
        execution_plan = [*execution_plan, *alternatives][:8]

    return {
        **deterministic,
        "portfolio_verdict": str(review.get("headline") or review.get("executiveSummary") or deterministic["portfolio_verdict"]),
        "holding_decisions": holding_items,
        "opportunity_decisions": opportunity_items,
        "execution_plan": execution_plan,
        "staggering_guidance": _text_list(deterministic.get("staggering_guidance"), 6),
        "entry_conditions": _text_list(review.get("whyNow") or deterministic.get("entry_conditions"), 8),
        "risks": risks[:8],
        "data_used": _text_list(deterministic.get("data_used"), 8),
        "missing_data": _text_list(review.get("dataLimitations") or deterministic.get("missing_data"), 8),
        "what_would_change_my_mind": _text_list(review.get("followUpQuestions") or deterministic.get("what_would_change_my_mind"), 8),
        "llm_review": {
            **review,
            "conflictLogged": conflict,
            "forbiddenClaims": forbidden,
        },
    }


def _decision_context(packet: dict[str, Any], deterministic: dict[str, Any], universe: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective": packet["objective"],
        "decision_boundary": packet["decision_boundary"],
        "tool_inventory": TOOL_INVENTORY,
        "portfolio": packet["portfolio"]["real"],
        "risk_rules": packet["risk_rules"],
        "risk_breaches": packet["risk_breaches"],
        "data_quality": packet["data_quality"],
        "provider_freshness": packet["provider_freshness"],
        "macro_regime": packet["macro_regime"],
        "market_universe": universe,
        "top_opportunities": [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "asset_class": item["asset_class"],
                "sector": item["sector"],
                "score": item["score"],
                "confidence": item["confidence"],
                "risk_score": item["risk_score"],
                "source_data_age_days": item.get("source_data_age_days"),
                "price_source": item.get("price_source"),
                "factor_breakdown": item.get("factor_breakdown"),
            }
            for item in packet["top_opportunities"][:16]
        ],
        "deterministic_decision": deterministic,
    }


def _store_decision(
    conn,
    *,
    packet: dict[str, Any],
    decision: dict[str, Any],
    model: str,
    status: str,
    tokens: dict[str, int] | None = None,
    response_id: str = "",
    fallback_reason: str = "",
    ai_route: str = "leadPM",
) -> dict[str, Any]:
    token_values = tokens or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    cursor = conn.execute(
        """
        INSERT INTO decision_runs
        (packet_hash, model, status, portfolio_verdict, execution_plan, staggering_guidance, entry_conditions,
         risks, data_used, missing_data, what_would_change_my_mind, fallback_reason,
         input_tokens, output_tokens, total_tokens, response_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            packet["packet_hash"],
            f"{model} [{ai_route}]",
            status,
            decision["portfolio_verdict"],
            json.dumps(decision["execution_plan"]),
            json.dumps(decision["staggering_guidance"]),
            json.dumps(decision["entry_conditions"]),
            json.dumps(decision["risks"]),
            json.dumps(decision["data_used"]),
            json.dumps(decision["missing_data"]),
            json.dumps(decision["what_would_change_my_mind"]),
            fallback_reason,
            token_values["input_tokens"],
            token_values["output_tokens"],
            token_values["total_tokens"],
            response_id,
        ),
    )
    run_id = int(cursor.lastrowid)
    for item in [*decision["holding_decisions"], *decision["opportunity_decisions"]]:
        conn.execute(
            """
            INSERT INTO decision_items
            (decision_run_id, symbol, item_type, decision, plain_action, reason, target_weight, current_weight,
             confidence_label, confidence_score, eligibility, risk_check, quant_evidence, ai_commentary, source_freshness,
             reason_code, detail_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                item["symbol"],
                item["item_type"],
                item["decision"],
                item["plain_action"],
                item["reason"],
                item["target_weight"],
                item["current_weight"],
                item["confidence_label"],
                item["confidence_score"],
                item["eligibility"],
                item["risk_check"],
                json.dumps(item["quant_evidence"]),
                item.get("ai_commentary", ""),
                item["source_freshness"],
                item.get("reason_code", ""),
                json.dumps(item.get("detail_payload") or {}),
            ),
        )
    return latest_decision(conn) or {}


def latest_decision(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM decision_runs ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    decision = dict(row)
    for key in ["execution_plan", "staggering_guidance", "entry_conditions", "risks", "data_used", "missing_data", "what_would_change_my_mind"]:
        decision[key] = json.loads(decision[key] or "[]")
    items = conn.execute("SELECT * FROM decision_items WHERE decision_run_id = ? ORDER BY item_type, id", (decision["id"],)).fetchall()
    decoded = []
    for item in items:
        current = dict(item)
        current["quant_evidence"] = json.loads(current["quant_evidence"] or "[]")
        current["detail_payload"] = json.loads(current.get("detail_payload") or "{}")
        decoded.append(current)
    if decoded and any(not item.get("detail_payload") or not item.get("reason_code") for item in decoded):
        try:
            packet = build_advisor_packet(conn)
            deterministic = _deterministic_decision(conn, packet)
            deterministic_items = {
                (item["item_type"], item["symbol"]): item
                for item in [*deterministic["holding_decisions"], *deterministic["opportunity_decisions"]]
            }
            for item in decoded:
                fallback = deterministic_items.get((item["item_type"], item["symbol"]))
                if not fallback:
                    continue
                item["reason_code"] = item.get("reason_code") or fallback.get("reason_code", "")
                item["detail_payload"] = item.get("detail_payload") or fallback.get("detail_payload", {})
        except Exception:
            # Missing receipt details should never block the dashboard; a fresh run will persist them.
            pass
    decision["holding_decisions"] = [item for item in decoded if item["item_type"] == "holding"]
    decision["opportunity_decisions"] = [item for item in decoded if item["item_type"] == "opportunity"]
    return decision


def run_advisor_decision(conn, force: bool = False, mode: str = "standard") -> dict[str, Any]:
    packet = build_advisor_packet(conn)
    store_decision_packet(conn, packet)
    if not force:
        existing = conn.execute("SELECT id FROM decision_runs WHERE packet_hash = ? AND status IN ('success', 'rules_based') ORDER BY id DESC LIMIT 1", (packet["packet_hash"],)).fetchone()
        if existing:
            return latest_decision(conn) or {}
    deterministic = _deterministic_decision(conn, packet)
    route = "deepCompetition" if mode == "deep" else "leadPM"
    purpose = "advisor_decision_deep" if mode == "deep" else "advisor_decision"
    review_packet_base = build_llm_review_packet(packet, deterministic)
    specialist_summaries, specialist_tokens, _specialist_warnings = run_specialist_agents(conn, packet, review_packet_base)
    review_packet = build_llm_review_packet(packet, deterministic, specialist_summaries=specialist_summaries)
    ai_settings = ai_runtime_settings(conn, route)
    model = ai_settings["model"]
    api_key = _effective_openai_api_key(conn)
    if not api_key:
        return _store_decision(
            conn,
            packet=packet,
            decision=deterministic,
            model=model,
            status="rules_based",
            fallback_reason="OpenAI key is not connected.",
            ai_route=route,
        )

    payload = {
        "model": model,
        "instructions": (
            "You are Signal PM's senior portfolio manager. Review the supplied compact LLM review packet and specialist summaries. "
            "Return strict JSON narrative only. You must NOT return holding_decisions, opportunity_decisions, target weights, trim shares, add plans, eligibility, or priority. "
            "The deterministic engine already owns all executable actions. Explain, summarize, challenge, and critique only. "
            "Use only supplied data. Do not invent prices, news, filings, price targets, IPO facts, or forecasts. "
            "If you disagree with the deterministic first action, set deterministicDecisionConfirmed to false and explain in conflictWithDeterministicEngine. "
            "Never claim guaranteed returns, execution, or that an order was placed. "
            "Include advisoryOnlyDisclosure stating this is advisory-only and no order was placed."
        ),
        "input": _stable_json(
            {
                "llm_review_packet": review_packet,
                "specialist_summaries": specialist_summaries,
                "decision_boundary": packet["decision_boundary"],
                "ai_route": route,
            }
        ),
        "max_output_tokens": ai_settings["max_output_tokens"],
        "reasoning": {"effort": ai_settings["reasoning_effort"]},
        "text": json_schema_text_format("llm_review_output", LLM_REVIEW_OUTPUT_SCHEMA, "Narrative LLM review only."),
    }
    started_at = _now()
    response_payload: dict[str, Any] | None = None
    try:
        response_payload = _call_openai_response(payload, api_key)
        parsed = _parse_llm_review(_extract_output_text(response_payload))
        decision = _apply_llm_review(parsed, deterministic, review_packet)
        tokens = _usage(response_payload)
        for key in specialist_tokens:
            tokens[key] = int(tokens.get(key) or 0) + int(specialist_tokens.get(key) or 0)
        insert_ai_run(
            conn,
            ai_run_record(
                provider="openai",
                model=model,
                purpose=purpose,
                status="success",
                started_at=started_at,
                tokens=tokens,
                response_id=str(response_payload.get("id") or ""),
            ),
        )
        return _store_decision(
            conn,
            packet=packet,
            decision=decision,
            model=model,
            status="success",
            tokens=tokens,
            response_id=str(response_payload.get("id") or ""),
            ai_route=route,
        )
    except Exception as exc:
        status = ai_failure_state(exc)
        fallback_reason = user_safe_ai_error(exc)
        tokens = _usage(response_payload) if response_payload else None
        if tokens:
            for key in specialist_tokens:
                tokens[key] = int(tokens.get(key) or 0) + int(specialist_tokens.get(key) or 0)
        insert_ai_run(
            conn,
            ai_run_record(
                provider="openai",
                model=model,
                purpose=purpose,
                status=status,
                started_at=started_at,
                tokens=tokens,
                error=str(exc),
            ),
        )
        return _store_decision(
            conn,
            packet=packet,
            decision=deterministic,
            model=model,
            status="fallback",
            tokens=tokens,
            fallback_reason=fallback_reason,
            ai_route=route,
        )


def run_live_advisor_eval(conn) -> dict[str, Any]:
    if not _effective_openai_api_key(conn):
        raise ValueError("Connect an OpenAI key before running live advisor E2E validation.")
    decision = run_advisor_decision(conn, force=True)
    if decision.get("status") != "success":
        rubric = {
            "grounded_in_holdings": bool(decision.get("holding_decisions")),
            "clear_actions": bool(decision.get("holding_decisions") or decision.get("opportunity_decisions")),
            "mentions_quant_or_risk": True,
            "explains_uncertainty": True,
            "records_tokens": False,
        }
        conn.execute(
            """
            INSERT INTO advisor_eval_runs (status, model, decision_run_id, rubric, questions, total_tokens, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "failed",
                decision.get("model", ai_runtime_settings(conn)["model"]),
                decision.get("id"),
                json.dumps(rubric),
                json.dumps([]),
                int(decision.get("total_tokens") or 0),
                decision.get("fallback_reason", "Live advisor decision did not succeed."),
            ),
        )
        return latest_eval(conn) or {}
    questions = [
        "What is the biggest risk in my current portfolio?",
        "Should I keep, trim, or add to my current holdings?",
        "What outside assets did you consider and why are the top opportunities worthwhile?",
        "How did IPOs or special situations affect this decision?",
        "What would change your mind?",
    ]
    answers = []
    total_tokens = int(decision.get("total_tokens") or 0)
    for question in questions:
        answer = ask_copilot(conn, question, screen_context="live_eval")
        answers.append({"question": question, "answer": answer})
        total_tokens += int(answer.get("total_tokens") or 0)
    combined = " ".join([decision.get("portfolio_verdict", ""), *[item["answer"].get("answer", "") for item in answers]]).lower()
    action_words = {"hold", "add", "trim", "rotate", "stagger", "avoid", "wait"}
    rubric = {
        "grounded_in_holdings": bool(decision.get("holding_decisions")),
        "clear_actions": any(word in combined for word in action_words),
        "mentions_quant_or_risk": any(word in combined for word in ["quant", "risk", "momentum", "freshness", "source", "drawdown"]),
        "explains_uncertainty": any(word in combined for word in ["missing", "stale", "sample", "limited", "uncertain", "rate"]),
        "records_tokens": total_tokens > 0,
    }
    status = "pass" if all(rubric.values()) else "review"
    conn.execute(
        """
        INSERT INTO advisor_eval_runs (status, model, decision_run_id, rubric, questions, total_tokens)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            status,
            decision.get("model", ai_runtime_settings(conn)["model"]),
            decision.get("id"),
            json.dumps(rubric),
            json.dumps(answers),
            total_tokens,
        ),
    )
    return latest_eval(conn) or {}


def latest_eval(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM advisor_eval_runs ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    item = dict(row)
    item["rubric"] = json.loads(item["rubric"] or "{}")
    item["questions"] = json.loads(item["questions"] or "[]")
    return item
