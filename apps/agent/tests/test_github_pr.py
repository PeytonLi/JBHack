from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import src.main as main_module
from src.config import Settings
from src.github_client import (
    PullRequestResult,
    build_commit_message,
    build_pr_body,
)
from src.main import create_app
from src.models import AnalyzeIncidentResponse, AnalyzePatch, DepCheckResult, DepVuln


def _sample_analysis() -> AnalyzeIncidentResponse:
    return AnalyzeIncidentResponse(
        severity="Medium",
        category="Unhandled exception",
        cwe="CWE-703",
        title="Guard warehouse lookup",
        explanation="KeyError when warehouse_id is absent.",
        violated_policy=["Do not expose stack traces."],
        fix_plan=["Guard the lookup.", "Return a controlled error."],
        diff="--- a/foo.py\n+++ b/foo.py\n@@\n-old\n+new\n",
        patch=AnalyzePatch(
            repo_relative_path="apps/target/src/main.py",
            old_text="old",
            new_text="new",
        ),
        reasoning_steps=["Observed KeyError", "Chose guarded lookup"],
        dep_check=DepCheckResult(
            scanner="pip-audit",
            vulnerabilities=[
                DepVuln(
                    id="PYSEC-2018-28",
                    severity="unknown",
                    package="requests",
                    version="2.19.0",
                    fixed_version="2.20.0",
                    summary="CRLF injection in requests.",
                )
            ],
            scanned_at=datetime.now(UTC),
        ),
    )


def test_build_commit_message_formats_cwe_and_path() -> None:
    msg = build_commit_message(_sample_analysis(), "apps/target/src/main.py")
    assert msg.startswith("fix(security): CWE-703 ")
    assert "apps/target/src/main.py" in msg


def test_build_pr_body_includes_sections() -> None:
    body = build_pr_body("incident-1", _sample_analysis())
    assert "**Severity:** Medium" in body
    assert "**CWE:** CWE-703" in body
    assert "Guard the lookup." in body
    assert "PYSEC-2018-28" in body
    assert "`incident-1`" in body


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    monkeypatch.setattr(main_module, "_PR_ARTIFACTS_ROOT", tmp_path / "out")
    return create_app(settings)


async def _initialize_store(app) -> None:
    await app.state.store.initialize()


async def _seed_analysis(app, incident_id: str) -> None:
    await _initialize_store(app)
    await app.state.store.put_analysis(incident_id, _sample_analysis())


@pytest.mark.asyncio
async def test_open_pr_requires_authorization(app) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ide/events/abc/open-pr",
            json={"updatedFileContent": "new"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_open_pr_returns_404_without_stored_analysis(app) -> None:
    await _initialize_store(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ide/events/missing/open-pr",
            json={"updatedFileContent": "new"},
            headers={"authorization": "Bearer ide-token"},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_open_pr_falls_back_to_local_artifacts_without_github_env(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    await _seed_analysis(app, "inc-1")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ide/events/inc-1/open-pr",
            json={"updatedFileContent": "the full updated file"},
            headers={"authorization": "Bearer ide-token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prUrl"] is None
    assert payload["localArtifactPath"]
    assert "GITHUB_TOKEN" in payload["error"]
    out_dir = Path(payload["localArtifactPath"])
    assert (out_dir / "fix.patch").exists()
    assert (out_dir / "COE.md").exists()
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["commitMessage"].startswith("fix(security): CWE-703 ")


@pytest.mark.asyncio
async def test_open_pr_uses_github_client_when_configured(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPO", "acme/repo")
    await _seed_analysis(app, "inc-2")

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, token: str, repo: str) -> None:
            captured["token"] = token
            captured["repo"] = repo

        def open_pr_for_incident(self, **kwargs: object) -> PullRequestResult:
            captured.update(kwargs)
            return PullRequestResult(
                pr_url="https://github.com/acme/repo/pull/7",
                pr_number=7,
                branch="secureloop/inc-2",
            )

    monkeypatch.setattr(main_module, "GitHubClient", FakeClient)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ide/events/inc-2/open-pr",
            json={"updatedFileContent": "new content"},
            headers={"authorization": "Bearer ide-token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prUrl"] == "https://github.com/acme/repo/pull/7"
    assert payload["prNumber"] == 7
    assert captured["repo"] == "acme/repo"
    assert captured["incident_id"] == "inc-2"


@pytest.mark.asyncio
async def test_open_pr_falls_back_when_github_client_raises(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPO", "acme/repo")
    await _seed_analysis(app, "inc-3")

    class BrokenClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "GitHubClient", BrokenClient)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/ide/events/inc-3/open-pr",
            json={"updatedFileContent": "after"},
            headers={"authorization": "Bearer ide-token"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prUrl"] is None
    assert payload["error"] == "boom"
    assert payload["localArtifactPath"]
