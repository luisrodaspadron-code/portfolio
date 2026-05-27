from __future__ import annotations

import asyncio
import threading
from typing import Any

from app.providers.alpaca import AlpacaProvider
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.fred import FredProvider
from app.providers.registry import provider_statuses
from app.providers.sec_edgar import SecEdgarProvider
from app.services.secrets_service import (
    PROVIDER_DEFINITIONS,
    delete_provider_secrets,
    effective_settings,
    save_provider_secrets,
    secret_field_status,
)


def connections_status(conn) -> dict[str, Any]:
    provider_rows = {item["name"]: item for item in provider_statuses(conn)}
    last_tests = _latest_connection_tests(conn)
    latest_uses = _latest_provider_uses(conn)
    providers = []
    for provider, definition in PROVIDER_DEFINITIONS.items():
        fields = secret_field_status(conn, provider)
        market_status = provider_rows.get(provider, {})
        configured = all(field["configured"] for field in fields)
        latest_use = latest_uses.get(provider)
        if provider == "openai":
            latest_test = last_tests.get(provider)
            if not configured:
                state = "missing"
            elif latest_test and latest_test["status"] == "rate_limited":
                state = "rate_limited"
            elif latest_test and latest_test["status"] == "failed":
                state = "error"
            elif latest_test and latest_test["status"] == "success":
                state = "live"
            else:
                state = "configured"
            capabilities = ["portfolio_ai_review", "research_memos", "token_audit"]
            note = definition["description"]
        else:
            state = market_status.get("state", "configured" if configured else "missing")
            capabilities = market_status.get("capabilities", [])
            note = market_status.get("note", definition["description"])
        providers.append(
            {
                "provider": provider,
                "label": definition["label"],
                "description": definition["description"],
                "configured": configured,
                "state": state,
                "fields": fields,
                "capabilities": capabilities,
                "note": note,
                "last_refresh": market_status.get("last_refresh"),
                "last_test": last_tests.get(provider),
                "records": market_status.get("records", 0),
                "error": market_status.get("error", ""),
                "connection_state": _connection_state(configured, last_tests.get(provider), state),
                "latest_use_state": _latest_use_state(provider, configured, latest_use, market_status),
                "user_message": _provider_user_message(provider, configured, last_tests.get(provider), latest_use, market_status),
                "last_successful_use": _last_successful_use(conn, provider),
                "next_fix": _provider_next_fix(provider, configured, last_tests.get(provider), latest_use, market_status),
            }
        )
    configured_count = sum(1 for provider in providers if provider["configured"])
    return {
        "summary": {
            "configured": configured_count,
            "total": len(providers),
            "missing": len(providers) - configured_count,
        },
        "providers": providers,
    }


def save_connection(conn, provider: str, values: dict[str, Any]) -> dict[str, Any]:
    save_provider_secrets(conn, provider, values)
    return connections_status(conn)


def delete_connection(conn, provider: str) -> dict[str, Any]:
    delete_provider_secrets(conn, provider)
    return connections_status(conn)


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - propagated to caller
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _record_connection_test(
    conn,
    provider: str,
    status: str,
    *,
    records: int = 0,
    message: str = "",
    error: str = "",
) -> dict[str, Any]:
    tested_at = datetime_now()
    conn.execute(
        """
        INSERT INTO connection_tests (provider, status, tested_at, records, message, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (provider, status, tested_at, records, message, error),
    )
    return {
        "provider": provider,
        "status": status,
        "tested_at": tested_at,
        "records": records,
        "message": message,
        "error": error,
    }


def _latest_connection_tests(conn) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT tests.provider, tests.status, tests.tested_at, tests.records, tests.message, tests.error
        FROM connection_tests tests
        INNER JOIN (
            SELECT provider, MAX(id) AS id
            FROM connection_tests
            GROUP BY provider
        ) latest ON latest.id = tests.id
        """
    ).fetchall()
    return {row["provider"]: row for row in rows}


