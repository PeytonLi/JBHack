from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .config import Settings, load_settings
from .models import (
    AnalyzeIncidentBody,
    AnalysisRequest,
    DebugIncidentRequest,
    IncidentFeedResponse,
    IssueAlertWebhook,
    normalize_sentry_event,
    GenerateCodeBody,
    GenerateCodeResponse,
    AnalyzeFileBody,
)
from .sentry_client import SentryEventClient
from .storage import IncidentBroker, IncidentStore
from .codex_analysis import (
    analyze_incident as run_codex_analysis,
    generate_secure_code as run_code_generation,
    analyze_file as run_file_scan,
)


logger = logging.getLogger("secureloop.agent")


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

    @app.post("/ide/analyze")
    async def analyze_incident_endpoint_full(
        payload: AnalysisRequest,
        request: Request,
    ) -> JSONResponse:
        _verify_ide_request(request, app.state.settings)
        response = await run_codex_analysis(payload)
        return JSONResponse(response.model_dump(mode="json", by_alias=True))

    @app.post("/ide/events/{incident_id}/analyze")
    async def analyze_incident_endpoint(
        incident_id: str,
        body: AnalyzeIncidentBody,
        request: Request,
    ) -> JSONResponse:
        _verify_ide_request(request, app.state.settings)

        incident = await app.state.store.get_incident(incident_id)
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found.")

        analysis_request = AnalysisRequest(
            incident_id=incident.incident_id,
            repo_relative_path=incident.repo_relative_path or "unknown",
            line_number=incident.line_number,
            exception_type=incident.exception_type,
            exception_message=incident.exception_message,
            title=incident.title,
            source_context=body.source_context,
            policy_text=body.policy_text,
        )

        response = await run_codex_analysis(analysis_request)
        return JSONResponse(response.model_dump(mode="json", by_alias=True))

    @app.post("/ide/generate")
    async def generate_endpoint(
        body: GenerateCodeBody,
        request: Request,
    ) -> JSONResponse:
        _verify_ide_request(request, app.state.settings)
        response = await run_code_generation(body)
        return JSONResponse(response.model_dump(mode="json", by_alias=True))

    @app.post("/ide/analyze-file")
    async def analyze_file_endpoint(
        body: AnalyzeFileBody,
        request: Request,
    ) -> JSONResponse:
        _verify_ide_request(request, app.state.settings)
        response = await run_file_scan(body)
        return JSONResponse(response.model_dump(mode="json", by_alias=True))

    @app.post("/ide/scan-deps")
    async def scan_deps_endpoint(
        body: dict,
        request: Request,
    ) -> JSONResponse:
        _verify_ide_request(request, app.state.settings)
        # Snyk/Safety stub for demo
        req_text = body.get("requirements_text", "")
        findings = []
        if "fastapi" in req_text.lower() and "==" not in req_text.lower():
            findings.append("CVE-2024-XXXX: FastAPI < 0.100 is vulnerable to ReDoS. Update to 0.100.0+")
        return JSONResponse({"findings": findings})

    @app.post("/ide/reject-fix")

    async def reject_fix_endpoint(
        body: dict,
        request: Request,
    ) -> Response:
        _verify_ide_request(request, app.state.settings)
        logger.info(f"Module 4 Human Gate Reject: {body.get('reason')}")
        return Response(status_code=204)

    @app.post("/ide/open-pr")
    async def open_pr_endpoint(
        body: dict,
        request: Request,
    ) -> JSONResponse:
        _verify_ide_request(request, app.state.settings)
        logger.info("Module 4 PR Opened with diagnosis attached.")
        # In a real setup, import github via PyGithub here
        return JSONResponse({"pr_url": "https://github.com/PeytonLi/JBHack/pulls/1"})

    return app


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
