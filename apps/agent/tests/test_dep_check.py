from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dep_check import (
    _parse_pip_audit_json,
    format_dep_scan_for_prompt,
    run_pip_audit,
)


def test_parse_pip_audit_json_extracts_vulnerabilities() -> None:
    payload = {
        "dependencies": [
            {
                "name": "requests",
                "version": "2.19.0",
                "vulns": [
                    {
                        "id": "PYSEC-2018-28",
                        "fix_versions": ["2.20.0"],
                        "description": "CRLF injection in requests.",
                    }
                ],
            },
            {
                "name": "urllib3",
                "version": "1.26.4",
                "vulns": [],
            },
        ]
    }

    result = _parse_pip_audit_json(json.dumps(payload).encode("utf-8"))

    assert result is not None
    assert result.scanner == "pip-audit"
    assert len(result.vulnerabilities) == 1
    vuln = result.vulnerabilities[0]
    assert vuln.id == "PYSEC-2018-28"
    assert vuln.package == "requests"
    assert vuln.version == "2.19.0"
    assert vuln.fixed_version == "2.20.0"
    assert "CRLF" in vuln.summary


def test_parse_pip_audit_json_tolerates_missing_fields() -> None:
    payload = {
        "dependencies": [
            {
                "name": "flask",
                "version": "1.0",
                "vulns": [{"id": "CVE-2021-0000"}],
            }
        ]
    }

    result = _parse_pip_audit_json(json.dumps(payload).encode("utf-8"))

    assert result is not None
    vuln = result.vulnerabilities[0]
    assert vuln.id == "CVE-2021-0000"
    assert vuln.fixed_version is None
    assert vuln.summary == "No advisory description provided."


def test_parse_pip_audit_json_returns_empty_on_blank_input() -> None:
    assert _parse_pip_audit_json(b"") is None
    assert _parse_pip_audit_json(b"   ") is None


def test_parse_pip_audit_json_rejects_non_json() -> None:
    assert _parse_pip_audit_json(b"not json") is None


def test_format_dep_scan_for_prompt_without_result() -> None:
    text = format_dep_scan_for_prompt(None)
    assert "unavailable" in text.lower()


def test_format_dep_scan_for_prompt_with_findings() -> None:
    payload = {
        "dependencies": [
            {
                "name": "requests",
                "version": "2.19.0",
                "vulns": [
                    {
                        "id": "PYSEC-2018-28",
                        "fix_versions": ["2.20.0"],
                        "description": "CRLF injection in requests.",
                    }
                ],
            }
        ]
    }
    result = _parse_pip_audit_json(json.dumps(payload).encode("utf-8"))
    text = format_dep_scan_for_prompt(result)
    assert "PYSEC-2018-28" in text
    assert "requests==2.19.0" in text
    assert "fixed in 2.20.0" in text


def test_format_dep_scan_for_prompt_with_empty_findings() -> None:
    result = _parse_pip_audit_json(b'{"dependencies": []}')
    text = format_dep_scan_for_prompt(result)
    assert "no vulnerable dependencies detected" in text


@pytest.mark.asyncio
async def test_run_pip_audit_returns_none_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SECURELOOP_PIP_AUDIT_BIN", "")
    monkeypatch.setattr("src.dep_check.shutil.which", lambda _name: None)

    result = await run_pip_audit(tmp_path, None)

    assert result is None
