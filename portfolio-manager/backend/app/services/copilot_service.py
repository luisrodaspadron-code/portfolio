from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from app.services.advisor_intelligence import (
    build_advisor_packet,
    advisor_trace_from_packet,
    store_decision_packet,
    _stable_json,
)
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


COPILOT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["answer", "data_used", "limitations", "suggested_followups"],
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "data_used": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "suggested_followups": {"type": "array", "items": {"type": "string"}},
    },
}


def _rules_based_answer(question: str, trace: dict[str, Any]) -> dict[str, Any]:
    risks = trace["top_risks"]
    holdings = trace["holdings_analyzed"]
    universe = trace["market_universe"]
    q = question.lower()
    if "risk" in q or "hurt" in q or "breach" in q:
        if risks:
            answer = f"The biggest visible risk is: {risks[0]['title']} The practical next step is to review whether that exposure is intentional before adding similar risk."
        else:
            answer = "No hard risk breach is visible in the current packet. Keep watching concentration, data freshness, and macro drag."
    elif "asset" in q or "consider" in q or "market" in q or "universe" in q:
        classes = ", ".join(universe["asset_classes"].keys()) or "enabled local instruments"
        answer = f"The advisor is considering {universe['enabled_instruments']} enabled instruments across {classes}, plus {universe['strategy_count']} strategy sleeves."
    elif "sec" in q or "edgar" in q:
        sec = trace["sec_edgar"]
        answer = sec["message"] if sec["configured"] else "SEC EDGAR needs a real contact identity before the app can refresh filing-derived fundamentals."
    else:
        top = holdings.get("top_holding")
        top_text = f" Top holding: {top['symbol']} at {top['weight']:.1%}." if top else ""
        answer = f"Signal PM analyzed {holdings['count']} real holdings against quant tools, risk gates, market data freshness, macro regime, and strategy sleeves.{top_text}"
    return {
        "answer": answer,
        "data_used": ["latest advisor packet", "portfolio holdings", "risk rules", "quant tool trace"],
        "limitations": ["No live AI call was used for this answer.", trace["ai"]["decision_boundary"]],
        "suggested_followups": [
            "What is the biggest risk in my current portfolio?",
            "What assets did you consider?",
            "What would change your mind?",
        ],
    }


def _as_text_list(value: Any, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value][:limit]
    if isinstance(value, list):
        return [str(item) for item in value][:limit]
    return [str(value)][:limit]


def _latest_decision_context(conn) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM decision_runs ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    decision = dict(row)
    for key in ["execution_plan", "staggering_guidance", "entry_conditions", "risks", "data_used", "missing_data", "what_would_change_my_mind"]:
        decision[key] = json.loads(decision[key] or "[]")
    items = conn.execute(
        """
        SELECT symbol, item_type, decision, plain_action, reason, target_weight, current_weight,
               confidence_label, eligibility, risk_check, source_freshness
        FROM decision_items
        WHERE decision_run_id = ?
        ORDER BY item_type, id
        """,
        (decision["id"],),
    ).fetchall()
    decision["items"] = [dict(item) for item in items]
    return decision


def _copilot_reasoning(question: str) -> str:
    q = question.lower()
    decision_terms = ["should i", "buy", "sell", "trim", "add", "rotate", "allocation", "risk", "biggest", "change", "opportunity"]
    return "medium" if any(term in q for term in decision_terms) else "low"


def ask_copilot(conn, question: str, conversation_id: str | None = None, screen_context: str | None = None) -> dict[str, Any]:
    packet = build_advisor_packet(conn)
    store_decision_packet(conn, packet)
    trace = advisor_trace_from_packet(conn, packet)
    route = "leadPM" if _copilot_reasoning(question) == "medium" else "fast"
    ai_settings = ai_runtime_settings(conn, route)
    model = ai_settings["model"]
    run_id = conversation_id or f"signal-{uuid4().hex[:12]}"
    api_key = _effective_openai_api_key(conn)
    if not api_key:
        fallback = _rules_based_answer(question, trace)
        return {
            **fallback,
            "conversation_id": run_id,
            "packet_hash": packet["packet_hash"],
            "model": model,
            "status": "rules_based",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    prompt_context = {
        "question": question,
        "screen_context": screen_context or "unknown",
        "advisor_packet": packet,
        "advisor_trace": trace,
        "latest_advisor_decision": _latest_decision_context(conn),
    }
    instructions = (
        "You are Signal PM's local portfolio copilot. Answer follow-up questions using only the supplied advisor packet and trace. "
        "Do not invent prices, news, filings, forecasts, model outputs, or unavailable sources. "
        "Do not recommend any action blocked by quant risk gates. "
        "Explain plainly for a non-quant user. Return strict JSON with fields: answer, data_used, limitations, suggested_followups. "
        "Keep the answer concise and mention when data is missing, stale, sample-only, or rate-limited."
    )
    payload = {
        "model": model,
        "instructions": instructions,
        "input": _stable_json(prompt_context),
        "max_output_tokens": min(int(ai_settings["max_output_tokens"]), 1200),
        "reasoning": {"effort": ai_settings["reasoning_effort"]},
        "text": json_schema_text_format("ask_signal_answer", COPILOT_JSON_SCHEMA, "Grounded Ask Signal answer."),
    }
    started_at = packet["created_at"]
    try:
        response_payload = _call_openai_response(payload, api_key)
        parsed = parse_model_json_object(_extract_output_text(response_payload))
        tokens = _usage(response_payload)
        insert_ai_run(
            conn,
            ai_run_record(
                provider="openai",
                model=model,
                purpose="copilot",
                status="success",
                started_at=started_at,
                tokens=tokens,
                response_id=str(response_payload.get("id") or ""),
            ),
        )
        return {
            "answer": str(parsed.get("answer") or ""),
            "data_used": _as_text_list(parsed.get("data_used"), 8),
            "limitations": _as_text_list(parsed.get("limitations"), 6),
            "suggested_followups": _as_text_list(parsed.get("suggested_followups"), 5),
            "conversation_id": run_id,
            "packet_hash": packet["packet_hash"],
            "model": model,
            "status": "success",
            **tokens,
        }
    except Exception as exc:
        status = ai_failure_state(exc)
        insert_ai_run(
            conn,
            ai_run_record(
                provider="openai",
                model=model,
                purpose="copilot",
                status=status,
                started_at=started_at,
                error=str(exc),
            ),
        )
        fallback = _rules_based_answer(question, trace)
        return {
            **fallback,
            "limitations": [user_safe_ai_error(exc), *fallback["limitations"]],
            "conversation_id": run_id,
            "packet_hash": packet["packet_hash"],
            "model": model,
            "status": status,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
