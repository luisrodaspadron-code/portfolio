from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.database import get_risk_rules
from app.services.action_service import portfolio_action_items
from app.services.ai_service import (
    _call_openai_response,
    _effective_openai_api_key,
    _extract_output_text,
    _usage,
    ai_run_record,
    ai_failure_state,
    ai_runtime_settings,
    insert_ai_run,
    json_schema_text_format,
    parse_model_json_object,
    user_safe_ai_error,
)
from app.services.backtest_service import recent_backtests
from app.services.connections_service import connections_status
from app.services.data_service import compute_universe_features, data_freshness
from app.services.portfolio_service import portfolio_summary
from app.services.quant_diagnostics import quant_diagnostics
from app.services.recommendation_service import latest_macro, recent_recommendations
from app.services.strategy_service import market_scope, strategy_reviews
from app.services.universe_service import universe_status


TOOL_INVENTORY = [
    {
        "name": "data_refresh",
        "description": "Refreshes live/recent provider data before analytics. Falls back to deterministic sample data when providers are missing.",
    },
    {
        "name": "feature_generation",
        "description": "Computes momentum, volatility, drawdown, trend persistence, quality, liquidity, confidence, and expected-return scores.",
    },
    {
        "name": "risk_gates",
        "description": "Applies hard concentration, liquidity, sector/theme, crypto proxy, and drawdown guardrails. AI cannot override failed gates.",
    },
    {
        "name": "target_sizing",
        "description": "Converts quant score and asset type into target weights bounded by risk rules.",
    },
    {
        "name": "strategy_sleeve_review",
        "description": "Compares broad strategy sleeves across factors, sectors, global equities, credit, real assets, commodities, and crypto proxies.",
    },
    {
        "name": "walk_forward_backtest",
        "description": "Runs deterministic walk-forward tests with transaction costs and no-lookahead feature windows.",
    },
    {
        "name": "portfolio_stress",
        "description": "Checks real holdings for cash, concentration, sector exposure, and risk breaches.",
    },
    {
        "name": "macro_regime",
        "description": "Scores macro conditions from rates, inflation, unemployment, and yield inputs.",
    },
    {
        "name": "memo_generation",
        "description": "Produces per-symbol research memos after quant evidence and risk status are known.",
    },
]


REVIEW_FIELDS = [
    "brief",
    "highest_priority_action",
    "approved_actions",
    "concerns",
    "rejected_or_blocked_ideas",
    "missing_data",
    "what_would_change_my_mind",
]

REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": REVIEW_FIELDS,
    "additionalProperties": False,
    "properties": {
        "brief": {"type": "string"},
        "highest_priority_action": {"type": "object", "additionalProperties": True},
        "approved_actions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "concerns": {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
        "rejected_or_blocked_ideas": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "missing_data": {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
        "what_would_change_my_mind": {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}]}},
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


VOLATILE_PACKET_HASH_KEYS = {
    "created_at",
    "packet_hash",
    "id",
    "started_at",
    "finished_at",
    "tested_at",
    "last_refresh",
    "last_successful_use",
    "response_id",
}


def _decision_stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _decision_stable(item)
            for key, item in value.items()
            if key not in VOLATILE_PACKET_HASH_KEYS
        }
    if isinstance(value, list):
        return [_decision_stable(item) for item in value]
    return value


def _packet_hash(packet: dict[str, Any]) -> str:
    stable_packet = _decision_stable(packet)
    return hashlib.sha256(_stable_json(stable_packet).encode("utf-8")).hexdigest()


def _data_quality(freshness: dict[str, Any], recommendations: list[dict[str, Any]]) -> dict[str, Any]:
    max_age = max([int(item.get("source_data_age_days", 0)) for item in recommendations] or [0])
    sample_only = freshness.get("provider_mode") != "live"
    if sample_only:
        confidence = "sample_only"
        message = "Live price providers are not connected; recommendations are downgraded because sample data is in use."
    elif max_age > 7:
        confidence = "stale"
        message = f"At least one surfaced idea uses price data {max_age} days old."
    else:
        confidence = "fresh"
        message = "Live/recent provider data is available for the current review."
    return {
        "confidence": confidence,
        "sample_only": sample_only,
        "max_source_age_days": max_age,
        "message": message,
    }


