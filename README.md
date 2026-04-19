<div align="center">
**SecureLoop**

<div align="center">

**AI security remediation that closes the loop from production alert to verified PR.**

`detect -> diagnose -> patch -> sandbox -> review -> ship`

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![Kotlin](https://img.shields.io/badge/Kotlin-JVM-7F52FF?logo=kotlin&logoColor=white)](https://kotlinlang.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![OpenAI](https://img.shields.io/badge/OpenAI-Codex-111111?logo=openai&logoColor=white)](https://openai.com)

Built at the JetBrains Codex Hackathon 2026 in San Francisco.

</div>

## The Problem

Security tools still hand developers disconnected fragments.

- Sentry shows the production failure, but not the fix.
- Dependency scanners show vulnerable packages, but not the application-level patch.
- AI chat can suggest code, but usually lacks the stack trace, repo policy,
  dependency context, verification result, and IDE approval surface.

That leaves developers doing security incident response by copy-paste: move the
stack trace into chat, explain the repo manually, write a fix manually, hope the
fix is safe, then open a PR manually.

SecureLoop turns that fragmented workflow into one controlled remediation loop.

## The Pitch

SecureLoop is a JetBrains-native AI security agent that converts a real
production-shaped alert into an OWASP/CWE-framed diagnosis, policy-aware patch,
sandbox proof, and developer-approved PR.

The key idea is simple: detection is not enough. Security tooling should carry a
finding all the way to a reviewable, verified fix, while keeping a human in the
loop before anything ships.

## What We Built

SecureLoop has four cooperating pieces:

- **FastAPI agent**: receives Sentry webhooks, normalizes incidents, runs Codex
  analysis, performs dependency checks, executes the autopilot pipeline, and
  streams state to the UI.
- **JetBrains plugin**: opens the affected file, highlights the line, renders
  severity, CWE, OWASP-style category, policy evidence, patch diff, and gives
  the developer the final approval gate.
- **Next.js dashboard**: shows live incidents, autopilot progress, reviewed
  history, PR state, and a stage-ready light/dark demo mode.
- **Demo target app**: intentionally broken FastAPI service used to produce
  reproducible incident traffic.

## The Five Modules

SecureLoop is strongest when it is shown as a security loop, not just a
dashboard or plugin. The current hackathon build implements the center of that
loop and leaves the broader proactive surface as roadmap.

### Module 1 - Production signal ingestion

Sentry sends a signed webhook. SecureLoop normalizes the event into an incident
with repo path, line number, exception type, environment, and source context.
This is real-world impact, not a hypothetical scan result.

**Status:** implemented.

### Module 2 - Vulnerability diagnosis

Codex receives the stack trace, nearby source, dependency scan output, and
`security-policy.md`. It returns a structured diagnosis with severity, CWE,
OWASP-style category, root cause, impact, violated policy rules, and fix plan.

**Status:** implemented for incident and selected-file analysis.

### Module 3 - Dependency checker

The agent runs `pip-audit` and feeds the result into the Codex prompt, so the
diagnosis can distinguish application-code failures from dependency risk.

**Status:** implemented for Python dependency context.

### Module 4 - Remediation + human approval gate

Codex produces a minimal patch and PR narrative. SecureLoop validates the patch,
runs a generated pytest sandbox for Python incidents, then presents the evidence
inside JetBrains for approval or rejection.

**Status:** implemented.

### Module 5 - Production verification

The long-term loop is to watch Sentry after merge for recurrence of the same
CWE/error class, then reopen the loop if the fix did not hold.

**Status:** roadmap, intentionally separated from the hackathon build.

## The Closed Loop

```text
Production error
  -> Sentry sends a signed webhook
  -> SecureLoop normalizes the issue into a repo-relative incident
  -> dashboard updates live over SSE
  -> agent fetches the affected source file from GitHub
  -> agent reads security-policy.md and dependency context
  -> Codex returns severity, CWE, OWASP-style category, and a minimal patch
  -> validator checks the response shape and patch preconditions
  -> sandbox runner generates and executes a pytest reproduction/fix test
  -> agent opens a GitHub PR, or writes local PR artifacts as fallback
  -> JetBrains opens the exact file and line for human review
```

This is not a passive scanner and not a prompt wrapper. It is a consequence-layer
security workflow: the system starts from something that affected users, ties it
back to source code, proposes the smallest safe fix, verifies it, and puts the
developer back in control inside the IDE.

## How It Works End-to-End

SecureLoop has two demo entry points. Both converge on the same security
diagnosis and remediation path.

### Entry Point A - Production alert autopilot

```text
Runtime error hits the target service
        -> Sentry captures the event
        -> Sentry fires a signed webhook to /sentry/webhook
        -> agent normalizes the alert and stores it in SQLite
        -> dashboard and JetBrains receive the update over SSE
        -> autopilot fetches the affected source file from GitHub
```

### Entry Point B - Pre-commit local scan

```text
Developer opens a file in JetBrains
        -> Scan Current File creates a local SecureLoop incident
        -> plugin sends selected-file context to /ide/analyze
        -> Codex returns severity, CWE, OWASP-style category, policy evidence,
           fix plan, and patch
```

The current proactive path is explicit because it is safer for a live demo. The
roadmap is automatic on-save scanning and Alt+Enter secure-code generation.

### Shared diagnosis and fix loop

```text
incident or scan context
        -> source window + security-policy.md + dependency context
        -> Codex structured diagnosis
        -> validator enforces response shape and patch constraints
        -> sandbox test proves the patch for Python incidents
        -> PR or local PR artifact is produced
        -> JetBrains remains the human approval gate
```

## The Security Model

SecureLoop is built around three constraints.

### 1. Policy beats generic AI advice

Every analysis request includes `security-policy.md`. In this repo, the policy
defines rules for:

- SQL and database access
- error handling
- secrets
- minimal, convention-matching fixes
- PR security rationale

Codex is not asked "what is a good fix in general?" It is asked "what is an
acceptable fix under this codebase's security policy?"

### 2. The patch must be reviewable

SecureLoop returns structured fields, not just prose:

- severity
- OWASP-style category
- CWE
- root cause
- attack scenario
- impact
- violated policy rules
- fix plan
- unified diff
- patch object
- PR title/body narrative

That structure is what lets the dashboard, PR body, and JetBrains plugin all
show the same evidence without another round of interpretation.

### 3. Humans approve the consequence

The agent can analyze, patch, test, and prepare a PR. The developer still owns
the merge decision. In the plugin, the human can inspect the affected line, read
the reasoning, view the diff, approve the fix, reject it, or open the PR.

Security decisions carry accountability. SecureLoop is designed to surface the
evidence, not hide it behind an autonomous black box.

## Cybersecurity Constitution

The long-term product idea is `security-policy.md` as a standard file in every
serious repository.

Repos already carry files that help tools understand the project:

- `README.md` explains the project to humans.
- `.gitignore` explains repository hygiene to Git.
- `package.json` or `pyproject.toml` explains dependencies to tooling.

There is no equivalent standard file that tells AI coding agents how to classify
and remediate security risk for this specific codebase. SecureLoop treats
`security-policy.md` as that missing contract: a version-controlled security
constitution that coding agents must follow when mapping incidents to CWE,
OWASP-style categories, policy violations, and patches.

That is the sponsor-aligned thesis: Codex becomes much more valuable inside the
IDE when it is grounded in the repo's own rules, files, failures, and approval
flow.

## What Makes SecureLoop Different

| Tool | What it gives you | Where it stops |
| --- | --- | --- |
| Sentry | Production error and stack trace | Investigation begins |
| Snyk / pip-audit | Dependency vulnerability signal | Developer must map it to code |
| SonarQube / static analysis | Pattern or rule violation | Fix and verification are separate |
| AI chat | Suggested code | Context, policy, tests, and PR are manual |
| SecureLoop | Incident, policy-aware diagnosis, patch, sandbox proof, PR, IDE review | Human decides whether to ship |

The differentiator is not that SecureLoop uses AI. The differentiator is that
the AI is placed inside an evidence-producing security workflow.

## Implemented In This Hackathon Build

- signed Sentry webhook ingestion
- Sentry issue/error normalization into repo-relative incidents
- SQLite incident store
- live SSE streams for dashboard and IDE
- dashboard open/reviewed queues
- dashboard autopilot progress view
- dashboard light/dark stage mode
- JetBrains tool window for incident review
- IDE file opening and line highlighting
- Codex analysis with structured severity, CWE, OWASP-style category, and patch
  output
- validation and retry path for malformed Codex responses
- `security-policy.md` prompt context
- `pip-audit` dependency scan context
- GitHub source fetch for affected files
- generated pytest sandbox step for Python incidents
- GitHub PR creation with generated title/body
- local PR artifact fallback when GitHub PR creation fails
- manual fallback paths: `Run Demo`, `Scan Current File`, `Analyze with Codex`,
  `Approve Fix`, `Reject`, `Show Diff`, `Open PR`, and `Mark Reviewed`

## Demo Narrative

Judges should watch for five proof points:

1. **Real signal enters the system**: a Sentry-shaped alert lands in SecureLoop.
2. **The agent does more than summarize**: it fetches source, reads policy,
   checks dependencies, and asks Codex for structured remediation.
3. **The output is security-specific**: severity, CWE, OWASP-style category,
   root cause, impact, policy violation, fix plan, and prevention are shown.
4. **The fix is tested before handoff**: the sandbox step proves the generated
   patch behavior before PR handoff.
5. **JetBrains is the approval gate**: the developer reviews the exact file,
   line, diff, and PR context inside the IDE.

## Architecture

```text
JBHack/
├── apps/
│   ├── agent/
│   │   └── src/
│   │       ├── main.py             # FastAPI routes, webhooks, SSE, IDE endpoints
│   │       ├── autopilot.py        # Sentry -> source -> Codex -> sandbox -> PR
│   │       ├── codex_analysis.py   # Codex analysis + sandbox test generation
│   │       ├── codex_client.py     # OpenAI client wrapper
│   │       ├── prompt_builder.py   # Policy-aware prompt construction
│   │       ├── validator.py        # Structured response validation
│   │       ├── dep_check.py        # pip-audit dependency context
│   │       ├── github_client.py    # source fetch, PR creation, local fallback
│   │       ├── sandbox_runner.py   # generated pytest sandbox execution
│   │       └── storage.py          # SQLite store and live event broker
│   │
│   ├── dashboard/                  # Next.js incident and autopilot UI
│   ├── jetbrains-plugin/           # Kotlin JetBrains plugin
│   └── target/                     # intentionally vulnerable FastAPI app
│
├── security-policy.md              # repo-local security rules for Codex
├── docs/                           # runbooks and demo notes
└── LICENSE                         # MIT
```

## Important Agent Endpoints

- `GET /health`
- `GET /status`
- `GET /incidents`
- `GET /incidents/{incident_id}/pipeline-state`
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

If another app is already using port 3000, Next.js will print another port such
as `3001`.

## Real Sentry Demo Setup

1. Start the agent on `localhost:8001`.
2. Expose it with ngrok or another tunnel.
3. Configure Sentry to send issue/error webhooks to:

```text
https://<your-ngrok-domain>/sentry/webhook
```

4. Confirm the dashboard shows the agent online and autopilot ready.
5. Trigger the target incident.
6. Watch the pipeline move through:

```text
Sentry -> Codex -> Sandbox -> PR -> JetBrains
```

## Local Fallback Demo

If Sentry, ngrok, GitHub, or the OpenAI API misbehaves during judging, the repo
still has local fallback paths:

- `Run Demo` creates a Sentry-shaped local incident.
- `Scan Current File` creates a proactive local scan from the active editor.
- `Analyze with Codex` calls the structured analysis path.
- `Approve Fix` applies the patch locally in the IDE.
- `Reject` discards the generated fix.
- PR creation falls back to local artifacts under `apps/agent/out/`.

The primary pitch is the Sentry-driven autopilot loop. The fallback exists so the
demo still has a working path under hackathon network conditions.

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

Autopilot is active when `OPENAI_API_KEY`, `GITHUB_TOKEN`, and `GITHUB_REPO` are
configured.

## Future Vision

SecureLoop started with a production-alert remediation loop, but the larger
security platform is:

```text
write secure code -> scan before commit -> fix with policy -> ship with proof
-> watch production -> feed recurrence back into the policy
```

The long-term product is a JetBrains security control plane for AI-assisted
development:

- **While writing code**: Codex suggestions are constrained by
  `security-policy.md`, so secure patterns show up before the vulnerable pattern
  is committed.
- **Before commit**: current-file and whole-repo checks classify risky code using
  severity, CWE, OWASP-style category, and local policy violations.
- **Before merge**: SecureLoop creates minimal PRs with fix rationale,
  dependency context, generated tests, and human-readable security evidence.
- **After deploy**: Sentry recurrence becomes a feedback signal. If the same
  CWE/error class reappears, SecureLoop marks the fix as incomplete and reopens
  the loop.
- **Across the organization**: `security-policy.md` becomes the shared security
  contract consumed by Codex, JetBrains, CI, and code review.

This is the bigger bet: AI coding agents should not just generate code. They
should operate against a version-controlled security constitution, produce
evidence, and leave developers with final authority over the change.

## Roadmap

These are product directions, not claims about the current hackathon build:

- Alt+Enter secure-code generation while writing code
- automatic on-save whole-file vulnerability scanning
- richer static-analysis integration for proactive findings
- dependency-fix PRs across broader ecosystems
- post-merge Sentry recurrence monitoring for the same CWE class
- rejected-fix feedback loop for policy tuning
- organization-wide `security-policy.md` standardization

## Team

| Member | Primary ownership |
| --- | --- |
| Abhiram Sribhashyam | Agent integration, Codex analysis flow, dashboard polish, demo strategy |
| Rahul Marri | Codex prompt/validation work, policy framing, README/vision contributions |
| Peyton Li | JetBrains plugin, Sentry ingestion, SSE streaming, autopilot pipeline |

## License

SecureLoop is open source under the [MIT License](LICENSE).
