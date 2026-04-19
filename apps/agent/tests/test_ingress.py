from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.main import create_app
from src.models import normalize_sentry_event


class StubSentryClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def fetch_event(self, event_url: str) -> dict:
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
        ide_auto_launch=False,
    )
    settings.ide_token_file.write_text(settings.ide_token, encoding="utf-8")
    return create_app(settings, sentry_client=StubSentryClient(sample_event_payload()))


@pytest.mark.asyncio
async def test_signed_webhook_persists_and_acknowledges_incident(app) -> None:
    await app.state.store.initialize()
    body = json.dumps(sample_issue_alert_payload()).encode("utf-8")
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    queue = await app.state.broker.subscribe()

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/sentry/webhook",
                content=body,
                headers={
                    "content-type": "application/json",
                    "sentry-hook-resource": "event_alert",
                    "sentry-hook-signature": signature,
                },
            )
            assert response.status_code == 204
            created_frame = json.loads(queue.get_nowait())
            assert created_frame["type"] == "incident.created"

            incidents = await app.state.store.list_unreviewed()
            assert len(incidents) == 1
            assert incidents[0].repo_relative_path == "apps/target/src/main.py"
            assert incidents[0].sentry_status == "unresolved"

            feed_response = await client.get("/incidents?status=all")
            assert feed_response.status_code == 200
            feed = feed_response.json()
            assert feed["summary"]["openCount"] == 1
            assert feed["summary"]["reviewedCount"] == 0
            assert len(feed["incidents"]) == 1
            assert feed["incidents"][0]["status"] == "open"
            assert feed["incidents"][0]["incident"]["sentryStatus"] == "unresolved"

            ack_response = await client.post(
                f"/ide/events/{incidents[0].incident_id}/review",
                headers={"authorization": "Bearer ide-token"},
            )
            assert ack_response.status_code == 204
            updated_frame = json.loads(queue.get_nowait())
            assert updated_frame["type"] == "incident.updated"
            assert updated_frame["incident"]["status"] == "reviewed"
            assert await app.state.store.list_unreviewed() == []

            reviewed_feed_response = await client.get("/incidents?status=reviewed")
            assert reviewed_feed_response.status_code == 200
            reviewed_feed = reviewed_feed_response.json()
            assert reviewed_feed["summary"]["openCount"] == 0
            assert reviewed_feed["summary"]["reviewedCount"] == 1
            assert reviewed_feed["incidents"][0]["status"] == "reviewed"
    finally:
        await app.state.broker.unsubscribe(queue)


@pytest.mark.asyncio
async def test_debug_endpoint_creates_live_incident(app) -> None:
    await app.state.store.initialize()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/debug/incidents",
            json={
                "repoRelativePath": "apps/target/src/main.py",
                "lineNumber": 45,
                "exceptionType": "RuntimeError",
                "exceptionMessage": "debug smoke test",
            },
            headers={"authorization": "Bearer ide-token"},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["repoRelativePath"] == "apps/target/src/main.py"
        incidents = await app.state.store.list_unreviewed()
        assert len(incidents) == 1


