from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import get_risk_rules
from app.services.ai_service import ai_model_config
from app.services.data_quality_service import build_source_matrix
from app.services.data_service import data_freshness
from app.services.decision_service import latest_decision, _deterministic_decision
from app.services.policy_engine import POLICY_VERSION as CANONICAL_POLICY_VERSION
from app.services.policy_engine import risk_policy_to_dict, selected_risk_policy
from app.services.portfolio_service import portfolio_summary
from app.services.universe_service import universe_status


PACKET_VERSION = "signal-prime.v2"
POLICY_VERSION = CANONICAL_POLICY_VERSION
DETERMINISTIC_ENGINE_VERSION = "deterministic-risk-sizing.v2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _canonical_action(value: str) -> str:
    mapping = {
        "Trim": "TRIM",
        "Add": "ADD",
        "Stagger Entry": "STAGGER_ENTRY",
        "Hold": "HOLD",
        "Avoid": "BLOCKED_BY_RISK",
        "Wait For Data": "WAIT_FOR_DATA",
        "Rotate": "REVIEW_MANUALLY",
    }
    return mapping.get(value, "REVIEW_MANUALLY")


def _severity_from_level(level: str) -> str:
    if level in {"elevated", "danger"}:
        return "danger"
    if level in {"watch", "attention"}:
        return "elevated"
    if level in {"unknown"}:
        return "attention"
    return "good"


def _data_quality(item: dict[str, Any]) -> dict[str, Any]:
    detail = item.get("detail_payload") or {}
    quality = detail.get("dataQuality") or {}
    return {
        "provider": quality.get("provider", "missing"),
        "sourceTimestamp": quality.get("sourceTimestamp", ""),
        "receivedAt": quality.get("receivedAt", _now()),
        "ageSeconds": int(quality.get("ageSeconds") or 999_999_999),
        "freshness": quality.get("freshness", "missing"),
        "coverage": quality.get("coverage", "missing"),
        "confidence": float(quality.get("confidence") or 0),
        "warnings": quality.get("warnings") or [],
    }


def _risk_breach_from_cap(symbol: str, detail: dict[str, Any], action: str) -> dict[str, Any] | None:
    cap = (detail or {}).get("capDistance") or {}
    if not cap.get("breached"):
        return None
    observed = float(cap.get("current_weight") or 0)
    limit = float(cap.get("limit") or 0)
    return {
        "id": f"{symbol.lower()}-single-name-cap",
        "severity": "danger" if action == "TRIM" else "elevated",
        "rule": "max_single_stock_weight" if limit <= 0.12 else "max_position_weight",
        "observed": observed,
        "limit": limit,
        "message": f"{symbol} is {_pct(observed - limit)} over its {_pct(limit)} cap.",
        "blocksAdds": True,
    }


def _sector_breaches(real: dict[str, Any], rules: dict[str, Any]) -> list[dict[str, Any]]:
    cap = float(rules.get("max_sector_weight") or 0.30)
    breaches: list[dict[str, Any]] = []
    for sector, weight in (real.get("stress") or {}).get("sector_weights", {}).items():
        if sector in {"Unknown", "Unclassified ETF"}:
            continue
        observed = float(weight or 0)
        if observed <= cap:
            continue
        breaches.append(
            {
                "id": f"{sector.lower().replace(' ', '-')}-sector-cap",
                "severity": "danger",
                "rule": "max_sector_weight",
                "observed": observed,
                "limit": cap,
                "message": f"{sector} exposure is {_pct(observed)} versus a {_pct(cap)} cap.",
                "blocksAdds": True,
            }
        )
    return breaches


