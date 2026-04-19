from __future__ import annotations

import pytest

import src.codex_analysis as codex_analysis_module
from src.codex_analysis import analyze_incident
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
