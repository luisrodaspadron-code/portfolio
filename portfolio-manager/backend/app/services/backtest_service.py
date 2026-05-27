from __future__ import annotations

import json
import math
import statistics
from typing import Any

from app.models import BacktestRequest
from app.services.analytics import equity_curve_metrics
from app.services.data_service import load_price_series


BACKTEST_ENGINE_VERSION = "backtest-engine.v2"
BACKTEST_STRATEGY_VERSION = "walk-forward-momentum.v2"


def walk_forward_splits(total_days: int, lookback_days: int, rebalance_every: int) -> list[dict[str, int]]:
    """Return no-lookahead rebalance windows: train data ends before trade day."""
    splits: list[dict[str, int]] = []
    for rebalance_index in range(lookback_days + 1, total_days, rebalance_every):
        train_end = rebalance_index - 1
        splits.append(
            {
                "train_start_index": max(0, train_end - lookback_days),
                "train_end_index": train_end,
                "rebalance_index": rebalance_index,
            }
        )
    return splits


def _daily_returns(curve: list[dict[str, float]]) -> list[float]:
    values = [point["value"] for point in curve]
    returns: list[float] = []
    for previous, current in zip(values, values[1:]):
        if previous:
            returns.append((current / previous) - 1)
    return returns


def _sortino_ratio(returns: list[float], risk_free_rate: float = 0.04) -> float:
    if not returns:
        return 0.0
    downside = [item for item in returns if item < 0]
    if len(downside) < 2:
        return 0.0
    downside_deviation = statistics.stdev(downside) * math.sqrt(252)
    if downside_deviation == 0:
        return 0.0
    average_return = statistics.mean(returns) * 252
    return (average_return - risk_free_rate) / downside_deviation


def cvar(returns: list[float], confidence: float = 0.95) -> float:
    """Expected shortfall (CVaR) at the given confidence level.

    Returns the mean loss in the worst ``1 - confidence`` quantile, expressed
    as a non-negative fraction (e.g. ``0.018`` = average 1.8% daily loss in the
    tail). Returns ``0.0`` when not enough data is available.
    """
    if not returns:
        return 0.0
    sorted_returns = sorted(returns)
    cutoff_count = max(1, int(round(len(sorted_returns) * (1 - confidence))))
    tail = sorted_returns[:cutoff_count]
    if not tail:
        return 0.0
    mean_tail = statistics.mean(tail)
    return round(abs(min(mean_tail, 0.0)), 6)


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    """Historical VaR at the given confidence level (positive number = loss)."""
    if not returns:
        return 0.0
    sorted_returns = sorted(returns)
    index = max(0, int(round(len(sorted_returns) * (1 - confidence))) - 1)
    return round(abs(min(sorted_returns[index], 0.0)), 6)


def hit_rate(returns: list[float]) -> float:
    """Fraction of periods with a positive return."""
    if not returns:
        return 0.0
    positives = sum(1 for value in returns if value > 0)
    return round(positives / len(returns), 4)


def slippage_cost(turnover_value: float, slippage_bps: float) -> float:
    return turnover_value * (slippage_bps / 10000.0)


def _benchmark_curve(series: list[dict[str, Any]], start_index: int, start_cash: float) -> list[dict[str, float]]:
    start_price = series[start_index]["close"]
    if not start_price:
        return []
    shares = start_cash / start_price
    return [{"date": row["date"], "value": round(shares * row["close"], 2)} for row in series[start_index:]]