@pytest.mark.asyncio
async def test_health_reports_demo_mode(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["allowDebugEndpoints"] is True
        assert payload["openIncidentCount"] == 0
        assert payload["reviewedIncidentCount"] == 0


@pytest.mark.asyncio
async def test_navigate_endpoint_404_for_unknown_incident(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ide/navigate",
            json={"incidentId": "does-not-exist"},
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_navigate_endpoint_returns_zero_subscribers_when_no_plugin_connected(
    app,
) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        seed_response = await client.post(
            "/debug/incidents",
            json={"repoRelativePath": "apps/target/src/main.py", "lineNumber": 45},
            headers={"authorization": "Bearer ide-token"},
        )
        assert seed_response.status_code == 201
        incident_id = seed_response.json()["incidentId"]

        response = await client.post(
            "/ide/navigate",
            json={"incidentId": incident_id},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload == {
            "delivered": False,
            "subscribers": 0,
            "incidentId": incident_id,
            "launched": False,
            "launchReason": "disabled",
        }
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )


@pytest.mark.asyncio
async def test_navigate_endpoint_cors_preflight(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options("/ide/navigate")
        assert response.status_code == 204
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )
        assert "POST" in response.headers.get("access-control-allow-methods", "")


async def _seed_incidents(client: AsyncClient) -> tuple[str, str]:
    first = await client.post(
        "/debug/incidents",
        json={"repoRelativePath": "apps/target/src/main.py", "lineNumber": 45},
        headers={"authorization": "Bearer ide-token"},
    )
    second = await client.post(
        "/debug/incidents",
        json={"repoRelativePath": "apps/target/src/main.py", "lineNumber": 88},
        headers={"authorization": "Bearer ide-token"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    return first.json()["incidentId"], second.json()["incidentId"]


@pytest.mark.asyncio
async def test_delete_incidents_all_clears_queue(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_id, second_id = await _seed_incidents(client)

        response = await client.delete("/incidents?status=all")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "all"
        assert payload["deletedCount"] == 2
        assert set(payload["incidentIds"]) == {first_id, second_id}
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )

        feed = (await client.get("/incidents?status=all")).json()
        assert feed["summary"]["totalCount"] == 0


@pytest.mark.asyncio
async def test_delete_incidents_reviewed_only(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_id, second_id = await _seed_incidents(client)
        await app.state.store.mark_reviewed(first_id)

        response = await client.delete("/incidents?status=reviewed")
        assert response.status_code == 200
        payload = response.json()
        assert payload["deletedCount"] == 1
        assert payload["incidentIds"] == [first_id]

        feed = (await client.get("/incidents?status=all")).json()
        assert feed["summary"]["openCount"] == 1
        assert feed["summary"]["reviewedCount"] == 0
        assert feed["incidents"][0]["incident"]["incidentId"] == second_id


@pytest.mark.asyncio
async def test_delete_incidents_open_only(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_id, second_id = await _seed_incidents(client)
        await app.state.store.mark_reviewed(first_id)

        response = await client.delete("/incidents?status=open")
        assert response.status_code == 200
        payload = response.json()
        assert payload["deletedCount"] == 1
        assert payload["incidentIds"] == [second_id]

        feed = (await client.get("/incidents?status=all")).json()
        assert feed["summary"]["openCount"] == 0
        assert feed["summary"]["reviewedCount"] == 1


@pytest.mark.asyncio
async def test_delete_incidents_rejects_unknown_status(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/incidents?status=bogus")
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_incidents_empty_queue(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/incidents?status=all")
        assert response.status_code == 200
        payload = response.json()
        assert payload["deletedCount"] == 0
        assert payload["incidentIds"] == []


@pytest.mark.asyncio
async def test_delete_incidents_cors_preflight(app) -> None:
    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options("/incidents")
        assert response.status_code == 204
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )
        methods = response.headers.get("access-control-allow-methods", "")
        assert "DELETE" in methods
        assert "GET" in methods


@pytest.mark.asyncio
async def test_delete_incidents_cascades_to_analysis_records(app) -> None:
    from src.models import AnalyzeIncidentResponse, AnalyzePatch

    await app.state.store.initialize()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first_id, _ = await _seed_incidents(client)
        analysis = AnalyzeIncidentResponse(
            severity="Low",
            category="test",
            cwe="CWE-000",
            title="noop",
            explanation="",
            violated_policy=[],
            fix_plan=[],
            diff="",
            patch=AnalyzePatch(
                repo_relative_path="apps/target/src/main.py",
                old_text="",
                new_text="",
            ),
        )
        await app.state.store.put_analysis(first_id, analysis)
        assert await app.state.store.get_analysis(first_id) is not None

        response = await client.delete("/incidents?status=all")
        assert response.status_code == 200
        assert await app.state.store.get_analysis(first_id) is None


def test_normalize_sentry_event_prefers_in_app_frame() -> None:
    incident = normalize_sentry_event(
        sample_issue_alert_payload_model(),
        sample_event_payload(),
    )
    assert incident.exception_type == "KeyError"
    assert incident.line_number == 45
    assert incident.repo_relative_path == "apps/target/src/main.py"


def sample_issue_alert_payload() -> dict:
    return {
        "action": "triggered",
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


def sample_issue_alert_payload_model():
    from src.models import IssueAlertWebhook

    return IssueAlertWebhook.model_validate(sample_issue_alert_payload())


def sample_event_payload() -> dict:
    return {
        "id": "abc123",
        "title": "KeyError: 999",
        "projectSlug": "autoscribe-target",
        "environment": "production",
        "permalink": "https://sentry.example/issues/42/events/abc123/",
        "entries": [
            {
                "type": "exception",
                "data": {
                    "values": [
                        {
                            "type": "KeyError",
                            "value": "999",
                            "stacktrace": {
                                "frames": [
                                    {
                                        "filename": "/opt/venv/lib/python3.13/site-packages/fastapi/routing.py",
                                        "function": "app",
                                        "lineno": 210,
                                        "in_app": False,
                                    },
                                    {
                                        "filename": "/workspace/JBHack/apps/target/src/main.py",
                                        "function": "checkout",
                                        "lineno": 45,
                                        "context_line": "warehouse_name = WAREHOUSES[warehouse_id]",
                                        "in_app": True,
                                    },
                                ]
                            },
                        }
                    ]
                },
            }
        ],
    }