def _latest_provider_uses(conn) -> dict[str, dict[str, Any]]:
    ai_rows = conn.execute(
        """
        SELECT provider, purpose, status, finished_at, total_tokens, error
        FROM ai_runs
        WHERE id IN (SELECT MAX(id) FROM ai_runs GROUP BY provider)
        """
    ).fetchall()
    provider_rows = conn.execute(
        """
        SELECT provider, status, finished_at, records, message, error
        FROM provider_refreshes
        WHERE id IN (SELECT MAX(id) FROM provider_refreshes GROUP BY provider)
        """
    ).fetchall()
    uses = {row["provider"]: dict(row) for row in provider_rows}
    for row in ai_rows:
        uses[row["provider"]] = dict(row)
    return uses


def _last_successful_use(conn, provider: str) -> str | None:
    if provider == "openai":
        row = conn.execute("SELECT finished_at FROM ai_runs WHERE provider = ? AND status = 'success' ORDER BY id DESC LIMIT 1", (provider,)).fetchone()
    else:
        row = conn.execute("SELECT finished_at FROM provider_refreshes WHERE provider = ? AND status IN ('success', 'partial') ORDER BY id DESC LIMIT 1", (provider,)).fetchone()
    return row["finished_at"] if row else None


def _connection_state(configured: bool, latest_test: dict[str, Any] | None, fallback_state: str) -> str:
    if not configured:
        return "missing"
    if latest_test:
        if latest_test["status"] == "success":
            return "tested"
        return latest_test["status"]
    return "saved" if fallback_state in {"configured", "live", "checked", "partial"} else fallback_state


def _latest_use_state(provider: str, configured: bool, latest_use: dict[str, Any] | None, market_status: dict[str, Any]) -> str:
    if not configured:
        return "not_configured"
    if not latest_use:
        return "not_used_yet"
    status = latest_use.get("status")
    if status == "success":
        return "used"
    if status == "partial":
        return "partial"
    if status == "rate_limited":
        return "rate_limited"
    if provider == "sec_edgar" and status == "failed" and "404" in str(latest_use.get("error", "")):
        return "partial"
    if status == "format_error":
        return "format_error"
    if status == "failed":
        return "failed"
    return str(status or market_status.get("state") or "unknown")


def _provider_user_message(
    provider: str,
    configured: bool,
    latest_test: dict[str, Any] | None,
    latest_use: dict[str, Any] | None,
    market_status: dict[str, Any],
) -> str:
    if not configured:
        if provider == "sec_edgar":
            return "Add a real SEC contact identity to enable company fundamentals for covered stocks."
        if provider == "openai":
            return "Add an OpenAI key to enable AI portfolio reviews and Ask Signal."
        return "Add credentials to let Signal use this source."
    connection = _connection_state(configured, latest_test, market_status.get("state", "configured"))
    use_state = _latest_use_state(provider, configured, latest_use, market_status)
    if provider == "openai":
        if connection in {"tested", "saved"} and use_state == "failed":
            return "The key is saved, but the latest advisor workflow failed. Quant fallback remains active."
        if use_state == "format_error":
            return "The key works, but the latest AI response format failed. Quant fallback remains active."
        if use_state == "rate_limited":
            return "The key is saved, but OpenAI is rate-limiting requests right now."
        return "OpenAI can power advisor decisions and follow-up questions."
    if provider == "sec_edgar":
        if use_state == "partial":
            return "SEC is connected. Some ETFs or unsupported symbols may be not applicable for company facts."
        return "SEC is used for revenue growth, gross margin, and debt-to-equity when facts are available."
    if market_status.get("state") == "error":
        return "The connection is saved, but the latest provider refresh needs attention."
    return market_status.get("note") or "Provider is ready for the next advisor workflow."


def _provider_next_fix(
    provider: str,
    configured: bool,
    latest_test: dict[str, Any] | None,
    latest_use: dict[str, Any] | None,
    market_status: dict[str, Any],
) -> str:
    if not configured:
        return "Add connection details."
    use_state = _latest_use_state(provider, configured, latest_use, market_status)
    if provider == "openai" and use_state in {"failed", "format_error"}:
        return "Run the advisor again; Signal will use quant fallback if the model response is unusable."
    if use_state == "rate_limited":
        return "Wait and retry, or keep using quant-only decisions."
    if provider == "sec_edgar" and use_state == "partial":
        return "No action needed for ETFs; add/update SEC identity only if tests fail."
    if latest_test and latest_test["status"] == "failed":
        return "Review the saved value and test again."
    return "No action needed."


