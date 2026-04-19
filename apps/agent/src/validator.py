from __future__ import annotations

import json
import re

from .models import AnalyzeIncidentRequest, AnalyzeIncidentResponse, AnalyzePatch


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
    request: AnalyzeIncidentRequest,
    response: AnalyzeIncidentResponse,
) -> list[str]:
    errors: list[str] = []

    if response.severity not in VALID_SEVERITIES:
        errors.append("severity must be one of Critical, High, Medium, Low")

    if response.patch.repo_relative_path != request.repo_relative_path:
        errors.append("patch.repoRelativePath must match the incident file")

    if not response.patch.old_text.strip():
        errors.append("patch.oldText must be non-empty")
    if not response.patch.new_text.strip():
        errors.append("patch.newText must be non-empty")

    if response.patch.old_text and response.patch.old_text not in request.source_context:
        errors.append("patch.oldText must be an exact snippet from sourceContext")

    if len(response.patch.old_text.strip().splitlines()) > 12:
        errors.append("patch.oldText should be a small snippet from the current file")

    return errors


def build_unified_diff(
    *,
    repo_relative_path: str,
    old_text: str,
    new_text: str,
) -> str:
    diff_lines = [
        f"--- a/{repo_relative_path}",
        f"+++ b/{repo_relative_path}",
        "@@",
    ]
    diff_lines.extend(f"-{line}" for line in old_text.splitlines() or [old_text])
    diff_lines.extend(f"+{line}" for line in new_text.splitlines() or [new_text])
    return "\n".join(diff_lines)


def ensure_diff_matches_patch(response: AnalyzeIncidentResponse) -> AnalyzeIncidentResponse:
    response.diff = build_unified_diff(
        repo_relative_path=response.patch.repo_relative_path,
        old_text=response.patch.old_text,
        new_text=response.patch.new_text,
    )
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


def normalize_policy_rules(policy_text: str, values: list[str]) -> list[str]:
    cleaned_values = [value.strip() for value in values if value.strip()]
    if not cleaned_values:
        return []

    policy_rule_ids = set(re.findall(r"\b(BANNED-[A-Z]+-\d+)\b", policy_text))
    if policy_rule_ids:
        return [value for value in cleaned_values if value in policy_rule_ids][:5]

    return cleaned_values[:5]
