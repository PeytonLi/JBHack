from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
from importlib import import_module
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Literal

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pathlib import Path
from pydantic import ValidationError

from .autopilot import run_autopilot
from .codex_client import codex_available
from .config import Settings, load_settings
from .github_client import (
    GitHubClient,
    PullRequestResult,
    build_commit_message,
    build_pr_body,
)
from .models import (
    AnalyzeIncidentRequest,
    AnalyzeIncidentResponse,
    AnalyzePatch,
    CamelModel,
    DebugIncidentRequest,
    DeleteIncidentsResponse,
    IncidentFeedResponse,
    InternalErrorWebhook,
    InternalIssueWebhook,
    IssueAlertWebhook,
    NavigateRequest,
    NavigateRequestBody,
    NavigateResponse,
    normalize_internal_error_event,
    normalize_internal_issue_event,
    normalize_sentry_event,
)
from .ide_launcher import IdeLauncher, LaunchResult
from .sentry_client import SentryEventClient
from .storage import IncidentBroker, IncidentStore


logger = logging.getLogger("secureloop.agent")

TRUTHY_ENV_VALUES = {"1", "true", "TRUE", "yes", "YES"}
ANALYZE_MODULE_CANDIDATES = (
    "src.analysis_service",
    "src.analysis",
    "src.ide_analyze",
    "src.codex_analysis",
)
_SUPPORTED_RESOURCES = {"event_alert", "issue", "error"}
_DASHBOARD_FORWARDED_TYPES = {
    "incident.created",
    "incident.updated",
    "pipeline.step",
    "pipeline.completed",
    "pipeline.failed",
}
_PIPELINE_EVENT_TYPES = {"pipeline.step", "pipeline.completed", "pipeline.failed"}
_DEFAULT_DASHBOARD_ORIGIN = "http://localhost:3000"
_PR_ARTIFACTS_ROOT = Path(__file__).resolve().parents[1] / "out"


class OpenPrRequest(CamelModel):
    updated_file_content: str
    relative_path: str | None = None