def build_advisor_packet(conn) -> dict[str, Any]:
    real = portfolio_summary(conn, mode="real")
    paper = portfolio_summary(conn, mode="paper")
    recommendations = recent_recommendations(conn, 12)
    diagnostics = quant_diagnostics(conn)
    macro = latest_macro(conn)
    features = compute_universe_features(conn)
    strategies = strategy_reviews(features)
    freshness = data_freshness(conn)
    backtests = recent_backtests(conn, 3)
    actions = portfolio_action_items(
        real_portfolio=real,
        recommendations=recommendations,
        diagnostics=diagnostics,
        macro=macro,
        strategies=strategies,
    )
    packet = {
        "created_at": _now(),
        "objective": "aggressive risk-managed long-term competition investing",
        "decision_boundary": "Decision-support only. No real trades are placed. Quant and risk rules decide eligibility; AI only reviews and explains.",
        "tool_inventory": TOOL_INVENTORY,
        "portfolio": {
            "real": real,
            "paper": {
                "cash": paper["cash"],
                "market_value": paper["market_value"],
                "total_value": paper["total_value"],
                "positions": paper["positions"][:12],
            },
        },
        "risk_rules": get_risk_rules(conn),
        "risk_breaches": real.get("stress", {}).get("warnings", []),
        "quant_diagnostics": diagnostics,
        "provider_freshness": freshness,
        "universe_status": universe_status(conn),
        "connections": connections_status(conn),
        "data_quality": _data_quality(freshness, recommendations),
        "macro_regime": macro,
        "top_opportunities": features[:12],
        "recommendations": recommendations,
        "strategy_sleeves": strategies[:12],
        "recent_backtests": backtests,
        "action_items": actions[:5],
        "instructions_to_ai": [
            "Use only this packet. Do not invent prices, news, filings, forecasts, or unavailable sources.",
            "Reference available quant tools, source freshness, risk gates, portfolio exposure, macro regime, and backtests when relevant.",
            "Never approve a recommendation whose quant status is fail or whose action is AVOID.",
            "Downgrade confidence when data_quality is sample_only or stale.",
            "Explain in plain English for a user who is not a quant specialist.",
        ],
    }
    packet["packet_hash"] = _packet_hash(packet)
    return packet


