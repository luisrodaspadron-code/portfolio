from __future__ import annotations

import math

import pytest

from app.database import get_conn, init_db
from app.models import BacktestRequest
from app.services.backtest_service import (
    BACKTEST_ENGINE_VERSION,
    BACKTEST_STRATEGY_VERSION,
    _ablation_run,
    _regime_metrics,
    cvar,
    hit_rate,
    run_backtest,
    slippage_cost,
    value_at_risk,
    walk_forward_splits,
)


def test_walk_forward_splits_trade_after_signal_window():
    splits = walk_forward_splits(total_days=130, lookback_days=60, rebalance_every=21)

    assert splits
    first = splits[0]
    assert first["train_start_index"] == 0
    assert first["train_end_index"] == 60
    assert first["rebalance_index"] == 61
    assert all(split["train_end_index"] < split["rebalance_index"] for split in splits)


# ---------------------------------------------------------------------------
# Tail / hit-rate helpers
# ---------------------------------------------------------------------------


def test_cvar_returns_mean_loss_in_tail():
    returns = [-0.10, -0.05, -0.02, -0.01, 0.0, 0.01, 0.02, 0.05, 0.10, 0.15]
    # Worst 10% (1 of 10) = -0.10
    assert cvar(returns, confidence=0.9) == pytest.approx(0.10, rel=1e-3)
    # Worst 20% (2 of 10) average = (-0.10 + -0.05)/2 = -0.075
    assert cvar(returns, confidence=0.8) == pytest.approx(0.075, rel=1e-3)


def test_cvar_returns_zero_when_tail_is_non_negative():
    returns = [0.001, 0.002, 0.003, 0.004]
    assert cvar(returns, confidence=0.95) == 0.0


def test_cvar_handles_empty_input():
    assert cvar([], confidence=0.95) == 0.0


def test_var_at_95_is_a_loss_quantile():
    returns = [-0.05, -0.03, -0.01, 0.0, 0.02, 0.05]
    assert value_at_risk(returns, confidence=0.95) > 0
    # 95% confidence on 6 samples → cutoff index ~0 → worst observation
    assert value_at_risk(returns, confidence=0.95) == pytest.approx(0.05, rel=1e-3)


def test_hit_rate_counts_positive_periods_only():
    assert hit_rate([0.01, -0.02, 0.0, 0.03, -0.01]) == pytest.approx(0.4)
    assert hit_rate([]) == 0.0
    assert hit_rate([-0.01, -0.02]) == 0.0


# ---------------------------------------------------------------------------
# Slippage modelling
# ---------------------------------------------------------------------------


def test_slippage_scales_with_turnover_and_bps():
    assert slippage_cost(turnover_value=100_000, slippage_bps=10) == 100.0
    assert slippage_cost(turnover_value=0, slippage_bps=10) == 0.0


# ---------------------------------------------------------------------------
# Regime holdouts / ablations
# ---------------------------------------------------------------------------


def test_regime_metrics_slice_curve_by_date_window():
    curve = [
        {"date": "2024-01-01", "value": 100.0},
        {"date": "2024-01-15", "value": 95.0},
        {"date": "2024-02-01", "value": 90.0},
        {"date": "2024-02-15", "value": 100.0},
        {"date": "2024-03-01", "value": 105.0},
    ]
    regimes = [
        {"name": "drawdown", "start": "2024-01-15", "end": "2024-02-01"},
        {"name": "recovery", "start": "2024-02-01", "end": "2024-03-01"},
    ]
    results = _regime_metrics(curve, regimes)
    assert len(results) == 2
    drawdown = results[0]
    assert drawdown["name"] == "drawdown"
    assert drawdown["insufficient_data"] is False
    assert drawdown["samples"] == 2
    assert "cvar_95" in drawdown["metrics"]
    assert "hit_rate" in drawdown["metrics"]
    # The recovery slice has 3 samples with monotonic positive growth.
    recovery = results[1]
    assert recovery["insufficient_data"] is False
    assert recovery["metrics"]["hit_rate"] >= 0.5


def test_regime_metrics_flags_short_slices_as_insufficient():
    curve = [{"date": "2024-01-01", "value": 100.0}]
    regimes = [{"name": "covid", "start": "2020-02-01", "end": "2020-05-01"}]
    results = _regime_metrics(curve, regimes)
    assert results[0]["insufficient_data"] is True
    assert results[0]["metrics"] == {}