def create_app(
    settings: Settings | None = None,
    sentry_client: SentryEventClient | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    store = IncidentStore(resolved_settings.sqlite_path)
    broker = IncidentBroker()
    client = sentry_client or SentryEventClient(resolved_settings.sentry_auth_token)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await store.initialize()
        yield

    app = FastAPI(
        title="SecureLoop Companion Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.store = store
    app.state.broker = broker
    app.state.sentry_client = client
    app.state.autopilot_locks = {}
    app.state.ide_launcher = IdeLauncher(
        command=resolved_settings.ide_launch_command or [],
        cwd=resolved_settings.ide_launch_cwd or Path("."),
        enabled=resolved_settings.ide_auto_launch,
    )

    @app.get("/status")
    async def status() -> JSONResponse:
        settings_state: Settings = app.state.settings
        dashboard_origin = _dashboard_origin(settings_state)
        return JSONResponse(
            {
                "autopilotEnabled": settings_state.autopilot_enabled(),
                "githubRepo": settings_state.github_repo,
                "codexAvailable": codex_available(),
            },
            headers={"Access-Control-Allow-Origin": dashboard_origin},
        )

    @app.get("/health")
    async def health() -> JSONResponse:
        settings_state: Settings = app.state.settings
        summary = await app.state.store.get_summary()
        return JSONResponse(
            {
                "status": "ok",
                "sqlitePath": str(settings_state.sqlite_path),
                "ideTokenFile": str(settings_state.ide_token_file),
                "allowDebugEndpoints": settings_state.allow_debug_endpoints,
                "openIncidentCount": summary.open_count,
                "reviewedIncidentCount": summary.reviewed_count,
                "totalIncidentCount": summary.total_count,
            }
        )

    @app.get("/incidents")
    async def incidents_feed(
        status: Literal["all", "open", "reviewed"] = Query(default="all"),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> IncidentFeedResponse:
        incidents = await app.state.store.list_incidents(status=status, limit=limit)
        summary = await app.state.store.get_summary()
        return IncidentFeedResponse(summary=summary, incidents=incidents)

    @app.get("/incidents/{incident_id}")
    async def get_incident(incident_id: str) -> JSONResponse:
        dashboard_origin = _dashboard_origin(app.state.settings)
        record = await app.state.store.get_record(incident_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Incident not found.")
        return JSONResponse(
            record.model_dump(mode="json", by_alias=True),
            headers={"Access-Control-Allow-Origin": dashboard_origin},
        )

    @app.delete("/incidents")
    async def delete_incidents(
        status: Literal["all", "open", "reviewed"] = Query(default="all"),
    ) -> JSONResponse:
        dashboard_origin = _dashboard_origin(app.state.settings)
        deleted_ids = await app.state.store.delete_incidents(status=status)
        if deleted_ids:
            await app.state.broker.publish_cleared(
                status=status,
                incident_ids=deleted_ids,
            )
        body = DeleteIncidentsResponse(
            status=status,
            deleted_count=len(deleted_ids),
            incident_ids=deleted_ids,
        )
        return JSONResponse(
            body.model_dump(mode="json", by_alias=True),
            headers={"Access-Control-Allow-Origin": dashboard_origin},
        )

    @app.options("/incidents")
    async def incidents_preflight() -> Response:
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": _dashboard_origin(app.state.settings),
                "Access-Control-Allow-Methods": "GET, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    @app.post("/sentry/webhook", status_code=204)
    @app.post("/webhook/sentry", status_code=204)
    async def sentry_webhook(request: Request) -> Response:
        settings_state: Settings = app.state.settings
        raw_body = await request.body()
        resource = _verify_sentry_request(request, raw_body, settings_state)

        if resource == "event_alert":
            return await _handle_event_alert(app, raw_body)
        if resource == "issue":
            return await _handle_internal_issue(app, raw_body)
        if resource == "error":
            return await _handle_internal_error(app, raw_body)
        return Response(status_code=204)

    @app.get("/ide/events/stream")
    async def ide_events_stream(request: Request) -> StreamingResponse:
        _verify_ide_request(request, app.state.settings)

        async def event_stream() -> AsyncIterator[str]:
            for incident in await app.state.store.list_unreviewed():
                yield f"data: {incident.model_dump_json(by_alias=True)}\n\n"

            queue = await app.state.broker.subscribe()
            for nav in await app.state.broker.drain_pending_navigates():
                envelope = {
                    "type": "ide.navigate",
                    "navigate": json.loads(nav.model_dump_json(by_alias=True)),
                }
                queue.put_nowait(json.dumps(envelope))
            try:
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                        envelope = json.loads(payload)
                        envelope_type = envelope.get("type", "incident.created")
                        if envelope_type == "ide.navigate":
                            yield f"event: ide.navigate\ndata: {json.dumps(envelope['navigate'])}\n\n"
                        elif envelope_type in _PIPELINE_EVENT_TYPES:
                            body = json.dumps(envelope["pipeline"])
                            yield f"event: {envelope_type}\ndata: {body}\n\n"
                        else:
                            inner_incident = envelope["incident"]["incident"]
                            yield f"data: {json.dumps(inner_incident)}\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"

                    if await request.is_disconnected():
                        break
            finally:
                await app.state.broker.unsubscribe(queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/dashboard/events/stream")
    async def dashboard_events_stream(request: Request) -> StreamingResponse:
        dashboard_origin = _dashboard_origin(app.state.settings)

        async def event_stream() -> AsyncIterator[str]:
            for record in await app.state.store.list_incidents(status="all", limit=50):
                body = record.model_dump_json(by_alias=True)
                yield f"event: incident.created\ndata: {body}\n\n"

            queue = await app.state.broker.subscribe()
            try:
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                        envelope = json.loads(payload)
                        event_name = envelope.get("type", "incident.created")
                        if event_name == "incidents.cleared":
                            body = json.dumps(envelope["cleared"])
                            yield f"event: incidents.cleared\ndata: {body}\n\n"
                            continue
                        if event_name in _PIPELINE_EVENT_TYPES:
                            body = json.dumps(envelope["pipeline"])
                            yield f"event: {event_name}\ndata: {body}\n\n"
                            continue
                        if event_name not in _DASHBOARD_FORWARDED_TYPES:
                            continue
                        body = json.dumps(envelope["incident"])
                        yield f"event: {event_name}\ndata: {body}\n\n"
                    except TimeoutError:
                        yield ": heartbeat\n\n"

                    if await request.is_disconnected():
                        break
            finally:
                await app.state.broker.unsubscribe(queue)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": dashboard_origin,
            },
        )

    @app.options("/dashboard/events/stream")
    async def dashboard_events_stream_preflight() -> Response:
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": _dashboard_origin(app.state.settings),
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    @app.post("/ide/navigate", response_model=NavigateResponse)
    async def ide_navigate(
        request: Request,
        payload: NavigateRequestBody = Body(...),
    ) -> JSONResponse:
        dashboard_origin = _dashboard_origin(app.state.settings)
        record = await app.state.store.get_record(payload.incident_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Incident not found.")
        inc = record.incident
        navigate = NavigateRequest(
            incident_id=inc.incident_id,
            repo_relative_path=inc.repo_relative_path,
            original_frame_path=inc.original_frame_path,
            line_number=inc.line_number,
            function_name=inc.function_name,
        )
        subscribers = await app.state.broker.publish_navigate(navigate)
        if subscribers > 0:
            launch_result = LaunchResult(launched=False, reason="plugin-connected")
        else:
            launch_result = await app.state.ide_launcher.ensure_running()
        body = NavigateResponse(
            delivered=subscribers > 0,
            subscribers=subscribers,
            incident_id=inc.incident_id,
            launched=launch_result.launched,
            launch_reason=launch_result.reason,
        )
        return JSONResponse(
            body.model_dump(mode="json", by_alias=True),
            headers={"Access-Control-Allow-Origin": dashboard_origin},
        )

    @app.options("/ide/navigate")
    async def ide_navigate_preflight() -> Response:
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": _dashboard_origin(app.state.settings),
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    @app.post("/ide/events/{incident_id}/ack", status_code=204)
    async def acknowledge_incident(incident_id: str, request: Request) -> Response:
        _verify_ide_request(request, app.state.settings)
        updated = await app.state.store.mark_reviewed(incident_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Incident not found.")
        return Response(status_code=204)

    @app.post("/ide/events/{incident_id}/review", status_code=204)
    async def review_incident(incident_id: str, request: Request) -> Response:
        _verify_ide_request(request, app.state.settings)
        updated = await app.state.store.mark_reviewed(incident_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Incident not found.")
        return Response(status_code=204)

    @app.post("/ide/analyze", response_model=AnalyzeIncidentResponse)
    async def analyze_incident(
        request: Request,
        payload: AnalyzeIncidentRequest | None = Body(default=None),
    ) -> AnalyzeIncidentResponse:
        _verify_ide_request(request, app.state.settings)
        if app.state.settings.autopilot_enabled():
            raise HTTPException(
                status_code=409,
                detail="autopilot owns this pipeline; manual IDE flow disabled",
            )
        if payload is None:
            logger.warning("Received empty /ide/analyze body; using deterministic demo analysis payload.")
            payload = _build_demo_analysis_request()
        broker = app.state.broker
        await broker.publish_pipeline(
            incident_id=payload.incident_id,
            event_type="pipeline.step",
            payload={"step": "analyzing", "status": "running"},
        )
        try:
            analysis = await _resolve_analysis(payload)
        except Exception as exc:
            await broker.publish_pipeline(
                incident_id=payload.incident_id,
                event_type="pipeline.failed",
                payload={"step": "analyzing", "status": "failed", "error": str(exc)},
            )
            raise
        try:
            await app.state.store.put_analysis(payload.incident_id, analysis)
        except Exception:
            logger.exception("Failed to persist analysis for incident %s.", payload.incident_id)
        await broker.publish_pipeline(
            incident_id=payload.incident_id,
            event_type="pipeline.step",
            payload={"step": "analyzing", "status": "completed"},
        )
        return analysis

    @app.post("/ide/events/{incident_id}/open-pr")
    async def open_pr(
        incident_id: str,
        request: Request,
        payload: OpenPrRequest = Body(...),
    ) -> PullRequestResult:
        _verify_ide_request(request, app.state.settings)
        if app.state.settings.autopilot_enabled():
            raise HTTPException(
                status_code=409,
                detail="autopilot owns this pipeline; manual IDE flow disabled",
            )
        analysis = await app.state.store.get_analysis(incident_id)
        if analysis is None:
            raise HTTPException(
                status_code=404,
                detail="no analysis stored for incident",
            )
        broker = app.state.broker
        await broker.publish_pipeline(
            incident_id=incident_id,
            event_type="pipeline.step",
            payload={"step": "pr_opening", "status": "running"},
        )
        relative_path = payload.relative_path or analysis.patch.repo_relative_path
        token = os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPO")
        if not token or not repo:
            result = _write_local_artifacts(
                incident_id=incident_id,
                analysis=analysis,
                relative_path=relative_path,
                updated_file_content=payload.updated_file_content,
                error="GITHUB_TOKEN or GITHUB_REPO not configured.",
            )
        else:
            try:
                client = GitHubClient(token, repo)
                result = client.open_pr_for_incident(
                    incident_id=incident_id,
                    analysis=analysis,
                    relative_path=relative_path,
                    updated_file_content=payload.updated_file_content,
                )
            except Exception as exc:
                logger.exception("PR creation failed; writing local artifacts.")
                result = _write_local_artifacts(
                    incident_id=incident_id,
                    analysis=analysis,
                    relative_path=relative_path,
                    updated_file_content=payload.updated_file_content,
                    error=str(exc),
                )
        if result.error:
            await broker.publish_pipeline(
                incident_id=incident_id,
                event_type="pipeline.failed",
                payload={"step": "pr_opening", "status": "failed", "error": result.error},
            )
        else:
            await broker.publish_pipeline(
                incident_id=incident_id,
                event_type="pipeline.step",
                payload={"step": "pr_opening", "status": "completed", "prUrl": result.pr_url},
            )
        return result

    @app.post("/debug/incidents", status_code=201)
    async def create_debug_incident(
        payload: DebugIncidentRequest,
        request: Request,
    ) -> JSONResponse:
        settings_state: Settings = app.state.settings
        if not settings_state.allow_debug_endpoints:
            raise HTTPException(status_code=404, detail="Debug endpoints are disabled.")

        _verify_ide_request(request, settings_state)
        incident = payload.to_incident()
        await app.state.store.put_if_absent(incident)
        record = await app.state.store.get_record(incident.incident_id)
        if record is not None:
            await app.state.broker.publish(record, event_type="incident.created")
        return JSONResponse(incident.model_dump(mode="json", by_alias=True), status_code=201)

    return app


async def _resolve_analysis(payload: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    if _use_fake_codex():
        return _build_fake_analysis(payload)

    try:
        analyze_impl = _resolve_analyze_impl()
    except RuntimeError as exc:
        logger.exception("Failed to load SecureLoop analysis implementation.")
        raise HTTPException(
            status_code=502,
            detail="SecureLoop analysis implementation could not be loaded.",
        ) from exc

    if analyze_impl is None:
        return _build_fake_analysis(payload)

    try:
        result = analyze_impl(payload)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        logger.exception("SecureLoop analysis implementation failed.")
        raise HTTPException(status_code=502, detail="SecureLoop analysis request failed.") from exc

    try:
        return AnalyzeIncidentResponse.model_validate(result)
    except ValidationError as exc:
        logger.exception("SecureLoop analysis implementation returned invalid data.")
        raise HTTPException(
            status_code=502,
            detail="SecureLoop analysis response was invalid.",
        ) from exc


def _use_fake_codex() -> bool:
    return os.getenv("SECURE_LOOP_USE_FAKE_CODEX", "0").strip() in TRUTHY_ENV_VALUES


def _build_demo_analysis_request() -> AnalyzeIncidentRequest:
    return AnalyzeIncidentRequest(
        incident_id="debug-empty-analyze-body",
        repo_relative_path="apps/target/src/main.py",
        line_number=45,
        exception_type="RuntimeError",
        exception_message="SecureLoop demo mode",
        title="SecureLoop demo incident",
        source_context="warehouse_name = WAREHOUSES[warehouse_id]",
        policy_text="\n".join(
            [
                "# SecureLoop Security Policy",
                "",
                "## Error Handling",
                "- Do not expose stack traces or internal exception messages to end users.",
            ]
        ),
    )


def _resolve_analyze_impl() -> Callable[[AnalyzeIncidentRequest], Any] | None:
    for module_path in ANALYZE_MODULE_CANDIDATES:
        try:
            module = import_module(module_path)
        except ModuleNotFoundError as exc:
            if exc.name == module_path:
                continue
            raise RuntimeError(f"Unable to import {module_path}.") from exc
        except Exception as exc:
            raise RuntimeError(f"Unable to import {module_path}.") from exc

        analyze_impl = getattr(module, "analyze_incident", None)
        if callable(analyze_impl):
            return analyze_impl

    return None


def _build_fake_analysis(payload: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    old_text = payload.source_context.strip() or "pass"
    new_text = f"{old_text}\n# Replace this placeholder with an approved fix."
    return AnalyzeIncidentResponse(
        severity="Medium",
        category="Runtime exception",
        cwe="CWE-703",
        title=f"Review {payload.exception_type} handling in {payload.repo_relative_path}",
        explanation=(
            "SecureLoop is running in deterministic fake mode because no Codex analysis "
            "implementation is available yet."
        ),
        violated_policy=_extract_violated_policy(payload.policy_text),
        fix_plan=[
            "Inspect the failing code path around the reported line.",
            "Add a minimal guard that turns the failure into a controlled application error.",
            "Review and approve the generated patch before applying it.",
        ],
        diff=_build_unified_diff(payload.repo_relative_path, old_text, new_text),
        patch=AnalyzePatch(
            repo_relative_path=payload.repo_relative_path,
            old_text=old_text,
            new_text=new_text,
        ),
    )


def _extract_violated_policy(policy_text: str) -> list[str]:
    canonical_rule = "Do not expose stack traces or internal exception messages to end users."
    if canonical_rule in policy_text:
        return [canonical_rule]

    bullet_lines = [
        line.lstrip("- ").strip()
        for line in policy_text.splitlines()
        if line.lstrip().startswith("-")
    ]
    return bullet_lines[:1] or [canonical_rule]


def _build_unified_diff(repo_relative_path: str, old_text: str, new_text: str) -> str:
    diff_lines = [
        f"--- a/{repo_relative_path}",
        f"+++ b/{repo_relative_path}",
        "@@",
    ]
    diff_lines.extend(f"-{line}" for line in old_text.splitlines() or [old_text])
    diff_lines.extend(f"+{line}" for line in new_text.splitlines() or [new_text])
    return "\n".join(diff_lines)


def _verify_sentry_request(request: Request, raw_body: bytes, settings: Settings) -> str:
    resource = request.headers.get("sentry-hook-resource")
    if resource not in _SUPPORTED_RESOURCES:
        raise HTTPException(status_code=400, detail="Unsupported Sentry webhook resource.")

    if not settings.sentry_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="SENTRY_WEBHOOK_SECRET is required to verify Sentry requests.",
        )

    expected_signature = request.headers.get("sentry-hook-signature")
    if not _is_valid_signature(raw_body, expected_signature, settings.sentry_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid Sentry webhook signature.")
    return resource


async def _handle_event_alert(app: FastAPI, raw_body: bytes) -> Response:
    try:
        payload = IssueAlertWebhook.model_validate_json(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.") from exc

    if payload.action != "triggered":
        return Response(status_code=204)

    try:
        event_payload = await app.state.sentry_client.fetch_event(payload.data.event.url)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        logger.exception("Failed to fetch Sentry event details.")
        raise HTTPException(
            status_code=502,
            detail="Unable to fetch event details from Sentry.",
        ) from exc

    incident = normalize_sentry_event(payload, event_payload)
    created = await app.state.store.put_if_absent(incident)
    if created:
        record = await app.state.store.get_record(incident.incident_id)
        if record is not None:
            await app.state.broker.publish(record, event_type="incident.created")
            _schedule_autopilot(app, incident.incident_id)
    return Response(status_code=204)


async def _handle_internal_issue(app: FastAPI, raw_body: bytes) -> Response:
    try:
        payload = InternalIssueWebhook.model_validate_json(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.") from exc

    issue = payload.data.issue
    if payload.action == "created":
        event_payload = payload.data.event
        if event_payload is None:
            try:
                event_payload = await app.state.sentry_client.fetch_issue(issue.id)
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except httpx.HTTPError as exc:
                logger.exception("Failed to fetch Sentry issue details.")
                raise HTTPException(
                    status_code=502,
                    detail="Unable to fetch issue details from Sentry.",
                ) from exc
        incident = normalize_internal_issue_event(payload, event_payload)
        created = await app.state.store.put_if_absent(incident)
        if created:
            record = await app.state.store.get_record(incident.incident_id)
            if record is not None:
                await app.state.broker.publish(record, event_type="incident.created")
                _schedule_autopilot(app, incident.incident_id)
        return Response(status_code=204)

    new_status = issue.status if payload.action != "assigned" else None
    assignee = _extract_assignee(issue.assigned_to) if payload.action == "assigned" else None
    updated = await app.state.store.update_sentry_status(
        issue_id=str(issue.id),
        sentry_status=new_status,
        assignee=assignee,
    )
    if not updated:
        logger.debug(
            "Received %s for unknown issue_id=%s; ignoring.",
            payload.action,
            issue.id,
        )
        return Response(status_code=204)
    for record in updated:
        await app.state.broker.publish(record, event_type="incident.updated")
    return Response(status_code=204)


async def _handle_internal_error(app: FastAPI, raw_body: bytes) -> Response:
    try:
        payload = InternalErrorWebhook.model_validate_json(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.") from exc

    incident = normalize_internal_error_event(payload)
    created = await app.state.store.put_if_absent(incident)
    if created:
        record = await app.state.store.get_record(incident.incident_id)
        if record is not None:
            await app.state.broker.publish(record, event_type="incident.created")
            _schedule_autopilot(app, incident.incident_id)
    return Response(status_code=204)


def _schedule_autopilot(app: FastAPI, incident_id: str) -> None:
    settings: Settings = app.state.settings
    if not settings.autopilot_enabled():
        return
    asyncio.create_task(run_autopilot(app, incident_id))


def _extract_assignee(assigned_to: dict[str, Any] | None) -> str | None:
    if not assigned_to:
        return None
    for key in ("name", "username", "email", "slug"):
        value = assigned_to.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _dashboard_origin(settings: Settings) -> str:
    configured = os.getenv("DASHBOARD_ORIGIN", "").strip()
    return configured or _DEFAULT_DASHBOARD_ORIGIN


def _verify_ide_request(request: Request, settings: Settings) -> None:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing IDE authorization token.")

    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.ide_token:
        raise HTTPException(status_code=401, detail="Invalid IDE authorization token.")


def _is_valid_signature(raw_body: bytes, header_value: str | None, secret: str) -> bool:
    if not header_value:
        return False

    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header_value)


def _write_local_artifacts(
    *,
    incident_id: str,
    analysis: AnalyzeIncidentResponse,
    relative_path: str,
    updated_file_content: str,
    error: str | None = None,
) -> PullRequestResult:
    out_dir = _PR_ARTIFACTS_ROOT / f"pr-{incident_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_path = out_dir / "fix.patch"
    coe_path = out_dir / "COE.md"
    meta_path = out_dir / "meta.json"
    patch_path.write_text(analysis.diff, encoding="utf-8")
    coe_path.write_text(
        build_pr_body(incident_id, analysis),
        encoding="utf-8",
    )
    meta_path.write_text(
        json.dumps(
            {
                "incidentId": incident_id,
                "relativePath": relative_path,
                "commitMessage": build_commit_message(analysis, relative_path),
                "updatedFileBytes": len(updated_file_content.encode("utf-8")),
                "error": error,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return PullRequestResult(
        pr_url=None,
        pr_number=None,
        branch=None,
        local_artifact_path=str(out_dir),
        error=error,
    )


app = create_app()
