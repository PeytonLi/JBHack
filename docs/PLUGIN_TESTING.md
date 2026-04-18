# Plugin Testing

Use this guide to verify the SecureLoop plugin from the easiest onboarding flow to the full signed Sentry path.

## Fast Demo Flow

This is the preferred smoke test for a new user.

1. Create `.env` from `.env.example`.
2. Set `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1` in `.env`.
3. Start the repo:

```bash
pnpm install
pnpm run install:python
pnpm dev
```

4. Confirm the agent is healthy:

```bash
curl http://127.0.0.1:8001/health
```

Expected fields:

- `status`
- `sqlitePath`
- `ideTokenFile`
- `allowDebugEndpoints`

5. Open `apps/jetbrains-plugin` as a Gradle project in IntelliJ IDEA or PyCharm.
6. Run the Gradle `runIde` task.
7. In the sandbox IDE, open this repo as the project.
8. Open the `SecureLoop` tool window.
9. Wait for the panel to show `Demo ready`.
10. Click `Run Demo`.

Expected result:

- the panel reports that the demo repo and security policy were detected
- a new incident appears in the `SecureLoop` tool window
- the sandbox IDE shows a notification balloon
- `apps/target/src/main.py` opens automatically if the sandbox window is active
- line 37 is highlighted with a warning gutter icon
- the dashboard at `http://127.0.0.1:3000` shows one open incident

11. Click `Mark Reviewed` inside the tool window.

Expected review result:

- the incident remains visible in the plugin for the current session, but is marked reviewed
- refreshing the dashboard moves the incident from `Open Incidents` to `Reviewed History`
- restarting the sandbox IDE does not replay that incident anymore

## Manual Debug Endpoint Check

Use this only if you want to verify the raw endpoint directly. The primary path is the `Run Demo` button.

PowerShell:

```powershell
$token = Get-Content $HOME\.secureloop\ide-token
$body = @{
  repoRelativePath = "apps/target/src/main.py"
  lineNumber = 37
  exceptionType = "RuntimeError"
  exceptionMessage = "plugin smoke test"
  title = "Local plugin smoke test"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8001/debug/incidents `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType "application/json" `
  -Body $body
```

Bash:

```bash
TOKEN="$(cat ~/.secureloop/ide-token)"
curl -X POST http://127.0.0.1:8001/debug/incidents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "repoRelativePath": "apps/target/src/main.py",
    "lineNumber": 37,
    "exceptionType": "RuntimeError",
    "exceptionMessage": "plugin smoke test",
    "title": "Local plugin smoke test"
  }'
```

## Full Sentry Flow

Use this when you want to verify the signed webhook path rather than the built-in demo flow.

1. Set these values in `.env`:

- `SENTRY_DSN`
- `SENTRY_AUTH_TOKEN`
- `SENTRY_WEBHOOK_SECRET`

2. In Sentry, configure an issue alert webhook pointing at the companion service:

```text
POST http://127.0.0.1:8001/sentry/webhook
```

If Sentry is remote, expose the local service with a tunnel first.

3. Start the target service, companion service, and sandbox IDE.
4. Trigger the broken checkout path:

```bash
curl -X POST http://127.0.0.1:8000/checkout \
  -H "Content-Type: application/json" \
  -d '{"order_id":"POISON-001"}'
```

5. Expected result:

- the target returns a 500
- Sentry records the event
- the companion service receives the signed alert and fetches the full event
- the plugin shows the incident and highlights the failing line
- the dashboard shows the same incident in the open queue until it is marked reviewed

## Failure Checklist

- panel says `Unsupported project`: open the JBHack repo root rather than only the plugin module
- panel says `Waiting for local agent`: start `pnpm dev` and verify `GET /health`
- panel says demo mode is off: set `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1` and restart the agent
- panel says `Agent authorization failed`: delete the stale token file under `~/.secureloop/ide-token` and restart the agent
- incident appears but file does not open: the repo path did not resolve uniquely in the open project
