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


@pytest.mark.asyncio
async def test_dashboard_stream_snapshot_and_live_frames(app) -> None:
    """Drive the SSE generator directly to avoid ASGITransport body buffering."""
    await app.state.store.initialize()

    seed_request = DebugIncidentRequest(issue_id="alpha")
    seed_incident = seed_request.to_incident()
    await app.state.store.put_if_absent(seed_incident)

    route = next(
        r for r in app.routes if getattr(r, "path", None) == "/dashboard/events/stream"
        and "GET" in getattr(r, "methods", set())
    )

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
    request = Request(scope, receive)
    response = await route.endpoint(request)  # type: ignore[attr-defined]
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    iterator = response.body_iterator
    snapshot_frame = await asyncio.wait_for(iterator.__anext__(), timeout=2.0)
    assert "event: incident.created" in snapshot_frame
    snapshot_body = json.loads(
        [ln for ln in snapshot_frame.splitlines() if ln.startswith("data:")][0][
            len("data: "):
        ]
    )
    assert snapshot_body["incident"]["sentryStatus"] == "unresolved"

    # Kick off the next __anext__ so the generator registers as a broker subscriber,
    # then publish and await the live frame.
    live_task = asyncio.create_task(iterator.__anext__())
    for _ in range(10):
        await asyncio.sleep(0)
        if app.state.broker._subscribers:  # type: ignore[attr-defined]
            break

    updated = await app.state.store.update_sentry_status(
        issue_id="alpha", sentry_status="resolved"
    )
    assert updated
    for record in updated:
        await app.state.broker.publish(record, event_type="incident.updated")

    live_frame = await asyncio.wait_for(live_task, timeout=2.0)
    assert "event: incident.updated" in live_frame
    body_line = [line for line in live_frame.splitlines() if line.startswith("data:")][0]
    record = json.loads(body_line[len("data: "):])
    assert record["status"] == "open"
    assert record["incident"]["sentryStatus"] == "resolved"

    await iterator.aclose()


@pytest.mark.asyncio
async def test_dashboard_stream_preflight_returns_cors_headers(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options("/dashboard/events/stream")
        assert response.status_code == 204
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )
