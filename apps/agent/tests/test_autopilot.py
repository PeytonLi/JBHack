from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import src.autopilot as autopilot_module
from src.autopilot import (
    apply_patch_to_file,
    extract_source_window,
    run_autopilot,
)
from src.codex_analysis import GeneratedSandboxTest, SandboxTestGenerationError
from src.config import Settings
from src.github_client import FetchedFile, PullRequestResult
from src.main import create_app
from src.models import (
    AnalyzeIncidentResponse,
    AnalyzePatch,
    NormalizedIncident,
)
from src.sandbox_runner import SandboxResult


def _settings(tmp_path: Path) -> Settings:
    ide_token_file = tmp_path / "ide-token"
    ide_token_file.write_text("ide-token", encoding="utf-8")
    return Settings(
        sentry_auth_token="t",
        sentry_webhook_secret="s",
        allow_debug_endpoints=True,
        secure_loop_home=tmp_path,
        sqlite_path=tmp_path / "ingress.db",
        ide_token_file=ide_token_file,
        ide_token="ide-token",
        agent_port=8001,
        github_token="gh",
        github_repo="acme/demo",
        openai_api_key="sk-test",
    )


def _incident(**overrides: object) -> NormalizedIncident:
    payload = {
        "incident_id": "inc-1",
        "sentry_event_id": "inc-1",
        "issue_id": "42",
        "title": "KeyError: 999",
        "exception_type": "KeyError",
        "exception_message": "999",
        "repo_relative_path": "apps/target/src/main.py",
        "original_frame_path": "apps/target/src/main.py",
        "line_number": 3,
        "function_name": "checkout",
        "code_context": "warehouse_name = WAREHOUSES[warehouse_id]",
        "event_web_url": "https://sentry.example/events/abc",
    }
    payload.update(overrides)
    return NormalizedIncident(**payload)


def _fake_analysis() -> AnalyzeIncidentResponse:
    return AnalyzeIncidentResponse(
        severity="Medium",
        category="Unhandled exception",
        cwe="CWE-703",
        title="Guard warehouse",
        explanation="...",
        violated_policy=["rule"],
        fix_plan=["step"],
        diff="--- a\n+++ b\n@@\n-old\n+new",
        patch=AnalyzePatch(
            repo_relative_path="apps/target/src/main.py",
            old_text="OLD",
            new_text="NEW",
        ),
    )


def test_extract_source_window_clips_around_line() -> None:
    text = "\n".join(f"line{i}" for i in range(20))
    window = extract_source_window(text, line=10, radius=2)
    assert window.splitlines() == ["line7", "line8", "line9", "line10", "line11"]


def test_apply_patch_to_file_exact_match() -> None:
    file_text = "a\nOLD\nb\n"
    patch = AnalyzePatch(repo_relative_path="f", old_text="OLD", new_text="NEW")
    assert apply_patch_to_file(file_text, patch) == "a\nNEW\nb\n"


def test_apply_patch_to_file_whitespace_tolerant() -> None:
    file_text = "a\n    OLD   \nb\n"
    patch = AnalyzePatch(repo_relative_path="f", old_text="    OLD", new_text="    NEW")
    assert "    NEW" in apply_patch_to_file(file_text, patch)


def test_apply_patch_to_file_raises_on_mismatch() -> None:
    patch = AnalyzePatch(repo_relative_path="f", old_text="DOES_NOT_EXIST", new_text="NEW")
    with pytest.raises(ValueError):
        apply_patch_to_file("hello world", patch)


async def _collect_pipeline_events(broker, deadline: float = 0.5) -> list[dict]:
    queue = await broker.subscribe()
    events: list[dict] = []
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=deadline)
            except asyncio.TimeoutError:
                break
            envelope = json.loads(payload)
            if envelope.get("type", "").startswith("pipeline."):
                events.append(envelope)
    finally:
        await broker.unsubscribe(queue)
    return events


def _ok_sandbox_result() -> SandboxResult:
    return SandboxResult(
        reproduced_bug=True,
        fix_passes=True,
        original_exit_code=1,
        patched_exit_code=0,
        original_stdout="1 failed",
        original_stderr="",
        patched_stdout="1 passed",
        patched_stderr="",
        elapsed_s=0.01,
    )


def _fake_generated_test() -> GeneratedSandboxTest:
    return GeneratedSandboxTest(
        test_file_relative_path="tests/autopilot/test_inc_inc-1.py",
        test_code="def test_sample():\n    assert True\n",
        rationale="demo",
    )


