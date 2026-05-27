import json
import httpx

from fastapi.testclient import TestClient


def test_without_openai_key_memos_are_rules_based(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/recommendations/run", json={"max_ideas": 1})
        assert response.status_code == 200

        memos = client.get("/api/research/memos")
        assert memos.status_code == 200
        memo = memos.json()["memos"][0]
        assert memo["generation_method"] == "rules_based"
        assert memo["ai_provider"] == ""
        assert memo["total_tokens"] == 0

        dashboard = client.get("/api/dashboard")
        assert dashboard.status_code == 200
        ai_status = dashboard.json()["ai_status"]
        assert ai_status["state"] == "disabled"
        assert ai_status["usage_totals"]["total_tokens"] == 0


def test_openai_memo_generation_logs_token_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import ai_service

    def fake_response(payload, api_key):
        assert api_key == "test-key"
        assert payload["model"] == "gpt-5.4-mini"
        assert payload["reasoning"] == {"effort": "medium"}
        assert payload["max_output_tokens"] == 1500
        assert "aggressive long-term competition portfolio manager" in payload["instructions"]
        assert "risk gates" in payload["instructions"]
        assert "source freshness" in payload["instructions"]
        return {
            "id": "resp_test",
            "output_text": json.dumps(
                {
                    "title": "SPY AI memo",
                    "thesis": "Model-generated thesis from supplied evidence.",
                    "evidence": "Model-reviewed evidence from quant inputs.",
                    "risks": "Model-reviewed risks from supplied flags.",
                    "counterargument": "Model-generated counterargument.",
                    "change_mind": "Model-generated change-mind trigger.",
                }
            ),
            "usage": {"input_tokens": 111, "output_tokens": 77, "total_tokens": 188},
        }

    monkeypatch.setattr(ai_service, "_call_openai_response", fake_response)

    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/recommendations/run", json={"max_ideas": 1, "universe": ["SPY"]})
        assert response.status_code == 200

        memo = client.get("/api/research/memos").json()["memos"][0]
        assert memo["generation_method"] == "openai"
        assert memo["ai_provider"] == "openai"
        assert memo["ai_model"] == "gpt-5.4-mini"
        assert memo["total_tokens"] == 188

        ai_status = client.get("/api/dashboard").json()["ai_status"]
        assert ai_status["state"] == "live"
        assert ai_status["model"] == "gpt-5.4-mini"
        assert ai_status["settings"]["reasoning_effort"] == "medium"
        assert ai_status["settings"]["memo_style"] == "competition_pm"
        assert ai_status["settings"]["max_output_tokens"] == 1500
        assert ai_status["model_router"]["leadPM"]["model"] == "gpt-5.5"
        assert "quant-gated" in ai_status["profile_summary"]
        assert ai_status["usage_totals"]["input_tokens"] >= 111
        assert ai_status["usage_totals"]["total_tokens"] >= 188


def test_legacy_ai_settings_update_specialist_route_without_prompt_customization(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "low")
    monkeypatch.setenv("OPENAI_MEMO_STYLE", "skeptical")
    monkeypatch.setenv("OPENAI_CUSTOM_INSTRUCTIONS", "Prefer brutal downside checks before enthusiasm.")
    monkeypatch.setenv("OPENAI_MAX_OUTPUT_TOKENS", "700")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import ai_service

    seen_payloads = []

    def fake_response(payload, api_key):
        seen_payloads.append(payload)
        assert api_key == "test-key"
        return {
            "id": "resp_custom",
            "output_text": json.dumps(
                {
                    "title": "Custom memo",
                    "thesis": "Custom thesis from supplied evidence.",
                    "evidence": "Custom evidence.",
                    "risks": "Custom risks.",
                    "counterargument": "Custom counterargument.",
                    "change_mind": "Custom trigger.",
                }
            ),
            "usage": {"input_tokens": 50, "output_tokens": 25, "total_tokens": 75},
        }

    monkeypatch.setattr(ai_service, "_call_openai_response", fake_response)

    from app.main import app

    with TestClient(app) as client:
        settings = client.put(
            "/api/settings/ai",
            json={
                "model": "gpt-5.4-mini",
                "reasoning_effort": "low",
                "memo_style": "skeptical",
                "max_output_tokens": 700,
                "custom_instructions": "Prefer brutal downside checks before enthusiasm.",
            },
        )
        assert settings.status_code == 200
        returned_settings = settings.json()["ai_status"]["settings"]
        assert returned_settings["model"] == "gpt-5.4-mini"
        assert returned_settings["reasoning_effort"] == "low"
        assert returned_settings["memo_style"] == "competition_pm"
        assert returned_settings["max_output_tokens"] == 700
        assert returned_settings["custom_instructions"] == ""

        response = client.post("/api/recommendations/run", json={"max_ideas": 1, "universe": ["SPY"]})
        assert response.status_code == 200

        payload = seen_payloads[-1]
        assert payload["model"] == "gpt-5.4-mini"
        assert payload["reasoning"] == {"effort": "low"}
        assert payload["max_output_tokens"] == 700
        assert "aggressive long-term competition portfolio manager" in payload["instructions"]
        assert "risk gates" in payload["instructions"]
        assert "Prefer brutal downside checks" not in payload["instructions"]


def test_local_openai_key_connection_flow_uses_optimized_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import ai_service

    seen_payloads = []
    seen_keys = []

    def fake_response(payload, api_key):
        seen_payloads.append(payload)
        seen_keys.append(api_key)
        return {
            "id": "resp_connection",
            "output_text": "{\"status\":\"ok\",\"message\":\"connected\"}",
            "usage": {"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
        }

    monkeypatch.setattr(ai_service, "_call_openai_response", fake_response)

    from app.main import app

    local_key = "sk-local-test-key-1234567890"
    with TestClient(app) as client:
        saved = client.put("/api/settings/openai-key", json={"api_key": local_key})
        assert saved.status_code == 200
        assert saved.json()["ai_status"]["configured"] is True
        assert local_key not in json.dumps(saved.json())

        tested = client.post("/api/settings/ai/test")
        assert tested.status_code == 200
        ai_status = tested.json()["ai_status"]
        assert ai_status["state"] == "live"
        assert ai_status["settings"]["model"] == "gpt-5.4-mini"
        assert ai_status["settings"]["reasoning_effort"] == "medium"
        assert ai_status["settings"]["memo_style"] == "competition_pm"
        assert ai_status["model_router"]["fast"]["reasoningEffort"] == "low"
        assert ai_status["last_run"]["purpose"] == "connection_test"
        assert ai_status["usage_totals"]["total_tokens"] >= 12

    assert seen_keys == [local_key]
    assert seen_payloads[0]["model"] == "gpt-5.4-mini"
    assert seen_payloads[0]["reasoning"] == {"effort": "low"}


def test_openai_rate_limit_is_recoverable_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import ai_service

    def rate_limited(payload, api_key):
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        response = httpx.Response(429, request=request, text="Too Many Requests")
        raise httpx.HTTPStatusError("Too Many Requests", request=request, response=response)

    monkeypatch.setattr(ai_service, "_call_openai_response", rate_limited)

    from app.main import app

    with TestClient(app) as client:
        saved = client.put("/api/settings/secrets", json={"provider": "openai", "values": {"openai_api_key": "sk-local-rate-limit-key"}})
        assert saved.status_code == 200

        tested = client.post("/api/settings/connections/test", json={"provider": "openai"})
        assert tested.status_code == 200
        assert tested.json()["status"] == "rate_limited"
        assert tested.json()["ai_status"]["state"] == "rate_limited"
        assert "rate-limiting" in tested.json()["ai_status"]["user_message"]

        dashboard = client.get("/api/dashboard").json()
        assert dashboard["ai_status"]["state"] == "rate_limited"
        openai = next(provider for provider in dashboard["connections"]["providers"] if provider["provider"] == "openai")
        assert openai["state"] == "rate_limited"