def _stale_data_breaches(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    breaches: list[dict[str, Any]] = []
    for item in items:
        quality = _data_quality(item)
        if quality["freshness"] not in {"missing", "stale"}:
            continue
        symbol = str(item.get("symbol") or "UNKNOWN")
        breaches.append(
            {
                "id": f"{symbol.lower()}-data-{quality['freshness']}",
                "severity": "attention",
                "rule": "data_freshness",
                "observed": quality["ageSeconds"],
                "limit": 86_400,
                "message": f"{symbol} uses {quality['freshness']} data; sizing confidence is reduced.",
                "blocksAdds": quality["freshness"] == "missing",
            }
        )
    return breaches


def _position_lookup(real: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {position["symbol"]: position for position in real.get("positions", [])}


def _position_decision(item: dict[str, Any], position: dict[str, Any] | None) -> dict[str, Any]:
    detail = item.get("detail_payload") or {}
    target_weight = float(item.get("target_weight") or 0)
    current_weight = float(item.get("current_weight") or 0)
    current_value = float((position or {}).get("market_value") or 0)
    live_price = float((position or {}).get("latest_price") or 0)
    return {
        "symbol": item["symbol"],
        "name": (position or {}).get("name") or item["symbol"],
        "assetClass": str((position or {}).get("asset_class") or "unknown").lower(),
        "sector": (position or {}).get("sector") or "Unknown",
        "action": _canonical_action(str(item.get("decision") or "")),
        "reasonCode": item.get("reason_code") or detail.get("reasonCode") or "",
        "explanation": item.get("reason") or "",
        "currentValue": current_value,
        "currentWeight": current_weight,
        "targetWeight": target_weight,
        "targetValue": target_weight * float(current_value / current_weight) if current_weight else 0,
        "livePrice": live_price or None,
        "priceTimestamp": ((_data_quality(item)).get("sourceTimestamp") or None),
        "dataQuality": _data_quality(item),
        "riskBreaches": [
            breach
            for breach in [_risk_breach_from_cap(item["symbol"], detail, _canonical_action(str(item.get("decision") or "")))]
            if breach
        ],
        "trimPlan": detail.get("trimPlan"),
        "addPlan": detail.get("addPlan"),
        "confidence": float(item.get("confidence_score") or 0),
        "confidenceDrivers": list(item.get("quant_evidence") or [])[:4],
        "blockers": detail.get("blockers") or ([] if item.get("eligibility") == "eligible" else [item.get("risk_check") or "Needs review."]),
    }


def _candidate_decision(item: dict[str, Any]) -> dict[str, Any]:
    detail = item.get("detail_payload") or {}
    return {
        "symbol": item["symbol"],
        "name": item["symbol"],
        "assetClass": "unknown",
        "sector": "Unknown",
        "action": _canonical_action(str(item.get("decision") or "")),
        "reasonCode": item.get("reason_code") or detail.get("reasonCode") or "",
        "explanation": item.get("reason") or "",
        "currentWeight": 0,
        "targetWeight": float(item.get("target_weight") or 0),
        "dataQuality": _data_quality(item),
        "riskBreaches": [],
        "addPlan": detail.get("addPlan"),
        "confidence": float(item.get("confidence_score") or 0),
        "confidenceDrivers": list(item.get("quant_evidence") or [])[:4],
        "blockers": detail.get("blockers") or ([] if item.get("eligibility") != "fail" else [item.get("risk_check") or "Failed risk gates."]),
    }


def _priority(
    positions: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    sector_breaches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    first = (
        next((item for item in positions if item["action"] == "TRIM"), None)
        or next((item for item in positions if item["action"] == "WAIT_FOR_DATA"), None)
        or next((item for item in candidates if item["action"] in {"ADD", "STAGGER_ENTRY"}), None)
        or next((item for item in positions if item["action"] == "HOLD"), None)
    )
    if not first:
        headline = "Import holdings, then run Signal Prime."
    elif first["action"] == "TRIM":
        plan = first.get("trimPlan") or {}
        headline = f"Trim {first['symbol']} toward {_pct(first['targetWeight'])}; estimated advisory trim {_money(float(plan.get('estimatedSellValue') or 0))}."
    elif first["action"] == "WAIT_FOR_DATA":
        headline = f"Wait for usable data on {first['symbol']} before sizing that position."
    elif first["action"] in {"ADD", "STAGGER_ENTRY"}:
        headline = f"{first['action'].replace('_', ' ').title()} {first['symbol']} only if current hard breaches are clear."
    else:
        headline = "Hold current positions and continue scheduled reviews."
    return {
        "headline": headline,
        "firstAction": first,
        "doNext": [
            headline,
            "Resolve hard concentration breaches before new single-stock adds.",
            "Use staged entries for long-term adds when data is fresh and gates pass.",
        ],
        "blockedActions": [
            *[
                f"New adds blocked until {item['symbol']} is under cap."
                for item in positions
                if item["action"] == "TRIM"
            ][:6],
            *[
                breach.get("message", "")
                for breach in sector_breaches or []
                if breach.get("blocksAdds")
            ][:3],
        ],
    }


def _data_sources(freshness: dict[str, Any]) -> list[dict[str, Any]]:
    latest = freshness.get("latest_provider_refresh") or {}
    return [
        {
            "name": freshness.get("preferred_price_source") or "sample",
            "domain": "prices",
            "state": freshness.get("provider_mode") or "sample",
            "records": freshness.get("live_price_symbols") or freshness.get("sample_price_symbols") or 0,
            "lastRefresh": latest.get("finished_at") or freshness.get("latest_price_date") or "",
            "freshness": "live" if freshness.get("provider_mode") == "live" else "partial",
            "message": latest.get("message") or "Using current local data cache.",
        }
    ]


def _decision_receipt(packet: dict[str, Any], decision: dict[str, Any] | None, next_review_at: str | None = None) -> dict[str, Any]:
    first = packet["recommendedPriority"]["firstAction"]
    if not first:
        return {
            "title": "Decision Receipt",
            "summary": "No portfolio-specific decision exists yet.",
            "advisoryOnly": True,
            "noOrderPlaced": True,
        }
    trim = first.get("trimPlan") or {}
    math = None
    if trim:
        math = {
            "portfolioValue": packet["portfolioValue"],
            "currentValue": trim.get("currentValue"),
            "targetValue": trim.get("targetValue"),
            "estimatedSellValue": trim.get("estimatedSellValue"),
            "sharesToSellExact": trim.get("sharesToSellExact"),
            "sharesToSellWhole": trim.get("sharesToSellWhole"),
            "sharesToSellWholeCompliant": trim.get("sharesToSellWholeCompliant"),
            "sharesToSellWholeReduceOnly": trim.get("sharesToSellWholeReduceOnly"),
            "sharesToSellFractionalCompliant": trim.get("sharesToSellFractionalCompliant"),
            "estimatedPostWeight": trim.get("estimatedPostWeight"),
            "estimatedPostWeightCompliant": trim.get("estimatedPostWeightCompliant"),
            "estimatedPostWeightReduceOnly": trim.get("estimatedPostWeightReduceOnly"),
            "wouldRemainAboveThresholdIfRoundedDown": trim.get("wouldRemainAboveThresholdIfRoundedDown"),
            "complianceMode": trim.get("complianceMode"),
            "policyThreshold": trim.get("policyThreshold"),
            "priceUsed": trim.get("priceUsed"),
            "priceTimestamp": trim.get("priceTimestamp"),
        }
    blocked_actions = packet["recommendedPriority"].get("blockedActions") or []
    return {
        "title": "Decision Receipt",
        "runId": packet["runId"],
        "timestamp": packet["generatedAt"],
        "advisoryOnly": True,
        "noOrderPlaced": True,
        "selectedPolicy": packet.get("selectedPolicy", {}).get("name", ""),
        "selectedPolicyPreset": packet.get("selectedPolicy", {}).get("preset", ""),
        "policyVersion": packet["policyVersion"],
        "portfolioValueUsed": packet["portfolioValue"],
        "firstAction": packet["recommendedPriority"]["headline"],
        "sizingMath": math,
        "hardGatesTripped": [
            breach["message"]
            for breach in [
                *packet["portfolioRisk"]["singleNameBreaches"],
                *packet["portfolioRisk"]["sectorBreaches"],
            ]
        ],
        "softWarnings": list(packet["audit"].get("warnings", [])),
        "riskIncreasingActionsBlocked": [
            action for action in blocked_actions if "blocked" in action.lower()
        ],
        "riskReducingActionsAllowed": [
            "Risk-reducing diversification may remain eligible if it improves concentration and passes data/risk gates.",
        ]
        if blocked_actions
        else [],
        "alternativesConsidered": [item["symbol"] for item in packet["candidates"][:5]],
        "dataLimitations": packet["audit"]["warnings"],
        "sourceReceipts": packet["dataSources"],
        "model": (decision or {}).get("model", ""),
        "modelRoute": packet["audit"].get("modelRoute", ""),
        "reasoningEffort": packet["audit"].get("llmReasoningEffort", ""),
        "promptVersion": packet.get("promptVersion", ""),
        "deterministicEngineVersion": packet["audit"]["deterministicEngineVersion"],
        "packetHash": packet.get("packetHash", ""),
        "tokenUsage": {
            "input_tokens": int((decision or {}).get("input_tokens") or 0),
            "output_tokens": int((decision or {}).get("output_tokens") or 0),
            "total_tokens": int((decision or {}).get("total_tokens") or 0),
        },
        "confidenceDrivers": first.get("confidenceDrivers", [])[:4],
        "nextScheduledReview": next_review_at or (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
    }


def build_canonical_advisor_packet(conn, *, next_review_at: str | None = None) -> dict[str, Any]:
    real = portfolio_summary(conn, mode="real")
    decision = latest_decision(conn)
    freshness = data_freshness(conn)
    rules = get_risk_rules(conn)
    model_router = ai_model_config(conn)
    policy = selected_risk_policy(conn)

    # Deterministic-first: if a stored decision exists, use it for compatibility with
    # the existing decision_items DB rows. Otherwise compute deterministic decisions
    # from a freshly-built advisor packet so the canonical packet still exists.
    holding_items: list[dict[str, Any]] = []
    opportunity_items: list[dict[str, Any]] = []
    if decision:
        holding_items = list((decision or {}).get("holding_decisions", []) or [])
        opportunity_items = list((decision or {}).get("opportunity_decisions", []) or [])
    else:
        try:
            from app.services.advisor_intelligence import build_advisor_packet

            seed_packet = build_advisor_packet(conn)
            deterministic = _deterministic_decision(conn, seed_packet)
            holding_items = list(deterministic.get("holding_decisions", []) or [])
            opportunity_items = list(deterministic.get("opportunity_decisions", []) or [])
        except Exception:
            holding_items = []
            opportunity_items = []

    by_symbol = _position_lookup(real)
    positions = [_position_decision(item, by_symbol.get(item["symbol"])) for item in holding_items]
    candidates = [_candidate_decision(item) for item in opportunity_items]
    single_breaches = [breach for item in positions for breach in item["riskBreaches"]]
    sector_breaches = _sector_breaches(real, rules)
    stale_breaches = _stale_data_breaches(holding_items)
    warnings = []
    if freshness.get("provider_mode") not in {"live", "recent"}:
        warnings.append("Price data is not fully live; confidence is downgraded until a provider refresh succeeds.")
    warnings.extend(breach["message"] for breach in stale_breaches[:4])
    source_matrix = build_source_matrix(conn, policy=policy)
    packet_seed = {
        "packetVersion": PACKET_VERSION,
        "runId": str((decision or {}).get("id") or "pending"),
        "promptVersion": "signal-prime-review.v1",
        "policyVersion": POLICY_VERSION,
        "selectedPolicy": risk_policy_to_dict(policy),
        "generatedAt": _now(),
        "portfolioValue": float(real.get("total_value") or 0),
        "cashValue": float(real.get("cash") or 0),
        "dataSources": _data_sources(freshness),
        "sourceMatrix": source_matrix,
        "positions": positions,
        "candidates": candidates,
        "portfolioRisk": {
            "severity": _severity_from_level((real.get("stress") or {}).get("level", "unknown")),
            "issueCount": len(single_breaches) + len(sector_breaches) + (1 if stale_breaches else 0),
            "concentrationScore": float((real.get("stress") or {}).get("concentration") or 0),
            "sectorBreaches": sector_breaches,
            "singleNameBreaches": single_breaches,
            "liquidityWarnings": [],
            "staleDataWarnings": stale_breaches,
        },
        "audit": {
            "deterministicEngineVersion": DETERMINISTIC_ENGINE_VERSION,
            "llmModel": (decision or {}).get("model", ""),
            "llmReasoningEffort": model_router["leadPM"]["reasoningEffort"] if decision else "",
            "modelRoute": "leadPM" if decision else "",
            "toolCalls": [
                {"tool": "portfolio_valuation", "status": "success", "records": len(real.get("positions", []))},
                {"tool": "risk_gates", "status": "success", "records": len(single_breaches) + len(sector_breaches)},
                {"tool": "trim_add_sizing", "status": "success", "records": len(positions) + len(candidates)},
                {"tool": "universe_screen", "status": "success", "records": universe_status(conn).get("included_assets", 0)},
                {"tool": "source_matrix", "status": "success", "records": len(source_matrix.get("matrix", {}))},
            ],
            "warnings": warnings,
            "errors": [] if decision else ["No advisor decision run has completed yet."],
        },
    }
    packet_seed["recommendedPriority"] = _priority(positions, candidates, sector_breaches)
    packet_seed["packetHash"] = _stable_hash(packet_seed)
    packet_seed["decisionReceipt"] = _decision_receipt(packet_seed, decision, next_review_at)
    return packet_seed
