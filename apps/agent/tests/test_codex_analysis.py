from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock

import pytest

import src.codex_analysis as codex_analysis_module
from src.codex_analysis import analyze_incident
from src.codex_client import CodexResult
from src.models import AnalyzeIncidentRequest


@pytest.mark.asyncio
async def test_codex_analysis_returns_demo_fallback_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SECURE_LOOP_USE_FAKE_CODEX", raising=False)

    request = sample_request()
    response = await analyze_incident(request)

    assert response.severity == "Medium"
    assert response.category == "Runtime exception"
    assert response.cwe == "CWE-703"
    assert response.patch.repo_relative_path == "apps/target/src/main.py"
    assert response.patch.old_text == request.source_context.strip()
    assert "# TODO: replace with an approved SecureLoop fix." in response.patch.new_text


@pytest.mark.asyncio
async def test_codex_analysis_respects_fake_mode_even_with_api_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SECURE_LOOP_USE_FAKE_CODEX", "1")

    request = sample_request()
    response = await analyze_incident(request)

    assert response.title == (
        f"Review {request.exception_type} handling in {request.repo_relative_path}"
    )
    assert response.patch.old_text in request.source_context


@pytest.mark.asyncio
async def test_codex_analysis_fallback_produces_generic_todo_when_path_unanchored(monkeypatch) -> None:
    """Fallback should produce the generic TODO patch regardless of incident text."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SECURE_LOOP_USE_FAKE_CODEX", raising=False)

    request = AnalyzeIncidentRequest(
        incident_id="unrelated-bug",
        repo_relative_path="services/unrelated.py",
        line_number=12,
        exception_type="RuntimeError",
        exception_message="something blew up",
        title="Warehouse not found in log",
        source_context="x = compute()",
        policy_text="# SecureLoop Security Policy",
    )

    response = await analyze_incident(request)

    assert response.patch.old_text == "x = compute()"
    assert "# TODO: replace with an approved SecureLoop fix." in response.patch.new_text
    assert "WAREHOUSES" not in response.patch.new_text


@pytest.mark.asyncio
async def test_codex_analysis_skips_pip_audit_on_non_python(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SECURE_LOOP_USE_FAKE_CODEX", raising=False)

    calls: list[object] = []

    async def spy_run_pip_audit(**kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(codex_analysis_module, "run_pip_audit", spy_run_pip_audit)

    ts_request = AnalyzeIncidentRequest(
        incident_id="local-scan:apps/target/src/app.ts",
        repo_relative_path="apps/target/src/app.ts",
        line_number=12,
        exception_type="TypeError",
        exception_message="Cannot read property foo of undefined",
        title="TS local scan",
        source_context="const warehouse = warehouses[warehouseId];",
        policy_text="# SecureLoop Security Policy",
    )

    response = await analyze_incident(ts_request)

    assert calls == []
    assert response.dep_check is None


def sample_request(line_number: int = 45) -> AnalyzeIncidentRequest:
    return AnalyzeIncidentRequest(
        incident_id="debug-warehouse-45",
        repo_relative_path="apps/target/src/main.py",
        line_number=line_number,
        exception_type="KeyError",
        exception_message="999",
        title="Warehouse lookup crash",
        source_context="\n".join(
            [
                '    warehouse_id = int(order["warehouse_id"])',
                "    warehouse_name = WAREHOUSES[warehouse_id]",
                "    return {",
            ]
        ),
        policy_text="\n".join(
            [
                "# SecureLoop Security Policy",
                "",
                "## Error Handling",
                "- Do not expose stack traces or internal exception messages to end users.",
            ]
        ),
    )



def _build_codex_payload(*, old_text: str, new_text: str) -> str:
    payload = {
        "severity": "Medium",
        "category": "Runtime exception",
        "cwe": "CWE-703",
        "title": "Guard warehouse lookup",
        "explanation": "Guard the lookup against unknown warehouse IDs.",
        "violatedPolicy": [
            "Do not expose stack traces or internal exception messages to end users."
        ],
        "fixPlan": [
            "Inspect the failing lookup.",
            "Return a controlled 404 instead of raising.",
            "Add regression test.",
        ],
        "diff": "--- a/apps/target/src/main.py\n+++ b/apps/target/src/main.py\n@@\n-old\n+new",
        "patch": {
            "repoRelativePath": "apps/target/src/main.py",
            "oldText": old_text,
            "newText": new_text,
        },
        "reasoningSteps": [
            "Read source context.",
            "Identify unhandled KeyError.",
            "Propose guarded replacement.",
        ],
    }
    return json.dumps(payload)


def _prime_codex_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("SECURE_LOOP_USE_FAKE_CODEX", raising=False)

    async def _skip_pip_audit(**_kwargs):
        return None

    monkeypatch.setattr(codex_analysis_module, "run_pip_audit", _skip_pip_audit)


@pytest.mark.asyncio
async def test_analyze_incident_retries_once_when_first_response_invalid(
    monkeypatch, caplog
) -> None:
    _prime_codex_env(monkeypatch)

    invalid_call = CodexResult(
        raw_text=_build_codex_payload(
            old_text="totally_hallucinated = 42",
            new_text="totally_hallucinated = 43",
        ),
        success=True,
    )
    valid_call = CodexResult(
        raw_text=_build_codex_payload(
            old_text="    warehouse_name = WAREHOUSES[warehouse_id]",
            new_text="    warehouse_name = WAREHOUSES.get(warehouse_id, 'unknown')",
        ),
        success=True,
    )
    mock_call = AsyncMock(side_effect=[invalid_call, valid_call])
    monkeypatch.setattr(codex_analysis_module, "call_codex", mock_call)

    with caplog.at_level(logging.INFO, logger="secureloop.agent.codex_analysis"):
        response = await analyze_incident(sample_request())

    assert mock_call.await_count == 2
    assert response.patch.old_text == "    warehouse_name = WAREHOUSES[warehouse_id]"
    assert response.patch.new_text == "    warehouse_name = WAREHOUSES.get(warehouse_id, 'unknown')"
    assert any("recovered on retry" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_analyze_incident_falls_back_when_retry_also_fails(monkeypatch) -> None:
    _prime_codex_env(monkeypatch)

    invalid_call_a = CodexResult(
        raw_text=_build_codex_payload(
            old_text="hallucinated_a = 1",
            new_text="hallucinated_a = 2",
        ),
        success=True,
    )
    invalid_call_b = CodexResult(
        raw_text=_build_codex_payload(
            old_text="hallucinated_b = 1",
            new_text="hallucinated_b = 2",
        ),
        success=True,
    )
    mock_call = AsyncMock(side_effect=[invalid_call_a, invalid_call_b])
    monkeypatch.setattr(codex_analysis_module, "call_codex", mock_call)

    request = sample_request()
    response = await analyze_incident(request)

    assert mock_call.await_count == 2
    assert "# TODO: replace with an approved SecureLoop fix." in response.patch.new_text
    assert response.patch.old_text == request.source_context.strip()
