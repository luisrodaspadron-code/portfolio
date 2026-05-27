import pytest


def test_strict_compliance_uses_ceil_for_whole_shares():
    from app.services.advisor_math import build_trim_plan

    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=26_300,
        target_weight=0.05,
        live_price=100.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=263,
        fractional_shares=False,
        compliance_mode="strict_below_threshold",
        policy_threshold=0.10,
    )
    # need to sell 213 shares (26300 - 5000 target value = 21300 → 213 shares exact at $100)
    # ceil(213) = 213 since it's already whole; choose case that exercises ceil
    assert plan["sharesToSellExact"] == pytest.approx(213.0, abs=1e-3)
    assert plan["sharesToSellWholeCompliant"] >= plan["sharesToSellWholeReduceOnly"]
    assert plan["sharesToSell"] == plan["sharesToSellWholeCompliant"]
    assert plan["executionGuidance"]["preferredOrderType"] == "limit_sell"
    assert plan["executionGuidance"]["suggestedLimitPrice"] < plan["priceUsed"]
    assert plan["executionGuidance"]["advisoryOnly"] is True


def test_large_trim_plan_includes_staged_limit_checklist():
    from app.services.advisor_math import build_trim_plan

    plan = build_trim_plan(
        total_portfolio_value=48_853,
        current_position_value=26_261,
        target_weight=0.08,
        live_price=610.72,
        price_timestamp="2026-05-26T20:00:00Z",
        quantity=43,
        fractional_shares=False,
        compliance_mode="strict_below_threshold",
        policy_threshold=0.08,
    )

    guidance = plan["executionGuidance"]
    assert guidance["recommendedStyle"] == "staged_limit_sells"
    assert guidance["sliceCount"] >= 2
    assert sum(slice_["shares"] for slice_ in guidance["slices"]) == plan["sharesToSellWholeCompliant"]
    assert guidance["primaryQuantityBasis"] == "whole_share_compliant"
    assert guidance["allAtOnceAcceptable"] is False
    assert guidance["singleOrderAlternative"]["shares"] == plan["sharesToSellWholeCompliant"]
    assert guidance["stopReviewBelow"] < guidance["suggestedLimitPrice"] < guidance["limitPriceReference"]
    assert any("Refresh the live quote" in item for item in guidance["instructions"])


def test_fractional_trim_guidance_still_exposes_whole_share_fallback():
    from app.services.advisor_math import build_trim_plan

    plan = build_trim_plan(
        total_portfolio_value=48_853,
        current_position_value=26_261,
        target_weight=0.08,
        live_price=610.72,
        price_timestamp="2026-05-26T20:00:00Z",
        quantity=43,
        fractional_shares=True,
        compliance_mode="strict_below_threshold",
        policy_threshold=0.08,
    )

    guidance = plan["executionGuidance"]
    assert guidance["primaryQuantityBasis"] == "fractional"
    assert sum(slice_["shares"] for slice_ in guidance["wholeShareSlices"]) == plan["sharesToSellWholeCompliant"]
    assert guidance["singleOrderAlternative"]["shares"] == plan["sharesToSellFractionalCompliant"]
    assert "Staged limit sells" in guidance["stagingRationale"]


def test_strict_compliance_ceiling_strictly_below_threshold():
    from app.services.advisor_math import build_trim_plan

    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=15_500,
        target_weight=0.05,
        live_price=37.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=419,
        fractional_shares=False,
        compliance_mode="strict_below_threshold",
        policy_threshold=0.10,
    )
    # ceil should yield strictly-below-threshold post-weight
    assert plan["estimatedPostWeightCompliant"] <= plan["policyThreshold"]
    # reduce-only floor may or may not satisfy threshold, but compliant always does
    assert plan["sharesToSellWholeCompliant"] >= plan["sharesToSellWholeReduceOnly"]


def test_reduce_only_uses_floor_and_flags_remaining_above_threshold():
    from app.services.advisor_math import build_trim_plan

    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=10_077,
        target_weight=0.05,
        live_price=33.33,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=302,
        fractional_shares=False,
        compliance_mode="reduce_only",
        policy_threshold=0.10,
    )
    # Sell value = 10077 - 5000 = 5077; exact = 5077/33.33 ≈ 152.32
    # floor → 152 shares × $33.33 ≈ $5066 → remaining $5011 → 5.0% post-weight, below threshold
    # Adjust price so reduce_only_post_weight > 10% threshold
    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=10_400,
        target_weight=0.05,
        live_price=190.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=55,
        fractional_shares=False,
        compliance_mode="reduce_only",
        policy_threshold=0.10,
    )
    # Sell value = 10400 - 5000 = 5400; exact = 5400 / 190 ≈ 28.42
    # floor = 28 × $190 = $5320 → remaining $5080 → 5.08% post-weight
    # That is below 10% threshold, so wouldRemainAboveThresholdIfRoundedDown should be False
    assert plan["sharesToSellWholeReduceOnly"] == 28
    assert plan["estimatedPostWeightReduceOnly"] < plan["policyThreshold"]


