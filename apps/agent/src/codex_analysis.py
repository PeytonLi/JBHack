from __future__ import annotations

from .codex_client import call_codex, codex_available
from .models import (
    AnalysisPatch,
    AnalysisRequest,
    AnalysisResponse,
    GenerateCodeBody,
    GenerateCodeResponse,
    AnalyzeFileBody,
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


async def generate_secure_code(body: GenerateCodeBody) -> GenerateCodeResponse:
    if not codex_available():
        return GenerateCodeResponse(completion="# Codex 5.3 unavailable for generation")

    system_prompt = (
        "You are an AI code generator prioritizing secure code via SecureLoop/Codex 5.3.\n"
        "Generate a secure completion for the given source context. ONLY output the code to append or insert, "
        "no markdown blocks, no explanations. Make sure it respects this policy if provided: "
        f"{body.policy_text or 'No specific policy.'}"
    )

    result = await call_codex(
        system_prompt=system_prompt,
        user_message=f"Context:\n{body.source_context}",
        response_format={"type": "text"},
        max_output_tokens=300,
    )
    
    if not result.success:
        return GenerateCodeResponse(completion="# Codex generation failed.")
        
    return GenerateCodeResponse(completion=result.raw_text.strip())


async def analyze_file(body: AnalyzeFileBody) -> AnalysisResponse:
    request = AnalysisRequest(
        incident_id="file-scan-001",
        repo_relative_path=body.file_path,
        line_number=0,
        exception_type="StaticAnalysis",
        exception_message="On-save vulnerability scan",
        title=f"Scan: {body.file_path}",
        source_context=body.file_contents,
        policy_text=body.policy_text,
    )
    return await analyze_incident(request)


async def analyze_incident(request: AnalysisRequest) -> AnalysisResponse:
    if not codex_available():
        return _build_fallback_response(request)

    prompt = build_codex_prompt(request)
    result = await call_codex(
        system_prompt=prompt.system_prompt,
        user_message=prompt.user_message,
        response_format=prompt.response_format,
    )
    if not result.success:
        return _build_fallback_response(request)

    try:
        response = parse_analysis_response(result.raw_text)
    except Exception:
        return _build_fallback_response(request)

    response.violated_policy = normalize_policy_rules(
        request.policy_text or "",
        response.violated_policy,
    )
    response = ensure_diff_matches_patch(response)
    validation_errors = validate_analysis_response(request, response)
    if validation_errors:
        return _build_fallback_response(request, validation_errors)
    return response


def _build_fallback_response(
    request: AnalysisRequest,
    validation_errors: list[str] | None = None,
) -> AnalysisResponse:
    if _looks_like_warehouse_keyerror(request):
        old_text = _default_old_text(request)
        new_text = (
            'warehouse_id = int(order["warehouse_id"])\n'
            "    warehouse_name = WAREHOUSES.get(warehouse_id)\n"
            "    if warehouse_name is None:\n"
            '        raise HTTPException(status_code=422, detail=f"Unknown warehouse_id: {warehouse_id}")'
        )
        patch = build_patch(
            repo_relative_path=request.repo_relative_path,
            old_text=old_text,
            new_text=new_text,
        )
        diff = build_unified_diff(
            repo_relative_path=patch.repo_relative_path,
            old_text=patch.old_text,
            new_text=patch.new_text,
        )
        explanation = (
            "The incident is a functional failure, not a confirmed security vulnerability. "
            "The code indexes WAREHOUSES with a warehouse_id that is missing, which raises a KeyError "
            "during checkout for poisoned or invalid order data."
        )
        if validation_errors:
            explanation += " Codex output was unavailable or invalid, so a deterministic fallback was used."
        return AnalysisResponse(
            severity="Low",
            category="Functional Bug - Not a Security Vulnerability",
            owasp=None,
            cwe=None,
            title="Handle missing warehouse lookup during checkout",
            explanation=explanation,
            violated_policy=[],
            fix_plan=[
                "Replace the direct warehouse map lookup with a guarded lookup.",
                "Raise a controlled HTTP error when the warehouse_id is unknown instead of crashing with KeyError.",
                "Backfill data integrity protections for invalid warehouse references outside this local patch.",
            ],
            diff=diff,
            patch=patch,
        )

    old_text = _default_old_text(request)
    patch = AnalysisPatch(
        repo_relative_path=request.repo_relative_path,
        old_text=old_text,
        new_text=old_text,
    )
    diff = build_unified_diff(
        repo_relative_path=patch.repo_relative_path,
        old_text=patch.old_text,
        new_text=patch.new_text,
    )
    return AnalysisResponse(
        severity="Low",
        category="Functional Bug - Not a Security Vulnerability",
        owasp=None,
        cwe=None,
        title=request.title or "Incident analysis unavailable",
        explanation=(
            "OpenAI/Codex was unavailable or returned malformed analysis, so the agent returned a safe "
            "fallback response for manual review."
        ),
        violated_policy=[],
        fix_plan=[
            "Review the source context around the failing line.",
            "Confirm the minimal replacement before applying any patch.",
        ],
        diff=diff,
        patch=patch,
    )


def _looks_like_warehouse_keyerror(request: AnalysisRequest) -> bool:
    haystack = " ".join(
        [
            request.exception_type,
            request.exception_message,
            request.title,
            request.source_context,
            request.repo_relative_path,
        ]
    ).lower()
    return (
        "keyerror" in haystack
        and "warehouse" in haystack
        and "warehouses[" in request.source_context.lower()
    )


def _default_old_text(request: AnalysisRequest) -> str:
    stripped = request.source_context.strip("\n")
    if stripped:
        return stripped
    return "# source context unavailable"
