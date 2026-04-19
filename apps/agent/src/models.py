from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )


class IssueAlertEvent(CamelModel):
    url: str
    web_url: str
    issue_url: str
    issue_id: str


class IssueAlertData(CamelModel):
    event: IssueAlertEvent
    triggered_rule: str


class IssueAlertWebhook(CamelModel):
    action: str
    data: IssueAlertData


class NormalizedIncident(CamelModel):
    incident_id: str
    sentry_event_id: str
    issue_id: str
    project_slug: str | None = None
    environment: str | None = None
    title: str
    exception_type: str
    exception_message: str
    repo_relative_path: str | None = None
    original_frame_path: str | None = None
    line_number: int | None = None
    function_name: str | None = None
    code_context: str | None = None
    event_web_url: str
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IncidentSummary(CamelModel):
    open_count: int
    reviewed_count: int
    total_count: int


class IncidentRecord(CamelModel):
    incident: NormalizedIncident
    status: Literal["open", "reviewed"]
    created_at: datetime
    reviewed_at: datetime | None = None


class IncidentFeedResponse(CamelModel):
    summary: IncidentSummary
    incidents: list[IncidentRecord]


class DebugIncidentRequest(CamelModel):
    title: str = "Local SecureLoop test incident"
    exception_type: str = "KeyError"
    exception_message: str = "999"
    repo_relative_path: str | None = "apps/target/src/main.py"
    original_frame_path: str | None = None
    line_number: int | None = 45
    function_name: str | None = "checkout"
    code_context: str | None = "warehouse_name = WAREHOUSES[warehouse_id]"
    project_slug: str | None = "autoscribe-target"
    environment: str | None = "local"
    issue_id: str = "local-debug"
    event_web_url: str = "https://example.invalid/secureloop/local-debug"

    def to_incident(self) -> NormalizedIncident:
        incident_id = f"debug-{uuid4().hex}"
        return NormalizedIncident(
            incident_id=incident_id,
            sentry_event_id=incident_id,
            issue_id=self.issue_id,
            project_slug=self.project_slug,
            environment=self.environment,
            title=self.title,
            exception_type=self.exception_type,
            exception_message=self.exception_message,
            repo_relative_path=self.repo_relative_path,
            original_frame_path=self.original_frame_path or self.repo_relative_path,
            line_number=self.line_number,
            function_name=self.function_name,
            code_context=self.code_context,
            event_web_url=self.event_web_url,
        )


class AnalysisRequest(CamelModel):
    incident_id: str
    repo_relative_path: str
    line_number: int | None = None
    exception_type: str
    exception_message: str
    title: str
    source_context: str
    policy_text: str | None = None


class AnalyzeIncidentBody(CamelModel):
    source_context: str
    policy_text: str | None = None


class GenerateCodeBody(CamelModel):
    source_context: str
    policy_text: str | None = None
    language: str = "python"


class GenerateCodeResponse(CamelModel):
    completion: str


class AnalyzeFileBody(CamelModel):
    file_path: str
    file_contents: str
    policy_text: str | None = None


class AnalysisPatch(CamelModel):
    repo_relative_path: str
    old_text: str
    new_text: str


class AnalysisResponse(CamelModel):
    severity: Literal["Critical", "High", "Medium", "Low"]
    category: str | None = None
    owasp: str | None = None
    cwe: str | None = None
    title: str
    explanation: str
    violated_policy: list[str] = Field(default_factory=list)
    fix_plan: list[str] = Field(default_factory=list)
    diff: str
    patch: AnalysisPatch


def normalize_sentry_event(
    webhook: IssueAlertWebhook,
    event_payload: dict[str, Any],
) -> NormalizedIncident:
    values = _extract_exception_values(event_payload)
    exception = values[-1] if values else {}
    frame = _select_primary_frame(exception)

    event_id = str(
        event_payload.get("eventID")
        or event_payload.get("id")
        or webhook.data.event.url.rstrip("/").split("/")[-1]
    )
    exception_type = str(exception.get("type") or "UnknownError")
    exception_message = str(exception.get("value") or "Unknown Sentry error")
    original_frame_path = _frame_value(frame, "filename", "abs_path", "absPath")
    code_context = _frame_value(frame, "context_line", "contextLine")

    return NormalizedIncident(
        incident_id=event_id,
        sentry_event_id=event_id,
        issue_id=str(webhook.data.event.issue_id),
        project_slug=_extract_project_slug(event_payload),
        environment=_extract_environment(event_payload),
        title=str(event_payload.get("title") or f"{exception_type}: {exception_message}"),
        exception_type=exception_type,
        exception_message=exception_message,
        repo_relative_path=_normalize_repo_relative_path(original_frame_path),
        original_frame_path=original_frame_path,
        line_number=_coerce_int(frame.get("lineno") or frame.get("lineNo")),
        function_name=_frame_value(frame, "function"),
        code_context=code_context,
        event_web_url=str(
            event_payload.get("permalink")
            or event_payload.get("web_url")
            or webhook.data.event.web_url
        ),
    )


def _extract_exception_values(event_payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = event_payload.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if entry.get("type") == "exception":
                data = entry.get("data", {})
                values = data.get("values")
                if isinstance(values, list):
                    return [value for value in values if isinstance(value, dict)]

    exception = event_payload.get("exception", {})
    values = exception.get("values")
    if isinstance(values, list):
        return [value for value in values if isinstance(value, dict)]
    return []


def _select_primary_frame(exception: dict[str, Any]) -> dict[str, Any]:
    stacktrace = exception.get("stacktrace", {})
    frames = stacktrace.get("frames")
    if not isinstance(frames, list):
        return {}

    valid_frames = [frame for frame in frames if isinstance(frame, dict)]
    for frame in reversed(valid_frames):
        if frame.get("in_app") is True or frame.get("inApp") is True:
            return frame

    return valid_frames[-1] if valid_frames else {}


def _extract_project_slug(event_payload: dict[str, Any]) -> str | None:
    project_slug = event_payload.get("projectSlug")
    if isinstance(project_slug, str) and project_slug:
        return project_slug

    project_name = event_payload.get("projectName")
    if isinstance(project_name, str) and project_name:
        return project_name

    return None


def _extract_environment(event_payload: dict[str, Any]) -> str | None:
    environment = event_payload.get("environment")
    if isinstance(environment, str) and environment:
        return environment

    tags = event_payload.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict) and tag.get("key") == "environment":
                value = tag.get("value")
                if isinstance(value, str) and value:
                    return value

            if (
                isinstance(tag, (list, tuple))
                and len(tag) == 2
                and tag[0] == "environment"
                and isinstance(tag[1], str)
            ):
                return tag[1]

    return None


def _normalize_repo_relative_path(raw_path: str | None) -> str | None:
    if not raw_path:
        return None

    path = raw_path.strip().replace("\\", "/")
    if not path:
        return None

    if "://" in path and not _looks_like_windows_drive(path):
        path = path.split("://", maxsplit=1)[1]

    if _looks_like_windows_drive(path):
        path = path[2:]

    path = path.lstrip("/")
    segments = [segment for segment in path.split("/") if segment and segment != "."]
    if not segments:
        return None

    collapsed = "/".join(segments)
    for marker in ("apps/", "packages/", "src/", "app/", "lib/"):
        index = collapsed.find(marker)
        if index != -1:
            return collapsed[index:]

    return collapsed


def _looks_like_windows_drive(path: str) -> bool:
    return len(path) > 2 and path[1] == ":" and path[0].isalpha() and path[2] == "/"


def _frame_value(frame: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = frame.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _coerce_int(value: str | int | None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
