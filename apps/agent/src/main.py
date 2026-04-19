from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
from importlib import import_module
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from .config import Settings, load_settings
from .models import (
    AnalyzeIncidentRequest,
    AnalyzeIncidentResponse,
    AnalyzePatch,
    DebugIncidentRequest,
    IncidentFeedResponse,
    IssueAlertWebhook,
    normalize_sentry_event,
)
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

    @app.post("/sentry/webhook", status_code=204)
    @app.post("/webhook/sentry", status_code=204)
    async def sentry_webhook(request: Request) -> Response:
        settings_state: Settings = app.state.settings
        raw_body = await request.body()
        _verify_sentry_request(request, raw_body, settings_state)

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
            await app.state.broker.publish(incident)

        return Response(status_code=204)

    @app.get("/ide/events/stream")
    async def ide_events_stream(request: Request) -> StreamingResponse:
        _verify_ide_request(request, app.state.settings)

        async def event_stream() -> AsyncIterator[str]:
            for incident in await app.state.store.list_unreviewed():
                yield f"data: {incident.model_dump_json(by_alias=True)}\n\n"

            queue = await app.state.broker.subscribe()
            try:
                while True:
                    try:
                        payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield f"data: {payload}\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"

                    if await request.is_disconnected():
                        break
            finally:
                await app.state.broker.unsubscribe(queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

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
    async def analyze_incident(payload: AnalyzeIncidentRequest, request: Request) -> AnalyzeIncidentResponse:
        _verify_ide_request(request, app.state.settings)
        return await _resolve_analysis(payload)

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
        await app.state.broker.publish(incident)
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
    if _is_warehouse_demo(payload):
        return _build_warehouse_demo_analysis(payload)

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


def _is_warehouse_demo(payload: AnalyzeIncidentRequest) -> bool:
    return (
        payload.repo_relative_path == "apps/target/src/main.py"
        and payload.line_number == 45
        and "WAREHOUSES[warehouse_id]" in payload.source_context
    )


def _build_warehouse_demo_analysis(payload: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    old_text = "warehouse_name = WAREHOUSES[warehouse_id]"
    new_text = "\n".join(
        [
            "warehouse_name = WAREHOUSES.get(warehouse_id)",
            "if warehouse_name is None:",
            '    raise HTTPException(status_code=409, detail="Order references an unknown warehouse.")',
        ]
    )
    return AnalyzeIncidentResponse(
        severity="Medium",
        category="Unhandled exception",
        cwe="CWE-703",
        title="Guard missing warehouse lookup in checkout flow",
        explanation=(
            "The checkout path dereferences a warehouse_id using direct dictionary indexing. "
            "When the order references warehouse 999, the lookup raises KeyError and turns "
            "bad data into a 500 instead of a controlled application error."
        ),
        violated_policy=_extract_violated_policy(payload.policy_text),
        fix_plan=[
            "Replace direct warehouse indexing with a guarded lookup.",
            "Return a controlled HTTP error when the warehouse reference is invalid.",
            "Keep the fix local to checkout without adding dependencies or applying it automatically.",
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


def _verify_sentry_request(request: Request, raw_body: bytes, settings: Settings) -> None:
    resource = request.headers.get("sentry-hook-resource")
    if resource != "event_alert":
        raise HTTPException(status_code=400, detail="Unsupported Sentry webhook resource.")

    if not settings.sentry_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="SENTRY_WEBHOOK_SECRET is required to verify Sentry requests.",
        )

    expected_signature = request.headers.get("sentry-hook-signature")
    if not _is_valid_signature(raw_body, expected_signature, settings.sentry_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid Sentry webhook signature.")


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


app = create_app()