@pytest.fixture
def app_and_patches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = _settings(tmp_path)
    app = create_app(settings)
    monkeypatch.setattr(autopilot_module, "load_policy_text", lambda: "policy")

    async def fake_fetch(*, token: str, repo: str, path: str) -> FetchedFile:
        return FetchedFile(content="line1\nOLD\nline3\n", sha="s", ref="main", path=path)

    captured: dict[str, object] = {}

    async def fake_open_pr(
        *,
        token,
        repo,
        incident_id,
        analysis,
        relative_path,
        updated_file_content,
        extra_files=None,
    ) -> PullRequestResult:
        captured["extra_files"] = list(extra_files or [])
        return PullRequestResult(
            pr_url="https://github.com/acme/demo/pull/1",
            pr_number=1,
            branch="secureloop/inc-1",
        )

    async def fake_resolve(request):
        return _fake_analysis()

    async def fake_generate(**kwargs) -> GeneratedSandboxTest:
        return _fake_generated_test()

    async def fake_run_sandbox(**kwargs) -> SandboxResult:
        return _ok_sandbox_result()

    monkeypatch.setattr(autopilot_module, "_fetch_file_async", fake_fetch)
    monkeypatch.setattr(autopilot_module, "_open_pr_async", fake_open_pr)
    monkeypatch.setattr(autopilot_module, "_resolve_analysis", fake_resolve)
    monkeypatch.setattr(autopilot_module, "generate_sandbox_test", fake_generate)
    monkeypatch.setattr(autopilot_module, "run_sandbox_test", fake_run_sandbox)
    app.state.autopilot_captured = captured
    return app


@pytest.mark.asyncio
async def test_run_autopilot_happy_path(app_and_patches) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    events = []

    async def capture() -> None:
        events.extend(await _collect_pipeline_events(app.state.broker, deadline=0.3))

    consumer = asyncio.create_task(capture())
    await asyncio.sleep(0)
    await run_autopilot(app, "inc-1")
    await consumer

    types = [evt["type"] for evt in events]
    assert "pipeline.step" in types
    assert types[-1] == "pipeline.completed"
    steps = [evt["pipeline"]["step"] for evt in events if evt["type"] == "pipeline.step"]
    assert steps == ["fetch_source", "analyze", "sandbox", "open_pr"]
    completed = events[-1]["pipeline"]
    assert completed["prUrl"] == "https://github.com/acme/demo/pull/1"
    extra_files = app_and_patches.state.autopilot_captured["extra_files"]
    assert extra_files
    assert extra_files[0][0] == "tests/autopilot/test_inc_inc-1.py"


@pytest.mark.asyncio
async def test_run_autopilot_falls_back_to_local_artifacts_when_pr_open_fails(
    app_and_patches, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    import src.main as main_module

    monkeypatch.setattr(main_module, "_PR_ARTIFACTS_ROOT", tmp_path / "out")

    async def fake_open_pr_raises(**kwargs) -> PullRequestResult:
        raise RuntimeError("github boom")

    monkeypatch.setattr(autopilot_module, "_open_pr_async", fake_open_pr_raises)

    events: list[dict] = []

    async def capture() -> None:
        events.extend(await _collect_pipeline_events(app.state.broker, deadline=0.3))

    consumer = asyncio.create_task(capture())
    await asyncio.sleep(0)
    await run_autopilot(app, "inc-1")
    await consumer

    assert events[-1]["type"] == "pipeline.completed"
    payload = events[-1]["pipeline"]
    assert payload["prUrl"] is None
    assert payload["prNumber"] is None
    assert payload["branch"] is None
    assert payload["error"] == "github boom"
    artifact_dir = Path(payload["localArtifactPath"])
    assert str(tmp_path) in str(artifact_dir)
    assert (artifact_dir / "fix.patch").exists()
    assert (artifact_dir / "COE.md").exists()
    assert (artifact_dir / "meta.json").exists()


@pytest.mark.asyncio
async def test_run_autopilot_missing_source_metadata(app_and_patches) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident(repo_relative_path=None, line_number=None))

    events: list[dict] = []

    async def capture() -> None:
        events.extend(await _collect_pipeline_events(app.state.broker, deadline=0.3))

    consumer = asyncio.create_task(capture())
    await asyncio.sleep(0)
    await run_autopilot(app, "inc-1")
    await consumer

    assert any(
        evt["type"] == "pipeline.failed"
        and evt["pipeline"].get("reason") == "missing_source_metadata"
        for evt in events
    )


@pytest.mark.asyncio
async def test_run_autopilot_patch_mismatch(app_and_patches, monkeypatch: pytest.MonkeyPatch) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    async def fake_fetch(*, token: str, repo: str, path: str) -> FetchedFile:
        return FetchedFile(content="completely different contents", sha="s", ref="main", path=path)

    monkeypatch.setattr(autopilot_module, "_fetch_file_async", fake_fetch)

    events: list[dict] = []

    async def capture() -> None:
        events.extend(await _collect_pipeline_events(app.state.broker, deadline=0.3))

    consumer = asyncio.create_task(capture())
    await asyncio.sleep(0)
    await run_autopilot(app, "inc-1")
    await consumer

    assert any(
        evt["type"] == "pipeline.failed"
        and evt["pipeline"].get("reason") == "patch_mismatch"
        for evt in events
    )


@pytest.mark.asyncio
async def test_run_autopilot_reentry_lock_skips_duplicate(app_and_patches, monkeypatch: pytest.MonkeyPatch) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    start = asyncio.Event()
    finish = asyncio.Event()

    async def slow_fetch(*, token: str, repo: str, path: str) -> FetchedFile:
        start.set()
        await finish.wait()
        return FetchedFile(content="line1\nOLD\nline3\n", sha="s", ref="main", path=path)

    monkeypatch.setattr(autopilot_module, "_fetch_file_async", slow_fetch)

    first = asyncio.create_task(run_autopilot(app, "inc-1"))
    await start.wait()
    second_result = await run_autopilot(app, "inc-1")
    finish.set()
    await first

    assert second_result is None
    assert "inc-1" in app.state.autopilot_locks