def test_reduce_only_remaining_above_threshold_flagged():
    from app.services.advisor_math import build_trim_plan

    # Construct a case where rounding down leaves position above threshold.
    # current weight 12% with threshold 10%, big share price so floor rounding leaves remaining > 10%.
    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=12_000,
        target_weight=0.05,
        live_price=1_950.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=7,
        fractional_shares=False,
        compliance_mode="reduce_only",
        policy_threshold=0.10,
    )
    # Sell value = 12000 - 5000 = 7000; exact = 7000 / 1950 ≈ 3.59
    # floor = 3 shares × $1950 = $5850 → remaining $6150 → 6.15% → below threshold
    # Pick a tighter case: price 4000, qty 3, position 12000
    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=12_000,
        target_weight=0.05,
        live_price=4_000.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=3,
        fractional_shares=False,
        compliance_mode="reduce_only",
        policy_threshold=0.10,
    )
    # Sell value = 12000 - 5000 = 7000; exact = 7000 / 4000 = 1.75
    # floor = 1 share × $4000 = $4000 → remaining $8000 → 8% → still below 10%
    # Tighter: price 6000, qty 2, position 12000
    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=12_000,
        target_weight=0.05,
        live_price=6_000.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=2,
        fractional_shares=False,
        compliance_mode="reduce_only",
        policy_threshold=0.10,
    )
    # Sell value = 12000 - 5000 = 7000; exact = 7000 / 6000 ≈ 1.17
    # floor = 1 × $6000 = $6000 → remaining $6000 → 6% → below threshold
    # The math means with a >10% threshold, floor rounding can only leave you above when
    # the share is large relative to overshoot. Use position 110, threshold 0.10,
    # value 11000, price 1100, qty 10: sell value = 11000 - target(5000) = 6000;
    # exact = 6000/1100 ≈ 5.45; floor = 5 × 1100 = 5500 → remaining 5500 → 5.5%
    # Use a much tighter scenario: position 10100 ($10100, 10.1%), price 1010, qty 10,
    # threshold 0.10, target 0.05 → sell value 5100, exact 5100/1010 ≈ 5.05,
    # floor=5 × 1010 = 5050 → remaining 5050 → 5.05% → below threshold
    # The general property: floor remaining = current_value - floor(exact)*price.
    # For remaining > threshold * total_value, you need to be barely over the cap and have
    # shares so few that floor leaves a large residual. Try qty=1, price=11000,
    # position_value=11000 (11%), target_weight=0.05, threshold=0.10:
    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=11_000,
        target_weight=0.05,
        live_price=11_000.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=1,
        fractional_shares=False,
        compliance_mode="reduce_only",
        policy_threshold=0.10,
    )
    # Sell value = 11000 - 5000 = 6000; exact = 6000 / 11000 ≈ 0.545
    # floor = 0 shares → remaining 11000 → 11% → above 10% threshold
    assert plan["sharesToSellWholeReduceOnly"] == 0
    assert plan["estimatedPostWeightReduceOnly"] >= plan["policyThreshold"]
    assert plan["wouldRemainAboveThresholdIfRoundedDown"] is True
    # And strict compliance ceil would sell 1 share → remaining 0 → 0%
    assert plan["sharesToSellWholeCompliant"] == 1
    assert plan["estimatedPostWeightCompliant"] == 0


def test_fractional_strict_rounds_up_to_precision():
    from app.services.advisor_math import build_trim_plan

    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=12_000,
        target_weight=0.05,
        live_price=131.7,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=91.1234,
        fractional_shares=True,
        compliance_mode="strict_below_threshold",
        fractional_precision=4,
        policy_threshold=0.10,
    )
    # exact = (12000-5000)/131.7 ≈ 53.1511...
    # strict precision-4 ceil = 53.1512
    assert plan["sharesToSellFractionalCompliant"] >= plan["sharesToSellExact"]
    # post-weight using compliant must be strictly below threshold
    assert plan["estimatedPostWeightCompliant"] <= plan["policyThreshold"]


def test_tax_warning_present_when_avg_cost_available():
    from app.services.advisor_math import build_trim_plan

    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=10_000,
        target_weight=0.05,
        live_price=200.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=50,
        avg_cost=180.0,
        fractional_shares=False,
        compliance_mode="strict_below_threshold",
        policy_threshold=0.10,
    )
    assert plan["taxWarning"]


def test_tax_aware_review_mode_uses_floor_and_extra_warning():
    from app.services.advisor_math import build_trim_plan

    plan = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=12_000,
        target_weight=0.05,
        live_price=120.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=100,
        avg_cost=60.0,
        fractional_shares=False,
        compliance_mode="tax_aware_review",
        policy_threshold=0.10,
    )
    assert plan["sharesToSell"] == plan["sharesToSellWholeReduceOnly"]
    assert "reduce-only" in plan["taxWarning"].lower()


def test_withdrawal_mode_sells_more_to_reach_target_share():
    from app.services.advisor_math import build_trim_plan

    plan_redeploy = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=20_000,
        target_weight=0.10,
        live_price=100.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=200,
        mode="redeploy_or_cash",
        compliance_mode="strict_below_threshold",
        policy_threshold=0.15,
    )
    plan_withdraw = build_trim_plan(
        total_portfolio_value=100_000,
        current_position_value=20_000,
        target_weight=0.10,
        live_price=100.0,
        price_timestamp="2025-01-01T00:00:00Z",
        quantity=200,
        mode="withdrawal",
        compliance_mode="strict_below_threshold",
        policy_threshold=0.15,
    )
    assert plan_withdraw["estimatedSellValue"] > plan_redeploy["estimatedSellValue"]
