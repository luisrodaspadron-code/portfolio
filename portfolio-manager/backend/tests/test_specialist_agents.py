import json


def test_specialist_agents_do_not_reuse_sqlite_connection_across_threads(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "portfolio.sqlite"))
    from app.config import get_settings

    get_settings.cache_clear()
    from app.database import get_conn, init_db
    from app.services import specialist_agents

    init_db()

    def fake_response(payload, api_key):
        name = payload["text"]["format"]["name"]
        if name.endswith("macro"):
            body = {"regime": "test", "summary": "Macro ok.", "risks": [], "macroFitNotes": "No invented data."}
        elif name.endswith("fundamental"):
            body = {"summary": "Fundamentals ok.", "marginWarnings": [], "qualityFlags": []}
        else:
            body = {"summary": "Technicals ok.", "momentumNotes": [], "volFlags": []}
        return {
            "id": f"resp-{name}",
            "output_text": json.dumps(body),
            "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
        }

    monkeypatch.setattr(specialist_agents, "_effective_openai_api_key", lambda conn: "sk-test-thread-safe")
    monkeypatch.setattr(specialist_agents, "_call_openai_response", fake_response)

    with get_conn() as conn:
        summaries, tokens, warnings = specialist_agents.run_specialist_agents(
            conn,
            {"macro_regime": {}, "provider_freshness": {}},
            {"dataQualitySummary": {}, "topExposures": [], "eligibleCandidates": [], "hardBreaches": []},
        )
        calls = conn.execute("SELECT COUNT(*) AS count FROM ai_runs WHERE purpose LIKE 'specialist_%'").fetchone()["count"]

    assert set(summaries) == {"macro", "fundamental", "technical"}
    assert tokens["total_tokens"] == 21
    assert warnings == []
    assert calls == 3
