from app.services.advisor_math import build_add_plan, build_trim_plan, cap_distance, data_quality_from_price


def test_trim_plan_mode_a_keeps_portfolio_value_constant():
    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=50_000,
        target_weight=0.08,
        live_price=500,
        price_timestamp="2026-05-27T14:30:00+00:00",
        quantity=100,
        avg_cost=250,
        fractional_shares=True,
    )

    assert plan["mode"] == "redeploy_or_cash"
    assert plan["targetValue"] == 8000
    assert plan["estimatedSellValue"] == 42000
    assert plan["sharesToSellExact"] == 84
    assert plan["sharesToSell"] == 84
    assert plan["estimatedPostWeight"] == 0.08
    assert plan["advisoryOnly"] is True
    assert "tax" in plan["taxWarning"].lower()


def test_trim_plan_mode_b_withdrawal_shrinks_portfolio():
    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=50_000,
        target_weight=0.08,
        live_price=500,
        price_timestamp="2026-05-27T14:30:00+00:00",
        quantity=100,
        fractional_shares=True,
        mode="withdrawal",
    )

    assert round(plan["estimatedSellValue"], 2) == 45652.17
    assert plan["sharesToSellExact"] == 91.304348
    assert plan["estimatedPostWeight"] == 0.08


def test_trim_plan_whole_share_rounding_reports_post_weight():
    plan = build_trim_plan(
        total_portfolio_value=10_000,
        current_position_value=1_100,
        target_weight=0.08,
        live_price=333,
        price_timestamp="2026-05-27",
        quantity=3.3033,
        fractional_shares=False,
        compliance_mode="reduce_only",
    )

    assert plan["sharesToSellExact"] == 0.900901
    assert plan["sharesToSellWholeReduceOnly"] == 0
    assert plan["sharesToSellWholeCompliant"] == 1
    assert plan["sharesToSellWhole"] == 0
    assert plan["sharesToSell"] == 0
    assert plan["estimatedPostWeight"] == 0.11
    assert plan["complianceMode"] == "reduce_only"


def test_data_quality_live_recent_stale_and_missing():
    live = data_quality_from_price(
        provider="alpaca",
        source_timestamp="2026-05-27T14:55:00+00:00",
        received_at="2026-05-27T15:00:00+00:00",
    )
    stale = data_quality_from_price(
        provider="alpaca",
        source_timestamp="2026-05-20T15:00:00+00:00",
        received_at="2026-05-27T15:00:00+00:00",
    )
    missing = data_quality_from_price(provider="alpaca")

    assert live["freshness"] == "live"
    assert live["confidence"] == 1.0
    assert stale["freshness"] == "stale"
    assert stale["confidence"] < live["confidence"]
    assert missing["freshness"] == "missing"
    assert missing["coverage"] == "missing"


def test_add_plan_blocks_sector_cap_and_uses_four_tranches():
    plan = build_add_plan(
        total_portfolio_value=50_000,
        target_weight=0.06,
        current_sector_weight=0.28,
        sector_cap=0.30,
    )

    assert plan["trancheCount"] == 4
    assert plan["initialWeight"] == 0.015
    assert plan["trancheSchedule"][0]["estimatedDollarAmount"] == 750
    assert plan["blockers"] == ["Sector cap would be breached by this add."]


def test_cap_distance_reports_percentage_point_breach():
    distance = cap_distance(0.538, 0.08)

    assert distance["breached"] is True
    assert distance["over_by"] == 0.458