def _safe_provider_error(provider: str, exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "rate limit" in lowered or "too many requests" in lowered or "429" in text:
        return f"{PROVIDER_DEFINITIONS[provider]['label']} is rate-limiting requests right now. Signal will retry later and keep using available fallback data."
    if "401" in text or "403" in text or "unauthorized" in lowered or "forbidden" in lowered or "invalid key" in lowered:
        return f"{PROVIDER_DEFINITIONS[provider]['label']} rejected the saved credentials. Review the saved value and test again."
    if "timeout" in lowered or "timed out" in lowered:
        return f"{PROVIDER_DEFINITIONS[provider]['label']} took too long to respond. The app kept the last valid local data."
    if provider == "sec_edgar":
        if "email" in lowered or "identity" in lowered or "user agent" in lowered:
            return "SEC EDGAR needs a real contact identity, such as a name and email, before company facts can be used."
        return "SEC EDGAR could not return company facts for the test symbol. ETFs and unsupported symbols remain not applicable, not broken."
    if provider == "openai":
        return "OpenAI could not complete the test. Quant-only fallback remains active."
    if provider == "alpaca":
        return "Alpaca could not return the test market-data record. Check the API key, secret, and account data permissions."
    if provider == "fred":
        return "FRED could not return the test macro series. Check the API key and try again."
    if provider == "alpha_vantage":
        return "Alpha Vantage could not return the test market series. The provider may be throttling or the key may need review."
    return "The provider test failed. Signal kept the last valid local data."


def datetime_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def test_connection(conn, provider: str) -> dict[str, Any]:
    if provider not in PROVIDER_DEFINITIONS:
        raise ValueError(f"Unknown provider: {provider}")

    try:
        if provider == "openai":
            from app.services.ai_service import test_openai_connection

            ai_status = test_openai_connection(conn)
            if ai_status.get("state") == "rate_limited":
                last_test = _record_connection_test(
                    conn,
                    provider,
                    "rate_limited",
                    records=0,
                    message="Key saved, but OpenAI is rate-limiting requests. Quant-only fallback is active.",
                )
                return {"provider": provider, "status": "rate_limited", "ai_status": ai_status, "last_test": last_test}
            last_test = _record_connection_test(conn, provider, "success", records=1, message="OpenAI key accepted.")
            return {"provider": provider, "status": "success", "ai_status": ai_status, "last_test": last_test}

        settings = effective_settings(conn)
        if provider == "alpaca":
            adapter = AlpacaProvider(settings)
            if not adapter.status().configured:
                raise ValueError("Add both Alpaca API key and secret before testing.")
            payload = _run_async(adapter.latest_bars(["SPY"]))
            records = len((payload or {}).get("bars", {})) if isinstance(payload, dict) else 0
            message = "Latest SPY bar returned."
        elif provider == "fred":
            adapter = FredProvider(settings)
            if not adapter.status().configured:
                raise ValueError("Add a FRED API key before testing.")
            payload = _run_async(adapter.observations("FEDFUNDS"))
            records = len((payload or {}).get("observations", [])) if isinstance(payload, dict) else 0
            message = "FEDFUNDS observations returned."
        elif provider == "alpha_vantage":
            adapter = AlphaVantageProvider(settings)
            if not adapter.status().configured:
                raise ValueError("Add an Alpha Vantage key before testing.")
            payload = _run_async(adapter.daily_adjusted("SPY"))
            records = len((payload or {}).get("Time Series (Daily)", {})) if isinstance(payload, dict) else 0
            message = "Daily adjusted SPY series returned."
        else:
            adapter = SecEdgarProvider(settings)
            if not adapter.status().configured:
                raise ValueError("Add a real SEC contact identity before testing.")
            payload = _run_async(adapter.company_facts("320193"))
            records = 1 if isinstance(payload, dict) and payload.get("cik") else 0
            message = "Apple company facts returned."
    except Exception as exc:
        safe_error = _safe_provider_error(provider, exc)
        _record_connection_test(conn, provider, "failed", message=safe_error, error=str(exc))
        conn.commit()
        raise ValueError(safe_error) from exc

    last_test = _record_connection_test(conn, provider, "success", records=records, message=message)
    return {
        "provider": provider,
        "status": "success",
        "records": records,
        "last_test": last_test,
        "connections": connections_status(conn),
    }
