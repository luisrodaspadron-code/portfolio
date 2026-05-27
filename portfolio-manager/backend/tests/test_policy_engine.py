import pytest


def test_balanced_preset_thresholds():
    from app.services.policy_engine import BALANCED

    s = BALANCED.single_stock
    assert (s.target, s.warning, s.hard_buy_block, s.urgent_review, s.extreme) == (
        0.05,
        0.08,
        0.10,
        0.15,
        0.25,
    )
    assert BALANCED.sector.warning == 0.25
    assert BALANCED.sector.hard_cap == 0.30
    assert BALANCED.crypto.enabled_by_default is False
    assert BALANCED.crypto.max_total == 0.03


def test_preset_ladder_is_strictly_monotonic():
    from app.services.policy_engine import PRESETS

    for name, policy in PRESETS.items():
        s = policy.single_stock
        assert 0 < s.target < s.warning < s.hard_buy_block < s.urgent_review < s.extreme, name
        assert 0 < policy.sector.warning <= policy.sector.hard_cap


def test_build_cap_distance_state_ladder():
    from app.services.policy_engine import BALANCED, build_cap_distance

    cases = [
        (0.02, "ok", False, False),
        (0.08, "warning", False, False),
        (0.105, "hard_buy_block", True, False),
        (0.16, "urgent_review", True, True),
        (0.30, "extreme", True, True),
    ]
    for weight, expected_state, expected_blocks, expected_requires in cases:
        result = build_cap_distance(weight, BALANCED.single_stock)
        assert result["state"] == expected_state, weight
        assert result["blocksNewBuys"] is expected_blocks, weight
        assert result["requiresTrimPlan"] is expected_requires, weight
        assert result["currentWeight"] == round(weight, 4)


def test_validate_custom_policy_rejects_inverted_ladder():
    from app.services.policy_engine import validate_custom_policy

    with pytest.raises(ValueError):
        validate_custom_policy(
            {
                "singleStock": {
                    "target": 0.10,
                    "warning": 0.08,
                    "hardBuyBlock": 0.06,
                    "urgentReview": 0.05,
                    "extreme": 0.04,
                },
            }
        )


def test_validate_custom_policy_accepts_valid_ladder():
    from app.services.policy_engine import validate_custom_policy

    policy = validate_custom_policy(
        {
            "id": "my-custom",
            "name": "My Custom",
            "singleStock": {
                "target": 0.04,
                "warning": 0.06,
                "hardBuyBlock": 0.08,
                "urgentReview": 0.12,
                "extreme": 0.20,
            },
            "sector": {"warning": 0.20, "hardCap": 0.28},
        }
    )
    assert policy.preset == "custom"
    assert policy.single_stock.warning == 0.06
    assert policy.sector.hard_cap == 0.28


def test_autopilot_default_off(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, get_risk_rules, init_db

    init_db()
    with get_conn() as conn:
        rules = get_risk_rules(conn)
    assert rules["autopilot_enabled"] is False
    assert rules["risk_policy_preset"] == "balanced"


def test_legacy_rules_match_balanced_preset():
    from app.services.policy_engine import BALANCED, legacy_rules_from_policy

    rules = legacy_rules_from_policy(BALANCED)
    assert rules["max_single_stock_weight"] == BALANCED.single_stock.urgent_review
    assert rules["max_sector_weight"] == BALANCED.sector.hard_cap
    assert rules["max_crypto_weight"] == BALANCED.crypto.max_total


def test_selected_risk_policy_reads_preset_from_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db, update_risk_rules
    from app.services.policy_engine import selected_risk_policy

    init_db()
    with get_conn() as conn:
        update_risk_rules(conn, {"risk_policy_preset": "competition"})
        policy = selected_risk_policy(conn)
    assert policy.preset == "competition"
    assert policy.single_stock.target == 0.10


def test_risk_policy_to_dict_uses_camelcase():
    from app.services.policy_engine import BALANCED, risk_policy_to_dict

    payload = risk_policy_to_dict(BALANCED)
    assert "singleStock" in payload
    assert "hardBuyBlock" in payload["singleStock"]
    assert "maxSingleBroadEtf" in payload["broadEtf"]
