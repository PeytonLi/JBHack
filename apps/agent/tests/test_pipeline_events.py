from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.main import create_app
from src.models import DebugIncidentRequest


@pytest.fixture
def app(tmp_path: Path):
    settings = Settings(
        sentry_auth_token="token",
        sentry_webhook_secret="secret",
        allow_debug_endpoints=True,
        secure_loop_home=tmp_path,
        sqlite_path=tmp_path / "ingress.db",
        ide_token_file=tmp_path / "ide-token",
        ide_token="ide-token",
        agent_port=8001,
    )
    settings.ide_token_file.write_text(settings.ide_token, encoding="utf-8")
    return create_app(settings)


def _build_dashboard_request(app) -> Request:
    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/dashboard/events/stream",
        "headers": [],
        "query_string": b"",
        "raw_path": b"/dashboard/events/stream",
        "client": ("test", 1234),
        "server": ("test", 80),
        "scheme": "http",
        "app": app,
    }
    return Request(scope, receive)


def _parse_frame(frame: str) -> tuple[str, dict]:
    event_line = next(line for line in frame.splitlines() if line.startswith("event:"))
    data_line = next(line for line in frame.splitlines() if line.startswith("data:"))
    event_name = event_line[len("event: "):].strip()
    body = json.loads(data_line[len("data: "):])
    return event_name, body


@pytest.mark.asyncio
async def test_analyze_emits_pipeline_step_events(app) -> None:
    await app.state.store.initialize()

    # Seed one incident so the SSE snapshot produces a frame we can drain.
    # Draining guarantees the generator has progressed past ``broker.subscribe()``
    # before we trigger the analyze call that publishes pipeline events.
    seed_incident = DebugIncidentRequest(issue_id="pipeline-test").to_incident()
    await app.state.store.put_if_absent(seed_incident)

    route = next(
        r
        for r in app.routes
        if getattr(r, "path", None) == "/dashboard/events/stream"
        and "GET" in getattr(r, "methods", set())
    )
    response = await route.endpoint(_build_dashboard_request(app))  # type: ignore[attr-defined]
    iterator = response.body_iterator

    snapshot_frame = await asyncio.wait_for(iterator.__anext__(), timeout=2.0)
    assert "event: incident.created" in snapshot_frame

    # Register as broker subscriber by priming the next __anext__ call.
    live_task = asyncio.create_task(iterator.__anext__())
    for _ in range(20):
        await asyncio.sleep(0)
        if app.state.broker._subscribers:  # type: ignore[attr-defined]
            break
    assert app.state.broker._subscribers, "generator failed to subscribe"  # type: ignore[attr-defined]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        analyze_response = await client.post(
            "/ide/analyze",
            headers={"Authorization": "Bearer ide-token"},
            content=b"",
        )
    assert analyze_response.status_code == 200

    first_frame = await asyncio.wait_for(live_task, timeout=2.0)
    event_name, body = _parse_frame(first_frame)
    assert event_name == "pipeline.step"
    assert body["step"] == "analyzing"
    assert body["status"] == "running"
    assert body["incidentId"] == "debug-empty-analyze-body"

    second_frame = await asyncio.wait_for(iterator.__anext__(), timeout=2.0)
    event_name, body = _parse_frame(second_frame)
    assert event_name == "pipeline.step"
    assert body["step"] == "analyzing"
    assert body["status"] == "completed"
    assert body["incidentId"] == "debug-empty-analyze-body"

    await iterator.aclose()
