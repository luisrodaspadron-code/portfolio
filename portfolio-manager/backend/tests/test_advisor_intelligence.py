import json

from fastapi.testclient import TestClient


def test_advisor_packet_contains_quant_toolchain_and_data_status(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/advisor/packet")
        assert response.status_code == 200
        packet = response.json()["packet"]
        tool_names = {tool["name"] for tool in packet["tool_inventory"]}

    assert {
        "data_refresh",
        "feature_generation",
        "risk_gates",
        "target_sizing",
        "strategy_sleeve_review",
        "walk_forward_backtest",
        "portfolio_stress",
        "macro_regime",
        "memo_generation",
    }.issubset(tool_names)
    assert packet["quant_diagnostics"]["status"] in {"healthy", "attention"}
    assert packet["provider_freshness"]["provider_mode"] in {"live", "recent", "stale", "partial", "missing", "sample"}
    assert packet["data_quality"]["confidence"] in {"fresh", "stale", "sample_only"}
    assert packet["decision_boundary"].startswith("Decision-support only")


def test_advisor_trace_exposes_user_facing_packet_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/advisor/trace")
        assert response.status_code == 200
        trace = response.json()["trace"]

    assert trace["packet_hash"]
    assert trace["ai_activity"] == "not_connected"
    assert trace["holdings_analyzed"]["count"] >= 0
    assert any(tool["name"] == "risk_gates" for tool in trace["quant_tools"])
    assert trace["market_universe"]["enabled_instruments"] > 0
    assert "allowed_categories" in trace["market_universe"]
    assert "max_single_stock_weight" in trace["risk_bounds"]
    assert trace["sec_edgar"]["purpose"].startswith("Company facts")


def test_advisor_review_payload_and_risk_gate_enforcement(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import advisor_intelligence, ai_service

    seen_payloads = []

    def fake_response(payload, api_key):
        seen_payloads.append(payload)
        if payload["max_output_tokens"] == 200:
            return {
                "id": "resp_connection",
                "output_text": "{\"status\":\"ok\",\"message\":\"connected\"}",
                "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
            }
        if payload["max_output_tokens"] == 800:
            return {
                "id": "resp_memo",
                "output_text": json.dumps(
                    {
                        "title": "Memo",
                        "thesis": "Thesis.",
                        "evidence": "Evidence.",
                        "risks": "Risks.",
                        "counterargument": "Counter.",
                        "change_mind": "Trigger.",
                    }
                ),
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
        return {
            "id": "resp_review",
            "output_text": json.dumps(
                {
                    "brief": "AI reviewed the full quant packet.",
                    "highest_priority_action": {"symbol": "FXE", "action": "BUY", "reason": "Model liked it."},
                    "approved_actions": [{"symbol": "FXE", "action": "BUY", "reason": "Approve despite risk gate."}],
                    "concerns": ["Sample data should lower confidence."],
                    "rejected_or_blocked_ideas": [],
                    "missing_data": [],
                    "what_would_change_my_mind": ["Fresh provider data changes the score."],
                }
            ),
            "usage": {"input_tokens": 321, "output_tokens": 123, "total_tokens": 444},
        }

    monkeypatch.setattr(advisor_intelligence, "_call_openai_response", fake_response)
    monkeypatch.setattr(ai_service, "_call_openai_response", fake_response)

    from app.database import get_conn
    from app.main import app

    with TestClient(app) as client:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO recommendations
                (symbol, action, target_weight, confidence, expected_return, risk_score, status, reason,
                 source_data_age_days, portfolio_impact, risk_flags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "FXE",
                    "AVOID",
                    0.0,
                    0.25,
                    -0.05,
                    0.9,
                    "fail",
                    "Fixture fail gate.",
                    12,
                    json.dumps({"target_weight": 0, "price_source": "sample", "data_confidence": "sample_only"}),
                    json.dumps(["Fixture risk gate failure."]),
                ),
            )

        response = client.post("/api/advisor/review")
        assert response.status_code == 200
        review = response.json()["advisor_review"]

    review_payload = next(payload for payload in seen_payloads if payload["max_output_tokens"] == 2500)
    packet = json.loads(review_payload["input"])
    assert review_payload["model"] == "gpt-5.5"
    assert review_payload["reasoning"] == {"effort": "medium"}
    assert "risk gates" in review_payload["instructions"]
    assert any(tool["name"] == "risk_gates" for tool in packet["tool_inventory"])
    assert packet["risk_rules"]["max_single_stock_weight"] == 0.15
    assert packet["data_quality"]["confidence"] == "sample_only"
    assert review["status"] == "success"
    assert not any(item.get("symbol") == "FXE" for item in review["approved_actions"])
    assert any(item.get("symbol") == "FXE" and item.get("quant_status") == "fail" for item in review["rejected_or_blocked_ideas"])
    assert review["total_tokens"] == 444


def test_copilot_uses_advisor_packet_and_records_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import copilot_service

    seen_payloads = []

    def fake_response(payload, api_key):
        seen_payloads.append(payload)
        context = json.loads(payload["input"])
        assert api_key == "test-key"
        assert context["question"] == "What assets did you consider?"
        assert "advisor_packet" in context
        assert any(tool["name"] == "risk_gates" for tool in context["advisor_packet"]["tool_inventory"])
        return {
            "id": "resp_copilot",
            "output_text": json.dumps(
                {
                    "answer": "The advisor considered the enabled market universe and strategy sleeves.",
                    "data_used": ["advisor packet", "market universe"],
                    "limitations": ["No invented data."],
                    "suggested_followups": ["What is blocked?"],
                }
            ),
            "usage": {"input_tokens": 222, "output_tokens": 44, "total_tokens": 266},
        }

    monkeypatch.setattr(copilot_service, "_call_openai_response", fake_response)

    from app.main import app

    with TestClient(app) as client:
        response = client.post("/api/ai/copilot", json={"question": "What assets did you consider?", "screen_context": "now"})
        assert response.status_code == 200
        body = response.json()
        dashboard = client.get("/api/dashboard").json()

    payload = seen_payloads[0]
    assert payload["model"] == "gpt-5.4-mini"
    assert payload["max_output_tokens"] == 800
    assert payload["reasoning"] == {"effort": "low"}
    assert body["status"] == "success"
    assert body["total_tokens"] == 266
    assert body["packet_hash"]
    assert dashboard["ai_activity"] == "reviewed"


def test_auto_brief_dedupes_by_packet_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import advisor_intelligence, ai_service

    review_calls = []

    def connection_response(payload, api_key):
        return {
            "id": "resp_connection",
            "output_text": "{\"status\":\"ok\",\"message\":\"connected\"}",
            "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
        }

    def review_response(payload, api_key):
        review_calls.append(payload)
        return {
            "id": "resp_review",
            "output_text": json.dumps(
                {
                    "brief": "Reviewed once.",
                    "highest_priority_action": {},
                    "approved_actions": [],
                    "concerns": [],
                    "rejected_or_blocked_ideas": [],
                    "missing_data": [],
                    "what_would_change_my_mind": [],
                }
            ),
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }

    monkeypatch.setattr(ai_service, "_call_openai_response", connection_response)
    monkeypatch.setattr(advisor_intelligence, "_call_openai_response", review_response)

    from app.main import app

    with TestClient(app) as client:
        first = client.post("/api/settings/connections/test", json={"provider": "openai"})
        second = client.post("/api/settings/connections/test", json={"provider": "openai"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["advisor_auto_review"]["ran"] is True
    assert second.json()["advisor_auto_review"]["ran"] is False
    assert len(review_calls) == 1


def test_connection_secrets_are_masked_and_never_returned(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn
    from app.main import app

    raw_key = "sk-local-secret-key-000000000000"
    with TestClient(app) as client:
        saved = client.put("/api/settings/secrets", json={"provider": "openai", "values": {"openai_api_key": raw_key}})
        assert saved.status_code == 200
        connections = client.get("/api/settings/connections").json()
        dashboard = client.get("/api/dashboard").json()
        with get_conn() as conn:
            stored = conn.execute("SELECT value FROM local_secrets WHERE provider = 'openai'").fetchone()["value"]

    combined = json.dumps({"saved": saved.json(), "connections": connections, "dashboard": dashboard})
    assert raw_key not in combined
    assert raw_key not in stored
    assert stored.startswith("fernet:")
    openai = next(provider for provider in connections["providers"] if provider["provider"] == "openai")
    assert openai["configured"] is True
    assert openai["fields"][0]["masked_value"].startswith("sk-l")
    assert openai["fields"][0]["source"] == "local"


def test_local_encrypted_secret_overrides_env_and_records_connection_test(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-secret-key-000000000000")

    from app.config import get_settings

    get_settings.cache_clear()
    from app.services import ai_service

    seen_keys = []

    def fake_response(payload, api_key):
        seen_keys.append(api_key)
        return {
            "id": "resp_connection",
            "output_text": "{\"status\":\"ok\",\"message\":\"connected\"}",
            "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
        }

    monkeypatch.setattr(ai_service, "_call_openai_response", fake_response)

    from app.main import app

    local_key = "sk-local-priority-key-000000000000"
    with TestClient(app) as client:
        saved = client.put("/api/settings/secrets", json={"provider": "openai", "values": {"openai_api_key": local_key}})
        assert saved.status_code == 200
        seen_keys.clear()
        tested = client.post("/api/settings/connections/test", json={"provider": "openai"})
        assert tested.status_code == 200
        connections = client.get("/api/settings/connections").json()

    assert seen_keys == [local_key]
    openai = next(provider for provider in connections["providers"] if provider["provider"] == "openai")
    assert openai["last_test"]["status"] == "success"
    assert openai["last_test"]["records"] == 1


def test_legacy_plaintext_secret_is_migrated_to_encrypted_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.main import app

    raw_key = "sk-legacy-secret-key-000000000000"
    init_db()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO local_secrets (provider, key, value) VALUES (?, ?, ?)",
            ("openai", "openai_api_key", raw_key),
        )

    with TestClient(app) as client:
        connections = client.get("/api/settings/connections").json()

    with get_conn() as conn:
        stored = conn.execute("SELECT value FROM local_secrets WHERE provider = 'openai'").fetchone()["value"]

    combined = json.dumps(connections)
    assert raw_key not in combined
    assert raw_key not in stored
    assert stored.startswith("fernet:")
