from __future__ import annotations

import asyncio
import logging
import os
import traceback
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI

from .config import Settings
from .github_client import FetchedFile, GitHubClient, PullRequestResult
from .models import (
    AnalyzeIncidentRequest,
    AnalyzeIncidentResponse,
    AnalyzePatch,
    NormalizedIncident,
)


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
) -> PullRequestResult:
    def _call() -> PullRequestResult:
        client = GitHubClient(token, repo)
        return client.open_pr_for_incident(
            incident_id=incident_id,
            analysis=analysis,
            relative_path=relative_path,
            updated_file_content=updated_file_content,
        )

    return await asyncio.to_thread(_call)


async def _resolve_analysis(request: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    from .main import _resolve_analysis as resolve

    return await resolve(request)
