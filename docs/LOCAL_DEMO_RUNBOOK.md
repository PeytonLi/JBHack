# SecureLoop Local Demo Runbook

Use this runbook to start SecureLoop locally, launch the JetBrains plugin
sandbox, and verify the judged demo flow.

## Prerequisites

- IntelliJ IDEA or PyCharm installed
- JDK 21 available to Gradle
- `uv` installed for Python services
- `pnpm` installed for the optional dashboard path
- repo opened at:

```bash
/Users/asribhas/Desktop/jetbrains-codex-hack/JBHack
```

## One-Time Setup

From the repo root:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack
pnpm install
pnpm run install:python
cp .env.example .env
```

For the live hackathon demo, use deterministic Codex mode unless we are
explicitly testing real API calls:

```dotenv
SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1
SECURE_LOOP_USE_FAKE_CODEX=1
```

Real OpenAI mode is optional:

```dotenv
OPENAI_API_KEY=sk-...
SECURE_LOOP_USE_FAKE_CODEX=0
```

Do not commit `.env`.

## Reset Demo State

Run this before every demo rehearsal so the vulnerable line exists again:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack
git restore apps/target/src/main.py
```

If the agent port is already taken:

```bash
lsof -nP -iTCP:8001 -sTCP:LISTEN
kill <PID>
```

If the target service port is already taken:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
kill <PID>
```

## Start The Agent

Terminal 1:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack/apps/agent
SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1 SECURE_LOOP_USE_FAKE_CODEX=1 PYTHONPATH=. uv run uvicorn src.main:app --host 127.0.0.1 --port 8001 --reload
```

Expected output:

```text
Uvicorn running on http://127.0.0.1:8001
Application startup complete.
```

Health check from another terminal:

```bash
curl http://127.0.0.1:8001/health
```

Expected shape:

```json
{
  "status": "ok",
  "allowDebugEndpoints": true
}
```

## Start The Target Service

Terminal 2:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack/apps/target
uv run uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

Expected output:

```text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

Optional target health check:

```bash
curl http://127.0.0.1:8000/health
```

## Launch The JetBrains Plugin Sandbox

Terminal 3:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack/apps/jetbrains-plugin
GRADLE_USER_HOME=$PWD/.gradle-home sh ./gradlew runIde
```

This opens a sandbox JetBrains IDE with the SecureLoop plugin installed.

Inside the sandbox IDE:

1. Open `/Users/asribhas/Desktop/jetbrains-codex-hack/JBHack` as the project.
2. Open the `SecureLoop` tool window on the right side.
3. Open `apps/target/src/main.py`.
4. Confirm the SecureLoop panel says it is connected to `http://127.0.0.1:8001`.

If the plugin UI looks stale, close the sandbox IDE and run `runIde` again.

## Primary Demo: Pre-Commit Scan

This is the main judged demo path.

1. Make sure `apps/target/src/main.py` contains:

```python
warehouse_name = WAREHOUSES[warehouse_id]
```

2. In the sandbox IDE, keep `apps/target/src/main.py` active.
3. Click `Scan Current File`.
4. Select the row:

```text
LocalScan Pre-Commit Scan apps/target/src/main.py:45
```

Expected panel state:

```text
Exception: LocalScan
Line: 45
Analysis state: Analysis ready
Severity: Medium
CWE: CWE-703
```

Expected explanation:

```text
Detected unchecked warehouse lookup that can raise an unhandled KeyError.
```

Expected diff:

```diff
-    warehouse_name = WAREHOUSES[warehouse_id]
+    warehouse_name = WAREHOUSES.get(warehouse_id)
+    if warehouse_name is None:
+        raise HTTPException(status_code=409, detail="Order references an unknown warehouse.")
```

5. Click `Approve Fix`.
6. Verify the patch:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack
git diff -- apps/target/src/main.py
```

7. Reset after verification:

```bash
git restore apps/target/src/main.py
```

## Secondary Demo: Sentry-Style Backstop

Use this only after the pre-commit scan path works.

In the SecureLoop tool window, click `Run Demo`.

Expected result:

- a `RuntimeError SecureLoop demo incident` row appears
- `apps/target/src/main.py` opens
- line `45` is highlighted
- `Analyze with Codex` can produce the same structured diagnosis and diff

Manual debug incident fallback:

```bash
TOKEN="$(cat ~/.secureloop/ide-token)"

curl -i -X POST http://127.0.0.1:8001/debug/incidents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "repoRelativePath": "apps/target/src/main.py",
    "lineNumber": 45,
    "exceptionType": "RuntimeError",
    "exceptionMessage": "SecureLoop demo mode",
    "title": "SecureLoop demo incident",
    "functionName": "checkout",
    "codeContext": "warehouse_name = WAREHOUSES[warehouse_id]"
  }'
```

Expected response:

```text
HTTP/1.1 201 Created
```

## Optional Dashboard

If `pnpm` is available:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack
pnpm dev
```

Open:

```text
http://localhost:3000
```

Expected dashboard behavior:

- agent health shows connected
- open incidents appear after `Run Demo`
- reviewed incidents move to history after `Mark Reviewed` in the IDE

If `pnpm dev` is too noisy during judging, skip the dashboard and keep the
JetBrains plugin as the primary demo.

## Verification Commands

Agent tests:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack/apps/agent
SECURE_LOOP_HOME=$PWD/.test-secureloop uv run pytest -q
rm -rf .test-secureloop
```

Plugin compile:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack/apps/jetbrains-plugin
GRADLE_USER_HOME=$PWD/.gradle-home sh ./gradlew compileKotlin
```

Dashboard checks, if `pnpm` is installed:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack
pnpm run typecheck
pnpm run build
```

## Troubleshooting

### `Address already in use`

Find and stop the stale process:

```bash
lsof -nP -iTCP:8001 -sTCP:LISTEN
kill <PID>
```

### `Analyze request failed with HTTP 422`

The plugin sandbox is likely stale. Close the sandbox IDE and restart:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack/apps/jetbrains-plugin
GRADLE_USER_HOME=$PWD/.gradle-home sh ./gradlew runIde
```

### `Patch precondition failed: expected oldText exactly once, found 0 matches`

The patch was already applied. Reset the target file:

```bash
cd /Users/asribhas/Desktop/jetbrains-codex-hack/JBHack
git restore apps/target/src/main.py
```

### `Scan Current File` falls back to the caret line

The vulnerable pattern is already fixed or missing. Reset the target file:

```bash
git restore apps/target/src/main.py
```

Then run `Scan Current File` again.

### Plugin cannot connect to agent

Confirm the agent is running:

```bash
curl http://127.0.0.1:8001/health
```

If health fails, restart the agent command from this runbook.

## Final Demo Checklist

- `git restore apps/target/src/main.py`
- agent running on `127.0.0.1:8001`
- plugin sandbox running
- SecureLoop tool window connected
- `Scan Current File` creates `LocalScan Pre-Commit Scan`
- analysis shows severity, CWE, policy, fix plan, dependency context, and diff
- `Approve Fix` applies patch
- `Show Diff` works if visible
- `Open PR` works or shows the local fallback
- `Run Demo` works as the Sentry-style backstop
