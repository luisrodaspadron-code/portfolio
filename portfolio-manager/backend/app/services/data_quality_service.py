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
    universe_row = _row("SELECT COUNT(*) AS rows, SUM(included) AS included, MAX(last_seen_at) AS latest FROM universe_assets")
    factor_row = _row("SELECT COUNT(*) AS rows, COUNT(DISTINCT symbol) AS symbols, MAX(snapshot_date) AS latest FROM factor_snapshots")
    liquidity_row = _row(
        """
        SELECT
            MAX(date) AS latest,
            COUNT(*) AS rows,
            COUNT(DISTINCT symbol) AS symbols,
            SUM(CASE WHEN volume > 0 THEN 1 ELSE 0 END) AS volume_rows,
            SUM(CASE WHEN close * volume >= ? THEN 1 ELSE 0 END) AS liquid_rows
        FROM price_bars
        """,
        (policy.liquidity.min_dollar_volume_default,),
    )
    portfolio_row = _row(
        """
        SELECT
            p.id,
            p.cash,
            p.created_at,
            COUNT(pos.id) AS positions,
            COUNT(DISTINCT pos.symbol) AS symbols,
            SUM(CASE WHEN pos.source = 'csv_import' THEN 1 ELSE 0 END) AS imported_rows,
            SUM(CASE WHEN pos.avg_cost > 0 THEN 1 ELSE 0 END) AS cost_rows
        FROM portfolios p
        LEFT JOIN positions pos ON pos.portfolio_id = p.id
        WHERE p.mode = 'real'
        GROUP BY p.id
        ORDER BY p.id
        LIMIT 1
        """
    )
    latest_ai_row = _row("SELECT * FROM ai_runs ORDER BY id DESC LIMIT 1")

    price_count_rows = conn.execute("SELECT source, COUNT(*) AS rows FROM price_bars GROUP BY source").fetchall() if price_row else []
    price_source_counts = {item["source"]: int(item["rows"] or 0) for item in price_count_rows}
    non_sample_price_counts = {source: count for source, count in price_source_counts.items() if source != "sample" and count > 0}
    price_provider = (
        max(non_sample_price_counts.items(), key=lambda item: item[1])[0]
        if non_sample_price_counts
        else "sample"
        if price_source_counts.get("sample", 0)
        else "unknown"
    )

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

    def _slow_source_freshness(value: str | None, *, has_data: bool) -> Freshness:
        age = _ts_age(value)
        if not has_data or age is None:
            return "missing"
        if age <= 45 * 86_400:
            return "recent"
        return "stale"

    def _confidence(freshness: str, coverage: str, *, configured: bool = True, used: bool = False) -> float:
        freshness_score = {
            "live": 1.0,
            "recent": 0.86,
            "partial": 0.62,
            "stale": 0.35,
            "missing": 0.0,
        }.get(freshness, 0.0)
        coverage_score = {
            "complete": 1.0,
            "partial": 0.7,
            "insufficient": 0.35,
            "missing": 0.0,
        }.get(coverage, 0.0)
        score = freshness_score * 0.6 + coverage_score * 0.4
        if not configured and not used:
            score *= 0.55
        return round(max(0.0, min(score, 1.0)), 2)

    def _finalize(entry: dict[str, Any], *, configured: bool = True) -> dict[str, Any]:
        freshness = str(entry.get("freshness") or "missing")
        coverage = str(entry.get("coverage") or "missing")
        entry.setdefault("configured", configured)
        entry.setdefault("confidence", _confidence(freshness, coverage, configured=configured, used=bool(entry.get("usedInRun"))))
        entry.setdefault("warnings", [])
        entry.setdefault("usedInLatestRun", bool(entry.get("usedInRun")))
        return entry

    try:
        from app.services.ai_service import ai_status

        ai = ai_status(conn)
    except Exception:
        ai = {
            "configured": False,
            "state": "disabled",
            "model": "",
            "model_router": {},
            "settings": {},
            "usage_totals": {},
            "last_run": None,
        }

    latest_ai_timestamp = (latest_ai_row or {}).get("finished_at") if latest_ai_row else None
    ai_state = str(ai.get("state") or "disabled")
    ai_configured = bool(ai.get("configured"))
    ai_used = bool(latest_ai_row and (latest_ai_row or {}).get("status") == "success")
    ai_freshness = "recent" if ai_used else "partial" if ai_configured else "missing"
    lead_route = (ai.get("model_router") or {}).get("leadPM") or {}
    specialist_route = (ai.get("model_router") or {}).get("specialist") or {}
    fast_route = (ai.get("model_router") or {}).get("fast") or {}

    liquidity_rows = int((liquidity_row or {}).get("rows") or 0) if liquidity_row else 0
    liquid_rows = int((liquidity_row or {}).get("liquid_rows") or 0) if liquidity_row else 0
    volume_rows = int((liquidity_row or {}).get("volume_rows") or 0) if liquidity_row else 0
    liquidity_coverage = (
        "complete"
        if liquidity_rows and liquid_rows / liquidity_rows >= 0.85
        else "partial"
        if liquidity_rows and volume_rows
        else "missing"
    )
    fundamentals_count = int((fundamentals_row or {}).get("rows") or 0) if fundamentals_row else 0
    portfolio_positions = int((portfolio_row or {}).get("positions") or 0) if portfolio_row else 0
    portfolio_cost_rows = int((portfolio_row or {}).get("cost_rows") or 0) if portfolio_row else 0
    macro_rows = int((macro_row or {}).get("rows") or 0) if macro_row else 0
    macro_freshness = _slow_source_freshness((macro_row or {}).get("latest") if macro_row else None, has_data=bool(macro_rows))
    price_rows = int((price_row or {}).get("rows") or 0) if price_row else 0
    price_symbols = int((price_row or {}).get("symbols") or 0) if price_row else 0
    price_coverage = "complete" if price_symbols >= portfolio_positions and portfolio_positions else "partial" if price_rows else "missing"
    price_warnings: list[str] = []
    if price_provider_mode == "stale":
        price_warnings.append("Market prices are stale under the selected policy; sizing should be reviewed against a fresh quote.")
    if price_provider == "sample" or "synthetic" in price_provider.lower():
        price_warnings.append("Market prices are from a local fixture/sample source; refresh a configured market-data provider before acting.")
    liquidity_warnings: list[str] = []
    if not (liquidity_rows and volume_rows):
        liquidity_warnings.append("No usable volume rows are available; liquidity gates degrade to conservative defaults.")
    elif price_provider_mode == "stale":
        liquidity_warnings.append("Liquidity inputs are based on stale price/volume rows.")
    if price_provider == "sample" or "synthetic" in price_provider.lower():
        liquidity_warnings.append("Liquidity is derived from local fixture/sample data, not a live provider.")
    ai_warnings: list[str] = []
    if not ai_configured:
        ai_warnings.append("AI narrative review is disabled; deterministic quant-only fallback remains active.")
    elif not ai_used:
        ai_warnings.append("The latest AI run did not complete successfully; deterministic quant-only fallback remains active.")

    matrix = {
        "prices": {
            "provider": price_provider,
            "fallback": "sample",
            "latestTimestamp": (price_row or {}).get("latest") if price_row else None,
            "ageSeconds": _ts_age((price_row or {}).get("latest") if price_row else None),
            "recordCount": price_rows,
            "symbolCount": price_symbols,
            "freshness": price_provider_mode,
            "coverage": price_coverage,
            "usedInRun": price_provider_mode != "missing",
            "warnings": price_warnings,
        },
        "liquidity": {
            "provider": price_provider if price_provider != "unknown" else "price_bars",
            "fallback": "volume_from_price_bars",
            "latestTimestamp": (liquidity_row or {}).get("latest") if liquidity_row else None,
            "ageSeconds": _ts_age((liquidity_row or {}).get("latest") if liquidity_row else None),
            "recordCount": liquidity_rows,
            "symbolCount": int((liquidity_row or {}).get("symbols") or 0) if liquidity_row else 0,
            "freshness": price_provider_mode if liquidity_rows else "missing",
            "coverage": liquidity_coverage,
            "usedInRun": bool(liquidity_rows and price_provider_mode != "missing"),
            "warnings": liquidity_warnings,
        },
        "macro": {
            "provider": "fred",
            "fallback": "manual",
            "latestTimestamp": (macro_row or {}).get("latest") if macro_row else None,
            "ageSeconds": _ts_age((macro_row or {}).get("latest") if macro_row else None),
            "recordCount": macro_rows,
            "freshness": macro_freshness,
            "coverage": "partial" if macro_rows else "missing",
            "usedInRun": bool(macro_rows),
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
        "filings": {
            "provider": "sec_edgar",
            "fallback": "company_facts_cache",
            "recordCount": fundamentals_count,
            "symbolCount": int((fundamentals_row or {}).get("symbols") or 0) if fundamentals_row else 0,
            "freshness": "recent" if fundamentals_count else "missing",
            "coverage": "partial" if fundamentals_count else "missing",
            "usedInRun": bool(fundamentals_count),
            "warnings": [
                "Raw filings index is not fully cached; structured company facts are used where SEC coverage exists."
            ]
            if fundamentals_count
            else ["SEC filings/company-facts coverage is missing for this local dataset."],
        },
        "universe": {
            "provider": "alpaca_assets",
            "fallback": "sample",
            "recordCount": int((universe_row or {}).get("rows") or 0) if universe_row else 0,
            "includedCount": int((universe_row or {}).get("included") or 0) if universe_row else 0,
            "latestTimestamp": (universe_row or {}).get("latest") if universe_row else None,
            "ageSeconds": _ts_age((universe_row or {}).get("latest") if universe_row else None),
            "freshness": _slow_source_freshness(
                (universe_row or {}).get("latest") if universe_row else None,
                has_data=bool(universe_row and (universe_row or {}).get("included")),
            ),
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
        "portfolioState": {
            "provider": "local_portfolio",
            "fallback": "manual_import",
            "latestTimestamp": (portfolio_row or {}).get("created_at") if portfolio_row else None,
            "ageSeconds": _ts_age((portfolio_row or {}).get("created_at") if portfolio_row else None),
            "recordCount": portfolio_positions,
            "symbolCount": int((portfolio_row or {}).get("symbols") or 0) if portfolio_row else 0,
            "freshness": "live" if portfolio_positions else "missing",
            "coverage": "complete"
            if portfolio_positions and portfolio_cost_rows >= portfolio_positions
            else "partial"
            if portfolio_positions
            else "missing",
            "usedInRun": bool(portfolio_positions),
            "warnings": []
            if portfolio_positions
            else ["No real-money holdings are loaded; portfolio-specific gates cannot fully run."],
        },
        "ai": {
            "provider": "openai" if ai_configured else "not_configured",
            "fallback": "quant_only",
            "latestTimestamp": latest_ai_timestamp,
            "ageSeconds": _ts_age(latest_ai_timestamp),
            "recordCount": int((ai.get("usage_totals") or {}).get("calls") or 0),
            "freshness": ai_freshness,
            "coverage": "complete" if ai_used else "partial" if ai_configured else "missing",
            "usedInRun": ai_used,
            "state": ai_state,
            "leadModel": lead_route.get("model") or "",
            "leadReasoningEffort": lead_route.get("reasoningEffort") or "",
            "specialistModel": specialist_route.get("model") or "",
            "fastModel": fast_route.get("model") or "",
            "promptVersion": lead_route.get("promptVersion") or "",
            "warnings": ai_warnings,
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
    matrix = {key: _finalize(value, configured=value.get("provider") != "not_configured") for key, value in matrix.items()}
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
            "requiredClassesCovered": {
                "marketPricesAndLiquidity": matrix["prices"]["usedInRun"] and matrix["liquidity"]["usedInRun"],
                "fundamentalsAndFilings": matrix["fundamentals"]["usedInRun"] or matrix["filings"]["usedInRun"],
                "macroRegime": matrix["macro"]["usedInRun"],
                "factorBenchmarks": matrix["factors"]["usedInRun"],
                "eventOpportunity": matrix["events"]["usedInRun"] or matrix["ipoCalendar"]["usedInRun"],
                "portfolioUserState": matrix["portfolioState"]["usedInRun"],
                "telemetryAudit": matrix["telemetry"]["usedInRun"],
            },
        },
    }
