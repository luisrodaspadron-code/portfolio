from __future__ import annotations

import json
from json import JSONDecodeError
from datetime import datetime, timezone
from typing import Any

import httpx

from app.database import get_app_settings, update_app_settings
from app.services.research import make_rules_based_memo
from app.services.secrets_service import get_effective_secret, save_provider_secrets

DEFAULT_AI_MODEL_CONFIG = {
    "mode": "balanced",
    "fast": {
        "role": "UI status, lightweight summaries, command palette, short follow-ups",
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "reasoningEffort": "low",
        "maxOutputTokens": 800,
    },
    "specialist": {
        "role": "Fundamental, technical, and macro synthesis from already-computed data",
        "provider": "openai",
        "model": "gpt-5.4-mini",
        "reasoningEffort": "medium",
        "maxOutputTokens": 1500,
    },
    "leadPM": {
        "role": "Final portfolio memo, ambiguity adjudication, and user-facing decision explanation",
        "provider": "openai",
        "model": "gpt-5.5",
        "reasoningEffort": "medium",
        "maxOutputTokens": 2500,
    },
    "deepCompetition": {
        "role": "Manual high-stakes competition review, not every refresh",
        "provider": "openai",
        "model": "gpt-5.5",
        "reasoningEffort": "high",
        "maxOutputTokens": 5000,
    },
}

OPTIMIZED_AI_PROFILE = {
    "model": DEFAULT_AI_MODEL_CONFIG["specialist"]["model"],
    "reasoning_effort": DEFAULT_AI_MODEL_CONFIG["specialist"]["reasoningEffort"],
    "memo_style": "competition_pm",
    "custom_instructions": "",
    "max_output_tokens": DEFAULT_AI_MODEL_CONFIG["specialist"]["maxOutputTokens"],
    "review_max_output_tokens": DEFAULT_AI_MODEL_CONFIG["leadPM"]["maxOutputTokens"],
}

