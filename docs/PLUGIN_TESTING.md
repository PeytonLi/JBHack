# Plugin Testing

Use this guide to verify the JetBrains plugin from the fastest local smoke test to the full signed Sentry flow.

## Fast Local Smoke Test

This is the quickest way to prove the plugin is connected, receiving incidents, and highlighting the expected file and line.

1. Create `.env` from `.env.example`.
2. Set `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1` in `.env`.
3. Start the target and companion services:

```bash
pnpm run install:python
pnpm dev
```

4. Confirm the companion service is healthy:

```bash
curl http://127.0.0.1:8001/health
```

The response should include `status`, `sqlitePath`, and `ideTokenFile`.

5. Open `apps/jetbrains-plugin` as a Gradle project in IntelliJ IDEA or PyCharm.
6. Run the Gradle `runIde` task from the IDE.
7. In the sandbox IDE, open this repo as the project.
8. Verify the `SecureLoop` tool window is visible.
9. Read the IDE token that the companion service wrote.

PowerShell:

```powershell
Get-Content $HOME\.secureloop\ide-token
```

Bash:

```bash
cat ~/.secureloop/ide-token
```

10. Post a debug incident using that token.

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

11. Expected result:

- a new item appears in the `SecureLoop` tool window
- the sandbox IDE shows a notification balloon
- `apps/target/src/main.py` opens automatically if the match is unique and the sandbox window is active
- line 37 is highlighted with a warning gutter icon

## Full Sentry Flow

Use this when you want to verify the signed webhook path rather than only the IDE path.

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

## What Working Looks Like

The plugin is working correctly when all of these are true:

- `GET /health` returns `status: ok`
- `%USERPROFILE%/.secureloop/ide-token` or `~/.secureloop/ide-token` exists
- the sandbox IDE shows the `SecureLoop` tool window
- posting to `/debug/incidents` returns `201`
- the tool window updates without restarting the companion service
- the file open and highlight match the `repoRelativePath` and `lineNumber` you sent

## Failure Checklist

- `401` from `/debug/incidents`: the bearer token does not match the token file written by the companion service
- `404` from `/debug/incidents`: `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS` is not enabled
- tool window is empty: the plugin is not running in the sandbox IDE or cannot connect to `http://127.0.0.1:8001`
- file does not open: the sandbox IDE did not open the JBHack repo, or the `repoRelativePath` does not match a project file
- incident appears but does not auto-open: the sandbox IDE window was not active, or the path matched multiple files
