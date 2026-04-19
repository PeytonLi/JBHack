from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .codex_client import call_codex, codex_available
from .dep_check import format_dep_scan_for_prompt, run_pip_audit
from .models import (
    AnalyzeIncidentRequest,
    AnalyzeIncidentResponse,
    DepCheckResult,
)
from .prompt_builder import (
    CodexPrompt,
    build_codex_prompt,
    build_correction_prompt,
    build_pytest_prompt,
)
from .validator import (
    build_patch,
    build_unified_diff,
    build_validation_diagnostic,
    ensure_diff_matches_patch,
    normalize_policy_rules,
    parse_analysis_response,
    validate_analysis_response,
)


logger = logging.getLogger("secureloop.agent.codex_analysis")


class SandboxTestGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeneratedSandboxTest:
    test_file_relative_path: str
    test_code: str
    rationale: str


async def generate_sandbox_test(
    *,
    incident_id: str,
    repo_relative_path: str,
    line_number: int,
    exception_type: str,
    exception_message: str,
    title: str,
    diff: str,
    original_source: str,
    patched_source: str,
) -> GeneratedSandboxTest:
    if not codex_available():
        raise SandboxTestGenerationError(
            "Codex unavailable: cannot generate sandbox test."
        )

    prompt = build_pytest_prompt(
        incident_id=incident_id,
        repo_relative_path=repo_relative_path,
        line_number=line_number,
        exception_type=exception_type,
        exception_message=exception_message,
        title=title,
        diff=diff,
        original_source=original_source,
        patched_source=patched_source,
    )
    result = await call_codex(
        system_prompt=prompt.system_prompt,
        user_message=prompt.user_message,
        response_format=prompt.response_format,
        max_output_tokens=2000,
    )
    if not result.success:
        raise SandboxTestGenerationError(result.error or "Codex call failed.")

    try:
        payload = json.loads(result.raw_text)
    except json.JSONDecodeError as exc:
        raise SandboxTestGenerationError(
            f"Codex returned non-JSON sandbox test: {exc}"
        ) from exc

    test_path = str(payload.get("testFileRelativePath") or "").strip()
    test_code = str(payload.get("testCode") or "")
    rationale = str(payload.get("rationale") or "")
    if not test_path or not test_code.strip():
        raise SandboxTestGenerationError(
            "Codex sandbox response missing testFileRelativePath or testCode."
        )
    return GeneratedSandboxTest(
        test_file_relative_path=test_path,
        test_code=test_code,
        rationale=rationale,
    )


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


async def _attempt_analysis(
    prompt: CodexPrompt,
    request: AnalyzeIncidentRequest,
) -> tuple[AnalyzeIncidentResponse | None, list[str]]:
    result = await call_codex(
        system_prompt=prompt.system_prompt,
        user_message=prompt.user_message,
        response_format=prompt.response_format,
    )
    if not result.success:
        return None, [f"codex_call_failed:{result.error}"]
    try:
        response = parse_analysis_response(result.raw_text)
    except Exception as exc:  # noqa: BLE001 - surface parse failure to caller
        return None, [f"codex_parse_failed:{exc!r}"]

    response.violated_policy = normalize_policy_rules(
        request.policy_text or "",
        response.violated_policy,
    )
    response = ensure_diff_matches_patch(response)
    errors = validate_analysis_response(request, response)
    return response, errors


async def analyze_incident(request: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    repo_root = _resolve_repo_root()
    if request.repo_relative_path.endswith(".py"):
        dep_check = await run_pip_audit(
            repo_root=repo_root,
            target_requirements=repo_root / "apps/target/requirements.txt",
        )
    else:
        dep_check = None
    dep_scan_text = format_dep_scan_for_prompt(dep_check)

    if not codex_available():
        return _finalize_fallback(request, dep_check)

    prompt = build_codex_prompt(request, dep_scan_text=dep_scan_text)
    response, errors = await _attempt_analysis(prompt, request)
    if response is not None and not errors:
        return _attach_dep_check(response, dep_check)

    if response is not None:
        logger.warning(
            "Codex analysis failed validation; retrying once. diagnostic=%s",
            build_validation_diagnostic(request, response, errors),
        )
        correction = build_correction_prompt(request, response, errors)
        response2, errors2 = await _attempt_analysis(correction, request)
        if response2 is not None and not errors2:
            logger.info("Codex analysis recovered on retry.")
            return _attach_dep_check(response2, dep_check)
        logger.warning(
            "Codex analysis still invalid after retry; using fallback. diagnostic=%s",
            build_validation_diagnostic(
                request,
                response2 or response,
                errors2 or errors,
            ),
        )
    else:
        logger.warning(
            "Codex analysis unavailable or unparseable; using fallback. errors=%s",
            errors,
        )

    return _finalize_fallback(request, dep_check)


def _finalize_fallback(
    request: AnalyzeIncidentRequest,
    dep_check: DepCheckResult | None,
) -> AnalyzeIncidentResponse:
    return _attach_dep_check(_build_fallback_response(request), dep_check)


def _attach_dep_check(
    response: AnalyzeIncidentResponse,
    dep_check: DepCheckResult | None,
) -> AnalyzeIncidentResponse:
    response.dep_check = dep_check
    if dep_check is None and not any(
        step.startswith("Dependency scan unavailable") for step in response.reasoning_steps
    ):
        response.reasoning_steps.insert(
            0,
            "Dependency scan unavailable (pip-audit binary missing or timed out).",
        )
    return response


def _build_fallback_response(request: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    old_text = request.source_context.strip() or "pass"
    new_text = f"{old_text}\n# TODO: replace with an approved SecureLoop fix."
    patch = build_patch(
        repo_relative_path=request.repo_relative_path,
        old_text=old_text,
        new_text=new_text,
    )
    return AnalyzeIncidentResponse(
        severity="Medium",
        category="Runtime exception",
        cwe="CWE-703",
        title=f"Review {request.exception_type} handling in {request.repo_relative_path}",
        explanation=(
            "Codex analysis was unavailable or invalid, so SecureLoop returned a deterministic "
            "fallback for human review."
        ),
        violated_policy=_extract_violated_policy(request.policy_text),
        fix_plan=[
            "Inspect the failing code path around the reported line.",
            "Add a minimal guard that turns the failure into a controlled application error.",
            "Review and approve the generated patch before applying it.",
        ],
        diff=build_unified_diff(
            repo_relative_path=patch.repo_relative_path,
            old_text=patch.old_text,
            new_text=patch.new_text,
        ),
        patch=patch,
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
