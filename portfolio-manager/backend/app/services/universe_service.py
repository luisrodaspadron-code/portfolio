from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from typing import Any

import httpx

from app.database import get_conn
from app.providers.alpaca import AlpacaProvider
from app.providers.sec_edgar import SecEdgarProvider
from app.seed import INSTRUMENTS
from app.services.classification import classify_instrument
from app.services.secrets_service import effective_settings


ETF_HINTS = (
    "ETF",
    "ETN",
    "FUND",
    "TRUST",
    "ISHARES",
    "VANGUARD",
    "SPDR",
    "INVESCO",
    "PROSHARES",
    "DIREXION",
    "GLOBAL X",
    "WISDOMTREE",
    "SCHWAB",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _record_rate_limit(conn, provider: str, status: str, message: str) -> None:
    conn.execute(
        """
        INSERT INTO provider_rate_limits (provider, status, message, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(provider) DO UPDATE SET
            status = excluded.status,
            message = excluded.message,
            updated_at = excluded.updated_at
        """,
        (provider, status, message, _now()),
    )


def _asset_class(name: str, symbol: str, raw_class: str = "") -> str:
    upper_name = name.upper()
    if any(hint in upper_name for hint in ETF_HINTS) or raw_class.lower() in {"etf", "fund"}:
        return "ETF"
    if symbol.endswith(".U") or symbol.endswith(".WS") or "WARRANT" in upper_name or "UNIT" in upper_name:
        return "Special Situation"
    return "Stock"


def _liquidity_tier(exchange: str, asset_class: str, symbol: str, existing_liquidity: float | None = None) -> str:
    if existing_liquidity is not None and existing_liquidity >= 85:
        return "core"
    if existing_liquidity is not None and existing_liquidity >= 65:
        return "candidate"
    if exchange in {"NYSE", "NASDAQ", "ARCA", "NYSEARCA"} and asset_class in {"Stock", "ETF"} and len(symbol) <= 5:
        return "candidate"
    return "long_tail"


def _upsert_universe_asset(conn, asset: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO universe_assets
        (symbol, name, asset_class, exchange, status, tradable, marginable, shortable, fractionable,
         attributes, is_ipo, cik, source, included, exclusion_reason, liquidity_tier, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            name = excluded.name,
            asset_class = excluded.asset_class,
            exchange = excluded.exchange,
            status = excluded.status,
            tradable = excluded.tradable,
            marginable = excluded.marginable,
            shortable = excluded.shortable,
            fractionable = excluded.fractionable,
            attributes = excluded.attributes,
            is_ipo = excluded.is_ipo,
            cik = CASE WHEN excluded.cik != '' THEN excluded.cik ELSE universe_assets.cik END,
            source = excluded.source,
            included = excluded.included,
            exclusion_reason = excluded.exclusion_reason,
            liquidity_tier = excluded.liquidity_tier,
            last_seen_at = excluded.last_seen_at
        """,
        (
            asset["symbol"],
            asset["name"],
            asset["asset_class"],
            asset.get("exchange", ""),
            asset.get("status", "active"),
            int(bool(asset.get("tradable"))),
            int(bool(asset.get("marginable"))),
            int(bool(asset.get("shortable"))),
            int(bool(asset.get("fractionable"))),
            json.dumps(asset.get("attributes", [])),
            int(bool(asset.get("is_ipo"))),
            asset.get("cik", ""),
            asset.get("source", "sample"),
            int(bool(asset.get("included", True))),
            asset.get("exclusion_reason", ""),
            asset.get("liquidity_tier", "unknown"),
            _now(),
        ),
    )


def _sync_seed_assets(conn) -> int:
    existing_liquidity = {row["symbol"]: row["liquidity_score"] for row in conn.execute("SELECT symbol, liquidity_score FROM instruments").fetchall()}
    inserted = 0
    for symbol, name, asset_class, sector, _multi, liquidity in INSTRUMENTS:
        _upsert_universe_asset(
            conn,
            {
                "symbol": symbol,
                "name": name,
                "asset_class": asset_class,
                "exchange": "sample",
                "status": "active",
                "tradable": True,
                "marginable": asset_class == "Stock",
                "shortable": False,
                "fractionable": True,
                "attributes": [],
                "is_ipo": False,
                "source": "sample",
                "included": True,
                "liquidity_tier": _liquidity_tier("sample", asset_class, symbol, existing_liquidity.get(symbol, liquidity)),
            },
        )
        inserted += 1
    return inserted


def _sync_missing_instrument_assets(conn) -> int:
    rows = conn.execute(
        """
        SELECT i.symbol, i.name, i.asset_class, i.sector, i.liquidity_score
        FROM instruments i
        LEFT JOIN universe_assets ua ON ua.symbol = i.symbol
        WHERE ua.symbol IS NULL
        """
    ).fetchall()
    for row in rows:
        _upsert_universe_asset(
            conn,
            {
                "symbol": row["symbol"],
                "name": row["name"],
                "asset_class": row["asset_class"],
                "exchange": "imported" if row["sector"] == "Imported" else "local",
                "status": "active",
                "tradable": True,
                "fractionable": True,
                "attributes": [],
                "source": "imported" if row["sector"] == "Imported" else "local",
                "included": True,
                "liquidity_tier": "current_holding" if row["sector"] == "Imported" else _liquidity_tier("local", row["asset_class"], row["symbol"], row["liquidity_score"]),
            },
        )
    return len(rows)


def _sync_alpaca_assets(conn) -> dict[str, Any]:
    settings = effective_settings(conn)
    provider = AlpacaProvider(settings)
    if not provider.status().configured:
        return {"provider": "alpaca", "status": "standby", "records": 0, "message": "Connect Alpaca to ingest the all-US tradable universe."}
    try:
        payload = _run_async(provider.assets())
        limit = max(0, settings.alpaca_asset_refresh_limit)
        assets = payload[:limit] if limit else payload
        existing_liquidity = {
            row["symbol"]: row["liquidity_score"]
            for row in conn.execute("SELECT symbol, liquidity_score FROM instruments").fetchall()
        }
        records = 0
        included = 0
        ipos = 0
        for raw in assets:
            symbol = str(raw.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            attrs = raw.get("attributes") or []
            if isinstance(attrs, str):
                attrs = [attrs]
            name = str(raw.get("name") or symbol).strip()
            exchange = str(raw.get("exchange") or "").upper()
            asset_class = _asset_class(name, symbol, str(raw.get("asset_class") or ""))
            tradable = bool(raw.get("tradable"))
            is_ipo = "ipo" in {str(item).lower() for item in attrs}
            allowed_exchange = exchange not in {"OTC"}
            include = tradable and raw.get("status", "active") == "active" and allowed_exchange and asset_class in {"Stock", "ETF", "Special Situation"}
            exclusion = "" if include else "Not active/tradable on a primary listed venue."
            tier = _liquidity_tier(exchange, asset_class, symbol, existing_liquidity.get(symbol))
            _upsert_universe_asset(
                conn,
                {
                    "symbol": symbol,
                    "name": name,
                    "asset_class": asset_class,
                    "exchange": exchange,
                    "status": str(raw.get("status") or "active"),
                    "tradable": tradable,
                    "marginable": bool(raw.get("marginable")),
                    "shortable": bool(raw.get("shortable")),
                    "fractionable": bool(raw.get("fractionable")),
                    "attributes": attrs,
                    "is_ipo": is_ipo,
                    "source": "alpaca",
                    "included": include,
                    "exclusion_reason": exclusion,
                    "liquidity_tier": tier,
                },
            )
            if include:
                classification = classify_instrument(symbol, name, "ETF" if asset_class == "ETF" else "Stock", "")
                conn.execute(
                    """
                    INSERT INTO instruments (symbol, name, asset_class, sector, is_multi_asset, liquidity_score, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        name = excluded.name,
                        asset_class = excluded.asset_class,
                        sector = CASE
                            WHEN instruments.sector IN ('Imported', 'Imported Universe', 'Unknown', 'Unclassified', 'Unclassified ETF')
                            THEN excluded.sector
                            ELSE instruments.sector
                        END,
                        enabled = 1
                    """,
                    (
                        symbol,
                        name,
                        classification["asset_class"],
                        classification["sector"],
                        int(asset_class == "ETF"),
                        68 if tier == "candidate" else 88 if tier == "core" else 50,
                        1,
                    ),
                )
                included += 1
            if is_ipo:
                ipos += 1
            records += 1
        _record_rate_limit(conn, "alpaca", "ok", "Universe assets refreshed.")
        return {"provider": "alpaca", "status": "success", "records": records, "included": included, "ipos": ipos, "message": "All-US tradable universe metadata refreshed."}
    except httpx.HTTPStatusError as exc:
        status = "rate_limited" if exc.response.status_code == 429 else "failed"
        message = "Alpaca rate-limited universe refresh." if status == "rate_limited" else f"Alpaca universe refresh failed with HTTP {exc.response.status_code}."
        _record_rate_limit(conn, "alpaca", status, message)
        return {"provider": "alpaca", "status": status, "records": 0, "message": message}
    except Exception as exc:
        _record_rate_limit(conn, "alpaca", "failed", "Alpaca universe refresh failed.")
        return {"provider": "alpaca", "status": "failed", "records": 0, "message": "Alpaca universe refresh failed.", "error": str(exc)}


def _sync_sec_tickers(conn) -> dict[str, Any]:
    settings = effective_settings(conn)
    provider = SecEdgarProvider(settings)
    if not provider.status().configured:
        return {"provider": "sec_edgar", "status": "standby", "records": 0, "message": "Add SEC identity to map tickers to CIKs."}
    try:
        payload = _run_async(provider.company_tickers())
        records = 0
        matched = 0
        for item in payload.values():
            symbol = str(item.get("ticker") or "").strip().upper().replace("-", ".")
            cik = str(item.get("cik_str") or "").strip()
            title = str(item.get("title") or symbol).strip()
            if not symbol or not cik:
                continue
            current = conn.execute("SELECT symbol FROM universe_assets WHERE symbol = ?", (symbol,)).fetchone()
            if current:
                conn.execute("UPDATE universe_assets SET cik = ?, last_seen_at = ? WHERE symbol = ?", (cik, _now(), symbol))
                matched += 1
            else:
                _upsert_universe_asset(
                    conn,
                    {
                        "symbol": symbol,
                        "name": title,
                        "asset_class": "Stock",
                        "exchange": "sec",
                        "status": "active",
                        "tradable": False,
                        "attributes": [],
                        "is_ipo": False,
                        "cik": cik,
                        "source": "sec_edgar",
                        "included": False,
                        "exclusion_reason": "SEC filer exists, but Alpaca tradable status has not been confirmed.",
                        "liquidity_tier": "unconfirmed",
                    },
                )
            records += 1
        _record_rate_limit(conn, "sec_edgar", "ok", "SEC ticker-CIK map refreshed.")
        return {"provider": "sec_edgar", "status": "success", "records": records, "matched": matched, "message": "SEC ticker-CIK map refreshed."}
    except httpx.HTTPStatusError as exc:
        status = "rate_limited" if exc.response.status_code == 429 else "failed"
        message = "SEC EDGAR rate-limited ticker mapping." if status == "rate_limited" else f"SEC ticker mapping failed with HTTP {exc.response.status_code}."
        _record_rate_limit(conn, "sec_edgar", status, message)
        return {"provider": "sec_edgar", "status": status, "records": 0, "message": message}
    except Exception as exc:
        _record_rate_limit(conn, "sec_edgar", "failed", "SEC ticker mapping failed.")
        return {"provider": "sec_edgar", "status": "failed", "records": 0, "message": "SEC ticker mapping failed.", "error": str(exc)}


def refresh_universe(conn) -> dict[str, Any]:
    seed_count = _sync_seed_assets(conn)
    alpaca = _sync_alpaca_assets(conn)
    sec = _sync_sec_tickers(conn)
    status = universe_status(conn)
    return {
        "status": "ok" if alpaca["status"] in {"success", "standby"} and sec["status"] in {"success", "standby"} else "partial",
        "seed_assets": seed_count,
        "providers": [alpaca, sec],
        "universe": status,
    }


def priority_symbols(conn, limit: int) -> list[str]:
    holdings = [
        row["symbol"]
        for row in conn.execute(
            """
            SELECT DISTINCT symbol
            FROM positions
            ORDER BY symbol
            """
        ).fetchall()
    ]
    rows = conn.execute(
        """
        SELECT i.symbol
        FROM instruments i
        LEFT JOIN universe_assets ua ON ua.symbol = i.symbol
        WHERE i.enabled = 1
          AND COALESCE(ua.included, 1) = 1
          AND (i.liquidity_score >= 65 OR COALESCE(ua.liquidity_tier, '') IN ('core', 'candidate'))
        ORDER BY
          CASE WHEN i.symbol IN (SELECT DISTINCT symbol FROM positions) THEN 0 ELSE 1 END,
          CASE COALESCE(ua.liquidity_tier, '') WHEN 'core' THEN 0 WHEN 'candidate' THEN 1 ELSE 2 END,
          i.liquidity_score DESC,
          i.symbol
        LIMIT ?
        """,
        (max(limit, len(holdings), 1),),
    ).fetchall()
    combined = [*holdings, *[row["symbol"] for row in rows]]
    return list(dict.fromkeys(combined))[:limit]


def universe_status(conn) -> dict[str, Any]:
    existing = conn.execute("SELECT COUNT(*) AS count FROM universe_assets").fetchone()["count"]
    if not existing:
        _sync_seed_assets(conn)
    _sync_missing_instrument_assets(conn)
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_assets,
            SUM(CASE WHEN included = 1 THEN 1 ELSE 0 END) AS included_assets,
            SUM(CASE WHEN tradable = 1 THEN 1 ELSE 0 END) AS tradable_assets,
            SUM(CASE WHEN is_ipo = 1 THEN 1 ELSE 0 END) AS ipo_assets,
            SUM(CASE WHEN liquidity_tier IN ('long_tail', 'unconfirmed') THEN 1 ELSE 0 END) AS low_liquidity_or_unconfirmed
        FROM universe_assets
        """
    ).fetchone()
    asset_rows = conn.execute("SELECT asset_class, COUNT(*) AS count FROM universe_assets WHERE included = 1 GROUP BY asset_class").fetchall()
    source_rows = conn.execute("SELECT source, COUNT(*) AS count FROM universe_assets GROUP BY source").fetchall()
    sources = {item["source"]: item["count"] for item in source_rows}
    priced = conn.execute("SELECT COUNT(DISTINCT symbol) AS count FROM price_bars").fetchone()["count"]
    sec = conn.execute("SELECT COUNT(*) AS count FROM universe_assets WHERE cik != ''").fetchone()["count"]
    rate_rows = conn.execute("SELECT * FROM provider_rate_limits").fetchall()
    last_refresh = conn.execute("SELECT MAX(last_seen_at) AS last_seen_at FROM universe_assets").fetchone()["last_seen_at"]
    return {
        "total_assets": int(row["total_assets"] or 0),
        "included_assets": int(row["included_assets"] or 0),
        "tradable_assets": int(row["tradable_assets"] or 0),
        "priced_symbols": int(priced or 0),
        "sec_mapped_symbols": int(sec or 0),
        "ipo_assets": int(row["ipo_assets"] or 0),
        "low_liquidity_or_unconfirmed": int(row["low_liquidity_or_unconfirmed"] or 0),
        "asset_classes": {item["asset_class"]: item["count"] for item in asset_rows},
        "sources": sources,
        "rate_limits": {item["provider"]: dict(item) for item in rate_rows},
        "last_refresh": last_refresh,
        "scope_label": "All US tradable assets from Alpaca" if sources.get("alpaca") else "Seeded local universe until Alpaca assets are connected",
    }