async def _run_and_collect(app) -> list[dict]:
    events: list[dict] = []

    async def capture() -> None:
        events.extend(await _collect_pipeline_events(app.state.broker, deadline=0.3))

    consumer = asyncio.create_task(capture())
    await asyncio.sleep(0)
    await run_autopilot(app, "inc-1")
    await consumer
    return events


def _failure_reasons(events: list[dict]) -> list[str]:
    return [
        evt["pipeline"].get("reason")
        for evt in events
        if evt["type"] == "pipeline.failed"
    ]


@pytest.mark.asyncio
async def test_run_autopilot_sandbox_test_generation_failed(
    app_and_patches, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    async def failing_generate(**kwargs) -> GeneratedSandboxTest:
        raise SandboxTestGenerationError("codex unavailable")

    monkeypatch.setattr(autopilot_module, "generate_sandbox_test", failing_generate)

    events = await _run_and_collect(app)
    assert "sandbox_test_generation_failed" in _failure_reasons(events)


@pytest.mark.asyncio
async def test_run_autopilot_sandbox_did_not_reproduce(
    app_and_patches, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    async def not_reproduced(**kwargs) -> SandboxResult:
        return SandboxResult(
            reproduced_bug=False,
            fix_passes=True,
            original_exit_code=0,
            patched_exit_code=0,
            original_stdout="",
            original_stderr="",
            patched_stdout="",
            patched_stderr="",
            elapsed_s=0.01,
        )

    monkeypatch.setattr(autopilot_module, "run_sandbox_test", not_reproduced)
    events = await _run_and_collect(app)
    assert "sandbox_did_not_reproduce" in _failure_reasons(events)


@pytest.mark.asyncio
async def test_run_autopilot_sandbox_fix_failed(
    app_and_patches, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    async def fix_failed(**kwargs) -> SandboxResult:
        return SandboxResult(
            reproduced_bug=True,
            fix_passes=False,
            original_exit_code=1,
            patched_exit_code=1,
            original_stdout="",
            original_stderr="",
            patched_stdout="",
            patched_stderr="still failing",
            elapsed_s=0.01,
        )

    monkeypatch.setattr(autopilot_module, "run_sandbox_test", fix_failed)
    events = await _run_and_collect(app)
    assert "sandbox_fix_failed" in _failure_reasons(events)


@pytest.mark.asyncio
async def test_run_autopilot_sandbox_timeout(
    app_and_patches, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    async def timed_out(**kwargs) -> SandboxResult:
        return SandboxResult(
            reproduced_bug=False,
            fix_passes=False,
            original_exit_code=-1,
            patched_exit_code=-1,
            original_stdout="",
            original_stderr="TIMEOUT",
            patched_stdout="",
            patched_stderr="TIMEOUT",
            elapsed_s=30.0,
            timed_out=True,
        )

    monkeypatch.setattr(autopilot_module, "run_sandbox_test", timed_out)
    events = await _run_and_collect(app)
    assert "sandbox_timeout" in _failure_reasons(events)


@pytest.mark.asyncio
async def test_run_autopilot_sandbox_disabled_via_env(
    app_and_patches, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(_incident())

    monkeypatch.setenv("SECURE_LOOP_AUTOPILOT_SANDBOX_DISABLED", "1")

    events = await _run_and_collect(app)
    steps = [evt["pipeline"]["step"] for evt in events if evt["type"] == "pipeline.step"]
    assert steps == ["fetch_source", "analyze", "open_pr"]
    assert events[-1]["type"] == "pipeline.completed"


@pytest.mark.asyncio
async def test_run_autopilot_skips_sandbox_on_non_python(
    app_and_patches, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = app_and_patches
    await app.state.store.initialize()
    await app.state.store.put_if_absent(
        _incident(
            repo_relative_path="apps/target/src/app.ts",
            original_frame_path="apps/target/src/app.ts",
        )
    )

    generate_calls: list[dict] = []
    sandbox_calls: list[dict] = []

    async def spy_generate(**kwargs) -> GeneratedSandboxTest:
        generate_calls.append(kwargs)
        return _fake_generated_test()

    async def spy_run_sandbox(**kwargs) -> SandboxResult:
        sandbox_calls.append(kwargs)
        return _ok_sandbox_result()

    monkeypatch.setattr(autopilot_module, "generate_sandbox_test", spy_generate)
    monkeypatch.setattr(autopilot_module, "run_sandbox_test", spy_run_sandbox)

    events = await _run_and_collect(app)
    steps = [evt["pipeline"]["step"] for evt in events if evt["type"] == "pipeline.step"]
    assert steps == ["fetch_source", "analyze", "open_pr"]
    assert events[-1]["type"] == "pipeline.completed"
    assert generate_calls == []
    assert sandbox_calls == []
