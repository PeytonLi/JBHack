from __future__ import annotations

import asyncio
import logging
import os
import traceback
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI

from .codex_analysis import (
    GeneratedSandboxTest,
    SandboxTestGenerationError,
    generate_sandbox_test,
)
from .config import Settings
from .github_client import FetchedFile, GitHubClient, PullRequestResult
from .models import (
    AnalyzeIncidentRequest,
    AnalyzeIncidentResponse,
    AnalyzePatch,
    NormalizedIncident,
)
from .sandbox_runner import SandboxResult, run_sandbox_test


logger = logging.getLogger("secureloop.agent.autopilot")

_BUNDLED_POLICY_PATH = Path(__file__).resolve().parent.parent / "resources" / "security-policy.md"


@lru_cache(maxsize=1)
def _cached_policy_text(path_str: str) -> str:
    return Path(path_str).read_text(encoding="utf-8")


def load_policy_text() -> str:
    override = os.environ.get("SECURELOOP_POLICY_PATH", "").strip()
    path = Path(override) if override else _BUNDLED_POLICY_PATH
    try:
        return _cached_policy_text(str(path))
    except FileNotFoundError:
        logger.warning("Security policy file missing at %s; using empty policy.", path)
        return ""


def extract_source_window(file_text: str, line: int, radius: int = 8) -> str:
    lines = file_text.splitlines()
    if not lines:
        return ""
    index = max(1, line) - 1
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    return "\n".join(lines[start:end])


def apply_patch_to_file(file_text: str, patch: AnalyzePatch) -> str:
    if patch.old_text in file_text:
        return file_text.replace(patch.old_text, patch.new_text, 1)

    normalized_file = "\n".join(line.rstrip() for line in file_text.splitlines())
    normalized_old = "\n".join(line.rstrip() for line in patch.old_text.splitlines())
    if normalized_old and normalized_old in normalized_file:
        logger.info("apply_patch_to_file: matched oldText after trailing-whitespace normalization.")
        patched = normalized_file.replace(normalized_old, patch.new_text, 1)
        if file_text.endswith("\n") and not patched.endswith("\n"):
            patched += "\n"
        return patched

    raise ValueError("patch_mismatch")


def build_analyze_request(
    incident: NormalizedIncident,
    source_context: str,
    policy_text: str,
) -> AnalyzeIncidentRequest:
    return AnalyzeIncidentRequest(
        incident_id=incident.incident_id,
        repo_relative_path=incident.repo_relative_path or "",
        line_number=incident.line_number or 1,
        exception_type=incident.exception_type,
        exception_message=incident.exception_message,
        title=incident.title,
        source_context=source_context,
        policy_text=policy_text,
    )


async def run_autopilot(app: FastAPI, incident_id: str) -> None:
    locks: dict[str, asyncio.Lock] = app.state.autopilot_locks
    lock = locks.get(incident_id)
    if lock is None:
        lock = asyncio.Lock()
        locks[incident_id] = lock
    if lock.locked():
        logger.info("autopilot: incident %s already running; skipping re-entry.", incident_id)
        return

    async with lock:
        try:
            await _run_autopilot_locked(app, incident_id)
        except Exception:
            tb = traceback.format_exc()
            logger.exception("autopilot: unexpected failure for incident %s.", incident_id)
            await app.state.broker.publish_pipeline(
                incident_id=incident_id,
                event_type="pipeline.failed",
                payload={"reason": "internal_error", "traceback": tb[-2000:]},
            )


