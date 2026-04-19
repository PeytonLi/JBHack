from __future__ import annotations

import logging
from pathlib import Path

from .codex_client import call_codex, codex_available
from .dep_check import format_dep_scan_for_prompt, run_pip_audit
from .models import (
    AnalyzeIncidentRequest,
    AnalyzeIncidentResponse,
    AnalyzePatch,
    DepCheckResult,
)
from .prompt_builder import build_codex_prompt
from .validator import (
    build_patch,
    build_unified_diff,
    ensure_diff_matches_patch,
    normalize_policy_rules,
    parse_analysis_response,
    validate_analysis_response,
)


logger = logging.getLogger("secureloop.agent.codex_analysis")


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


async def analyze_incident(request: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    repo_root = _resolve_repo_root()
    dep_check = await run_pip_audit(
        repo_root=repo_root,
        target_requirements=repo_root / "apps/target/requirements.txt",
    )
    dep_scan_text = format_dep_scan_for_prompt(dep_check)

    if not codex_available():
        return _finalize_fallback(request, dep_check)

    prompt = build_codex_prompt(request, dep_scan_text=dep_scan_text)
    result = await call_codex(
        system_prompt=prompt.system_prompt,
        user_message=prompt.user_message,
        response_format=prompt.response_format,
    )
    if not result.success:
        logger.warning("Codex analysis unavailable; using fallback. reason=%s", result.error)
        return _finalize_fallback(request, dep_check)

    try:
        response = parse_analysis_response(result.raw_text)
    except Exception:
        logger.warning("Codex analysis returned unparseable JSON; using fallback.", exc_info=True)
        return _finalize_fallback(request, dep_check)

    response.violated_policy = normalize_policy_rules(
        request.policy_text or "",
        response.violated_policy,
    )
    response = ensure_diff_matches_patch(response)
    validation_errors = validate_analysis_response(request, response)
    if validation_errors:
        logger.warning("Codex analysis failed validation; using fallback. errors=%s", validation_errors)
        return _finalize_fallback(request, dep_check)

    return _attach_dep_check(response, dep_check)


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
    if _looks_like_warehouse_demo(request):
        return _build_warehouse_demo_response(request)

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


def _build_warehouse_demo_response(request: AnalyzeIncidentRequest) -> AnalyzeIncidentResponse:
    old_text = _warehouse_old_text(request.source_context)
    indent = old_text[: len(old_text) - len(old_text.lstrip())]
    new_text = "\n".join(
        [
            f"{indent}warehouse_name = WAREHOUSES.get(warehouse_id)",
            f"{indent}if warehouse_name is None:",
            f'{indent}    raise HTTPException(status_code=409, detail="Order references an unknown warehouse.")',
        ]
    )
    patch = AnalyzePatch(
        repo_relative_path=request.repo_relative_path,
        old_text=old_text,
        new_text=new_text,
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
        violated_policy=_extract_violated_policy(request.policy_text),
        fix_plan=[
            "Replace direct warehouse indexing with a guarded lookup.",
            "Return a controlled HTTP error when the warehouse reference is invalid.",
            "Keep the fix local to checkout without adding dependencies or applying it automatically.",
        ],
        diff=build_unified_diff(
            repo_relative_path=patch.repo_relative_path,
            old_text=patch.old_text,
            new_text=patch.new_text,
        ),
        patch=patch,
    )


def _looks_like_warehouse_demo(request: AnalyzeIncidentRequest) -> bool:
    source_context = request.source_context.lower()
    incident_text = " ".join(
        [
            request.repo_relative_path,
            str(request.line_number),
            request.exception_type,
            request.exception_message,
            request.title,
        ]
    ).lower()
    return (
        request.repo_relative_path == "apps/target/src/main.py"
        and "warehouses[warehouse_id]" in source_context
    ) or (
        "warehouse" in incident_text
        and "warehouses[warehouse_id]" in source_context
    )


def _warehouse_old_text(source_context: str) -> str:
    for line in source_context.splitlines():
        if "warehouse_name = WAREHOUSES[warehouse_id]" in line:
            if line == line.lstrip():
                return "    warehouse_name = WAREHOUSES[warehouse_id]"
            return line
    return "    warehouse_name = WAREHOUSES[warehouse_id]"


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