_STYLE_PROMPTS = {
    "competition_pm": (
        "Write like an aggressive long-term competition portfolio manager who is trying to compound capital while respecting hard risk controls. "
        "Be skeptical before enthusiasm: look for stale data, crowded trades, high volatility, drawdown risk, liquidity weakness, and portfolio duplication. "
        "You must reference the provided quant tools or evidence, including scores, risk gates, source freshness, macro regime, and portfolio-impact fields when relevant. "
        "Never recommend an action that contradicts risk-rule status or risk flags, and never invent prices, news, filings, forecasts, or unavailable data."
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_output_text(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text
    chunks: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def _extract_json_object_text(output_text: str) -> str:
    text = output_text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    if start < 0:
        raise JSONDecodeError("No JSON object found in model output", text, 0)
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise JSONDecodeError("Unterminated JSON object in model output", text, start)


def parse_model_json_object(output_text: str) -> dict[str, Any]:
    parsed = json.loads(_extract_json_object_text(output_text))
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object.")
    return parsed


def json_schema_text_format(name: str, schema: dict[str, Any], description: str = "") -> dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": name,
            "description": description or f"Structured JSON for {name}.",
            "schema": schema,
            "strict": False,
        }
    }


def _usage(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def ai_run_record(
    *,
    provider: str,
    model: str,
    purpose: str,
    status: str,
    started_at: str,
    tokens: dict[str, int] | None = None,
    response_id: str = "",
    error: str = "",
) -> dict[str, Any]:
    token_values = tokens or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    return {
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "status": status,
        "started_at": started_at,
        "finished_at": _now(),
        "input_tokens": token_values["input_tokens"],
        "output_tokens": token_values["output_tokens"],
        "total_tokens": token_values["total_tokens"],
        "response_id": response_id,
        "error": error,
    }


def _memo_context(candidate: dict[str, Any], recommendation: dict[str, Any], macro: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": candidate["symbol"],
        "name": candidate.get("name"),
        "action": recommendation["action"],
        "risk_gate_status": recommendation["status"],
        "target_weight": recommendation["target_weight"],
        "confidence": recommendation["confidence"],
        "expected_return_score": recommendation["expected_return"],
        "risk_score": recommendation["risk_score"],
        "risk_flags": recommendation.get("risk_flags", []),
        "reason": recommendation["reason"],
        "source_data_age_days": recommendation.get("source_data_age_days", 0),
        "price_source": candidate.get("price_source", "unknown"),
        "quant_features": {
            "momentum_63d": candidate.get("momentum_63d"),
            "momentum_126d": candidate.get("momentum_126d"),
            "volatility": candidate.get("volatility"),
            "max_drawdown": candidate.get("max_drawdown"),
            "trend_persistence": candidate.get("trend_persistence"),
            "quality_score": candidate.get("quality_score"),
            "liquidity_score": candidate.get("liquidity_score"),
        },
        "macro_regime": macro,
    }


def _call_openai_response(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def ai_failure_state(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return "rate_limited"
    if isinstance(exc, (JSONDecodeError, ValueError)) and any(
        phrase in str(exc).lower()
        for phrase in ["json", "advisor decision", "advisor review", "model response", "missing field", "unterminated"]
    ):
        return "format_error"
    return "failed"


def user_safe_ai_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return "OpenAI is rate-limiting this key right now. Quant-only fallback is active."
        if status in {401, 403}:
            return "OpenAI rejected this key. Add a valid key and test again."
        return f"OpenAI request failed with HTTP {status}. Quant-only fallback is active."
    if isinstance(exc, (JSONDecodeError, ValueError)) and any(
        phrase in str(exc).lower()
        for phrase in ["json", "advisor decision", "advisor review", "model response", "missing field", "unterminated"]
    ):
        return "AI response format failed; quant-only fallback is active."
    return "OpenAI could not be reached. Quant-only fallback is active."


def _effective_openai_api_key(conn) -> str:
    return get_effective_secret(conn, "openai", "openai_api_key")


def _insert_ai_run(conn, run: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO ai_runs
        (provider, model, purpose, status, started_at, finished_at,
         input_tokens, output_tokens, total_tokens, response_id, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run["provider"],
            run["model"],
            run["purpose"],
            run["status"],
            run["started_at"],
            run["finished_at"],
            run["input_tokens"],
            run["output_tokens"],
            run["total_tokens"],
            run["response_id"],
            run["error"],
        ),
    )


def insert_ai_run(conn, run: dict[str, Any]) -> None:
    _insert_ai_run(conn, run)


def _normalize_route(route: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    reasoning = str(route.get("reasoningEffort") or route.get("reasoning_effort") or fallback["reasoningEffort"])
    if reasoning not in {"none", "low", "medium", "high", "xhigh"}:
        reasoning = fallback["reasoningEffort"]
    tokens = int(route.get("maxOutputTokens") or route.get("max_output_tokens") or fallback["maxOutputTokens"])
    return {
        "role": str(route.get("role") or fallback["role"]),
        "provider": str(route.get("provider") or fallback["provider"]),
        "model": str(route.get("model") or fallback["model"]).strip()[:80],
        "reasoningEffort": reasoning,
        "maxOutputTokens": max(200, min(tokens, 8000)),
    }


def ai_model_config(conn) -> dict[str, Any]:
    saved = get_app_settings(conn, "ai_model_config").get("ai_model_config", {})
    saved = saved if isinstance(saved, dict) else {}
    return {
        "mode": str(saved.get("mode") or DEFAULT_AI_MODEL_CONFIG["mode"]),
        "fast": _normalize_route(saved.get("fast") or {}, DEFAULT_AI_MODEL_CONFIG["fast"]),
        "specialist": _normalize_route(saved.get("specialist") or {}, DEFAULT_AI_MODEL_CONFIG["specialist"]),
        "leadPM": _normalize_route(saved.get("leadPM") or {}, DEFAULT_AI_MODEL_CONFIG["leadPM"]),
        "deepCompetition": _normalize_route(saved.get("deepCompetition") or {}, DEFAULT_AI_MODEL_CONFIG["deepCompetition"]),
    }


def update_ai_model_config(conn, values: dict[str, Any]) -> dict[str, Any]:
    current = ai_model_config(conn)
    merged = {**current, **{key: value for key, value in values.items() if key == "mode"}}
    for route in ["fast", "specialist", "leadPM", "deepCompetition"]:
        if route in values and isinstance(values[route], dict):
            merged[route] = _normalize_route({**current[route], **values[route]}, DEFAULT_AI_MODEL_CONFIG[route])
        else:
            merged[route] = current[route]
    update_app_settings(conn, {"ai_model_config": merged})
    return ai_status(conn)


def ai_runtime_settings(conn, route: str = "specialist") -> dict[str, Any]:
    router = ai_model_config(conn)
    selected = router.get(route) or router["specialist"]
    return {
        **OPTIMIZED_AI_PROFILE,
        "model": selected["model"],
        "reasoning_effort": selected["reasoningEffort"],
        "max_output_tokens": selected["maxOutputTokens"],
        "review_max_output_tokens": router["leadPM"]["maxOutputTokens"],
        "model_route": route,
        "model_router": router,
    }


def apply_ai_settings(conn, values: dict[str, Any]) -> dict[str, Any]:
    # Backward-compatible endpoint: older clients can still save a single model,
    # but it is mapped to the specialist route instead of bypassing the router.
    update_ai_model_config(
        conn,
        {
            "specialist": {
                "model": values.get("model"),
                "reasoningEffort": values.get("reasoning_effort"),
                "maxOutputTokens": values.get("max_output_tokens"),
            }
        },
    )
    return ai_status(conn)


def save_openai_key(conn, api_key: str) -> dict[str, Any]:
    save_provider_secrets(conn, "openai", {"openai_api_key": api_key})
    return ai_status(conn)


def test_openai_connection(conn) -> dict[str, Any]:
    ai_settings = ai_runtime_settings(conn, "fast")
    api_key = _effective_openai_api_key(conn)
    if not api_key:
        raise ValueError("Connect an OpenAI key before testing the advisor.")

    started_at = _now()
    payload = {
        "model": ai_settings["model"],
        "instructions": (
            "You are checking connectivity for a local portfolio advisor. "
            "Return exactly this JSON shape with short strings: {\"status\":\"ok\",\"message\":\"connected\"}."
        ),
        "input": json.dumps({"test": "openai_connection", "profile": ai_settings["memo_style"]}, separators=(",", ":")),
        "max_output_tokens": 200,
        "reasoning": {"effort": "low"},
    }
    try:
        response_payload = _call_openai_response(payload, api_key)
        output_text = _extract_output_text(response_payload)
        if output_text:
            parse_model_json_object(output_text)
        run = ai_run_record(
            provider="openai",
            model=ai_settings["model"],
            purpose="connection_test",
            status="success",
            started_at=started_at,
            tokens=_usage(response_payload),
            response_id=str(response_payload.get("id") or ""),
        )
        _insert_ai_run(conn, run)
        return ai_status(conn)
    except Exception as exc:
        status = ai_failure_state(exc)
        run = ai_run_record(
            provider="openai",
            model=ai_settings["model"],
            purpose="connection_test",
            status=status,
            started_at=started_at,
            error=str(exc),
        )
        _insert_ai_run(conn, run)
        if status == "rate_limited":
            return ai_status(conn)
        raise ValueError(user_safe_ai_error(exc)) from exc


def generate_research_memo(conn, candidate: dict[str, Any], recommendation: dict[str, Any], macro: dict[str, Any]) -> dict[str, Any]:
    ai_settings = ai_runtime_settings(conn, "specialist")
    api_key = _effective_openai_api_key(conn)
    if not api_key:
        return make_rules_based_memo(candidate, recommendation, macro)

    started_at = _now()
    model = ai_settings["model"]
    provider = "openai"
    style_instruction = _STYLE_PROMPTS[ai_settings["memo_style"]]
    custom_instruction = ai_settings["custom_instructions"]
    instructions = (
        "You are an investment research co-pilot inside a local-only decision-support app. "
        "Use only the JSON evidence provided. Do not invent prices, filings, estimates, or sources. "
        "Do not claim certainty or guarantee returns. Return strict JSON with these string fields: "
        "title, thesis, evidence, risks, counterargument, change_mind. Keep each field concise and decision-useful. "
        "Preserve tokens by prioritizing only evidence that changes the decision. "
        f"{style_instruction}"
    )
    if custom_instruction:
        instructions = f"{instructions} User customization: {custom_instruction}"
    request_payload = {
        "model": model,
        "instructions": instructions,
        "input": json.dumps(_memo_context(candidate, recommendation, macro), separators=(",", ":")),
        "max_output_tokens": ai_settings["max_output_tokens"],
        "reasoning": {"effort": ai_settings["reasoning_effort"]},
    }

    try:
        response_payload = _call_openai_response(request_payload, api_key)
        output_text = _extract_output_text(response_payload)
        parsed = parse_model_json_object(output_text)
        tokens = _usage(response_payload)
        run = ai_run_record(
            provider=provider,
            model=model,
            purpose="research_memo",
            status="success",
            started_at=started_at,
            tokens=tokens,
            response_id=str(response_payload.get("id") or ""),
        )
        return {
            "symbol": candidate["symbol"],
            "title": str(parsed["title"]),
            "thesis": str(parsed["thesis"]),
            "evidence": str(parsed["evidence"]),
            "risks": str(parsed["risks"]),
            "counterargument": str(parsed["counterargument"]),
            "change_mind": str(parsed["change_mind"]),
            "generation_method": "openai",
            "ai_provider": provider,
            "ai_model": model,
            "ai_run": run,
            **tokens,
        }
    except Exception as exc:
        status = ai_failure_state(exc)
        run = ai_run_record(
            provider=provider,
            model=model,
            purpose="research_memo",
            status=status,
            started_at=started_at,
            error=str(exc),
        )
        fallback = make_rules_based_memo(candidate, recommendation, macro)
        fallback["title"] = f"{fallback['title']} (rules-based fallback)"
        fallback["ai_run"] = run
        return fallback


def ai_status(conn) -> dict[str, Any]:
    ai_settings = ai_runtime_settings(conn, "specialist")
    model_router = ai_settings["model_router"]
    configured = bool(_effective_openai_api_key(conn))
    latest = conn.execute("SELECT * FROM ai_runs ORDER BY id DESC LIMIT 1").fetchone()
    totals = conn.execute(
        """
        SELECT
            COUNT(*) AS calls,
            SUM(input_tokens) AS input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(total_tokens) AS total_tokens
        FROM ai_runs
        WHERE status = 'success'
        """
    ).fetchone()
    if not configured:
        state = "disabled"
        message = "Connect AI to enable real model reviews. Memos are rules-based until a key is connected."
    elif latest and latest["status"] == "success":
        state = "live"
        message = f"OpenAI Responses API is generating memos with {ai_settings['model']}."
    elif latest and (latest["status"] == "rate_limited" or "429" in str(latest["error"]) or "Too Many Requests" in str(latest["error"])):
        state = "rate_limited"
        message = "OpenAI is rate-limiting this key right now. Quant-only fallback is active."
    elif latest and latest["status"] == "format_error":
        state = "error"
        message = "AI response format failed on the latest model call. Quant-only fallback is active."
    elif latest and latest["status"] == "failed":
        state = "error"
        message = "OpenAI is configured but the last model call failed; the app used rules-based fallback."
    else:
        state = "configured"
        message = "OpenAI is configured and will be used on the next recommendation run."

    return {
        "provider": "openai",
        "configured": configured,
        "state": state,
        "model": ai_settings["model"] if configured else "",
        "max_output_tokens": ai_settings["max_output_tokens"],
        "settings": ai_settings,
        "model_router": model_router,
        "profile_summary": (
            f"{model_router['leadPM']['model']} · lead PM {model_router['leadPM']['reasoningEffort']} · "
            f"fast route {model_router['fast']['model']} · quant-gated"
        ),
        "message": message,
        "user_message": message,
        "technical_error": str(latest["error"]) if latest and latest["error"] else "",
        "last_run": dict(latest) if latest else None,
        "usage_totals": {
            "calls": totals["calls"] or 0,
            "input_tokens": totals["input_tokens"] or 0,
            "output_tokens": totals["output_tokens"] or 0,
            "total_tokens": totals["total_tokens"] or 0,
        },
    }
