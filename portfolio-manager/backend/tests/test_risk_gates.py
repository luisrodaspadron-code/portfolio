def _balanced_snapshot():
    return {
        "totalValue": 100_000.0,
        "positions": [
            {"symbol": "META", "weight": 0.538, "sector": "Communication Services", "assetClass": "stock"},
            {"symbol": "MSFT", "weight": 0.02, "sector": "Technology", "assetClass": "stock"},
        ],
        "sectorWeights": {"Communication Services": 0.538, "Technology": 0.02},
    }


def test_buying_overweight_symbol_is_blocked():
    from app.services.policy_engine import BALANCED
    from app.services.trade_impact import evaluate_trade_impact

    impact = evaluate_trade_impact(
        _balanced_snapshot(),
        {
            "symbol": "META",
            "side": "buy",
            "weightDelta": 0.02,
            "sector": "Communication Services",
            "assetClass": "stock",
        },
        BALANCED,
    )
    assert impact.worsens_breach is True
    assert impact.blocked is True
    assert impact.pre_state == "extreme"


def test_buying_diversified_etf_is_risk_reducing():
    from app.services.policy_engine import BALANCED
    from app.services.trade_impact import evaluate_trade_impact

    impact = evaluate_trade_impact(
        _balanced_snapshot(),
        {
            "symbol": "VTI",
            "side": "buy",
            "weightDelta": 0.05,
            "sector": "Diversified",
            "assetClass": "etf",
            "isBroadEtf": True,
        },
        BALANCED,
    )
    assert impact.reduces_portfolio_risk is True
    assert impact.blocked is False


def test_selling_breached_position_is_risk_reducing():
    from app.services.policy_engine import BALANCED
    from app.services.trade_impact import evaluate_trade_impact

    impact = evaluate_trade_impact(
        _balanced_snapshot(),
        {
            "symbol": "META",
            "side": "sell",
            "weightDelta": 0.10,
            "sector": "Communication Services",
            "assetClass": "stock",
        },
        BALANCED,
    )
    assert impact.reduces_portfolio_risk is True
    assert impact.blocked is False


def test_buying_in_overweight_sector_is_blocked():
    from app.services.policy_engine import BALANCED
    from app.services.trade_impact import evaluate_trade_impact

    snapshot = {
        "totalValue": 100_000.0,
        "positions": [],
        "sectorWeights": {"Technology": 0.34},  # above 0.30 hard cap
    }
    impact = evaluate_trade_impact(
        snapshot,
        {
            "symbol": "NVDA",
            "side": "buy",
            "weightDelta": 0.02,
            "sector": "Technology",
            "assetClass": "stock",
        },
        BALANCED,
    )
    assert impact.worsens_breach is True
    assert impact.blocked is True


def test_warning_state_does_not_block_new_buys():
    from app.services.policy_engine import BALANCED
    from app.services.trade_impact import evaluate_trade_impact

    snapshot = {
        "totalValue": 100_000.0,
        "positions": [{"symbol": "AAPL", "weight": 0.085, "sector": "Technology", "assetClass": "stock"}],
        "sectorWeights": {"Technology": 0.085},
    }
    impact = evaluate_trade_impact(
        snapshot,
        {
            "symbol": "AAPL",
            "side": "buy",
            "weightDelta": 0.005,
            "sector": "Technology",
            "assetClass": "stock",
        },
        BALANCED,
    )
    # warning → warning when post-weight stays below 0.10; should not block
    assert impact.blocked is False


def test_cap_distance_includes_v8_fields_when_policy_provided():
    from app.services.advisor_math import cap_distance
    from app.services.policy_engine import BALANCED

    distance = cap_distance(0.16, single_stock=BALANCED.single_stock)
    assert distance["state"] == "urgent_review"
    assert distance["blocksNewBuys"] is True
    assert distance["requiresTrimPlan"] is True
    # legacy compatibility fields still present
    assert distance["current_weight"] == 0.16
    assert distance["breached"] is True