def store_decision_packet(conn, packet: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO decision_packets (packet_hash, packet, created_at)
        VALUES (?, ?, ?)
        """,
        (packet["packet_hash"], json.dumps(packet), packet["created_at"]),
    )


def decision_packet_status(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "packet_hash": packet["packet_hash"],
        "created_at": packet["created_at"],
        "tool_count": len(packet["tool_inventory"]),
        "data_confidence": packet["data_quality"]["confidence"],
        "sample_only": packet["data_quality"]["sample_only"],
        "max_source_age_days": packet["data_quality"]["max_source_age_days"],
        "recommendations": len(packet["recommendations"]),
        "risk_breaches": len(packet["risk_breaches"]),
    }


def _latest_ai_run(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM ai_runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _latest_decision_meta(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT id, packet_hash, status, model, total_tokens, created_at FROM decision_runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _latest_eval_meta(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT id, status, model, total_tokens, created_at FROM advisor_eval_runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def ai_activity(conn) -> str:
    if not _effective_openai_api_key(conn):
        return "not_connected"
    latest = _latest_ai_run(conn)
    if not latest:
        return "ready"
    if latest["status"] == "rate_limited":
        return "rate_limited"
    if latest["status"] in {"failed", "format_error"}:
        return "error"
    if latest["status"] == "success":
        return "reviewed" if latest["purpose"] in {"advisor_review", "copilot"} else "ready"
    return "idle"


def _provider_map(packet: dict[str, Any]) -> dict[str, Any]:
    return {provider["provider"]: provider for provider in packet["connections"]["providers"]}


def _sec_edgar_trace(conn, packet: dict[str, Any]) -> dict[str, Any]:
    providers = _provider_map(packet)
    sec = providers.get("sec_edgar", {})
    freshness = packet["provider_freshness"]
    latest_refresh = freshness.get("latest_provider_refresh") or {}
    rows = conn.execute(
        """
        SELECT symbol, COUNT(*) AS facts
        FROM fundamental_facts
        WHERE source = 'sec_edgar'
        GROUP BY symbol
        ORDER BY symbol
        """
    ).fetchall()
    covered_symbols = [row["symbol"] for row in rows]
    facts_count = sum(int(row["facts"]) for row in rows)
    return {
        "configured": bool(sec.get("configured")),
        "state": sec.get("state", "standby"),
        "purpose": "Company facts from SEC filings: revenue growth, gross margin, and debt-to-equity for covered stocks.",
        "covered_symbols": covered_symbols[:12],
        "facts_count": facts_count,
        "latest_refresh": sec.get("last_refresh") or latest_refresh.get("finished_at", ""),
        "last_test": sec.get("last_test"),
        "message": sec.get("note", "Add a real SEC contact identity to enable filing-derived fundamentals."),
    }


def advisor_trace_from_packet(conn, packet: dict[str, Any]) -> dict[str, Any]:
    real = packet["portfolio"]["real"]
    positions = real.get("positions", [])
    risks = real.get("stress", {}).get("warnings", [])
    top_holding = max(positions, key=lambda item: item.get("weight", 0), default=None)
    rules = packet["risk_rules"]
    freshness = packet["provider_freshness"]
    scope = market_scope(conn)
    providers = _provider_map(packet)
    tool_status = {
        "data_refresh": "checked" if freshness.get("price_bars", 0) else "waiting",
        "feature_generation": "checked" if packet["quant_diagnostics"]["coverage"].get("scored_instruments", 0) else "waiting",
        "risk_gates": "review" if risks else "checked",
        "target_sizing": "checked" if packet["recommendations"] else "waiting",
        "strategy_sleeve_review": "checked" if packet["strategy_sleeves"] else "waiting",
        "walk_forward_backtest": "checked" if packet["recent_backtests"] else "waiting",
        "portfolio_stress": "checked" if positions else "needs_holdings",
        "macro_regime": "checked" if packet["macro_regime"].get("latest") else "waiting",
        "memo_generation": "checked" if packet["recommendations"] else "waiting",
    }
    latest_run = _latest_ai_run(conn)
    ai_settings = ai_runtime_settings(conn, "leadPM")
    router = ai_settings["model_router"]
    universe = universe_status(conn)
    return {
        "packet_hash": packet["packet_hash"],
        "created_at": packet["created_at"],
        "ai_activity": ai_activity(conn),
        "ai": {
            "model": ai_settings["model"],
            "model_route": {
                "advisor_decision": router["leadPM"]["model"],
                "copilot": router["leadPM"]["model"],
                "connection_test": router["fast"]["model"],
                "reasoning_effort": router["leadPM"]["reasoningEffort"],
                "review_token_cap": router["leadPM"]["maxOutputTokens"],
                "decision_token_cap": router["leadPM"]["maxOutputTokens"],
            },
            "last_run": latest_run,
            "review_status": (latest_advisor_review(conn) or {}).get("status", "none"),
            "latest_decision": _latest_decision_meta(conn),
            "latest_eval": _latest_eval_meta(conn),
            "decision_boundary": packet["decision_boundary"],
        },
        "holdings_analyzed": {
            "count": len(positions),
            "total_value": real.get("total_value", 0),
            "top_holding": top_holding,
            "symbols": [item["symbol"] for item in positions],
        },
        "top_risks": [
            {
                "title": warning,
                "severity": "high" if "exceeds" in warning.lower() or "above" in warning.lower() else "medium",
                "what_to_do": "Review whether this exposure is intentional before adding similar risk.",
            }
            for warning in risks[:8]
        ],
        "risk_bounds": {
            "max_single_stock_weight": rules["max_single_stock_weight"],
            "max_etf_weight": rules["max_etf_weight"],
            "max_sector_weight": rules["max_sector_weight"],
            "max_crypto_weight": rules["max_crypto_weight"],
            "max_positions": rules["max_positions"],
            "real_money_trading_enabled": rules["real_money_trading_enabled"],
        },
        "quant_tools": [
            {
                "name": tool["name"],
                "label": tool["name"].replace("_", " ").title(),
                "description": tool["description"],
                "status": tool_status.get(tool["name"], "waiting"),
            }
            for tool in TOOL_INVENTORY
        ],
        "market_universe": {
            **scope,
            "coverage": universe,
            "allowed_categories": [
                "All active/tradable US stocks available through Alpaca metadata when connected",
                "ETFs",
                "Multi-asset ETFs",
                "IPO and special-situation watchlist names with strict eligibility checks",
                "Treasury, credit, commodity, real-asset, international, and crypto-proxy sleeves",
            ],
            "blocked_or_limited_categories": [
                "Direct crypto and direct commodities are capped unless explicitly enabled by data/risk settings.",
                "Any idea failing risk gates is blocked from approval.",
                "No real-money trades are placed by the app.",
            ],
            "top_opportunities": [
                {
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "asset_class": item["asset_class"],
                    "sector": item["sector"],
                    "score": item["score"],
                    "confidence": item["confidence"],
                    "risk_score": item["risk_score"],
                }
                for item in packet["top_opportunities"][:8]
            ],
        },
        "provider_freshness": {
            "mode": freshness.get("provider_mode"),
            "preferred_source": freshness.get("preferred_price_source"),
            "price_bars": freshness.get("price_bars"),
            "live_price_symbols": freshness.get("live_price_symbols"),
            "latest_provider_refresh": freshness.get("latest_provider_refresh"),
            "providers": [
                {
                    "provider": provider,
                    "label": data.get("label", provider),
                    "state": data.get("state", "standby"),
                    "configured": data.get("configured", False),
                    "used_in_review": provider in {freshness.get("preferred_price_source"), "openai", "fred", "sec_edgar"},
                    "records": data.get("records", 0),
                    "last_refresh": data.get("last_refresh"),
                    "last_test": data.get("last_test"),
                }
                for provider, data in providers.items()
            ],
        },
        "sec_edgar": _sec_edgar_trace(conn, packet),
    }


def build_advisor_trace(conn) -> dict[str, Any]:
    packet = build_advisor_packet(conn)
    store_decision_packet(conn, packet)
    return advisor_trace_from_packet(conn, packet)


def _latest_review_for_packet(conn, packet_hash: str, statuses: set[str]) -> dict[str, Any] | None:
    placeholders = ",".join("?" for _ in statuses)
    row = conn.execute(
        f"""
        SELECT * FROM advisor_reviews
        WHERE packet_hash = ? AND status IN ({placeholders})
        ORDER BY id DESC LIMIT 1
        """,
        (packet_hash, *sorted(statuses)),
    ).fetchone()
    return _decode_review(row) if row else None


def ensure_current_advisor_review(conn, trigger: str = "auto") -> dict[str, Any]:
    packet = build_advisor_packet(conn)
    store_decision_packet(conn, packet)
    has_key = bool(_effective_openai_api_key(conn))
    statuses = {"success"} if has_key else {"rules_based", "fallback"}
    existing = _latest_review_for_packet(conn, packet["packet_hash"], statuses)
    if existing:
        return {
            "ran": False,
            "reason": f"Current packet already has a {existing['status']} review.",
            "trigger": trigger,
            "packet_hash": packet["packet_hash"],
            "advisor_review": existing,
        }
    review = run_advisor_review(conn)
    return {
        "ran": True,
        "reason": "Created a concise advisor review for the current packet.",
        "trigger": trigger,
        "packet_hash": packet["packet_hash"],
        "advisor_review": review,
    }


def _action_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": item.get("symbol"),
        "action": "REVIEW",
        "title": item.get("title", "Review advisor output"),
        "next_step": item.get("next_step", "Review the dashboard before taking any brokerage action."),
        "reason": item.get("why", ""),
    }


def _fallback_review(packet: dict[str, Any], reason: str) -> dict[str, Any]:
    pass_recommendations = [item for item in packet["recommendations"] if item.get("status") == "pass" and item.get("action") != "AVOID"]
    approved = [
        {
            "symbol": item["symbol"],
            "action": item["action"],
            "title": f"Review {item['symbol']} {item['action']}",
            "next_step": f"Read the {item['symbol']} memo and compare it with current holdings.",
            "reason": item["reason"],
            "quant_status": item["status"],
        }
        for item in pass_recommendations[:3]
    ]
    blocked = [
        {
            "symbol": item["symbol"],
            "action": item["action"],
            "reason": "Blocked by quant/risk status before AI review.",
            "quant_status": item["status"],
        }
        for item in packet["recommendations"]
        if item.get("status") == "fail" or item.get("action") == "AVOID"
    ][:4]
    first_action = _action_from_item(packet["action_items"][0]) if packet["action_items"] else (approved[0] if approved else {})
    return {
        "brief": (
            "Quant advisor cycle completed. Live AI review is not available for this run, so the app is showing a deterministic "
            "risk-gated brief from the quant packet."
        ),
        "highest_priority_action": first_action,
        "approved_actions": approved,
        "concerns": [
            packet["data_quality"]["message"],
            *packet["risk_breaches"][:2],
        ],
        "rejected_or_blocked_ideas": blocked,
        "missing_data": [
            "Import real holdings to activate portfolio-specific exposure checks."
        ]
        if not (packet["portfolio"]["real"]["positions"] or packet["portfolio"]["real"]["cash"] > 0)
        else [],
        "what_would_change_my_mind": [
            "Fresh live provider data changes the top-ranked opportunities.",
            "A risk breach clears or a quant gate changes from fail/watch to pass.",
            "Backtest drawdown or volatility materially worsens after the next walk-forward run.",
        ],
        "fallback_reason": reason,
    }


def _parse_review_payload(output_text: str) -> dict[str, Any]:
    parsed = parse_model_json_object(output_text)
    if not isinstance(parsed, dict):
        raise ValueError("Advisor review response was not a JSON object.")
    for field in REVIEW_FIELDS:
        if field not in parsed:
            raise ValueError(f"Advisor review missing field: {field}")
    return parsed


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_action(action: Any) -> dict[str, Any]:
    if isinstance(action, str):
        return {"title": action, "reason": action}
    if not isinstance(action, dict):
        return {"title": "Review action", "reason": str(action)}
    return dict(action)


def _enforce_review(packet: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    recs = {item["symbol"]: item for item in packet["recommendations"]}
    approved: list[dict[str, Any]] = []
    blocked = [_normalize_action(item) for item in _listify(review.get("rejected_or_blocked_ideas"))]

    for raw in _listify(review.get("approved_actions")):
        item = _normalize_action(raw)
        symbol = str(item.get("symbol") or "").upper()
        quant = recs.get(symbol)
        if not symbol or not quant:
            item["reason"] = f"{item.get('reason', 'Unknown idea')} Backend blocked it because no matching quant recommendation exists."
            item["quant_status"] = "missing"
            blocked.append(item)
            continue
        item["symbol"] = symbol
        item["action"] = str(item.get("action") or quant["action"]).upper()
        item["quant_status"] = quant["status"]
        item["risk_flags"] = quant.get("risk_flags", [])
        if quant["status"] == "fail" or quant["action"] == "AVOID":
            item["reason"] = f"{item.get('reason', '')} Backend blocked this because quant risk gate is {quant['status']}."
            blocked.append(item)
            continue
        approved.append(item)

    highest = _normalize_action(review.get("highest_priority_action"))
    if highest.get("symbol"):
        symbol = str(highest["symbol"]).upper()
        quant = recs.get(symbol)
        if quant and (quant["status"] == "fail" or quant["action"] == "AVOID"):
            highest = _action_from_item(packet["action_items"][0]) if packet["action_items"] else {}

    return {
        "brief": str(review.get("brief") or ""),
        "highest_priority_action": highest,
        "approved_actions": approved,
        "concerns": [str(item) if not isinstance(item, dict) else item for item in _listify(review.get("concerns"))],
        "rejected_or_blocked_ideas": blocked,
        "missing_data": [str(item) if not isinstance(item, dict) else item for item in _listify(review.get("missing_data"))],
        "what_would_change_my_mind": [
            str(item) if not isinstance(item, dict) else item for item in _listify(review.get("what_would_change_my_mind"))
        ],
        "fallback_reason": str(review.get("fallback_reason") or ""),
    }


def _store_review(
    conn,
    *,
    packet: dict[str, Any],
    review: dict[str, Any],
    model: str,
    status: str,
    tokens: dict[str, int] | None = None,
    response_id: str = "",
    fallback_reason: str = "",
) -> dict[str, Any]:
    token_values = tokens or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    cursor = conn.execute(
        """
        INSERT INTO advisor_reviews
        (packet_hash, model, status, brief, highest_priority_action, approved_actions, concerns,
         rejected_or_blocked_ideas, missing_data, what_would_change_my_mind, fallback_reason,
         input_tokens, output_tokens, total_tokens, response_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            packet["packet_hash"],
            model,
            status,
            review["brief"],
            json.dumps(review["highest_priority_action"]),
            json.dumps(review["approved_actions"]),
            json.dumps(review["concerns"]),
            json.dumps(review["rejected_or_blocked_ideas"]),
            json.dumps(review["missing_data"]),
            json.dumps(review["what_would_change_my_mind"]),
            fallback_reason or review.get("fallback_reason", ""),
            token_values["input_tokens"],
            token_values["output_tokens"],
            token_values["total_tokens"],
            response_id,
        ),
    )
    review_id = int(cursor.lastrowid)
    for item in review["approved_actions"]:
        if not item.get("symbol"):
            continue
        conn.execute(
            """
            INSERT INTO advisor_review_items (review_id, symbol, action, status, quant_status, reason, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                item["symbol"],
                item.get("action", "REVIEW"),
                "approved",
                item.get("quant_status", ""),
                item.get("reason", ""),
                "ai" if status == "success" else "rules",
            ),
        )
    return latest_advisor_review(conn) or {}


def run_advisor_review(conn) -> dict[str, Any]:
    packet = build_advisor_packet(conn)
    store_decision_packet(conn, packet)
    ai_settings = ai_runtime_settings(conn, "leadPM")
    model = ai_settings["model"]
    api_key = _effective_openai_api_key(conn)
    if not api_key:
        review = _fallback_review(packet, "OpenAI key is not connected.")
        return _store_review(conn, packet=packet, review=review, model=model, status="rules_based", fallback_reason=review["fallback_reason"])

    instructions = (
        "You are a senior competition portfolio manager reviewing an auditable quant packet. "
        "The quant engine is source of truth for calculations, risk gates, sizing, ranking, data freshness, and backtests. "
        "You may critique, prioritize, and explain, but you cannot approve ideas blocked by risk rules. "
        "Use plain English. Return strict JSON with exactly these fields: brief, highest_priority_action, approved_actions, "
        "concerns, rejected_or_blocked_ideas, missing_data, what_would_change_my_mind. "
        "Approved/rejected action objects should include symbol, action, reason, next_step when possible. "
        "Be concise: spend tokens only on decision-changing evidence, risks, and next steps."
    )
    request_payload = {
        "model": model,
        "instructions": instructions,
        "input": _stable_json(packet),
        "max_output_tokens": ai_settings["review_max_output_tokens"],
        "reasoning": {"effort": ai_settings["reasoning_effort"]},
        "text": json_schema_text_format("advisor_review", REVIEW_JSON_SCHEMA, "Concise portfolio advisor review."),
    }
    started_at = _now()
    try:
        response_payload = _call_openai_response(request_payload, api_key)
        parsed = _parse_review_payload(_extract_output_text(response_payload))
        review = _enforce_review(packet, parsed)
        tokens = _usage(response_payload)
        insert_ai_run(
            conn,
            ai_run_record(
                provider="openai",
                model=model,
                purpose="advisor_review",
                status="success",
                started_at=started_at,
                tokens=tokens,
                response_id=str(response_payload.get("id") or ""),
            ),
        )
        return _store_review(
            conn,
            packet=packet,
            review=review,
            model=model,
            status="success",
            tokens=tokens,
            response_id=str(response_payload.get("id") or ""),
        )
    except Exception as exc:
        status = ai_failure_state(exc)
        fallback_reason = user_safe_ai_error(exc)
        insert_ai_run(
            conn,
            ai_run_record(
                provider="openai",
                model=model,
                purpose="advisor_review",
                status=status,
                started_at=started_at,
                error=str(exc),
            ),
        )
        review = _fallback_review(packet, fallback_reason)
        return _store_review(conn, packet=packet, review=review, model=model, status="fallback", fallback_reason=fallback_reason)


def _decode_review(row: dict[str, Any]) -> dict[str, Any]:
    review = dict(row)
    for key in [
        "highest_priority_action",
        "approved_actions",
        "concerns",
        "rejected_or_blocked_ideas",
        "missing_data",
        "what_would_change_my_mind",
    ]:
        review[key] = json.loads(review[key] or ("{}" if key == "highest_priority_action" else "[]"))
    return review


def latest_advisor_review(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM advisor_reviews ORDER BY id DESC LIMIT 1").fetchone()
    return _decode_review(row) if row else None


def advisor_reviews(conn, limit: int = 10) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM advisor_reviews ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [_decode_review(row) for row in rows]