async def _run_autopilot_locked(app: FastAPI, incident_id: str) -> None:
    settings: Settings = app.state.settings
    broker = app.state.broker
    store = app.state.store

    record = await store.get_record(incident_id)
    if record is None:
        await broker.publish_pipeline(
            incident_id=incident_id,
            event_type="pipeline.failed",
            payload={"reason": "incident_not_found"},
        )
        return

    incident = record.incident
    if not incident.repo_relative_path or incident.line_number is None:
        await broker.publish_pipeline(
            incident_id=incident_id,
            event_type="pipeline.failed",
            payload={"reason": "missing_source_metadata"},
        )
        return

    await broker.publish_pipeline(
        incident_id=incident_id,
        event_type="pipeline.step",
        payload={"step": "fetch_source"},
    )
    try:
        fetched = await _fetch_file_async(
            token=settings.github_token or "",
            repo=settings.github_repo or "",
            path=incident.repo_relative_path,
        )
    except FileNotFoundError:
        await broker.publish_pipeline(
            incident_id=incident_id,
            event_type="pipeline.failed",
            payload={"reason": "source_file_not_found", "path": incident.repo_relative_path},
        )
        return

    source_context = extract_source_window(fetched.content, incident.line_number)
    analyze_request = build_analyze_request(incident, source_context, load_policy_text())

    await broker.publish_pipeline(
        incident_id=incident_id,
        event_type="pipeline.step",
        payload={"step": "analyze"},
    )
    analysis = await _resolve_analysis(analyze_request)
    try:
        await store.put_analysis(incident_id, analysis)
    except Exception:
        logger.exception("autopilot: failed to persist analysis for %s.", incident_id)

    try:
        updated_content = apply_patch_to_file(fetched.content, analysis.patch)
    except ValueError:
        await broker.publish_pipeline(
            incident_id=incident_id,
            event_type="pipeline.failed",
            payload={"reason": "patch_mismatch"},
        )
        return

    extra_files: list[tuple[str, str]] = []
    if _sandbox_enabled() and (incident.repo_relative_path or "").endswith(".py"):
        await broker.publish_pipeline(
            incident_id=incident_id,
            event_type="pipeline.step",
            payload={"step": "sandbox"},
        )
        sandbox_outcome = await _run_sandbox_step(
            incident=incident,
            analysis=analysis,
            original_content=fetched.content,
            patched_content=updated_content,
        )
        if sandbox_outcome.failure_reason is not None:
            await broker.publish_pipeline(
                incident_id=incident_id,
                event_type="pipeline.failed",
                payload={
                    "reason": sandbox_outcome.failure_reason,
                    "detail": sandbox_outcome.failure_detail,
                },
            )
            return
        assert sandbox_outcome.generated is not None
        extra_files.append(
            (
                sandbox_outcome.generated.test_file_relative_path,
                sandbox_outcome.generated.test_code,
            )
        )

    await broker.publish_pipeline(
        incident_id=incident_id,
        event_type="pipeline.step",
        payload={"step": "open_pr"},
    )
    pr_result = await _open_pr_async(
        token=settings.github_token or "",
        repo=settings.github_repo or "",
        incident_id=incident_id,
        analysis=analysis,
        relative_path=incident.repo_relative_path,
        updated_file_content=updated_content,
        extra_files=extra_files,
    )
    await broker.publish_pipeline(
        incident_id=incident_id,
        event_type="pipeline.completed",
        payload={
            "prUrl": pr_result.pr_url,
            "prNumber": pr_result.pr_number,
            "branch": pr_result.branch,
            "localArtifactPath": pr_result.local_artifact_path,
            "error": pr_result.error,
        },
    )


async def _fetch_file_async(*, token: str, repo: str, path: str) -> FetchedFile:
    def _call() -> FetchedFile:
        client = GitHubClient(token, repo)
        return client.fetch_file(path)

    return await asyncio.to_thread(_call)


async def _open_pr_async(
    *,
    token: str,
    repo: str,
    incident_id: str,
    analysis: AnalyzeIncidentResponse,
    relative_path: str,
    updated_file_content: str,
    extra_files: list[tuple[str, str]] | None = None,
) -> PullRequestResult:
    def _call() -> PullRequestResult:
        client = GitHubClient(token, repo)
        return client.open_pr_for_incident(
            incident_id=incident_id,
            analysis=analysis,
            relative_path=relative_path,
            updated_file_content=updated_file_content,
            extra_files=extra_files,
        )

    return await asyncio.to_thread(_call)


async def _resolve_analysis(request: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    from .main import _resolve_analysis as resolve

    return await resolve(request)


def _sandbox_enabled() -> bool:
    disabled = os.environ.get("SECURE_LOOP_AUTOPILOT_SANDBOX_DISABLED", "").strip().lower()
    return disabled not in {"1", "true", "yes"}


@dataclass(frozen=True)
class _SandboxOutcome:
    generated: GeneratedSandboxTest | None
    result: SandboxResult | None
    failure_reason: str | None
    failure_detail: str | None


async def _run_sandbox_step(
    *,
    incident: NormalizedIncident,
    analysis: AnalyzeIncidentResponse,
    original_content: str,
    patched_content: str,
) -> _SandboxOutcome:
    try:
        generated = await generate_sandbox_test(
            incident_id=incident.incident_id,
            repo_relative_path=incident.repo_relative_path or "",
            line_number=incident.line_number or 1,
            exception_type=incident.exception_type,
            exception_message=incident.exception_message,
            title=incident.title,
            diff=analysis.diff,
            original_source=original_content,
            patched_source=patched_content,
        )
    except SandboxTestGenerationError as exc:
        logger.warning("autopilot: sandbox test generation failed: %s", exc)
        return _SandboxOutcome(
            generated=None,
            result=None,
            failure_reason="sandbox_test_generation_failed",
            failure_detail=str(exc),
        )

    try:
        result = await run_sandbox_test(
            original_content=original_content,
            patched_content=patched_content,
            repo_relative_path=incident.repo_relative_path or "",
            test_code=generated.test_code,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("autopilot: sandbox runner crashed.")
        return _SandboxOutcome(
            generated=generated,
            result=None,
            failure_reason="sandbox_runner_error",
            failure_detail=str(exc),
        )

    if result.timed_out:
        return _SandboxOutcome(
            generated=generated,
            result=result,
            failure_reason="sandbox_timeout",
            failure_detail=None,
        )
    if not result.reproduced_bug:
        return _SandboxOutcome(
            generated=generated,
            result=result,
            failure_reason="sandbox_did_not_reproduce",
            failure_detail=(result.original_stdout + result.original_stderr)[-800:],
        )
    if not result.fix_passes:
        return _SandboxOutcome(
            generated=generated,
            result=result,
            failure_reason="sandbox_fix_failed",
            failure_detail=(result.patched_stdout + result.patched_stderr)[-800:],
        )
    return _SandboxOutcome(
        generated=generated,
        result=result,
        failure_reason=None,
        failure_detail=None,
    )
