from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import Request

from src.config import Settings
from src.main import create_app
from src.models import DebugIncidentRequest
from src.storage import IncidentBroker, IncidentStore


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
        ide_auto_launch=False,
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
async def test_publish_pipeline_upserts_state(tmp_path: Path) -> None:
    store = IncidentStore(tmp_path / "store.db")
    await store.initialize()
    broker = IncidentBroker(store=store)

    await broker.publish_pipeline(
        incident_id="abc",
        event_type="pipeline.step",
        payload={"step": "analyze", "status": "running"},
    )
    row = await store.get_pipeline_state("abc")
    assert row is not None
    assert row.phase == "running"
    assert row.step == "analyze"
    assert row.status == "running"
    first_updated_at = row.updated_at

    await asyncio.sleep(0.01)
    await broker.publish_pipeline(
        incident_id="abc",
        event_type="pipeline.completed",
        payload={
            "prUrl": "https://github.com/owner/repo/pull/1",
            "prNumber": 1,
            "branch": "secureloop/abc",
            "localArtifactPath": "/tmp/out/pr-abc",
        },
    )
    row = await store.get_pipeline_state("abc")
    assert row is not None
    assert row.phase == "completed"
    assert row.pr_url == "https://github.com/owner/repo/pull/1"
    assert row.pr_number == 1
    assert row.branch == "secureloop/abc"
    assert row.local_artifact_path == "/tmp/out/pr-abc"
    assert row.step is None
    assert row.status is None
    assert row.updated_at >= first_updated_at


@pytest.mark.asyncio
async def test_publish_pipeline_failed_preserves_error(tmp_path: Path) -> None:
    store = IncidentStore(tmp_path / "store.db")
    await store.initialize()
    broker = IncidentBroker(store=store)

    await broker.publish_pipeline(
        incident_id="xyz",
        event_type="pipeline.failed",
        payload={"error": "boom"},
    )
    row = await store.get_pipeline_state("xyz")
    assert row is not None
    assert row.phase == "failed"
    assert row.error == "boom"


@pytest.mark.asyncio
async def test_sse_stream_replays_pipeline_state_before_live(app) -> None:
    await app.state.store.initialize()

    seed_incident = DebugIncidentRequest(issue_id="snap-complete").to_incident()
    await app.state.store.put_if_absent(seed_incident)
    await app.state.broker.publish_pipeline(
        incident_id=seed_incident.incident_id,
        event_type="pipeline.completed",
        payload={
            "prUrl": "https://github.com/owner/repo/pull/7",
            "prNumber": 7,
            "branch": "secureloop/snap-complete",
        },
    )

    route = next(
        r for r in app.routes
        if getattr(r, "path", None) == "/dashboard/events/stream"
        and "GET" in getattr(r, "methods", set())
    )
    response = await route.endpoint(_build_dashboard_request(app))  # type: ignore[attr-defined]
    iterator = response.body_iterator

    first_frame = await asyncio.wait_for(iterator.__anext__(), timeout=2.0)
    first_name, first_body = _parse_frame(first_frame)
    assert first_name == "incident.created"
    assert first_body["incident"]["incidentId"] == seed_incident.incident_id

    second_frame = await asyncio.wait_for(iterator.__anext__(), timeout=2.0)
    second_name, second_body = _parse_frame(second_frame)
    assert second_name == "pipeline.completed"
    assert second_body["incidentId"] == seed_incident.incident_id
    assert second_body["prUrl"] == "https://github.com/owner/repo/pull/7"
    assert second_body["prNumber"] == 7
    assert second_body["error"] is None

    await iterator.aclose()


@pytest.mark.asyncio
async def test_sse_stream_no_pipeline_state_yields_no_replay(app) -> None:
    await app.state.store.initialize()

    seed_incident = DebugIncidentRequest(issue_id="snap-no-pipeline").to_incident()
    await app.state.store.put_if_absent(seed_incident)

    route = next(
        r for r in app.routes
        if getattr(r, "path", None) == "/dashboard/events/stream"
        and "GET" in getattr(r, "methods", set())
    )
    response = await route.endpoint(_build_dashboard_request(app))  # type: ignore[attr-defined]
    iterator = response.body_iterator

    first_frame = await asyncio.wait_for(iterator.__anext__(), timeout=2.0)
    first_name, _ = _parse_frame(first_frame)
    assert first_name == "incident.created"

    # Kick off the next __anext__; let the generator progress past the pipeline
    # snapshot block and register as a broker subscriber.
    live_task = asyncio.create_task(iterator.__anext__())
    for _ in range(100):
        await asyncio.sleep(0.01)
        if app.state.broker._subscribers:  # type: ignore[attr-defined]
            break
    assert app.state.broker._subscribers, "generator failed to subscribe"  # type: ignore[attr-defined]

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(live_task), timeout=0.3)

    live_task.cancel()
    try:
        await live_task
    except (asyncio.CancelledError, BaseException):
        pass
    await iterator.aclose()


@pytest.mark.asyncio
async def test_pipeline_store_upsert_survives_sqlite_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = IncidentStore(tmp_path / "store.db")
    await store.initialize()
    broker = IncidentBroker(store=store)

    queue = await broker.subscribe()

    async def _boom(**_: object) -> None:
        raise RuntimeError("sqlite is down")

    monkeypatch.setattr(store, "upsert_pipeline_state", _boom)

    subscribers = await broker.publish_pipeline(
        incident_id="resilient",
        event_type="pipeline.step",
        payload={"step": "analyze", "status": "running"},
    )
    assert subscribers == 1

    delivered = queue.get_nowait()
    envelope = json.loads(delivered)
    assert envelope["type"] == "pipeline.step"
    assert envelope["pipeline"]["incidentId"] == "resilient"

    await broker.unsubscribe(queue)


@pytest.mark.asyncio
async def test_get_pipeline_state_endpoint_returns_row(app) -> None:
    await app.state.store.initialize()

    seed_incident = DebugIncidentRequest(issue_id="endpoint").to_incident()
    await app.state.store.put_if_absent(seed_incident)
    await app.state.broker.publish_pipeline(
        incident_id=seed_incident.incident_id,
        event_type="pipeline.step",
        payload={"step": "analyze", "status": "running"},
    )

    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/incidents/{seed_incident.incident_id}/pipeline-state"
        )
    assert response.status_code == 200
    body = response.json()
    assert body is not None
    assert body["incidentId"] == seed_incident.incident_id
    assert body["phase"] == "running"
    assert body["step"] == "analyze"
    assert body["status"] == "running"


@pytest.mark.asyncio
async def test_get_pipeline_state_endpoint_returns_null_when_absent(app) -> None:
    await app.state.store.initialize()

    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/incidents/does-not-exist/pipeline-state")
    assert response.status_code == 200
    assert response.json() is None
