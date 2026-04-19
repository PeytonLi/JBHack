from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .models import DepCheckResult, DepVuln


logger = logging.getLogger("secureloop.agent.dep_check")

_ADVISORY_URL = "https://pypi.org/security/"


def repo_has_python_manifest(repo_root: Path) -> bool:
    if (repo_root / "pyproject.toml").exists():
        return True
    if (repo_root / "requirements.txt").exists():
        return True
    try:
        for entry in repo_root.iterdir():
            if entry.is_file() and entry.name.startswith("requirements-") and entry.name.endswith(".txt"):
                return True
    except (FileNotFoundError, PermissionError):
        return False
    return False


async def run_pip_audit(
    repo_root: Path,
    target_requirements: Path | None,
    timeout_s: float = 30.0,
) -> DepCheckResult | None:
    if not repo_has_python_manifest(repo_root):
        return None

    binary = os.environ.get("SECURELOOP_PIP_AUDIT_BIN") or shutil.which("pip-audit")
    if not binary:
        return None

    args: list[str] = [binary, "--format", "json"]
    if target_requirements and target_requirements.exists():
        args += ["-r", str(target_requirements)]
    else:
        args += ["--local"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return None
    except (FileNotFoundError, OSError):
        return None

    return _parse_pip_audit_json(stdout)


def _parse_pip_audit_json(raw: bytes) -> DepCheckResult | None:
    if not raw:
        return None

    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("pip-audit produced non-JSON output; ignoring.")
        return None

    dependencies = (
        payload.get("dependencies")
        if isinstance(payload, dict)
        else payload
    )
    if not isinstance(dependencies, list):
        return DepCheckResult(
            scanner="pip-audit",
            vulnerabilities=[],
            advisory_url=_ADVISORY_URL,
            scanned_at=datetime.now(UTC),
        )

    vulns: list[DepVuln] = []
    for dep in dependencies:
        if not isinstance(dep, dict):
            continue
        name = str(dep.get("name") or dep.get("package") or "").strip()
        version = str(dep.get("version") or "").strip()
        raw_vulns = dep.get("vulns") or dep.get("vulnerabilities") or []
        if not isinstance(raw_vulns, list):
            continue
        for vuln in raw_vulns:
            if not isinstance(vuln, dict):
                continue
            advisory_id = str(vuln.get("id") or "").strip()
            fix_versions = vuln.get("fix_versions") or vuln.get("fixVersions") or []
            fixed_version = None
            if isinstance(fix_versions, list) and fix_versions:
                fixed_version = str(fix_versions[0])
            description = str(
                vuln.get("description")
                or vuln.get("summary")
                or ""
            ).strip()
            vulns.append(
                DepVuln(
                    id=advisory_id or "UNKNOWN",
                    severity=_severity_for(advisory_id),
                    package=name or "unknown",
                    version=version or "unknown",
                    fixed_version=fixed_version,
                    summary=description or "No advisory description provided.",
                )
            )

    return DepCheckResult(
        scanner="pip-audit",
        vulnerabilities=vulns,
        advisory_url=_ADVISORY_URL,
        scanned_at=datetime.now(UTC),
    )


def _severity_for(advisory_id: str) -> str:
    ident = advisory_id.upper()
    if ident.startswith("GHSA-"):
        return "unknown"
    if ident.startswith("PYSEC-") or ident.startswith("CVE-"):
        return "unknown"
    return "unknown"


def format_dep_scan_for_prompt(result: DepCheckResult | None) -> str:
    if result is None:
        return "Dependency scan unavailable (pip-audit binary missing or timed out)."
    if not result.vulnerabilities:
        return "pip-audit: no vulnerable dependencies detected."
    lines = ["pip-audit findings:"]
    for v in result.vulnerabilities:
        fixed = f" (fixed in {v.fixed_version})" if v.fixed_version else ""
        lines.append(f"- [{v.id}] {v.package}=={v.version}{fixed}: {v.summary}")
    return "\n".join(lines)
