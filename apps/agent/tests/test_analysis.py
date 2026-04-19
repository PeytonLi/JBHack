from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import src.main as main_module
from src.config import Settings
from src.main import create_app


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
async def test_ide_analyze_requires_authorization(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/ide/analyze", json=sample_analysis_request())
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ide_analyze_returns_fake_response_when_impl_is_unavailable(app, monkeypatch) -> None:
    monkeypatch.delenv("SECURE_LOOP_USE_FAKE_CODEX", raising=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ide/analyze",
            json=sample_analysis_request(),
            headers={"authorization": "Bearer ide-token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["severity"] == "Medium"
    assert payload["patch"]["oldText"] == "warehouse_name = WAREHOUSES[warehouse_id]"
    assert payload["patch"]["repoRelativePath"] == "apps/target/src/main.py"


@pytest.mark.asyncio
async def test_ide_analyze_returns_502_for_broken_teammate_impl(app, monkeypatch) -> None:
    monkeypatch.delenv("SECURE_LOOP_USE_FAKE_CODEX", raising=False)

    async def broken_analyze_incident(_payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "_resolve_analyze_impl", lambda: broken_analyze_incident)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ide/analyze",
            json=sample_analysis_request(),
            headers={"authorization": "Bearer ide-token"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "SecureLoop analysis request failed."


def sample_analysis_request() -> dict[str, object]:
    return {
        "incidentId": "debug-warehouse-45",
        "repoRelativePath": "apps/target/src/main.py",
        "lineNumber": 45,
        "exceptionType": "KeyError",
        "exceptionMessage": "999",
        "title": "Warehouse lookup crash",
        "sourceContext": "warehouse_name = WAREHOUSES[warehouse_id]",
        "policyText": "\n".join(
            [
                "# SecureLoop Security Policy",
                "",
                "## Error Handling",
                "- Do not expose stack traces or internal exception messages to end users.",
            ]
        ),
    }
