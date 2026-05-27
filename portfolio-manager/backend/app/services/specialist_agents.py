from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

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

SPECIALIST_SCHEMAS: dict[str, dict[str, Any]] = {
    "macro": {
        "type": "object",
        "required": ["regime", "summary", "risks", "macroFitNotes"],
        "additionalProperties": False,
        "properties": {
            "regime": {"type": "string"},
            "summary": {"type": "string"},
            "risks": {"type": "array", "items": {"type": "string"}},
            "macroFitNotes": {"type": "string"},
        },
    },
    "fundamental": {
        "type": "object",
        "required": ["summary", "marginWarnings", "qualityFlags"],
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "marginWarnings": {"type": "array", "items": {"type": "string"}},
            "qualityFlags": {"type": "array", "items": {"type": "string"}},
        },
    },
    "technical": {
        "type": "object",
        "required": ["summary", "momentumNotes", "volFlags"],
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "momentumNotes": {"type": "array", "items": {"type": "string"}},
            "volFlags": {"type": "array", "items": {"type": "string"}},
        },
    },
}

SPECIALIST_INSTRUCTIONS: dict[str, str] = {
    "macro": (
        "You are a macro specialist. Using only the supplied FRED/macro regime data, return strict JSON. "
        "Summarize the prevailing regime in one sentence. Do not invent data or forecasts."
    ),
    "fundamental": (
        "You are a fundamental specialist. Using only supplied SEC/company facts, return strict JSON. "
        "Flag margin or balance-sheet warnings when supported by the data. Do not invent filings."
    ),
    "technical": (
        "You are a technical specialist. Using only supplied price/momentum/volatility fields, return strict JSON. "
        "Note momentum and volatility flags. Do not invent prices."
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fallback(name: str, message: str) -> dict[str, Any]:
    if name == "macro":
        return {"regime": "unknown", "summary": message, "risks": [], "macroFitNotes": message}
    if name == "fundamental":
        return {"summary": message, "marginWarnings": [], "qualityFlags": []}
    return {"summary": message, "momentumNotes": [], "volFlags": []}


def _specialist_input(name: str, packet: dict[str, Any], review_packet: dict[str, Any]) -> dict[str, Any]:
    if name == "macro":
        return {
            "macro_regime": packet.get("macro_regime"),
            "provider_freshness": packet.get("provider_freshness"),
            "data_quality": review_packet.get("dataQualitySummary"),
        }
    if name == "fundamental":
        return {
            "top_exposures": review_packet.get("topExposures"),
            "eligible_candidates": review_packet.get("eligibleCandidates"),
            "data_quality": review_packet.get("dataQualitySummary"),
        }
    return {
        "top_exposures": review_packet.get("topExposures"),
        "eligible_candidates": review_packet.get("eligibleCandidates"),
        "hard_breaches": review_packet.get("hardBreaches"),
    }


def _run_one_specialist(
    conn,
    name: str,
    packet: dict[str, Any],
    review_packet: dict[str, Any],
    api_key: str,
) -> tuple[str, dict[str, Any], dict[str, int]]:
    ai_settings = ai_runtime_settings(conn, "specialist")
    model = ai_settings["model"]
    started_at = _now()
    payload = {
        "model": model,
        "instructions": SPECIALIST_INSTRUCTIONS[name],
        "input": json.dumps(_specialist_input(name, packet, review_packet), default=str),
        "max_output_tokens": min(ai_settings["max_output_tokens"], 900),
        "reasoning": {"effort": ai_settings["reasoning_effort"]},
        "text": json_schema_text_format(f"specialist_{name}", SPECIALIST_SCHEMAS[name], f"{name} specialist summary."),
    }
    try:
        response = _call_openai_response(payload, api_key)
        parsed = parse_model_json_object(_extract_output_text(response))
        if not isinstance(parsed, dict):
            raise ValueError(f"{name} specialist response was not a JSON object.")
        tokens = _usage(response)
        insert_ai_run(
            conn,
            ai_run_record(
                provider="openai",
                model=model,
                purpose=f"specialist_{name}",
                status="success",
                started_at=started_at,
                tokens=tokens,
                response_id=str(response.get("id") or ""),
            ),
        )
        return name, parsed, tokens
    except Exception as exc:
        status = ai_failure_state(exc)
        insert_ai_run(
            conn,
            ai_run_record(
                provider="openai",
                model=model,
                purpose=f"specialist_{name}",
                status=status,
                started_at=started_at,
                error=str(exc),
            ),
        )
        return name, _fallback(name, user_safe_ai_error(exc)), {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def run_specialist_agents(
    conn,
    packet: dict[str, Any],
    review_packet: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int], list[str]]:
    api_key = _effective_openai_api_key(conn)
    if not api_key:
        message = "OpenAI key not connected; specialist summaries skipped."
        return (
            {name: _fallback(name, message) for name in SPECIALIST_SCHEMAS},
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            [message],
        )

    summaries: dict[str, Any] = {}
    total_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    warnings: list[str] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_run_one_specialist, conn, name, packet, review_packet, api_key): name
            for name in SPECIALIST_SCHEMAS
        }
        for future in as_completed(futures):
            name, parsed, tokens = future.result()
            summaries[name] = parsed
            for key in total_tokens:
                total_tokens[key] += int(tokens.get(key) or 0)
            if "skipped" in str(parsed.get("summary", "")).lower():
                warnings.append(f"{name} specialist degraded.")
    return summaries, total_tokens, warnings
