from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any


def pct_change(values: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(values, values[1:]):
        if previous:
            returns.append((current / previous) - 1)
    return returns


def annualized_return(closes: list[float]) -> float:
    if len(closes) < 2 or closes[0] <= 0:
        return 0.0
    years = max((len(closes) - 1) / 252, 1 / 252)
    return (closes[-1] / closes[0]) ** (1 / years) - 1


def annualized_volatility(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    return statistics.stdev(returns) * math.sqrt(252)


def max_drawdown(closes: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for close in closes:
        peak = max(peak, close)
        if peak:
            worst = min(worst, (close / peak) - 1)
    return abs(worst)


def momentum(closes: list[float], days: int) -> float:
    if len(closes) <= days or closes[-days] == 0:
        return 0.0
    return (closes[-1] / closes[-days]) - 1


def sharpe_ratio(returns: list[float], risk_free_rate: float = 0.04) -> float:
    vol = annualized_volatility(returns)
    if vol == 0:
        return 0.0
    avg = statistics.mean(returns) * 252
    return (avg - risk_free_rate) / vol


def trend_persistence(closes: list[float]) -> float:
    returns = pct_change(closes[-90:])
    if not returns:
        return 0.0
    positive_days = sum(1 for item in returns if item > 0) / len(returns)
    above_ma = 1.0 if closes[-1] > statistics.mean(closes[-120:]) else 0.0 if len(closes) >= 120 else 0.5
    return round((positive_days * 0.6 + above_ma * 0.4), 4)


def beta_to_benchmark(asset_returns: list[float], benchmark_returns: list[float]) -> float:
    paired = list(zip(asset_returns[-252:], benchmark_returns[-252:]))
    if len(paired) < 20:
        return 1.0
    a = [item[0] for item in paired]
    b = [item[1] for item in paired]
    b_var = statistics.variance(b) if len(set(b)) > 1 else 0
    if b_var == 0:
        return 1.0
    cov = sum((x - statistics.mean(a)) * (y - statistics.mean(b)) for x, y in paired) / (len(paired) - 1)
    return cov / b_var


def correlation_matrix(series: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    symbols = list(series)
    matrix: dict[str, dict[str, float]] = defaultdict(dict)
    for left in symbols:
        for right in symbols:
            left_returns = pct_change(series[left])[-252:]
            right_returns = pct_change(series[right])[-252:]
            paired = list(zip(left_returns, right_returns))
            if len(paired) < 3:
                corr = 0.0
            else:
                lx = [p[0] for p in paired]
                rx = [p[1] for p in paired]
                st_l = statistics.stdev(lx) if len(set(lx)) > 1 else 0
                st_r = statistics.stdev(rx) if len(set(rx)) > 1 else 0
                if st_l == 0 or st_r == 0:
                    corr = 0.0
                else:
                    corr = statistics.correlation(lx, rx)
            matrix[left][right] = round(corr, 3)
    return dict(matrix)


def instrument_score(features: dict[str, Any]) -> dict[str, float]:
    mom_6m = features.get("momentum_126d", 0.0)
    mom_3m = features.get("momentum_63d", 0.0)
    mom_12m = features.get("one_year_return", 0.0)
    vol = features.get("volatility", 0.0)
    dd = features.get("max_drawdown", 0.0)
    trend = features.get("trend_persistence", 0.0)
    liquidity = features.get("liquidity_score", 75) / 100
    quality = features.get("quality_score", 0.5)
    value_proxy = features.get("value_score", 0.5)
    low_vol = max(0.0, min(1.0, 1 - vol))
    drawdown_control = max(0.0, min(1.0, 1 - dd))
    cross_momentum = 0.65 * mom_6m + 0.35 * mom_3m
    time_series_momentum = 0.70 * mom_12m + 0.30 * trend
    expected_return = 0.34 * cross_momentum + 0.22 * time_series_momentum + 0.20 * quality + 0.12 * value_proxy + 0.12 * low_vol
    risk_penalty = 0.55 * vol + 0.35 * dd + 0.10 * max(0, 0.8 - liquidity)
    raw = expected_return - risk_penalty * 0.50 + drawdown_control * 0.04
    confidence = max(0.05, min(0.95, 0.48 + raw + liquidity * 0.12))
    risk_score = max(0.01, min(1.0, 0.55 * vol + 0.35 * dd + 0.10 * (1 - liquidity)))
    return {
        "score": round(raw, 4),
        "expected_return": round(expected_return, 4),
        "confidence": round(confidence, 4),
        "risk_score": round(risk_score, 4),
        "cross_section_momentum": round(cross_momentum, 4),
        "time_series_momentum": round(time_series_momentum, 4),
        "low_volatility_score": round(low_vol, 4),
        "drawdown_control_score": round(drawdown_control, 4),
    }


def quality_score(fundamentals: dict[str, float]) -> float:
    if not fundamentals:
        return 0.50
    revenue_growth = fundamentals.get("revenue_growth", 0.06)
    gross_margin = fundamentals.get("gross_margin", 0.35)
    fcf_yield = fundamentals.get("free_cash_flow_yield", 0.02)
    debt = fundamentals.get("debt_to_equity", 0.7)
    score = (
        min(max(revenue_growth, -0.2), 0.8) * 0.40
        + min(max(gross_margin, 0), 0.85) * 0.25
        + min(max(fcf_yield, -0.05), 0.08) * 2.0
        + max(0, 1.2 - debt) * 0.12
    )
    return max(0.0, min(1.0, score))


def portfolio_stress(total_value: float, positions: list[dict[str, Any]], rules: dict[str, Any]) -> dict[str, Any]:
    if total_value <= 0:
        return {"level": "unknown", "warnings": ["No portfolio value available."], "concentration": 0, "sector_weights": {}, "unknown_sector_weight": 0}
    warnings: list[str] = []
    concentration = 0.0
    sector_weights: dict[str, float] = defaultdict(float)
    unknown_sector_weight = 0.0
    for position in positions:
        weight = position.get("weight", 0.0)
        concentration += weight * weight
        sector = position.get("sector", "Unknown") or "Unknown"
        sector_weights[sector] += weight
        if sector in {"Unknown", "Unclassified ETF"}:
            unknown_sector_weight += weight
        asset_class = position.get("asset_class", "Stock")
        if asset_class == "Stock" and weight > rules["max_single_stock_weight"]:
            warnings.append(f"{position['symbol']} exceeds max single-stock weight.")
        if asset_class == "ETF" and weight > rules["max_etf_weight"]:
            warnings.append(f"{position['symbol']} exceeds max ETF weight.")
    for sector, weight in sector_weights.items():
        if sector in {"Unknown", "Unclassified ETF"}:
            continue
        if weight > rules["max_sector_weight"]:
            warnings.append(f"{sector} exposure is above the configured sector cap.")
    if unknown_sector_weight > 0:
        warnings.append("Some holdings still need sector metadata; Signal is using an Unknown bucket instead of guessing.")
    herfindahl = round(concentration, 4)
    level = "calm"
    if warnings or herfindahl > 0.18:
        level = "watch"
    if len(warnings) >= 3 or herfindahl > 0.28:
        level = "elevated"
    return {
        "level": level,
        "warnings": warnings,
        "concentration": herfindahl,
        "sector_weights": dict(sector_weights),
        "unknown_sector_weight": round(unknown_sector_weight, 4),
    }


def macro_regime(points: list[dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, float] = {}
    history: dict[str, list[float]] = defaultdict(list)
    for point in points:
        latest[point["series_id"]] = point["value"]
        history[point["series_id"]].append(point["value"])

    inflation = latest.get("CPI_YOY", 3.0)
    policy = latest.get("FEDFUNDS", 4.5)
    unemployment = latest.get("UNRATE", 4.0)
    ten_year = latest.get("DGS10", 4.0)
    inflation_trend = inflation - (history["CPI_YOY"][-60] if len(history["CPI_YOY"]) > 60 else inflation)
    growth_stress = unemployment > 4.7 or (history["UNRATE"] and unemployment - min(history["UNRATE"][-120:]) > 0.55)

    if growth_stress:
        label = "defensive slowdown"
        risk_bias = "cut cyclicals, raise quality and duration hedges"
        score = 0.38
    elif inflation > 3.4 and inflation_trend > 0:
        label = "inflation pressure"
        risk_bias = "prefer pricing power, energy, cash discipline"
        score = 0.46
    elif policy > ten_year + 0.35:
        label = "restrictive but easing watch"
        risk_bias = "barbell quality growth with duration hedge"
        score = 0.58
    else:
        label = "risk-on expansion"
        risk_bias = "lean into diversified growth while monitoring drawdown"
        score = 0.68

    return {
        "label": label,
        "risk_bias": risk_bias,
        "score": round(score, 2),
        "latest": {key: round(value, 3) for key, value in latest.items()},
        "inflation_trend_60d": round(inflation_trend, 3),
    }


def equity_curve_metrics(curve: list[dict[str, float]]) -> dict[str, float]:
    values = [point["value"] for point in curve]
    returns = pct_change(values)
    return {
        "total_return": round((values[-1] / values[0]) - 1, 4) if len(values) > 1 and values[0] else 0.0,
        "annualized_return": round(annualized_return(values), 4),
        "annualized_volatility": round(annualized_volatility(returns), 4),
        "max_drawdown": round(max_drawdown(values), 4),
        "sharpe": round(sharpe_ratio(returns), 4),
    }
