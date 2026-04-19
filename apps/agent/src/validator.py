from __future__ import annotations

import json
import re

from .models import AnalyzePatch, AnalysisRequest, AnalyzeIncidentResponse


VALID_SEVERITIES = {"Critical", "High", "Medium", "Low"}


def parse_analysis_response(raw_text: str) -> AnalyzeIncidentResponse:
    cleaned = (
        raw_text.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    payload = json.loads(cleaned)
    return AnalyzeIncidentResponse.model_validate(payload)


def validate_analysis_response(
    request: AnalysisRequest,
    response: AnalyzeIncidentResponse,
) -> list[str]:
    errors: list[str] = []

    if response.severity not in VALID_SEVERITIES:
        errors.append("severity must be one of Critical, High, Medium, Low")

    patch = response.patch
    if patch.repo_relative_path != request.repo_relative_path:
        errors.append("patch.repoRelativePath must match the incident file")

    if not patch.old_text.strip():
        errors.append("patch.oldText must be non-empty")
    if not patch.new_text.strip():
        errors.append("patch.newText must be non-empty")

    source_context = request.source_context
    if patch.old_text.strip() and patch.old_text not in source_context:
        errors.append("patch.oldText must be an exact snippet from the provided sourceContext")

    if len(patch.old_text.strip().splitlines()) > 12:
        errors.append("patch.oldText should be a small snippet from the current file")

    return errors


def build_unified_diff(
    *,
    repo_relative_path: str,
    old_text: str,
    new_text: str,
) -> str:
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff_lines = [
        f"--- a/{repo_relative_path}",
        f"+++ b/{repo_relative_path}",
        "@@",
    ]
    diff_lines.extend(f"-{line}" for line in old_lines)
    diff_lines.extend(f"+{line}" for line in new_lines)
    return "\n".join(diff_lines)


def extract_policy_rule_ids(policy_text: str) -> set[str]:
    return set(re.findall(r"\b(BANNED-[A-Z]+-\d+)\b", policy_text))


def normalize_policy_rules(policy_text: str, values: list[str]) -> list[str]:
    valid_ids = extract_policy_rule_ids(policy_text)
    if not valid_ids:
        return []
    return [value for value in values if value in valid_ids]


def ensure_diff_matches_patch(response: AnalyzeIncidentResponse) -> AnalyzeIncidentResponse:
    expected_diff = build_unified_diff(
        repo_relative_path=response.patch.repo_relative_path,
        old_text=response.patch.old_text,
        new_text=response.patch.new_text,
    )
    if response.diff != expected_diff:
        response.diff = expected_diff
    return response


def build_patch(
    *,
    repo_relative_path: str,
    old_text: str,
    new_text: str,
) -> AnalyzePatch:
    return AnalyzePatch(
        repo_relative_path=repo_relative_path,
        old_text=old_text,
        new_text=new_text,
    )
