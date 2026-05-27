"""V8 data-quality taxonomy and source-coverage matrix.

The previous data_freshness logic marked anything non-sample as ``live``. V8
requires timestamp + policy threshold logic; ``live``/``recent``/``stale`` are
distinct, ``partial`` and ``missing`` are explicit, and the source matrix shows
provider/fallback/timestamp/coverage per data class.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.services.policy_engine import RiskPolicy, selected_risk_policy


Freshness = Literal["live", "recent", "stale", "partial", "missing"]
Coverage = Literal["complete", "partial", "insufficient", "missing"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{normalized}T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def freshness_from_age(
    age_seconds: int | None,
    *,
    policy: RiskPolicy,
    asset_class: str = "stock",
    has_data: bool = True,
) -> Freshness:
    if not has_data or age_seconds is None:
        return "missing"
    dq = policy.data_quality
    if asset_class.lower() == "crypto":
        live_limit = dq.crypto_live_seconds
        recent_limit = dq.crypto_recent_seconds
    else:
        live_limit = dq.equity_live_seconds
        recent_limit = dq.equity_recent_seconds
    if age_seconds <= live_limit:
        return "live"
    if age_seconds <= recent_limit:
        return "recent"
    return "stale"


def provider_mode_for_prices(
    latest_price_date: str | None,
    price_source_counts: dict[str, int],
    *,
    policy: RiskPolicy,
    now: datetime | None = None,
) -> Freshness:
    """Return the timestamp-based provider mode.

    ``provider_mode = "live"`` requires both: at least one non-sample source AND
    the latest price timestamp within the live freshness threshold. ``recent``
    means data is non-sample but older than the live threshold. ``partial`` is
    used when the sample source dominates. ``missing`` is no data.
    """

    now = now or _now()
    parsed = _parse_timestamp(latest_price_date)
    if parsed is None:
        return "missing"
    age = max(0, int((now - parsed).total_seconds()))
    non_sample_total = sum(count for source, count in price_source_counts.items() if source != "sample")
    sample_total = price_source_counts.get("sample", 0)
    if non_sample_total == 0:
        return "missing" if sample_total == 0 else "partial"
    if sample_total > non_sample_total:
        # Coverage is dominated by sample data even if a few live rows exist.
        if age <= policy.data_quality.equity_live_seconds:
            return "partial"
        return "stale"
    return freshness_from_age(age, policy=policy, asset_class="stock", has_data=True)


def coverage_label(
    symbols_with_data: int,
    expected_symbols: int,
    *,
    full_history_days: int,
    actual_history_days: int,
) -> Coverage:
    if expected_symbols <= 0:
        return "missing"
    if symbols_with_data == 0:
        return "missing"
    ratio = symbols_with_data / expected_symbols
    if ratio >= 0.99 and actual_history_days >= full_history_days:
        return "complete"
    if ratio >= 0.6 and actual_history_days >= full_history_days // 2:
        return "partial"
    return "insufficient"


def build_source_matrix(conn, *, policy: RiskPolicy | None = None) -> dict[str, Any]:
    """Return the V8 ``DataSourceMatrix`` for the current advisor run.

    Each entry includes provider, fallback, latest timestamp, record count,
    coverage, confidence, warnings, and whether the data was usable in the
    current advisor run. We pull from existing tables where possible and mark
    unknown entries as missing rather than fabricating data.
    """

    policy = policy or selected_risk_policy(conn)
    now = _now()

    def _row(query: str, params: tuple = ()) -> Any:
        try:
            return conn.execute(query, params).fetchone()
        except Exception:
            return None

    price_row = _row("SELECT MAX(date) AS latest, COUNT(*) AS rows, COUNT(DISTINCT symbol) AS symbols FROM price_bars")
    macro_row = _row("SELECT MAX(date) AS latest, COUNT(*) AS rows FROM macro_series")
    fundamentals_row = _row("SELECT COUNT(*) AS rows, COUNT(DISTINCT symbol) AS symbols FROM fundamental_facts")
    universe_row = _row("SELECT COUNT(*) AS rows, SUM(included) AS included FROM universe_assets")
    factor_row = _row("SELECT COUNT(*) AS rows, COUNT(DISTINCT symbol) AS symbols, MAX(snapshot_date) AS latest FROM factor_snapshots")
    refresh_row = _row("SELECT provider, status, finished_at, message FROM provider_refreshes ORDER BY id DESC LIMIT 1")

    price_count_rows = conn.execute("SELECT source, COUNT(*) AS rows FROM price_bars GROUP BY source").fetchall() if price_row else []
    price_source_counts = {item["source"]: int(item["rows"] or 0) for item in price_count_rows}

    price_provider_mode = provider_mode_for_prices(
        (price_row or {}).get("latest") if price_row else None,
        price_source_counts,
        policy=policy,
        now=now,
    )

    def _ts_age(value: str | None) -> int | None:
        parsed = _parse_timestamp(value)
        if parsed is None:
            return None
        return max(0, int((now - parsed).total_seconds()))

    matrix = {
        "prices": {
            "provider": (refresh_row or {}).get("provider") if refresh_row else "unknown",
            "fallback": "sample",
            "latestTimestamp": (price_row or {}).get("latest") if price_row else None,
            "ageSeconds": _ts_age((price_row or {}).get("latest") if price_row else None),
            "recordCount": int((price_row or {}).get("rows") or 0) if price_row else 0,
            "symbolCount": int((price_row or {}).get("symbols") or 0) if price_row else 0,
            "freshness": price_provider_mode,
            "coverage": "complete" if price_provider_mode in {"live", "recent"} else "partial" if price_provider_mode == "partial" else "missing",
            "usedInRun": price_provider_mode != "missing",
            "warnings": [],
        },
        "macro": {
            "provider": "fred",
            "fallback": "manual",
            "latestTimestamp": (macro_row or {}).get("latest") if macro_row else None,
            "ageSeconds": _ts_age((macro_row or {}).get("latest") if macro_row else None),
            "recordCount": int((macro_row or {}).get("rows") or 0) if macro_row else 0,
            "freshness": "live" if (macro_row and (macro_row or {}).get("rows")) else "missing",
            "coverage": "partial" if macro_row and (macro_row or {}).get("rows") else "missing",
            "usedInRun": bool(macro_row and (macro_row or {}).get("rows")),
            "warnings": [],
        },
        "fundamentals": {
            "provider": "sec_company_facts",
            "fallback": "manual",
            "recordCount": int((fundamentals_row or {}).get("rows") or 0) if fundamentals_row else 0,
            "symbolCount": int((fundamentals_row or {}).get("symbols") or 0) if fundamentals_row else 0,
            "freshness": "recent" if fundamentals_row and (fundamentals_row or {}).get("rows") else "missing",
            "coverage": "partial",
            "usedInRun": bool(fundamentals_row and (fundamentals_row or {}).get("rows")),
            "warnings": ["SEC company facts may not cover foreign issuers; partial fundamentals do not automatically block analysis."],
        },
        "universe": {
            "provider": "alpaca_assets",
            "fallback": "sample",
            "recordCount": int((universe_row or {}).get("rows") or 0) if universe_row else 0,
            "includedCount": int((universe_row or {}).get("included") or 0) if universe_row else 0,
            "freshness": "live" if universe_row and (universe_row or {}).get("included") else "missing",
            "coverage": "complete" if universe_row and (universe_row or {}).get("included") else "missing",
            "usedInRun": bool(universe_row and (universe_row or {}).get("included")),
            "warnings": [],
        },
        "factors": {
            "provider": "internal",
            "fallback": "sample",
            "recordCount": int((factor_row or {}).get("rows") or 0) if factor_row else 0,
            "symbolCount": int((factor_row or {}).get("symbols") or 0) if factor_row else 0,
            "latestTimestamp": (factor_row or {}).get("latest") if factor_row else None,
            "freshness": "recent" if factor_row and (factor_row or {}).get("rows") else "missing",
            "coverage": "partial",
            "usedInRun": bool(factor_row and (factor_row or {}).get("rows")),
            "warnings": [],
        },
        "events": {
            "provider": "not_configured",
            "fallback": "manual",
            "freshness": "missing",
            "coverage": "missing",
            "usedInRun": False,
            "warnings": ["No event/news provider is configured; event-driven signals are not available."],
        },
        "ipoCalendar": {
            "provider": "not_configured",
            "fallback": "manual",
            "freshness": "missing",
            "coverage": "missing",
            "usedInRun": False,
            "warnings": ["No IPO calendar provider is configured; limited-history playbook applies."],
        },
        "cryptoMetadata": {
            "provider": "not_configured",
            "fallback": "manual",
            "freshness": "missing",
            "coverage": "missing",
            "usedInRun": False,
            "warnings": ["Crypto data is disabled by default and requires explicit user enablement."],
        },
        "telemetry": {
            "provider": "internal",
            "fallback": "manual",
            "freshness": "live",
            "coverage": "complete",
            "usedInRun": True,
            "warnings": [],
        },
    }
    return {
        "generatedAt": now.isoformat(),
        "policyVersion": policy.version,
        "selectedPreset": policy.preset,
        "matrix": matrix,
        "summary": {
            "priceProviderMode": price_provider_mode,
            "macroAvailable": matrix["macro"]["usedInRun"],
            "fundamentalsPartial": matrix["fundamentals"]["coverage"] == "partial",
            "cryptoEnabled": policy.crypto.enabled_by_default,
        },
    }