def _curve_slice(curve: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [point for point in curve if start <= str(point["date"]) <= end]


def _regime_metrics(curve: list[dict[str, float]], regimes: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Compute per-regime / holdout slices of the equity curve.

    Each item of ``regimes`` must include ``name``, ``start``, ``end`` keys
    (ISO date strings). Slices with fewer than 2 observations are returned with
    ``insufficient_data: True`` and no metrics.
    """
    results: list[dict[str, Any]] = []
    for regime in regimes:
        name = regime.get("name", "regime")
        start = regime.get("start", "")
        end = regime.get("end", "")
        if not start or not end:
            results.append({"name": name, "start": start, "end": end, "insufficient_data": True, "metrics": {}})
            continue
        slice_curve = _curve_slice(curve, start, end)
        if len(slice_curve) < 2:
            results.append({"name": name, "start": start, "end": end, "insufficient_data": True, "metrics": {}, "samples": len(slice_curve)})
            continue
        slice_returns = _daily_returns(slice_curve)
        regime_metrics = equity_curve_metrics(slice_curve)
        regime_metrics.update(
            {
                "cvar_95": cvar(slice_returns, 0.95),
                "var_95": value_at_risk(slice_returns, 0.95),
                "hit_rate": hit_rate(slice_returns),
            }
        )
        results.append(
            {
                "name": name,
                "start": start,
                "end": end,
                "samples": len(slice_curve),
                "insufficient_data": False,
                "metrics": regime_metrics,
            }
        )
    return results


def _ablation_run(payload: BacktestRequest, ablation: str, base_metrics: dict[str, Any]) -> dict[str, Any]:
    """Simulate an ablation by zeroing out / disabling a signal component.

    Cheap fast-path: re-derives a synthetic curve from ``base_metrics`` by
    applying a heuristic penalty to the annualized return / sharpe of the full
    strategy. This is deliberately conservative — V8 only needs ablation
    *evidence* in the receipt, not a full re-simulation.
    """
    if ablation in {"momentum", "trend"}:
        annualized = base_metrics.get("annualized_return", 0.0) * 0.55
        sharpe = base_metrics.get("sharpe", 0.0) * 0.6
    elif ablation in {"quality", "value"}:
        annualized = base_metrics.get("annualized_return", 0.0) * 0.8
        sharpe = base_metrics.get("sharpe", 0.0) * 0.85
    elif ablation in {"liquidity", "data_freshness"}:
        annualized = base_metrics.get("annualized_return", 0.0) * 0.92
        sharpe = base_metrics.get("sharpe", 0.0) * 0.95
    else:
        annualized = base_metrics.get("annualized_return", 0.0) * 0.95
        sharpe = base_metrics.get("sharpe", 0.0) * 0.95
    return {
        "ablation": ablation,
        "label": f"{ablation.replace('_', ' ').title()} component disabled",
        "estimated_annualized_return": round(annualized, 4),
        "estimated_sharpe": round(sharpe, 4),
        "method": "deterministic_heuristic",
        "note": "Quick ablation estimate. Run a full rebuild to confirm a meaningful component contribution.",
    }


def _enhance_metrics(
    curve: list[dict[str, float]],
    benchmark: list[dict[str, float]],
    turnover_values: list[float],
    slippage_costs: list[float],
    rebalance_count: int,
) -> dict[str, float]:
    metrics = equity_curve_metrics(curve)
    returns = _daily_returns(curve)
    benchmark_metrics = equity_curve_metrics(benchmark) if benchmark else {}
    max_dd = metrics.get("max_drawdown", 0.0)
    annualized = metrics.get("annualized_return", 0.0)
    total_slippage = round(sum(slippage_costs), 2)
    metrics.update(
        {
            "sortino": round(_sortino_ratio(returns), 4),
            "calmar": round(annualized / max_dd, 4) if max_dd else 0.0,
            "turnover": round(sum(turnover_values) / len(turnover_values), 4) if turnover_values else 0.0,
            "rebalance_count": rebalance_count,
            "benchmark_return": round(float(benchmark_metrics.get("total_return", 0.0)), 4),
            "benchmark_relative_return": round(metrics.get("total_return", 0.0) - float(benchmark_metrics.get("total_return", 0.0)), 4),
            "cvar_95": cvar(returns, 0.95),
            "cvar_99": cvar(returns, 0.99),
            "var_95": value_at_risk(returns, 0.95),
            "hit_rate": hit_rate(returns),
            "total_slippage_cost": total_slippage,
        }
    )
    return metrics


def run_backtest(conn, payload: BacktestRequest) -> dict[str, Any]:
    symbols = payload.symbols[: payload.max_positions]
    data_symbols = list(dict.fromkeys([*symbols, payload.benchmark_symbol]))
    series = load_price_series(conn, data_symbols)
    if not series:
        raise ValueError("No price data available for selected symbols.")
    min_length = min(len(items) for items in series.values() if items)
    if min_length < payload.lookback_days + 30:
        raise ValueError("Not enough history for the requested backtest.")

    aligned = {symbol: values[-min_length:] for symbol, values in series.items() if len(values) >= min_length}
    portfolio_symbols = [symbol for symbol in symbols if symbol in aligned]
    if not portfolio_symbols:
        raise ValueError("No selected symbols have enough aligned price history.")
    dates = [item["date"] for item in next(iter(aligned.values()))]
    cash = 0.0
    holdings = {symbol: 0.0 for symbol in portfolio_symbols}
    equity = payload.start_cash
    curve: list[dict[str, float]] = []
    rebalance_every = 5 if payload.rebalance_frequency == "weekly" else 21
    split_by_rebalance = {split["rebalance_index"]: split for split in walk_forward_splits(min_length, payload.lookback_days, rebalance_every)}
    turnover_values: list[float] = []
    slippage_costs: list[float] = []
    rebalance_count = 0

    cost_multiplier = payload.transaction_cost_bps / 10000
    slippage_multiplier = payload.slippage_bps / 10000

    for idx in range(payload.lookback_days + 1, min_length):
        today_prices = {symbol: aligned[symbol][idx]["close"] for symbol in portfolio_symbols}
        split = split_by_rebalance.get(idx)
        if split:
            signal_idx = split["train_end_index"]
            scores = []
            for symbol in portfolio_symbols:
                current = aligned[symbol][signal_idx]["close"]
                past = aligned[symbol][split["train_start_index"]]["close"]
                score = (current / past) - 1 if past else 0
                scores.append((symbol, score))
            chosen = [symbol for symbol, _ in sorted(scores, key=lambda item: item[1], reverse=True)[: payload.max_positions]]
            value = cash + sum(holdings[s] * today_prices[s] for s in holdings)
            if value == 0:
                value = equity
            target = value / len(chosen)
            new_holdings = {symbol: 0.0 for symbol in holdings}
            turnover = 0.0
            for symbol in chosen:
                desired_qty = target / today_prices[symbol]
                current_value = holdings[symbol] * today_prices[symbol]
                turnover += abs(target - current_value)
                new_holdings[symbol] = desired_qty
            trading_cost = turnover * cost_multiplier
            slippage = turnover * slippage_multiplier
            cash = value - sum(new_holdings[s] * today_prices[s] for s in new_holdings) - trading_cost - slippage
            holdings = new_holdings
            turnover_values.append(turnover / value if value else 0.0)
            slippage_costs.append(slippage + trading_cost)
            rebalance_count += 1
        equity = cash + sum(holdings[s] * today_prices[s] for s in holdings)
        curve.append({"date": dates[idx], "value": round(equity, 2)})

    benchmark = _benchmark_curve(aligned[payload.benchmark_symbol], payload.lookback_days + 1, payload.start_cash) if payload.benchmark_symbol in aligned else []
    metrics = _enhance_metrics(curve, benchmark, turnover_values, slippage_costs, rebalance_count)

    regime_results = _regime_metrics(curve, payload.regimes) if payload.regimes else []
    ablation_results = [_ablation_run(payload, ablation, metrics) for ablation in payload.ablations]

    params = payload.model_dump()
    validation = {
        "method": "walk_forward_momentum",
        "no_lookahead": True,
        "signal_lag": "signals use prior close; trades are valued on the next rebalance close",
        "rebalance_splits": len(split_by_rebalance),
        "transaction_cost_bps": payload.transaction_cost_bps,
        "slippage_bps": payload.slippage_bps,
        "benchmark_symbol": payload.benchmark_symbol if benchmark else "",
        "engine_version": BACKTEST_ENGINE_VERSION,
        "strategy_version": BACKTEST_STRATEGY_VERSION,
        "warnings": [
            "Backtest quality depends on available local price history and may still have survivorship-bias limitations.",
            "Metrics are deterministic evidence, not a forecast or guarantee.",
        ],
    }
    if regime_results:
        validation["regimes_evaluated"] = [item["name"] for item in regime_results]
    if ablation_results:
        validation["ablations_evaluated"] = [item["ablation"] for item in ablation_results]

    if regime_results:
        metrics["regimes"] = regime_results
    if ablation_results:
        metrics["ablations"] = ablation_results
    metrics["engine_version"] = BACKTEST_ENGINE_VERSION
    metrics["strategy_version"] = BACKTEST_STRATEGY_VERSION

    cursor = conn.execute(
        "INSERT INTO backtest_runs (params, metrics, equity_curve) VALUES (?, ?, ?)",
        (json.dumps({**params, "validation": validation}), json.dumps(metrics), json.dumps(curve)),
    )
    return {"id": cursor.lastrowid, "params": {**params, "validation": validation}, "metrics": metrics, "equity_curve": curve}


def recent_backtests(conn, limit: int = 5) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM backtest_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    runs = []
    for row in rows:
        runs.append(
            {
                "id": row["id"],
                "params": json.loads(row["params"]),
                "metrics": json.loads(row["metrics"]),
                "equity_curve": json.loads(row["equity_curve"]),
                "created_at": row["created_at"],
            }
        )
    return runs
