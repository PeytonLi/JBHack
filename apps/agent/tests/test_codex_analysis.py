from __future__ import annotations

import asyncio

from src.codex_analysis import analyze_incident
from src.models import AnalysisRequest


def test_analyze_incident_returns_demo_fallback(monkeypatch) -> None:
    monkeypatch.setenv("SECURE_LOOP_USE_FAKE_CODEX", "1")

    response = asyncio.run(
        analyze_incident(
            AnalysisRequest(
                incident_id="incident-123",
                repo_relative_path="apps/target/src/main.py",
                line_number=45,
                exception_type="KeyError",
                exception_message="999",
                title="KeyError: 999",
                source_context='warehouse_id = int(order["warehouse_id"])\n    warehouse_name = WAREHOUSES[warehouse_id]',
                policy_text="",
            )
        )
    )

    assert response.severity == "Low"
    assert response.category == "Functional Bug - Not a Security Vulnerability"
    assert response.patch.repo_relative_path == "apps/target/src/main.py"
    assert 'WAREHOUSES[warehouse_id]' in response.patch.old_text
    assert "WAREHOUSES.get(warehouse_id)" in response.patch.new_text
