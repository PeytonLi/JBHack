"""End-to-end smoke test for the Open-in-IDE flow.

Run against a live agent on http://127.0.0.1:8001. Requires
SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1 and the IDE token at
~/.secureloop/ide-token.

Usage: uv run python apps/agent/tests/smoke_open_in_ide.py
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8001"
TOKEN_FILE = Path.home() / ".secureloop" / "ide-token"


def post(path: str, body: dict, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.post(f"{BASE}{path}", json=body, headers=headers, timeout=10.0)
    return resp.status_code, (resp.json() if resp.content else {})


def collect_sse(
    path: str,
    token: str | None,
    sink: list,
    ready: threading.Event,
    deadline: float,
) -> None:
    headers = {"Accept": "text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    timeout = httpx.Timeout(15.0, read=15.0)
    with httpx.stream("GET", f"{BASE}{path}", headers=headers, timeout=timeout) as resp:
        ready.set()
        event_name = "message"
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                sink.append((event_name, line[len("data:"):].strip()))
                event_name = "message"
            if time.time() > deadline:
                return


def main() -> int:
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    print(f"[smoke] token loaded ({len(token)} chars) from {TOKEN_FILE}")

    status, payload = post(
        "/debug/incidents",
        {
            "repoRelativePath": "apps/target/src/main.py",
            "lineNumber": 45,
            "exceptionType": "KeyError",
            "exceptionMessage": "999",
            "title": "Open-in-IDE smoke incident",
        },
        token=token,
    )
    assert status == 201, f"debug create failed: {status} {payload}"
    incident_id = payload["incidentId"]
    print(f"[smoke] created incident {incident_id}")

    plugin_sink: list = []
    dash_sink: list = []
    plugin_ready = threading.Event()
    dash_ready = threading.Event()
    deadline = time.time() + 8.0
    plugin_t = threading.Thread(
        target=collect_sse,
        args=("/ide/events/stream", token, plugin_sink, plugin_ready, deadline),
        daemon=True,
    )
    dash_t = threading.Thread(
        target=collect_sse,
        args=("/dashboard/events/stream", None, dash_sink, dash_ready, deadline),
        daemon=True,
    )
    plugin_t.start()
    dash_t.start()
    assert plugin_ready.wait(5.0), "plugin SSE did not connect"
    assert dash_ready.wait(5.0), "dashboard SSE did not connect"
    time.sleep(1.5)

    status, navigate_resp = post("/ide/navigate", {"incidentId": incident_id})
    print(f"[smoke] /ide/navigate -> {status} {navigate_resp}")
    assert status == 200, f"navigate failed: {status} {navigate_resp}"

    plugin_t.join(timeout=7.0)
    dash_t.join(timeout=7.0)

    plugin_navigates = [(name, data) for name, data in plugin_sink if name == "ide.navigate"]
    dash_navigates = [(name, data) for name, data in dash_sink if name == "ide.navigate"]
    print(f"[smoke] plugin received {len(plugin_navigates)} ide.navigate event(s)")
    print(f"[smoke] dashboard received {len(dash_navigates)} ide.navigate event(s)")
    if plugin_navigates:
        nav_payload = json.loads(plugin_navigates[0][1])
        print(f"[smoke] navigate payload = {json.dumps(nav_payload, indent=2)}")
        assert nav_payload["incidentId"] == incident_id
        assert nav_payload["repoRelativePath"] == "apps/target/src/main.py"
        assert nav_payload["lineNumber"] == 45

    failures = []
    if not navigate_resp.get("delivered"):
        failures.append(f"delivered=False (subscribers={navigate_resp.get('subscribers')})")
    if navigate_resp.get("incidentId") != incident_id:
        failures.append(f"incidentId mismatch: {navigate_resp.get('incidentId')!r} != {incident_id!r}")
    if len(plugin_navigates) != 1:
        failures.append(f"expected 1 ide.navigate on plugin stream, got {len(plugin_navigates)}")
    if dash_navigates:
        failures.append(f"dashboard stream leaked {len(dash_navigates)} ide.navigate event(s)")

    if failures:
        print("[smoke] FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[smoke] PASS — Open-in-IDE end-to-end OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
