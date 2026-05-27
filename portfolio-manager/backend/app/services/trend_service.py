from __future__ import annotations

from datetime import date
from typing import Any

from app.services.data_service import load_price_series
from app.services.portfolio_service import portfolio_summary


def _pct_change(current: float, previous: float) -> float:
    return round((current / previous) - 1, 4) if previous else 0.0


def _change_label(latest_day: str, previous_day: str) -> str:
    try:
        latest = date.fromisoformat(latest_day)
        previous = date.fromisoformat(previous_day)
    except ValueError:
        return "latest move"
    gap = (latest - previous).days
    if gap <= 3:
        return "today"
    return f"since {previous.strftime('%b %-d')}"


def portfolio_trend(conn, mode: str = "real", days: int = 90) -> dict[str, Any]:
    portfolio = portfolio_summary(conn, mode=mode)
    positions = portfolio.get("positions", [])
    if not positions:
        return {
            "granularity": "daily",
            "intraday_available": False,
            "points": [],
            "day_change": 0,
            "day_change_pct": 0,
            "week_change": 0,
            "week_change_pct": 0,
            "month_change": 0,
            "month_change_pct": 0,
            "latest_change_label": "today",
            "comparison_date": None,
            "as_of_date": None,
            "source_note": "Import holdings to build a portfolio trend.",
            "position_changes": [],
        }

    quantities = {position["symbol"]: float(position["quantity"]) for position in positions}
    proxy_prices = {
        position["symbol"]: float(position["avg_cost"])
        for position in positions
        if float(position.get("avg_cost") or 0) > 0
    }
    raw_series = load_price_series(conn, list(quantities))
    mixed_source_history = False
    series: dict[str, list[dict[str, Any]]] = {}
    for symbol, symbol_points in raw_series.items():
        live_points = [point for point in symbol_points if point.get("source") != "sample"]
        if live_points:
            mixed_source_history = mixed_source_history or len(live_points) < len(symbol_points)
            series[symbol] = live_points
        else:
            series[symbol] = symbol_points
    dates = sorted({point["date"][:10] for points in series.values() for point in points})[-days:]
    last_prices: dict[str, float] = dict(proxy_prices)
    daily_prices: dict[str, dict[str, float]] = {symbol: {} for symbol in quantities}
    points: list[dict[str, Any]] = []
    for day in dates:
        for symbol, points_for_symbol in series.items():
            matches = [point for point in points_for_symbol if point["date"][:10] == day]
            if matches:
                last_prices[symbol] = float(matches[-1]["close"])
            if symbol in last_prices:
                daily_prices[symbol][day] = last_prices[symbol]
        if not last_prices:
            continue
        value = portfolio["cash"] + sum(quantities[symbol] * last_prices.get(symbol, 0) for symbol in quantities)
        points.append({"date": day, "value": round(value, 2)})

    if not points:
        return {
            "granularity": "daily",
            "intraday_available": False,
            "points": [],
            "day_change": 0,
            "day_change_pct": 0,
            "week_change": 0,
            "week_change_pct": 0,
            "month_change": 0,
            "month_change_pct": 0,
            "latest_change_label": "today",
            "comparison_date": None,
            "as_of_date": None,
            "source_note": "No historical price bars are available for the imported holdings yet.",
            "position_changes": [],
        }

    latest = points[-1]["value"]
    previous_day_value = points[-2]["value"] if len(points) >= 2 else latest
    previous_week_value = points[-6]["value"] if len(points) >= 6 else points[0]["value"]
    previous_month_value = points[-22]["value"] if len(points) >= 22 else points[0]["value"]
    latest_day = points[-1]["date"]
    previous_day_date = points[-2]["date"] if len(points) >= 2 else latest_day
    latest_change_label = _change_label(latest_day, previous_day_date)
    position_changes = []
    for position in positions:
        symbol = position["symbol"]
        latest_price = daily_prices.get(symbol, {}).get(latest_day)
        previous_price = daily_prices.get(symbol, {}).get(previous_day_date)
        if latest_price is None or previous_price is None:
            continue
        quantity = quantities[symbol]
        symbol_series = series.get(symbol, [])
        position_changes.append(
            {
                "symbol": symbol,
                "day_change": round((latest_price - previous_price) * quantity, 2),
                "day_change_pct": _pct_change(latest_price, previous_price),
                "latest_price": latest_price,
                "source": symbol_series[-1].get("source", "unknown"),
            }
        )
    position_changes.sort(key=lambda item: abs(item["day_change"]), reverse=True)
    live_sources = {item["source"] for item in position_changes if item["source"] != "sample"}
    uses_proxy_prices = bool(proxy_prices) and any(
        not series.get(symbol)
        or (dates and min(point["date"][:10] for point in series[symbol]) > dates[0])
        for symbol in quantities
    )
    if len(points) < 2 and live_sources:
        source_note = (
            "Current value uses latest provider snapshots. Daily and hourly trend lines need at least two consistent live history points."
        )
    elif mixed_source_history or uses_proxy_prices:
        source_note = (
            "Daily portfolio trend avoids mixing sample history with live provider snapshots; imported cost basis fills gaps when needed."
        )
    elif live_sources:
        source_note = (
            "Daily portfolio trend from local price bars. Hourly trends need an intraday history provider; current live mode uses latest snapshots."
        )
    else:
        source_note = "Daily portfolio trend from local sample/history bars until live intraday history is connected."
    return {
        "granularity": "daily",
        "intraday_available": False,
        "points": points,
        "day_change": round(latest - previous_day_value, 2),
        "day_change_pct": _pct_change(latest, previous_day_value),
        "week_change": round(latest - previous_week_value, 2),
        "week_change_pct": _pct_change(latest, previous_week_value),
        "month_change": round(latest - previous_month_value, 2),
        "month_change_pct": _pct_change(latest, previous_month_value),
        "latest_change_label": latest_change_label,
        "comparison_date": previous_day_date,
        "as_of_date": latest_day,
        "source_note": source_note,
        "position_changes": position_changes[:8],
    }
