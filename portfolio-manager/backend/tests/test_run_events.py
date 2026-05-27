from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app
from app.services import run_events


@pytest.fixture(autouse=True)
def _reset_bus():
    run_events.reset_for_tests()
    yield
    run_events.reset_for_tests()


def test_publish_assigns_monotonic_event_ids_and_records_history():
    a = run_events.publish(
        7,
        type="run",
        phase="lifecycle",
        status="running",
        title="Advisor run started",
        detail="Trigger: manual.",
    )
    b = run_events.publish(
        7,
        type="step",
        phase="universe",
        status="running",
        title="Universe screened",
        detail="Checking tradable universe and coverage.",
    )
    c = run_events.publish(
        7,
        type="step",
        phase="universe",
        status="success",
        title="Universe screened",
        detail="Universe refreshed.",
        metrics={"records": 12500},
    )

    assert [event.event_id for event in (a, b, c)] == [1, 2, 3]
    history = run_events.history_as_dicts(7)
    assert [event["type"] for event in history] == ["run", "step", "step"]
    assert history[2]["metrics"]["records"] == 12500
    assert not run_events.is_closed(7)


def test_terminal_event_marks_run_closed_and_terminates_stream():
    run_events.publish(11, type="run", phase="lifecycle", status="running", title="run started")
    run_events.publish(11, type="step", phase="universe", status="success", title="Universe screened")
    run_events.publish(11, type="run", phase="lifecycle", status="success", title="Advisor run finished")

    assert run_events.is_closed(11)
    collected = []
    for event in run_events.stream(11, heartbeat_seconds=0.05):
        if event is None:
            break
        collected.append(event)
    assert [event.type for event in collected] == ["run", "step", "run"]
    assert collected[-1].status == "success"


def test_sse_endpoint_streams_existing_history_for_terminal_run():
    init_db()
    client = TestClient(app)

    with client:
        with client as session:
            seed = session.post("/api/advisor/runs").json()
        run_id = int(seed["run_id"])

        run_events.publish(
            run_id,
            type="step",
            phase="universe",
            status="success",
            title="Universe screened",
            detail="OK",
            metrics={"records": 1},
        )
        run_events.publish(
            run_id,
            type="run",
            phase="lifecycle",
            status="success",
            title="Advisor run finished",
            detail="ok",
        )

        with client.stream("GET", f"/api/advisor/runs/{run_id}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = b"".join(chunk for chunk in response.iter_bytes()).decode("utf-8")

    assert "event: step" in body
    assert "event: run" in body
    assert "event: end" in body
    data_lines = [line[6:] for line in body.splitlines() if line.startswith("data: ") and line[6:].strip() != "{}"]
    payloads = [json.loads(line) for line in data_lines]
    assert any(item["title"] == "Universe screened" and item["type"] == "step" for item in payloads)
    assert any(item["status"] == "success" and item["type"] == "run" for item in payloads)


def test_sse_endpoint_returns_404_for_unknown_run():
    init_db()
    client = TestClient(app)
    response = client.get("/api/advisor/runs/9999999/events")
    assert response.status_code == 404