def test_ablation_run_records_signal_component_estimate():
    base_metrics = {"annualized_return": 0.12, "sharpe": 1.2}
    payload = BacktestRequest(symbols=["SPY", "QQQ"], max_positions=2)
    ablation = _ablation_run(payload, "momentum", base_metrics)
    assert ablation["ablation"] == "momentum"
    assert ablation["method"] == "deterministic_heuristic"
    # Momentum ablation halves alpha materially in our heuristic.
    assert ablation["estimated_annualized_return"] < base_metrics["annualized_return"]
    assert ablation["estimated_sharpe"] < base_metrics["sharpe"]


# ---------------------------------------------------------------------------
# Full backtest run with V8 metric surface
# ---------------------------------------------------------------------------


def _seed_price_series(conn, symbol: str, days: int, start_price: float = 100.0, drift: float = 0.001, vol: float = 0.01) -> None:
    """Insert deterministic synthetic daily bars for a symbol."""
    conn.execute(
        "INSERT OR IGNORE INTO instruments (symbol, name, asset_class, sector, liquidity_score, enabled) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (symbol, symbol, "ETF", "Test", 90.0),
    )
    price = start_price
    for offset in range(days):
        delta = drift + (vol if offset % 2 == 0 else -vol * 0.9)
        price = max(1.0, price * (1 + delta))
        year = 2024
        month = (offset // 28) + 1
        day = (offset % 28) + 1
        date = f"{year}-{month:02d}-{day:02d}"
        conn.execute(
            "INSERT OR REPLACE INTO price_bars (symbol, date, open, high, low, close, volume, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol, date, price, price * 1.005, price * 0.995, price, 1_000_000, "synthetic_test"),
        )


def test_run_backtest_persists_v8_metrics_and_versions():
    init_db()
    with get_conn() as conn:
        for symbol in ("SPY", "QQQ", "TLT", "GLD"):
            _seed_price_series(conn, symbol, days=180)
        conn.commit()

    with get_conn() as conn:
        request = BacktestRequest(
            symbols=["QQQ", "TLT", "GLD"],
            benchmark_symbol="SPY",
            lookback_days=40,
            max_positions=2,
            transaction_cost_bps=5,
            slippage_bps=4,
            ablations=["momentum", "quality"],
            regimes=[
                {"name": "first_half", "start": "2024-01-01", "end": "2024-03-15"},
                {"name": "second_half", "start": "2024-03-16", "end": "2024-06-30"},
            ],
        )
        result = run_backtest(conn, request)
        conn.commit()

    metrics = result["metrics"]
    assert metrics["engine_version"] == BACKTEST_ENGINE_VERSION
    assert metrics["strategy_version"] == BACKTEST_STRATEGY_VERSION
    assert "cvar_95" in metrics
    assert "cvar_99" in metrics
    assert "var_95" in metrics
    assert "hit_rate" in metrics
    assert metrics["total_slippage_cost"] >= 0
    assert 0.0 <= metrics["hit_rate"] <= 1.0
    assert isinstance(metrics["regimes"], list) and len(metrics["regimes"]) == 2
    assert all("metrics" in regime for regime in metrics["regimes"])
    assert isinstance(metrics["ablations"], list) and len(metrics["ablations"]) == 2
    assert {entry["ablation"] for entry in metrics["ablations"]} == {"momentum", "quality"}

    params = result["params"]
    validation = params["validation"]
    assert validation["engine_version"] == BACKTEST_ENGINE_VERSION
    assert validation["strategy_version"] == BACKTEST_STRATEGY_VERSION
    assert validation["slippage_bps"] == 4
    assert validation["regimes_evaluated"] == ["first_half", "second_half"]
    assert validation["ablations_evaluated"] == ["momentum", "quality"]


def test_run_backtest_slippage_increases_total_costs():
    init_db()
    with get_conn() as conn:
        conn.execute("DELETE FROM price_bars WHERE symbol IN ('SLPA', 'SLPB', 'SLPC', 'SLPD')")
        for symbol in ("SLPA", "SLPB", "SLPC", "SLPD"):
            _seed_price_series(conn, symbol, days=180, start_price=100.0)
        conn.commit()

    base_request = BacktestRequest(
        symbols=["SLPB", "SLPC", "SLPD"],
        benchmark_symbol="SLPA",
        lookback_days=40,
        max_positions=2,
        transaction_cost_bps=5,
        slippage_bps=0,
    )
    with get_conn() as conn:
        low = run_backtest(conn, base_request)
        conn.commit()
        high = run_backtest(
            conn,
            base_request.model_copy(update={"slippage_bps": 50}),
        )
        conn.commit()

    # Higher slippage bps must produce a strictly higher total slippage cost when
    # turnover is the same — and that cost shows up in the receipt's audit trail.
    assert high["metrics"]["total_slippage_cost"] > low["metrics"]["total_slippage_cost"]
    assert high["params"]["validation"]["slippage_bps"] == 50
    assert low["params"]["validation"]["slippage_bps"] == 0
