from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.database import get_conn
from app.providers.alpaca import AlpacaProvider
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.fred import FredProvider
from app.providers.sec_edgar import SecEdgarProvider
from app.seed import seed_sample_data
from app.services.analytics import (
    annualized_return,
    annualized_volatility,
    instrument_score,
    max_drawdown,
    momentum,
    pct_change,
    quality_score,
    trend_persistence,
)
from app.services.secrets_service import effective_settings
from app.services.universe_service import priority_symbols

SOURCE_PRIORITY = {
    "alpaca": 100,
    "fred": 80,
    "sec_edgar": 70,
    "alpha_vantage": 60,
    "sample": 10,
}

FRED_SERIES = {
    "FEDFUNDS": "FEDFUNDS",
    "UNRATE": "UNRATE",
    "DGS10": "DGS10",
    "CPIAUCSL": "CPI_YOY",
}

CIK_BY_SYMBOL = {
    "AAPL": "320193",
    "MSFT": "789019",
    "NVDA": "1045810",
    "AMZN": "1018724",
    "GOOGL": "1652044",
    "META": "1326801",
    "BRK.B": "1067983",
    "JPM": "19617",
    "LLY": "59478",
    "COST": "909832",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_rank(source: str) -> int:
    return SOURCE_PRIORITY.get(source, 0)


def refresh_data(force_sample: bool = False) -> dict[str, Any]:
    counts = seed_sample_data(force=force_sample)
    provider_results = _run_provider_refresh()
    return {
        "status": "ok",
        "message": _refresh_message(provider_results),
        "counts": counts,
        "providers": provider_results,
    }


def _refresh_message(provider_results: list[dict[str, Any]]) -> str:
    live_records = sum(result["records"] for result in provider_results if result["status"] == "success")
    if live_records:
        return f"Provider refresh complete. {live_records} live/recent records updated before analytics ran."
    configured = [result for result in provider_results if result["status"] not in {"standby", "skipped"}]
    if configured:
        return "Provider refresh checked configured sources, but no newer records were loaded. Using best local data."
    return "No live provider keys configured. Using deterministic local sample data until provider credentials are added."


def _run_provider_refresh() -> list[dict[str, Any]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_refresh_configured_providers())

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(_refresh_configured_providers())
        except Exception as exc:  # pragma: no cover - propagated to caller
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value", [])


async def _refresh_configured_providers() -> list[dict[str, Any]]:
    with get_conn() as conn:
        settings = effective_settings(conn)
        symbols = priority_symbols(conn, max(1, settings.alpaca_latest_bar_limit))
        sec_ciks = _sec_ciks_for_refresh(conn, symbols)

    results: list[dict[str, Any]] = []
    alpaca_result = await _refresh_alpaca(symbols, settings)
    results.append(alpaca_result)
    alpaca_symbols = set(alpaca_result.get("symbols", []))

    results.append(await _refresh_alpha_vantage([symbol for symbol in symbols if symbol not in alpaca_symbols], settings))
    results.append(await _refresh_fred(settings))
    results.append(await _refresh_sec_edgar(sec_ciks, settings))
    return results


def _record_provider_run(provider: str, status: str, started_at: str, records: int, message: str = "", error: str = "") -> dict[str, Any]:
    finished_at = _now()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO provider_refreshes (provider, status, started_at, finished_at, records, message, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (provider, status, started_at, finished_at, records, message, error),
        )
    return {
        "provider": provider,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "records": records,
        "message": message,
        "error": error,
    }


def _date_from_timestamp(value: str | None) -> str:
    if not value:
        return date.today().isoformat()
    return value[:10]


async def _refresh_alpaca(symbols: list[str], settings) -> dict[str, Any]:
    provider = AlpacaProvider(settings)
    started_at = _now()
    if not provider.status().configured:
        return _record_provider_run(provider.name, "standby", started_at, 0, "Missing Alpaca API keys.")
    try:
        payload = await provider.latest_bars(symbols)
        bars = payload.get("bars", {}) if isinstance(payload, dict) else {}
        rows = []
        loaded_symbols: list[str] = []
        for symbol, bar in bars.items():
            close = bar.get("c") or bar.get("close")
            if close is None:
                continue
            open_price = bar.get("o") or bar.get("open") or close
            high = bar.get("h") or bar.get("high") or close
            low = bar.get("l") or bar.get("low") or close
            volume = bar.get("v") or bar.get("volume") or 0
            rows.append(
                (
                    symbol.upper(),
                    _date_from_timestamp(bar.get("t")),
                    float(open_price),
                    float(high),
                    float(low),
                    float(close),
                    float(volume),
                    provider.name,
                )
            )
            loaded_symbols.append(symbol.upper())
        if rows:
            with get_conn() as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO price_bars
                    (symbol, date, open, high, low, close, volume, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        result = _record_provider_run(provider.name, "success", started_at, len(rows), "Latest minute bars loaded.")
        result["symbols"] = loaded_symbols
        return result
    except Exception as exc:
        return _record_provider_run(provider.name, "failed", started_at, 0, "Alpaca latest bars failed.", str(exc))


async def _refresh_alpha_vantage(symbols: list[str], settings) -> dict[str, Any]:
    provider = AlphaVantageProvider(settings)
    started_at = _now()
    if not provider.status().configured:
        return _record_provider_run(provider.name, "standby", started_at, 0, "Missing Alpha Vantage API key.")
    records = 0
    errors: list[str] = []
    limit = max(0, settings.alpha_vantage_refresh_limit)
    for symbol in symbols[:limit]:
        try:
            payload = await provider.daily_adjusted(symbol)
            series = payload.get("Time Series (Daily)") or payload.get("Time Series (Daily Adjusted)") or {}
            rows = []
            for day, values in list(series.items())[:100]:
                close = values.get("5. adjusted close") or values.get("4. close")
                if close is None:
                    continue
                rows.append(
                    (
                        symbol,
                        day,
                        float(values.get("1. open", close)),
                        float(values.get("2. high", close)),
                        float(values.get("3. low", close)),
                        float(close),
                        float(values.get("6. volume") or values.get("5. volume") or 0),
                        provider.name,
                    )
                )
            if rows:
                with get_conn() as conn:
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO price_bars
                        (symbol, date, open, high, low, close, volume, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
                records += len(rows)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            break
    status = "success" if not errors else "failed"
    message = f"Daily adjusted fallback refreshed for up to {limit} symbols."
    return _record_provider_run(provider.name, status, started_at, records, message, "; ".join(errors))


def _parse_observations(payload: dict[str, Any]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for item in payload.get("observations", []):
        value = item.get("value")
        if value in {None, "."}:
            continue
        try:
            rows.append((item["date"], float(value)))
        except (TypeError, ValueError):
            continue
    return rows


async def _refresh_fred(settings) -> dict[str, Any]:
    provider = FredProvider(settings)
    started_at = _now()
    if not provider.status().configured:
        return _record_provider_run(provider.name, "standby", started_at, 0, "Missing FRED API key.")
    observation_start = (date.today() - timedelta(days=730)).isoformat()
    records = 0
    errors: list[str] = []
    try:
        cpi_history: list[tuple[str, float]] = []
        for raw_series, target_series in FRED_SERIES.items():
            payload = await provider.observations(raw_series, observation_start=observation_start)
            observations = _parse_observations(payload)
            if raw_series == "CPIAUCSL":
                cpi_history = observations
                continue
            with get_conn() as conn:
                for day, value in observations:
                    conn.execute(
                        "INSERT OR REPLACE INTO macro_series (series_id, date, value, source) VALUES (?, ?, ?, ?)",
                        (target_series, day, value, provider.name),
                    )
                    records += 1
        if cpi_history:
            by_date = {day: value for day, value in cpi_history}
            dates = sorted(by_date)
            with get_conn() as conn:
                for idx, day in enumerate(dates):
                    if idx < 12:
                        continue
                    prior = by_date[dates[idx - 12]]
                    if prior:
                        yoy = (by_date[day] / prior - 1) * 100
                        conn.execute(
                            "INSERT OR REPLACE INTO macro_series (series_id, date, value, source) VALUES (?, ?, ?, ?)",
                            ("CPI_YOY", day, round(yoy, 4), provider.name),
                        )
                        records += 1
    except Exception as exc:
        errors.append(str(exc))
    status = "success" if not errors else "failed"
    return _record_provider_run(provider.name, status, started_at, records, "Macro observations refreshed.", "; ".join(errors))


def _fact_units(facts: dict[str, Any], tag: str, unit: str = "USD") -> list[dict[str, Any]]:
    return facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, [])


def _latest_numeric(facts: dict[str, Any], tag: str, unit: str = "USD") -> float | None:
    rows = [item for item in _fact_units(facts, tag, unit) if isinstance(item.get("val"), (int, float))]
    if not rows:
        return None
    rows.sort(key=lambda item: (item.get("end", ""), item.get("filed", "")))
    return float(rows[-1]["val"])


def _revenue_growth(facts: dict[str, Any]) -> float | None:
    rows = _fact_units(facts, "RevenueFromContractWithCustomerExcludingAssessedTax") or _fact_units(facts, "Revenues")
    numeric = [item for item in rows if isinstance(item.get("val"), (int, float))]
    if len(numeric) < 2:
        return None
    numeric.sort(key=lambda item: (item.get("end", ""), item.get("filed", "")))
    latest, previous = float(numeric[-1]["val"]), float(numeric[-2]["val"])
    if not previous:
        return None
    return max(-1.0, min(1.0, latest / abs(previous) - 1))


def _fundamentals_from_sec(facts: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    revenue = _latest_numeric(facts, "RevenueFromContractWithCustomerExcludingAssessedTax") or _latest_numeric(facts, "Revenues")
    gross_profit = _latest_numeric(facts, "GrossProfit")
    liabilities = _latest_numeric(facts, "Liabilities")
    equity = _latest_numeric(facts, "StockholdersEquity")
    revenue_growth = _revenue_growth(facts)
    if revenue_growth is not None:
        metrics["revenue_growth"] = round(revenue_growth, 5)
    if revenue and gross_profit:
        metrics["gross_margin"] = round(max(-1.0, min(1.0, gross_profit / revenue)), 5)
    if liabilities is not None and equity:
        metrics["debt_to_equity"] = round(max(0.0, min(5.0, liabilities / equity)), 5)
    return metrics


def _sec_ciks_for_refresh(conn, symbols: list[str]) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT symbol, cik, asset_class
        FROM universe_assets
        WHERE cik != ''
        """
    ).fetchall()
    ciks = {row["symbol"]: str(row["cik"]) for row in rows if row.get("asset_class") not in {"ETF", "Fund"}}
    for symbol, cik in CIK_BY_SYMBOL.items():
        ciks.setdefault(symbol, cik)
    selected = {symbol: ciks[symbol] for symbol in symbols if symbol in ciks}
    if not selected:
        selected = {symbol: cik for symbol, cik in ciks.items() if symbol in CIK_BY_SYMBOL}
    return selected


async def _refresh_sec_edgar(symbol_ciks: dict[str, str], settings) -> dict[str, Any]:
    provider = SecEdgarProvider(settings)
    started_at = _now()
    if not provider.status().configured:
        return _record_provider_run(provider.name, "standby", started_at, 0, "Set SEC_USER_AGENT with real contact info to enable EDGAR.")
    records = 0
    errors: list[str] = []
    not_applicable: list[str] = []
    for symbol, cik in list(symbol_ciks.items())[: max(0, settings.sec_edgar_refresh_limit)]:
        try:
            payload = await provider.company_facts(cik)
            metrics = _fundamentals_from_sec(payload)
            if metrics:
                period = date.today().isoformat()
                with get_conn() as conn:
                    for metric, value in metrics.items():
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO fundamental_facts
                            (symbol, metric, period, value, source)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (symbol, metric, period, value, provider.name),
                        )
                        records += 1
            else:
                not_applicable.append(symbol)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                not_applicable.append(symbol)
                continue
            errors.append(f"{symbol}: SEC company facts HTTP {exc.response.status_code}")
            continue
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            continue
    status = "success" if not errors else ("partial" if records or not_applicable else "failed")
    message = "SEC company facts refreshed."
    if not_applicable:
        sample = ", ".join(not_applicable[:5])
        message = f"SEC company facts refreshed. {len(not_applicable)} symbols were not company-facts covered ({sample})."
    if errors and (records or not_applicable):
        message = f"{message} {len(errors)} symbols need retry."
    return _record_provider_run(provider.name, status, started_at, records, message, "; ".join(errors[:8]))


def latest_prices(conn) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT symbol, date, close, source
        FROM price_bars
        ORDER BY symbol, date DESC
        """
    ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = latest.get(row["symbol"])
        if not current:
            latest[row["symbol"]] = dict(row)
            continue
        if row["date"] == current["date"] and _source_rank(row["source"]) > _source_rank(current["source"]):
            latest[row["symbol"]] = dict(row)
    return {symbol: row["close"] for symbol, row in latest.items()}


def load_price_series(conn, symbols: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    params: list[Any] = []
    where = ""
    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        where = f"WHERE symbol IN ({placeholders})"
        params = symbols
    rows = conn.execute(
        f"SELECT symbol, date, close, source FROM price_bars {where} ORDER BY symbol, date, source",
        params,
    ).fetchall()
    by_symbol_date: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        current = by_symbol_date[row["symbol"]].get(row["date"])
        if not current or _source_rank(row["source"]) >= _source_rank(current["source"]):
            by_symbol_date[row["symbol"]][row["date"]] = {"date": row["date"], "close": row["close"], "source": row["source"]}
    return {
        symbol: [by_date[day] for day in sorted(by_date)]
        for symbol, by_date in by_symbol_date.items()
    }


def latest_fundamentals(conn) -> dict[str, dict[str, float]]:
    rows = conn.execute(
        """
        SELECT f.symbol, f.metric, f.value, f.source
        FROM fundamental_facts f
        JOIN (
            SELECT symbol, metric, MAX(period) AS max_period
            FROM fundamental_facts
            GROUP BY symbol, metric
        ) latest ON f.symbol = latest.symbol AND f.metric = latest.metric AND f.period = latest.max_period
        """
    ).fetchall()
    facts_by_source: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        source = row.get("source", "sample")
        facts_by_source[row["symbol"]][row["metric"]][source] = row["value"]
    facts: dict[str, dict[str, float]] = defaultdict(dict)
    for symbol, metrics in facts_by_source.items():
        for metric, values in metrics.items():
            source = max(values, key=_source_rank)
            facts[symbol][metric] = values[source]
    return dict(facts)


def _value_score(facts: dict[str, float]) -> float:
    fcf_yield = facts.get("free_cash_flow_yield")
    debt = facts.get("debt_to_equity")
    revenue_growth = facts.get("revenue_growth")
    score = 0.50
    if fcf_yield is not None:
        score += max(-0.20, min(0.30, fcf_yield * 3.0))
    if debt is not None:
        score += max(-0.15, min(0.12, (1.0 - debt) * 0.08))
    if revenue_growth is not None:
        score += max(-0.10, min(0.10, revenue_growth * 0.10))
    return round(max(0.0, min(1.0, score)), 4)


def _factor_breakdown(item: dict[str, Any]) -> dict[str, Any]:
    data_quality = "sample_only" if item["price_source"] == "sample" else "stale" if item["source_data_age_days"] > 7 else "fresh"
    return {
        "cross_section_momentum": item.get("cross_section_momentum", 0),
        "time_series_momentum": item.get("time_series_momentum", 0),
        "quality_profitability": item.get("quality_score", 0.5),
        "value_proxy": item.get("value_score", 0.5),
        "low_volatility": item.get("low_volatility_score", 0),
        "drawdown_control": item.get("drawdown_control_score", 0),
        "liquidity": item.get("liquidity_score", 0) / 100,
        "data_quality": data_quality,
        "ipo_or_special_situation": bool(item.get("is_ipo") or item.get("asset_class") == "Special Situation"),
    }


def _store_factor_snapshot(conn, item: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO factor_snapshots
        (symbol, snapshot_date, source, factors, score)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            item["symbol"],
            item.get("latest_date") or date.today().isoformat(),
            item.get("price_source", "unknown"),
            json.dumps(item["factor_breakdown"]),
            item["score"],
        ),
    )


def compute_universe_features(conn, symbols: list[str] | None = None, store_snapshots: bool = False) -> list[dict[str, Any]]:
    instruments = conn.execute(
        "SELECT * FROM instruments WHERE enabled = 1 ORDER BY symbol"
    ).fetchall()
    if symbols:
        wanted = set(symbols)
        instruments = [item for item in instruments if item["symbol"] in wanted]

    series = load_price_series(conn, [item["symbol"] for item in instruments])
    fundamentals = latest_fundamentals(conn)
    features: list[dict[str, Any]] = []
    for instrument in instruments:
        symbol = instrument["symbol"]
        price_points = series.get(symbol, [])
        closes = [item["close"] for item in price_points]
        returns = pct_change(closes)
        fact_score = quality_score(fundamentals.get(symbol, {}))
        if len(closes) < 120:
            continue
        latest_point = price_points[-1]
        try:
            source_age_days = max(0, (date.today() - date.fromisoformat(latest_point["date"][:10])).days)
        except ValueError:
            source_age_days = 999
        facts = fundamentals.get(symbol, {})
        item = {
            **instrument,
            "is_multi_asset": bool(instrument["is_multi_asset"]),
            "latest_price": closes[-1],
            "latest_date": latest_point["date"],
            "price_source": latest_point.get("source", "unknown"),
            "source_data_age_days": source_age_days,
            "one_year_return": annualized_return(closes[-252:]),
            "momentum_63d": momentum(closes, 63),
            "momentum_126d": momentum(closes, 126),
            "volatility": annualized_volatility(returns[-252:]),
            "max_drawdown": max_drawdown(closes[-252:]),
            "trend_persistence": trend_persistence(closes),
            "quality_score": fact_score,
            "value_score": _value_score(facts),
        }
        item.update(instrument_score(item))
        item["factor_breakdown"] = _factor_breakdown(item)
        if store_snapshots:
            _store_factor_snapshot(conn, item)
        features.append(item)
    return sorted(features, key=lambda item: item["score"], reverse=True)


def data_freshness(conn) -> dict[str, Any]:
    row = conn.execute("SELECT MAX(date) AS latest_price_date, COUNT(*) AS bars FROM price_bars").fetchone()
    macro = conn.execute("SELECT MAX(date) AS latest_macro_date, COUNT(*) AS points FROM macro_series").fetchone()
    source_rows = conn.execute("SELECT source, COUNT(*) AS count, COUNT(DISTINCT symbol) AS symbols FROM price_bars GROUP BY source").fetchall()
    macro_source_rows = conn.execute("SELECT source, COUNT(*) AS count FROM macro_series GROUP BY source").fetchall()
    provider_run = conn.execute("SELECT * FROM provider_refreshes ORDER BY id DESC LIMIT 1").fetchone()
    price_source_counts = {item["source"]: item["count"] for item in source_rows}
    price_source_symbols = {item["source"]: item["symbols"] for item in source_rows}
    live_sources = [source for source in price_source_counts if source != "sample"]
    preferred_source = max(price_source_counts, key=_source_rank) if price_source_counts else "none"
    live_symbols = sum(price_source_symbols.get(source, 0) for source in live_sources)
    provider_mode = "live" if live_symbols else "sample"
    return {
        "latest_price_date": row["latest_price_date"],
        "price_bars": row["bars"],
        "latest_macro_date": macro["latest_macro_date"],
        "macro_points": macro["points"],
        "provider_mode": provider_mode,
        "preferred_price_source": preferred_source,
        "live_price_symbols": live_symbols,
        "sample_price_symbols": price_source_symbols.get("sample", 0),
        "price_source_counts": price_source_counts,
        "macro_source_counts": {item["source"]: item["count"] for item in macro_source_rows},
        "latest_provider_refresh": dict(provider_run) if provider_run else None,
    }


def ensure_data() -> None:
    seed_sample_data(force=False)
