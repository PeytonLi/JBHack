from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from github import Github, GithubException, UnknownObjectException

from .models import AnalyzeIncidentResponse, CamelModel


logger = logging.getLogger("secureloop.agent.github_client")


class PullRequestResult(CamelModel):
    pr_url: str | None = None
    pr_number: int | None = None
    branch: str | None = None
    local_artifact_path: str | None = None
    error: str | None = None


@dataclass(slots=True)
class FetchedFile:
    content: str
    sha: str
    ref: str
    path: str


class GitHubClient:
    def __init__(self, token: str, repo: str) -> None:
        self._gh = Github(token)
        self._repo = self._gh.get_repo(repo)
        self._default_branch_cache: str | None = None

    @property
    def default_branch(self) -> str:
        return self._repo.default_branch or "main"

    def fetch_default_branch(self) -> str:
        if self._default_branch_cache is None:
            self._default_branch_cache = self._repo.default_branch or "main"
        return self._default_branch_cache

    def fetch_file(self, path: str, ref: str | None = None) -> FetchedFile:
        resolved_ref = ref or self.fetch_default_branch()
        try:
            contents = self._repo.get_contents(path, ref=resolved_ref)
        except UnknownObjectException as exc:
            raise FileNotFoundError(path) from exc
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError(path) from exc
            raise
        if isinstance(contents, list):
            raise FileNotFoundError(path)

        raw = contents.content or ""
        encoding = (contents.encoding or "").lower()
        if encoding == "base64":
            decoded = base64.b64decode(raw).decode("utf-8")
        else:
            decoded = raw
        return FetchedFile(
            content=decoded,
            sha=contents.sha,
            ref=resolved_ref,
            path=contents.path,
        )

    def open_pr_for_incident(
        self,
        incident_id: str,
        analysis: AnalyzeIncidentResponse,
        relative_path: str,
        updated_file_content: str,
        base_branch: str | None = None,
        extra_files: list[tuple[str, str]] | None = None,
    ) -> PullRequestResult:
        base = base_branch or self.default_branch
        branch = _branch_name(incident_id, analysis)
        base_ref = self._repo.get_branch(base)
        branch = self._create_branch(branch, base_ref.commit.sha)

        commit_message = build_commit_message(analysis, relative_path)
        existing = self._get_file_sha(relative_path, branch)
        if existing is None:
            self._repo.create_file(
                path=relative_path,
                message=commit_message,
                content=updated_file_content,
                branch=branch,
            )
        else:
            self._repo.update_file(
                path=relative_path,
                message=commit_message,
                content=updated_file_content,
                sha=existing,
                branch=branch,
            )

        for extra_path, extra_content in extra_files or []:
            extra_sha = self._get_file_sha(extra_path, branch)
            extra_message = f"test(security): add sandbox reproduction for {incident_id}"
            if extra_sha is None:
                self._repo.create_file(
                    path=extra_path,
                    message=extra_message,
                    content=extra_content,
                    branch=branch,
                )
            else:
                self._repo.update_file(
                    path=extra_path,
                    message=extra_message,
                    content=extra_content,
                    sha=extra_sha,
                    branch=branch,
                )

        pr = self._repo.create_pull(
            title=commit_message,
            body=build_pr_body(incident_id, analysis),
            head=branch,
            base=base,
        )
        return PullRequestResult(
            pr_url=pr.html_url,
            pr_number=pr.number,
            branch=branch,
        )

    def _create_branch(self, branch: str, sha: str) -> str:
        ref = f"refs/heads/{branch}"
        try:
            self._repo.create_git_ref(ref=ref, sha=sha)
            return branch
        except GithubException as exc:
            if exc.status != 422:
                raise
            suffix = datetime.now(UTC).strftime("%H%M%S")
            alternate = f"{branch}-{suffix}"
            self._repo.create_git_ref(ref=f"refs/heads/{alternate}", sha=sha)
            return alternate

    def _get_file_sha(self, path: str, branch: str) -> str | None:
        try:
            contents = self._repo.get_contents(path, ref=branch)
        except UnknownObjectException:
            return None
        except GithubException as exc:
            if exc.status == 404:
                return None
            raise
        if isinstance(contents, list):
            return None
        return contents.sha


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "fix"


def _branch_name(incident_id: str, analysis: AnalyzeIncidentResponse) -> str:
    identifier = analysis.cwe or analysis.category or "fix"
    return f"secureloop/{incident_id[:8]}-{_slugify(identifier)}"


def build_commit_message(analysis: AnalyzeIncidentResponse, relative_path: str) -> str:
    cwe = analysis.cwe or "security"
    category = analysis.category or "fix"
    return f"fix(security): {cwe} {category} in {relative_path}"


def _render_section(lines: list[str], heading: str, value: str) -> None:
    lines.append(heading)
    lines.append(value.strip() or "_Not provided._")
    lines.append("")


def build_pr_body(incident_id: str, analysis: AnalyzeIncidentResponse) -> str:
    lines: list[str] = []
    lines.append(f"**Severity:** {analysis.severity}")
    lines.append(f"**CWE:** {analysis.cwe}")
    lines.append(f"**Category:** {analysis.category}")
    lines.append("")

    _render_section(lines, "## Attack scenario", analysis.explanation or "(no explanation provided)")
    _render_section(lines, "## Root cause", analysis.root_cause)
    _render_section(lines, "## The fix", analysis.fix_summary)

    lines.append("## Fix plan")
    if analysis.fix_plan:
        for idx, step in enumerate(analysis.fix_plan, start=1):
            lines.append(f"{idx}. {step}")
    else:
        lines.append("1. (no fix plan)")
    lines.append("")

    _render_section(lines, "## Impact", analysis.impact)
    _render_section(lines, "## How to prevent this", analysis.prevention)
    _render_section(lines, "## Severity rationale", analysis.severity_rationale)

    lines.append("## Dependency scan")
    dep = analysis.dep_check
    if dep is None:
        lines.append("Dependency scan unavailable.")
    elif not dep.vulnerabilities:
        lines.append(f"{dep.scanner}: no vulnerable dependencies detected.")
    else:
        lines.append(f"{dep.scanner}: {len(dep.vulnerabilities)} vulnerable package(s).")
        for v in dep.vulnerabilities:
            fixed = f" (fix: {v.fixed_version})" if v.fixed_version else ""
            lines.append(f"- [{v.id}] {v.package}=={v.version}{fixed}: {v.summary}")
    lines.append("")
    lines.append(f"Incident ID: `{incident_id}`")
    lines.append("")
    lines.append("_Generated by SecureLoop_")
    return "\n".join(lines)
