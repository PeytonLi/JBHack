# SecureLoop

SecureLoop turns production Sentry alerts into Codex-generated, sandbox-tested,
human-approved fixes inside JetBrains.

**One-line pitch:** production alert to verified PR, with the developer still in
control.

```text
alert -> diagnose -> patch -> sandbox -> PR -> IDE approval
```

Built for the **JetBrains Codex Hackathon 2026**.

## Why It Matters

Security and reliability tools usually stop at detection.

- Sentry catches a production error, then leaves the developer with a stack trace.
- Dependency scanners flag risk, then leave the developer with a dashboard.
- AI assistants can suggest code, but usually lack the incident, policy, repo,
  verification, and review context in one loop.

SecureLoop connects those steps. A real production-shaped alert enters the agent,
Codex reasons over source context and project policy, a sandbox test checks the
patch, and the final review stays in JetBrains before code is shipped.

## What We Built

SecureLoop is a local developer workflow with four pieces:

- **FastAPI agent**: receives Sentry webhooks, stores incidents, runs Codex
  analysis, launches the autopilot pipeline, and emits live events.
- **JetBrains plugin**: shows incidents in the IDE, opens the affected file,
  highlights the line, renders analysis, and keeps the human approval surface.
- **Next.js dashboard**: shows the live incident queue, autopilot progress,
  session history, and light/dark stage mode for the demo.
- **Demo target app**: intentionally vulnerable/broken service used to produce
  reproducible incidents.

## Primary Demo Flow

```text
Sentry alert
  -> signed webhook reaches SecureLoop agent
  -> incident appears on dashboard via SSE
  -> autopilot fetches the affected source file from GitHub
  -> Codex analyzes stack trace, source context, dependency context, and policy
  -> Codex returns severity, CWE, root cause, fix plan, diff, and PR narrative
  -> agent applies the patch in memory
  -> generated pytest sandbox verifies the original failure and patched behavior
  -> GitHub PR is opened, or local PR artifacts are written as fallback
  -> JetBrains opens the file for developer review and approval
```

The design intentionally keeps a human in the loop. SecureLoop can propose and
verify a fix, but it does not ask developers to blindly trust an agent.

## Implemented Today

- Sentry webhook ingestion with signature verification
- Sentry issue/error normalization into repo-relative incidents
- SQLite incident store and live SSE broker
- dashboard incident stream with open/reviewed queues
- dashboard autopilot stage view with light/dark theme toggle
- JetBrains plugin tool window for incidents and line highlighting
- Open-in-IDE navigation from dashboard/agent to the plugin
- Codex-backed analysis path with structured JSON validation
- `security-policy.md` as repo-local policy context for analysis/fixes
- dependency scan context using `pip-audit`
- autopilot source fetch from GitHub
- generated sandbox pytest step for Python incidents
- GitHub PR creation with rich generated title/body
- local PR artifact fallback when GitHub PR creation fails
- manual/local fallback paths: `Scan Current File`, `Run Demo`, `Analyze with Codex`,
  `Approve Fix`, `Reject`, and `Mark Reviewed`

## What Makes It Different

| Tool | Typical output | Where it stops |
| --- | --- | --- |
| Sentry | Stack trace and issue | Investigation starts |
| Snyk / pip-audit | Vulnerable dependency | Developer must decide and patch |
| AI chat | Suggested fix | Context transfer and verification are manual |
| SecureLoop | Incident, analysis, patch, sandbox proof, PR, IDE approval | Developer reviews a verified code change |

SecureLoop operates in the consequence layer: it starts from a real alert,
connects it back to code, and produces a reviewable fix with evidence.

## Why JetBrains + Codex

This is not a chatbot wrapped around a repo.

- **JetBrains** is the control surface: affected files open in the IDE, the
  relevant line is highlighted, and the developer approves or rejects the patch
  where they already work.
- **Codex** is the remediation engine: it receives the incident, source context,
  dependency context, and policy text, then returns structured analysis and a
  minimal patch.
- **The agent** connects the loop: Sentry, GitHub, sandbox verification,
  dashboard state, and JetBrains events all stay synchronized.

## What To Watch In The Demo

1. A production-shaped Sentry alert lands in SecureLoop.
2. The dashboard moves from detection to Codex diagnosis to sandbox proof.
3. JetBrains opens the exact file and line tied to the alert.
4. The developer reviews the generated fix with severity, CWE, policy evidence,
   diff, and PR narrative.
5. The fix is opened as a PR, or written as local PR artifacts if GitHub is not
   available during the live demo.

## Policy-Aware Fixes

The repository includes `security-policy.md`, which acts as local guidance for
Codex. It defines banned patterns, required error-handling behavior, secret
handling expectations, and fix constraints.

That is why the demo uses the phrase **smallest policy-aware fix**:

- **smallest**: minimize blast radius during incident remediation
- **policy-aware**: use repo-specific constraints instead of generic internet
  advice
- **fix**: produce a concrete patch, not just a summary

The broader product idea is that every serious repo should ship a
`security-policy.md` next to its README and `.gitignore`, so AI coding tools have
project-specific security rules instead of generic advice.

## Architecture

