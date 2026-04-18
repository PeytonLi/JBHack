# SecureLoop (JBHack)

SecureLoop turns a production-style alert into an IDE-native security workflow. This repo currently implements the ingress and review slice of the hackathon demo: a broken target service, a local companion agent, a JetBrains plugin, and a dashboard over the local incident queue.

## Repo Layout

- `apps/target`: intentionally broken FastAPI service
- `apps/agent`: companion service that receives Sentry alerts and streams normalized incidents to the IDE
- `apps/dashboard`: Next.js dashboard for local incident queue visibility and review history
- `apps/jetbrains-plugin`: IntelliJ Platform plugin for incident surfacing and line highlighting
- `security-policy.md`: repo-local security constraints used by the SecureLoop flow

## Quick Start For New Users

This is the shortest path for someone new to the project to see the plugin work without touching tokens or curl commands.

1. Install dependencies:

```bash
pnpm install
pnpm run install:python
```

2. Create a local environment file:

```bash
cp .env.example .env
```

3. Enable demo mode in `.env`:

```dotenv
SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1
```

4. Start the target service, agent, and dashboard:

```bash
pnpm dev
```

5. Open `apps/jetbrains-plugin` as a Gradle project in IntelliJ IDEA or PyCharm.
6. Run the `runIde` Gradle task.
7. In the sandbox IDE, open the JBHack repo root.
8. Open the `SecureLoop` tool window.
9. Click `Run Demo`.

Expected result:

- the tool window reports `Demo ready`
- a sample incident appears in the incident list
- `apps/target/src/main.py` opens automatically when the window is active
- the failing line is highlighted in the editor
- the dashboard at `http://127.0.0.1:3000` shows the incident as `open`
- clicking `Mark Reviewed` in the plugin moves the incident into reviewed history

## Real Webhook Flow

After demo mode works, you can switch to a real signed Sentry flow.

Set these values in `.env`:

- `SENTRY_DSN`
- `SENTRY_AUTH_TOKEN`
- `SENTRY_WEBHOOK_SECRET`

Then configure Sentry to send an issue alert webhook to:

```text
POST http://127.0.0.1:8001/sentry/webhook
```

If Sentry is remote, expose the local agent with a tunnel first.

## Root Scripts

- `pnpm dev`: run target, agent, and dashboard concurrently
- `pnpm run install:python`: install Python dependencies for agent and target
- `pnpm run build`: build the dashboard
- `pnpm run typecheck`: run TypeScript checks for dashboard and shared-types

## What Exists Today

- signed Sentry webhook ingestion into the local companion service
- normalized incident streaming to the JetBrains plugin over SSE
- explicit human review in the plugin via `Mark Reviewed`
- a dashboard that reflects open incidents and reviewed history from the local queue

## Not Implemented Yet

- Codex analysis, CWE classification, or fix generation
- COE artifact generation
- GitHub PR creation
- Supabase-backed production data investigation

## Documentation

- `apps/jetbrains-plugin/README.md`: plugin-specific setup and behavior
- `docs/PLUGIN_TESTING.md`: smoke test, dashboard verification, and signed webhook checks
- `docs/AGENT_CONTEXT.md`: internal implementation plan
- `docs/DESIGN_DOC.md`: design rationale and tradeoffs
- `STORYBOARD.md`: 3-minute demo storyline

## Security Notes

- `.env` is ignored by git and must never contain committed secrets.
- Keep `.env.example` as placeholders only.
- If a credential is ever pasted into chat, screenshots, or a public commit, rotate it immediately.
