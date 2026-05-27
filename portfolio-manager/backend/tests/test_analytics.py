from app.services.analytics import annualized_return, max_drawdown, pct_change, quality_score, sharpe_ratio


def test_return_and_drawdown_calculations_are_stable():
    closes = [100, 110, 90, 120]
    returns = pct_change(closes)

    assert [round(item, 4) for item in returns] == [0.1, -0.1818, 0.3333]
    assert round(max_drawdown(closes), 4) == 0.1818
    assert annualized_return(closes) > 1000


def test_quality_score_rewards_growth_cash_flow_and_low_debt():
    strong = quality_score(
        {
            "revenue_growth": 0.25,
            "gross_margin": 0.72,
            "free_cash_flow_yield": 0.05,
            "debt_to_equity": 0.2,
        }
    )
    weak = quality_score(
        {
            "revenue_growth": -0.02,
            "gross_margin": 0.22,
            "free_cash_flow_yield": 0.0,
            "debt_to_equity": 2.0,
        }
    )

    assert strong > weak
    assert 0 <= weak <= 1
    assert sharpe_ratio([0.01, 0.02, -0.01, 0.015]) != 0
