from __future__ import annotations

import csv
import io
from typing import Any

from app.database import get_risk_rules
from app.services.analytics import portfolio_stress
from app.services.classification import classify_instrument
from app.services.data_service import latest_prices


def get_default_portfolio_id(conn, mode: str = "paper") -> int:
    row = conn.execute("SELECT id FROM portfolios WHERE mode = ? ORDER BY id LIMIT 1", (mode,)).fetchone()
    if row:
        return row["id"]
    if mode == "real":
        legacy = conn.execute("SELECT id FROM portfolios WHERE mode = 'watchlist' ORDER BY id LIMIT 1").fetchone()
        if legacy:
            conn.execute(
                "UPDATE portfolios SET mode = 'real', name = 'Real Money Portfolio' WHERE id = ?",
                (legacy["id"],),
            )
            return legacy["id"]
    cash = 100000.0 if mode == "paper" else 0.0
    name_by_mode = {
        "paper": "Paper Strategy Sandbox",
        "real": "Real Money Portfolio",
        "watchlist": "Imported Holdings Watchlist",
    }
    cursor = conn.execute(
        "INSERT INTO portfolios (name, mode, base_currency, cash) VALUES (?, ?, ?, ?)",
        (name_by_mode.get(mode, "Portfolio"), mode, "USD", cash),
    )
    return int(cursor.lastrowid)


def portfolio_summary(conn, portfolio_id: int | None = None, mode: str = "paper") -> dict[str, Any]:
    if portfolio_id is None:
        portfolio_id = get_default_portfolio_id(conn, mode)
    portfolio = conn.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()
    prices = latest_prices(conn)
    rows = conn.execute(
        """
        SELECT p.*, i.name, i.asset_class, i.sector
        FROM positions p
        JOIN instruments i ON p.symbol = i.symbol
        WHERE p.portfolio_id = ?
        ORDER BY p.symbol
        """,
        (portfolio_id,),
    ).fetchall()
    market_value = 0.0
    positions: list[dict[str, Any]] = []
    for row in rows:
        has_market_price = row["symbol"] in prices and prices[row["symbol"]] > 0
        if has_market_price:
            price = prices[row["symbol"]]
            valuation_status = "priced"
            valuation_note = "Using latest local market price."
        elif row["avg_cost"] > 0:
            price = row["avg_cost"]
            valuation_status = "proxy"
            valuation_note = "Using imported average cost until market data is available."
        else:
            price = 0.0
            valuation_status = "missing_price"
            valuation_note = "No local price or average cost is available yet."
        value = row["quantity"] * price
        market_value += value
        gain_loss = value - row["quantity"] * row["avg_cost"]
        classification = classify_instrument(row["symbol"], row["name"], row["asset_class"], row["sector"])
        positions.append(
            {
                **row,
                "asset_class": classification["asset_class"],
                "sector": classification["sector"],
                "theme": classification["theme"],
                "metadata_source": classification["metadata_source"],
                "metadata_confidence": classification["metadata_confidence"],
                "latest_price": price,
                "valuation_status": valuation_status,
                "valuation_note": valuation_note,
                "market_value": round(value, 2),
                "gain_loss": round(gain_loss, 2),
                "gain_loss_pct": round(gain_loss / (row["quantity"] * row["avg_cost"]), 4)
                if row["quantity"] * row["avg_cost"]
                else 0,
            }
        )
    total_value = portfolio["cash"] + market_value
    for position in positions:
        position["weight"] = round(position["market_value"] / total_value, 4) if total_value else 0
    return {
        "id": portfolio["id"],
        "name": portfolio["name"],
        "mode": portfolio["mode"],
        "base_currency": portfolio["base_currency"],
        "cash": round(portfolio["cash"], 2),
        "market_value": round(market_value, 2),
        "total_value": round(total_value, 2),
        "positions": positions,
        "stress": portfolio_stress(total_value, positions, get_risk_rules(conn)),
    }


