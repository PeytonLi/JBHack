# SecureLoop

SecureLoop is a JetBrains-native security loop for catching risky code before production, walking the developer through analysis and remediation in the IDE, and using Sentry only as the last-resort safety net for issues that still escape.

## What It Does

- surfaces incidents in the `SecureLoop` tool window
- scans the active editor before commit with `Scan Current File`
- highlights the affected line in IntelliJ IDEA or PyCharm
- runs a local demo incident path for production-feedback walkthroughs
- sends the current file or selected incident to `/ide/analyze` for structured Codex analysis
- renders the analysis in the plugin, including fix plan and patch
- requires a human gate: `Approve Fix` or `Reject`
- applies the approved patch locally in the IDE
- marks incidents reviewed so the same issue does not keep replaying

## Demo Path

This is the shortest path to a visible demo.

1. Install dependencies.

```bash
pnpm install
pnpm run install:python
```

2. Create a local environment file.

```bash
cp .env.example .env
```

3. Enable demo mode in `.env`. `SECURE_LOOP_USE_FAKE_CODEX=1` keeps the live demo deterministic; set it to `0` when you want the agent to call OpenAI with `OPENAI_API_KEY`.

```dotenv
SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1
SECURE_LOOP_USE_FAKE_CODEX=1
```

4. Start the local services.

```bash
pnpm dev
```

5. Open `apps/jetbrains-plugin` as a Gradle project in IntelliJ IDEA or PyCharm.
6. Run the `runIde` task.
7. Open the JBHack repo root inside the sandbox IDE.
8. Open the `SecureLoop` tool window.
9. Open `apps/target/src/main.py`.
10. Click `Scan Current File`.
11. Review the generated analysis, then click `Approve Fix` or `Reject`.
12. Optional: click `Run Demo` to show the same loop from a Sentry-shaped production alert.

Expected result:

- a `Pre-Commit Scan` item appears immediately in the tool window
- the analysis panel shows severity, category, policy context, fix plan, diff, and patch
- `Approve Fix` applies the local patch in the editor
- `Reject` discards the suggestion without changing files
- `Run Demo` still loads a Sentry-shaped incident and highlights `apps/target/src/main.py`
- `Mark Reviewed` clears the incident from the replay queue

## Architecture

- `apps/jetbrains-plugin`: IDE plugin, current-file scan, line highlighting, analysis rendering, approve/reject gate, local patch apply
- `apps/agent`: FastAPI companion service with `/sentry/webhook`, `/ide/events/stream`, `/ide/analyze`, and review endpoints
- `apps/target`: intentionally broken demo service used to produce the incident
- `apps/dashboard`: optional queue visibility for the local incident feed

Backend analysis flow today:

1. plugin collects active-file or incident file context and the repo security policy
2. plugin POSTs to `/ide/analyze`
3. agent resolves the analysis implementation
4. Codex-backed analysis runs when available
5. validator checks the response
6. deterministic fallback returns if Codex is unavailable or invalid

## Setup

Root scripts:

- `pnpm dev`: run target, agent, and dashboard concurrently
- `pnpm run install:python`: install Python dependencies for agent and target
- `pnpm run build`: build the dashboard
- `pnpm run typecheck`: run TypeScript checks for dashboard and shared types

Real Sentry flow:

1. Set `SENTRY_DSN`, `SENTRY_AUTH_TOKEN`, and `SENTRY_WEBHOOK_SECRET` in `.env`.
2. Configure Sentry to send an issue alert webhook to `POST http://127.0.0.1:8001/sentry/webhook`.
3. Use a tunnel if Sentry is running remotely.

## Judging Story

- Pre-production is the center of gravity: the plugin finds the issue in the IDE before the code ships.
- Human review is intentional: SecureLoop proposes a fix, but the developer decides when it applies.
- Sentry is still valuable: it becomes the backstop for escaped issues and the same incident feed can still land in the IDE.

## Implemented Today

- JetBrains tool window with incident list and status
- `Scan Current File` pre-commit analysis entry point
- IDE line highlight for the resolved incident
- `Run Demo` local incident injection
- `Analyze with Codex` request path
- rendered structured analysis, including patch text
- `Approve Fix`, `Reject`, and `Mark Reviewed`
- signed Sentry webhook ingestion into the companion service
- deterministic analysis fallback when Codex is unavailable or invalid

## Roadmap

- dependency checker and dependency-aware guidance
- broader project support beyond the demo repo
- richer remediation workflows after analysis
- production hardening around incident routing and policy coverage

## Demo Script

See [docs/demo-script.md](docs/demo-script.md) for the 3-minute demo, 1-minute video script, and judge Q&A.

## Local Runbook

See [docs/LOCAL_DEMO_RUNBOOK.md](docs/LOCAL_DEMO_RUNBOOK.md) for exact commands to start the agent, launch the JetBrains plugin sandbox, run the pre-commit scan demo, test the Sentry-style backstop, and reset local demo state.

## Security Notes

- `.env` is ignored by git and must never contain committed secrets.
- Keep `.env.example` as placeholders only.
- If a credential is ever pasted into chat, screenshots, or a public commit, rotate it immediately.

## License

SecureLoop is open source under the [MIT License](LICENSE).
