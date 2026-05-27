def test_default_model_router_has_v8_fields():
    from app.services.ai_service import DEFAULT_AI_MODEL_CONFIG

    for route in ("fast", "specialist", "leadPM", "deepCompetition"):
        config = DEFAULT_AI_MODEL_CONFIG[route]
        assert "timeoutMs" in config
        assert "stream" in config
        assert "purpose" in config
        assert "requiresManualRun" in config
        assert "promptVersion" in config


def test_deep_competition_is_manual_only():
    from app.services.ai_service import DEFAULT_AI_MODEL_CONFIG

    assert DEFAULT_AI_MODEL_CONFIG["deepCompetition"]["requiresManualRun"] is True
    assert DEFAULT_AI_MODEL_CONFIG["leadPM"]["requiresManualRun"] is False


def test_router_accepts_minimal_reasoning_effort():
    from app.services.ai_service import DEFAULT_AI_MODEL_CONFIG, _normalize_route

    normalized = _normalize_route({"reasoningEffort": "minimal"}, DEFAULT_AI_MODEL_CONFIG["fast"])
    assert normalized["reasoningEffort"] == "minimal"


def test_router_rejects_unknown_reasoning_effort():
    from app.services.ai_service import DEFAULT_AI_MODEL_CONFIG, _normalize_route

    normalized = _normalize_route({"reasoningEffort": "ultra-extreme"}, DEFAULT_AI_MODEL_CONFIG["fast"])
    # Falls back to route default
    assert normalized["reasoningEffort"] == DEFAULT_AI_MODEL_CONFIG["fast"]["reasoningEffort"]


def test_runtime_settings_expose_governance_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services.ai_service import ai_runtime_settings

    init_db()
    with get_conn() as conn:
        settings = ai_runtime_settings(conn, "leadPM")
    assert settings["model_route"] == "leadPM"
    assert "prompt_version" in settings
    assert "timeout_ms" in settings
    assert "requires_manual_run" in settings


def test_llm_review_output_schema_excludes_canonical_action_fields():
    from app.services.llm_review_output import LLM_REVIEW_OUTPUT_SCHEMA

    forbidden = {"holding_decisions", "opportunity_decisions", "action", "target_weight"}
    properties = LLM_REVIEW_OUTPUT_SCHEMA["properties"].keys()
    for field in forbidden:
        assert field not in properties
    assert LLM_REVIEW_OUTPUT_SCHEMA["additionalProperties"] is False


def test_detect_forbidden_claims_flags_guaranteed_language():
    from app.services.llm_review_output import detect_forbidden_claims

    flagged = detect_forbidden_claims("This trade is guaranteed and will outperform the market.")
    assert "guaranteed" in flagged
    assert "will outperform" in flagged


def test_detect_forbidden_claims_passes_safe_text():
    from app.services.llm_review_output import detect_forbidden_claims

    assert detect_forbidden_claims("This is advisory-only; no order has been placed.") == []


def test_detect_decision_conflict_when_not_confirmed():
    from app.services.llm_review_output import detect_decision_conflict

    conflict = detect_decision_conflict(
        {
            "deterministicDecisionConfirmed": False,
            "conflictWithDeterministicEngine": None,
        },
        deterministic_first_action_symbol="META",
        deterministic_first_action_label="Trim",
    )
    assert conflict is not None
    assert "META" in conflict


def test_detect_decision_conflict_returns_none_when_confirmed():
    from app.services.llm_review_output import detect_decision_conflict

    assert (
        detect_decision_conflict(
            {"deterministicDecisionConfirmed": True, "conflictWithDeterministicEngine": None},
            "META",
            "Trim",
        )
        is None
    )


def test_detect_decision_conflict_preserves_explicit_conflict():
    from app.services.llm_review_output import detect_decision_conflict

    conflict = detect_decision_conflict(
        {"deterministicDecisionConfirmed": True, "conflictWithDeterministicEngine": "LLM thinks Add is fine."},
        "META",
        "Trim",
    )
    assert conflict == "LLM thinks Add is fine."