def execute_paper_order(conn, payload) -> dict[str, Any]:
    portfolio_id = get_default_portfolio_id(conn, "paper")
    portfolio = conn.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()
    symbol = payload.symbol
    instrument = conn.execute("SELECT * FROM instruments WHERE symbol = ?", (symbol,)).fetchone()
    if not instrument:
        raise ValueError(f"{symbol} is not in the configured universe.")
    prices = latest_prices(conn)
    price = payload.price or prices.get(symbol)
    if not price:
        raise ValueError(f"No price available for {symbol}.")
    notional = payload.quantity * price
    position = conn.execute(
        "SELECT * FROM positions WHERE portfolio_id = ? AND symbol = ?",
        (portfolio_id, symbol),
    ).fetchone()

    if payload.side == "buy":
        if notional > portfolio["cash"]:
            raise ValueError("Insufficient paper cash for this order.")
        new_cash = portfolio["cash"] - notional
        if position:
            total_qty = position["quantity"] + payload.quantity
            avg_cost = ((position["quantity"] * position["avg_cost"]) + notional) / total_qty
            conn.execute(
                "UPDATE positions SET quantity = ?, avg_cost = ? WHERE id = ?",
                (total_qty, avg_cost, position["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO positions (portfolio_id, symbol, quantity, avg_cost, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (portfolio_id, symbol, payload.quantity, price, "paper"),
            )
    else:
        if not position or position["quantity"] < payload.quantity:
            raise ValueError("Paper portfolio does not hold enough shares to sell.")
        new_cash = portfolio["cash"] + notional
        remaining = position["quantity"] - payload.quantity
        if remaining:
            conn.execute("UPDATE positions SET quantity = ? WHERE id = ?", (remaining, position["id"]))
        else:
            conn.execute("DELETE FROM positions WHERE id = ?", (position["id"],))

    conn.execute("UPDATE portfolios SET cash = ? WHERE id = ?", (new_cash, portfolio_id))
    conn.execute(
        """
        INSERT INTO transactions (portfolio_id, symbol, side, quantity, price, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (portfolio_id, symbol, payload.side, payload.quantity, price, payload.notes),
    )
    return portfolio_summary(conn, portfolio_id)


def _row_value(row: dict[str, str], names: list[str]) -> str:
    normalized = {key.strip().lower().replace(" ", "_"): value for key, value in row.items() if key is not None}
    for name in names:
        value = normalized.get(name)
        if value not in (None, ""):
            return str(value).replace("$", "").replace(",", "").strip()
    return ""


def _clean_numeric(value: Any) -> str:
    return str(value or "").replace("$", "").replace(",", "").replace("%", "").strip()


def _float_or_zero(value: str) -> float:
    cleaned = _clean_numeric(value)
    if cleaned in ("", "-", "--"):
        return 0.0
    return float(cleaned)


def _normalized_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _has_header(rows: list[list[str]]) -> bool:
    if not rows:
        return False
    normalized = {_normalized_header(item) for item in rows[0]}
    known = {
        "symbol",
        "ticker",
        "security",
        "holding",
        "instrument",
        "quantity",
        "shares",
        "qty",
        "units",
        "avg_cost",
        "average_cost",
        "cost_basis",
        "cost_basis_per_share",
        "price_paid",
        "unit_cost",
        "market_value",
        "current_value",
        "value",
    }
    return bool(normalized & known)


def _holding_rows(text: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    raw_rows = [row for row in csv.reader(io.StringIO(text)) if any(str(cell).strip() for cell in row)]
    if not raw_rows:
        raise ValueError("No holdings were found. Include symbol and shares.")
    if _has_header(raw_rows):
        reader = csv.DictReader(io.StringIO(text))
        return list(reader), {"symbol": "detected", "quantity": "detected", "avg_cost": "detected"}

    rows: list[dict[str, str]] = []
    for row in raw_rows:
        padded = [*row, "", "", ""]
        rows.append(
            {
                "symbol": padded[0],
                "quantity": padded[1],
                "avg_cost": padded[2],
            }
        )
    return rows, {"symbol": "column_1", "quantity": "column_2", "avg_cost": "column_3"}


def import_holdings_csv(conn, content: bytes) -> dict[str, Any]:
    portfolio_id = get_default_portfolio_id(conn, "real")
    text = content.decode("utf-8-sig")
    imported: list[dict[str, Any]] = []
    warnings: list[str] = []
    rejected_rows: list[dict[str, Any]] = []
    rows, detected_columns = _holding_rows(text)
    prices = latest_prices(conn)
    for index, row in enumerate(rows, start=1):
        symbol = _row_value(row, ["symbol", "ticker", "security", "holding", "instrument"]).upper()
        if not symbol:
            rejected_rows.append({"row": index, "reason": "Missing symbol."})
            continue
        try:
            quantity = _float_or_zero(_row_value(row, ["quantity", "shares", "qty", "units"]))
            avg_cost = _float_or_zero(
                _row_value(row, ["avg_cost", "average_cost", "cost_basis", "cost_basis_per_share", "price_paid", "unit_cost"])
            )
            market_value = _float_or_zero(_row_value(row, ["market_value", "current_value", "value"]))
        except ValueError:
            rejected_rows.append({"row": index, "symbol": symbol, "reason": "Shares, cost, or market value is not a valid number."})
            continue
        name = _row_value(row, ["name", "description", "instrument_name"]) or symbol

        if symbol in {"CASH", "USD", "CORE", "MONEYMARKET", "MONEY_MARKET"}:
            conn.execute("UPDATE portfolios SET cash = cash + ? WHERE id = ?", (market_value or quantity, portfolio_id))
            imported.append({"symbol": "CASH", "quantity": 1, "avg_cost": market_value or quantity})
            continue

        if quantity <= 0 and market_value > 0:
            price = prices.get(symbol)
            if price:
                quantity = market_value / price
        if quantity <= 0:
            rejected_rows.append({"row": index, "symbol": symbol, "reason": "Missing positive shares/quantity."})
            continue
        if avg_cost <= 0:
            avg_cost = market_value / quantity if market_value > 0 else prices.get(symbol, 0)
        if avg_cost <= 0:
            warnings.append(f"{symbol} imported, but valuation will stay missing until market data is refreshed.")

        exists = conn.execute("SELECT symbol FROM instruments WHERE symbol = ?", (symbol,)).fetchone()
        classification = classify_instrument(symbol, name, "Stock", "")
        if not exists:
            conn.execute(
                """
                INSERT INTO instruments (symbol, name, asset_class, sector, is_multi_asset, liquidity_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    name,
                    classification["asset_class"],
                    classification["sector"],
                    int(classification["asset_class"] == "ETF"),
                    60,
                ),
            )
        conn.execute(
            """
            INSERT INTO universe_assets
            (symbol, name, asset_class, exchange, status, tradable, fractionable, attributes, source,
             included, exclusion_reason, liquidity_tier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = CASE WHEN universe_assets.source = 'sample' THEN excluded.name ELSE universe_assets.name END,
                asset_class = CASE WHEN universe_assets.source IN ('sample', 'imported') THEN excluded.asset_class ELSE universe_assets.asset_class END,
                included = 1,
                liquidity_tier = CASE WHEN universe_assets.liquidity_tier = 'unknown' THEN 'current_holding' ELSE universe_assets.liquidity_tier END
            """,
            (symbol, name, classification["asset_class"], "imported", "active", 1, 1, "[]", "imported", 1, "", "current_holding"),
        )
        conn.execute(
            """
            INSERT INTO positions (portfolio_id, symbol, quantity, avg_cost, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(portfolio_id, symbol) DO UPDATE SET
                quantity = excluded.quantity,
                avg_cost = excluded.avg_cost,
                source = excluded.source
            """,
            (portfolio_id, symbol, quantity, avg_cost, "csv"),
        )
        imported.append({"symbol": symbol, "quantity": quantity, "avg_cost": avg_cost})
    if not imported:
        detail = rejected_rows[0]["reason"] if rejected_rows else "Include symbol and quantity/shares columns."
        raise ValueError(f"No holdings were found. {detail}")
    return {
        "status": "partial" if warnings or rejected_rows else "success",
        "imported": imported,
        "portfolio": portfolio_summary(conn, portfolio_id, "real"),
        "detected_columns": detected_columns,
        "warnings": warnings,
        "rejected_rows": rejected_rows,
    }
