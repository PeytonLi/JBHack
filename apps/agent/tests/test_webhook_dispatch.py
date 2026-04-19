from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.main import create_app

from tests.test_ingress import sample_event_payload


class StubSentryClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def fetch_event(self, event_url: str) -> dict:
        return self._payload

    async def fetch_issue(self, issue_id: str) -> dict:
        return self._payload


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
    return create_app(settings, sentry_client=StubSentryClient(sample_event_payload()))


def _sign(body: bytes) -> str:
    return hmac.new(b"secret", body, hashlib.sha256).hexdigest()


def _post(client: AsyncClient, body: dict, resource: str):
    payload = json.dumps(body).encode("utf-8")
    return client.post(
        "/sentry/webhook",
        content=payload,
        headers={
            "content-type": "application/json",
            "sentry-hook-resource": resource,
            "sentry-hook-signature": _sign(payload),
        },
    )


def _issue_alert_body(action: str = "triggered") -> dict:
    return {
        "action": action,
        "data": {
            "event": {
                "url": "https://sentry.example/api/0/projects/acme/shop/events/abc123/",
                "web_url": "https://sentry.example/issues/42/events/abc123/",
                "issue_url": "https://sentry.example/api/0/issues/42/",
                "issue_id": "42",
            },
            "triggered_rule": "Prod checkout failure",
        },
    }


def _internal_issue_body(action: str, *, include_event: bool = True) -> dict:
    body: dict = {
        "action": action,
        "data": {
            "issue": {
                "id": "42",
                "status": {
                    "created": "unresolved",
                    "resolved": "resolved",
                    "unresolved": "unresolved",
                    "ignored": "ignored",
                    "assigned": "unresolved",
                }.get(action, "unresolved"),
                "assigned_to": {"name": "ada"} if action == "assigned" else None,
                "web_url": "https://sentry.example/issues/42/",
            },
        },
    }
    if include_event and action == "created":
        body["data"]["event"] = sample_event_payload()
    return body


def _internal_error_body() -> dict:
    return {"action": "created", "data": {"event": sample_event_payload()}}


@pytest.mark.asyncio
async def test_unknown_resource_returns_400(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _post(client, _issue_alert_body(), resource="project")
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_missing_signature_returns_401(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/sentry/webhook",
            content=json.dumps(_issue_alert_body()).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "sentry-hook-resource": "event_alert",
            },
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_event_alert_resolved_action_is_noop(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _post(
            client, _issue_alert_body(action="resolved"), resource="event_alert"
        )
        assert response.status_code == 204
        assert await app.state.store.list_unreviewed() == []


@pytest.mark.asyncio
async def test_internal_issue_created_persists_incident(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _post(client, _internal_issue_body("created"), "issue")
        assert response.status_code == 204
        incidents = await app.state.store.list_unreviewed()
        assert len(incidents) == 1
        assert incidents[0].sentry_status == "unresolved"


@pytest.mark.asyncio
async def test_internal_issue_resolved_updates_status(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    queue = await app.state.broker.subscribe()
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await _post(client, _internal_issue_body("created"), "issue")
            assert created.status_code == 204
            assert queue.qsize() == 1
            first = json.loads(queue.get_nowait())
            assert first["type"] == "incident.created"

            resolved = await _post(client, _internal_issue_body("resolved"), "issue")
            assert resolved.status_code == 204
            assert queue.qsize() == 1
            second = json.loads(queue.get_nowait())
            assert second["type"] == "incident.updated"
            assert second["incident"]["incident"]["sentryStatus"] == "resolved"

        records = await app.state.store.list_incidents(status="all")
        assert len(records) == 1
        assert records[0].incident.sentry_status == "resolved"
    finally:
        await app.state.broker.unsubscribe(queue)


@pytest.mark.asyncio
async def test_internal_issue_resolved_unknown_is_noop(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    queue = await app.state.broker.subscribe()
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await _post(client, _internal_issue_body("resolved"), "issue")
            assert response.status_code == 204
        assert queue.qsize() == 0
    finally:
        await app.state.broker.unsubscribe(queue)


@pytest.mark.asyncio
async def test_internal_error_created_is_idempotent(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await _post(client, _internal_error_body(), "error")
        second = await _post(client, _internal_error_body(), "error")
        assert first.status_code == 204
        assert second.status_code == 204
    incidents = await app.state.store.list_unreviewed()
    assert len(incidents) == 1