```text
JBHack/
├── apps/
│   ├── agent/                 # FastAPI companion service and autopilot
│   │   └── src/
│   │       ├── main.py             # HTTP routes, Sentry webhooks, SSE streams
│   │       ├── autopilot.py        # Sentry -> source -> Codex -> sandbox -> PR
│   │       ├── codex_analysis.py   # Codex analysis and sandbox test generation
│   │       ├── codex_client.py     # OpenAI client wrapper
│   │       ├── dep_check.py        # pip-audit dependency context
│   │       ├── github_client.py    # source fetch and PR/local artifact output
│   │       ├── sandbox_runner.py   # generated pytest sandbox execution
│   │       ├── storage.py          # SQLite incident store and SSE broker
│   │       └── validator.py        # structured response validation
│   │
│   ├── dashboard/             # Next.js live dashboard
│   ├── jetbrains-plugin/      # Kotlin JetBrains plugin
│   └── target/                # Intentionally vulnerable demo service
│
├── security-policy.md         # Repo-local security policy for Codex
├── docs/                      # Runbooks, design notes, demo scripts
└── LICENSE                    # MIT
```

## Important Agent Endpoints

- `GET /health`
- `GET /status`
- `GET /incidents`
- `GET /dashboard/events/stream`
- `POST /sentry/webhook`
- `GET /ide/events/stream`
- `POST /ide/navigate`
- `POST /ide/analyze`
- `POST /ide/events/{incident_id}/review`
- `POST /ide/events/{incident_id}/open-pr`
- `POST /debug/incidents` when debug endpoints are enabled

## Quick Start

```bash
git clone https://github.com/PeytonLi/JBHack.git
cd JBHack

pnpm install
pnpm run install:python
cp .env.example .env
```

For the full autopilot demo, configure `.env`:

```dotenv
OPENAI_API_KEY=...
GITHUB_TOKEN=...
GITHUB_REPO=owner/repo
SENTRY_AUTH_TOKEN=...
SENTRY_WEBHOOK_SECRET=...
SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1
```

Start the local services:

```bash
pnpm dev
```

Launch the JetBrains plugin sandbox:

```bash
cd apps/jetbrains-plugin
GRADLE_USER_HOME=$PWD/.gradle-home sh ./gradlew runIde
```

Open the dashboard at the printed Next.js URL, usually:

```text
http://localhost:3000
```

If another app is already on port 3000, Next.js will print another port such as
`3001`.

## Real Sentry Demo Setup

1. Start the agent on `localhost:8001`.
2. Expose it with ngrok or another tunnel.
3. Configure Sentry to send issue/error webhooks to:

```text
https://<your-ngrok-domain>/sentry/webhook
```

4. Confirm the dashboard shows:

```text
Agent Online
Autopilot Active
Codex Ready
```

5. Trigger the target incident and watch the dashboard pipeline progress through:

```text
Sentry -> Codex -> Sandbox -> PR -> JetBrains review
```

## Local Fallback Demo

If live Sentry or ngrok fails during judging, the repo still supports a local
fallback:

- `Run Demo` creates a Sentry-shaped local incident.
- `Scan Current File` analyzes the active editor file.
- `Analyze with Codex` runs the structured analysis path.
- `Approve Fix` applies the patch locally in the IDE.
- `Reject` discards the suggestion.
- PR creation falls back to local artifacts under `apps/agent/out/`.

This fallback is for demo reliability; the primary pitch is the Sentry-driven
autopilot loop.

## Verification

```bash
pnpm run typecheck
pnpm run build

cd apps/agent
SECURE_LOOP_HOME=$PWD/.test-secureloop uv run pytest -q

cd ../jetbrains-plugin
GRADLE_USER_HOME=$PWD/.gradle-home sh ./gradlew compileKotlin
```

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Enables Codex analysis and sandbox test generation |
| `OPENAI_MODEL` / `SECURE_LOOP_OPENAI_MODEL` | Optional model override |
| `GITHUB_TOKEN` | Fetches source and opens PRs |
| `GITHUB_REPO` | Target repo in `owner/repo` form |
| `SENTRY_AUTH_TOKEN` | Fetches full Sentry event details |
| `SENTRY_WEBHOOK_SECRET` | Verifies signed Sentry webhooks |
| `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS` | Enables local demo/debug incident endpoint |
| `SECURE_LOOP_IDE_TOKEN` | Optional fixed IDE bearer token |
| `SECURE_LOOP_IDE_AUTO_LAUNCH` | Enables agent-assisted JetBrains sandbox launch |
| `DASHBOARD_ORIGIN` | Optional CORS origin for dashboard |

Autopilot is considered active when `OPENAI_API_KEY`, `GITHUB_TOKEN`, and
`GITHUB_REPO` are configured.

## Roadmap

These are product directions, not claims about the current hackathon build:

- Alt+Enter secure-code generation while writing code
- automatic on-save whole-file vulnerability scanning
- dependency-fix PRs across broader ecosystems
- post-merge Sentry recurrence monitoring for the same CWE class
- richer policy tuning from rejected fixes
- organization-wide `security-policy.md` standardization

## Team

| Member | Primary ownership |
| --- | --- |
| Abhiram Sribhashyam | Agent integration, Codex analysis flow, dashboard polish, demo strategy |
| Rahul Marri | Codex prompt/validation work, policy framing, README/vision contributions |
| Peyton Li | JetBrains plugin, Sentry ingestion, SSE streaming, autopilot pipeline |

## License

SecureLoop is open source under the [MIT License](LICENSE).
