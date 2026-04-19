from __future__ import annotations

from src.models import AnalyzeIncidentRequest, AnalyzeIncidentResponse, AnalyzePatch
from src.validator import validate_analysis_response


SOURCE_CONTEXT = "\n".join(
    [
        '    warehouse_id = int(order["warehouse_id"])',
        "    warehouse_name = WAREHOUSES[warehouse_id]",
        "    return {",
    ]
)


def _req(source_context: str = SOURCE_CONTEXT) -> AnalyzeIncidentRequest:
    return AnalyzeIncidentRequest(
        incident_id="inc-test",
        repo_relative_path="apps/target/src/main.py",
        line_number=45,
        exception_type="KeyError",
        exception_message="999",
        title="Warehouse lookup crash",
        source_context=source_context,
        policy_text="# SecureLoop Security Policy",
    )


def _resp(old: str, new: str, repo_relative_path: str = "apps/target/src/main.py") -> AnalyzeIncidentResponse:
    return AnalyzeIncidentResponse(
        severity="Medium",
        category="Runtime exception",
        cwe="CWE-703",
        title="Review KeyError handling",
        explanation="Test explanation.",
        violated_policy=[],
        fix_plan=["step one", "step two", "step three"],
        diff="--- a/x\n+++ b/x\n@@\n-old\n+new",
        patch=AnalyzePatch(
            repo_relative_path=repo_relative_path,
            old_text=old,
            new_text=new,
        ),
    )


def test_validator_accepts_exact_match() -> None:
    response = _resp(
        old="    warehouse_name = WAREHOUSES[warehouse_id]",
        new="    warehouse_name = WAREHOUSES.get(warehouse_id, 'unknown')",
    )
    assert validate_analysis_response(_req(), response) == []


def test_validator_accepts_trailing_whitespace_variant() -> None:
    old_with_trailing_space = "    warehouse_name = WAREHOUSES[warehouse_id]   "
    response = _resp(
        old=old_with_trailing_space,
        new="    warehouse_name = WAREHOUSES.get(warehouse_id, 'unknown')",
    )
    errors = validate_analysis_response(_req(), response)
    assert errors == [], f"expected rstrip-normalized match to pass, got {errors}"


def test_validator_rejects_completely_different_old_text() -> None:
    response = _resp(
        old="something_the_model_hallucinated = 42",
        new="fix = 43",
    )
    errors = validate_analysis_response(_req(), response)
    assert any("patch.oldText must be an exact snippet" in err for err in errors)


def test_validator_rejects_empty_old_text() -> None:
    response = _resp(old="", new="some replacement")
    errors = validate_analysis_response(_req(), response)
    assert any("patch.oldText must be non-empty" in err for err in errors)


def test_validator_rejects_over_12_line_old_text() -> None:
    long_snippet = "\n".join(f"line_{i}" for i in range(13))
    response = _resp(old=long_snippet, new="short replacement")
    errors = validate_analysis_response(_req(source_context=long_snippet), response)
    assert any("small snippet" in err for err in errors)


def test_validator_rejects_wrong_repo_path() -> None:
    response = _resp(
        old="    warehouse_name = WAREHOUSES[warehouse_id]",
        new="    warehouse_name = WAREHOUSES.get(warehouse_id, 'unknown')",
        repo_relative_path="apps/target/src/other.py",
    )
    errors = validate_analysis_response(_req(), response)
    assert any("repoRelativePath" in err for err in errors)
