from __future__ import annotations

from src.models import (
    IssueAlertWebhook,
    normalize_internal_error_event,
    normalize_internal_issue_event,
    normalize_sentry_event,
    InternalErrorWebhook,
    InternalIssueWebhook,
)


def _issue_alert_webhook() -> IssueAlertWebhook:
    return IssueAlertWebhook.model_validate(
        {
            "action": "triggered",
            "data": {
                "event": {
                    "url": "https://sentry.example/api/0/projects/acme/shop/events/abc/",
                    "web_url": "https://sentry.example/events/abc/",
                    "issue_url": "https://sentry.example/api/0/issues/42/",
                    "issue_id": "42",
                },
                "triggered_rule": "Prod checkout failure",
            },
        }
    )


def _event_with_stackframe(extra: dict | None = None) -> dict:
    payload: dict = {
        "id": "abc",
        "title": "KeyError: 999",
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
                                        "filename": "/workspace/app/routes/checkout.ts",
                                        "function": "checkout",
                                        "lineno": 88,
                                        "in_app": True,
                                    }
                                ]
                            },
                        }
                    ]
                },
            }
        ],
    }
    if extra is not None:
        payload["extra"] = {"secureloop": extra}
    return payload


def test_secureloop_extra_overrides_stack_frame_metadata() -> None:
    incident = normalize_sentry_event(
        _issue_alert_webhook(),
        _event_with_stackframe(
            extra={
                "repo_relative_path": "apps/web/routes/checkout.ts",
                "source_line": 120,
                "cwe_hint": "CWE-89",
                "scenario_id": "sqli",
            }
        ),
    )
    assert incident.repo_relative_path == "apps/web/routes/checkout.ts"
    assert incident.line_number == 120


def test_secureloop_extra_falls_back_to_stack_frame_when_absent() -> None:
    incident = normalize_sentry_event(
        _issue_alert_webhook(),
        _event_with_stackframe(extra=None),
    )
    assert incident.repo_relative_path == "app/routes/checkout.ts"
    assert incident.line_number == 88


def test_secureloop_extra_partial_metadata_merges_with_frame() -> None:
    incident = normalize_sentry_event(
        _issue_alert_webhook(),
        _event_with_stackframe(extra={"source_line": 200}),
    )
    assert incident.line_number == 200
    assert incident.repo_relative_path == "app/routes/checkout.ts"


def test_contexts_secureloop_also_accepted() -> None:
    payload = _event_with_stackframe(extra=None)
    payload["contexts"] = {
        "secureloop": {"repo_relative_path": "apps/api/handler.py", "source_line": 5}
    }
    incident = normalize_sentry_event(_issue_alert_webhook(), payload)
    assert incident.repo_relative_path == "apps/api/handler.py"
    assert incident.line_number == 5


def test_internal_issue_event_uses_extras() -> None:
    webhook = InternalIssueWebhook.model_validate(
        {
            "action": "created",
            "data": {
                "issue": {"id": "42", "status": "unresolved"},
                "event": _event_with_stackframe(
                    extra={"repo_relative_path": "apps/web/foo.ts", "source_line": 9}
                ),
            },
        }
    )
    incident = normalize_internal_issue_event(webhook, webhook.data.event or {})
    assert incident.repo_relative_path == "apps/web/foo.ts"
    assert incident.line_number == 9


def test_internal_error_event_uses_extras() -> None:
    webhook = InternalErrorWebhook.model_validate(
        {
            "action": "created",
            "data": {
                "event": _event_with_stackframe(
                    extra={"repo_relative_path": "apps/web/bar.ts", "source_line": 77}
                ),
            },
        }
    )
    incident = normalize_internal_error_event(webhook)
    assert incident.repo_relative_path == "apps/web/bar.ts"
    assert incident.line_number == 77
