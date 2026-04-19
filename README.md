<div align="center">

# 🔐 SecureLoop

**The first AI security tool that closes the full loop. Write → Scan → Fix → Ship → Verify.**

*A JetBrains Hackathon Project — Built by Team SecureLoop*

[![Branch](https://img.shields.io/badge/branch-Rahul-blue)](https://github.com/PeytonLi/JBHack/tree/Rahul)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![Kotlin](https://img.shields.io/badge/Kotlin-JVM%2017-7F52FF?logo=kotlin&logoColor=white)](https://kotlinlang.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-Codex%205.3-412991?logo=openai&logoColor=white)](https://openai.com)

</div>

---

## The Problem

Every developer team uses at least three security tools today:

- **Snyk** — scans your `requirements.txt` for CVEs
- **SonarQube** — flags vulnerable code patterns
- **Sentry** — catches production runtime errors

But here's the brutal truth: **none of them talk to each other.** You get a Sentry alert at 2am, copy-paste the stack trace into a chat window, prompt an AI separately, write a fix manually, review it manually, and open a GitHub PR — none of which captures what went wrong or prevents it from happening again. The loop never closes.

**SecureLoop is the first tool to close that loop entirely — inside your IDE.**

---

## The Vision

<div align="center">

![SecureLoop Full Architecture](./secureloop_plugin_vision.svg)

*Five modules forming a closed security loop from code writing through production verification*

</div>

The diagram above shows the complete SecureLoop lifecycle. Every module is either fully implemented or directly staged for production deployment:

| Module | Name | What it does | Status |
|--------|------|-------------|--------|
| **1** | Secure Code Generation | `Alt+Enter` in JetBrains calls Codex 5.3 with your repo's own security policy to generate safe completions inline | ✅ Implemented |
| **2** | Vulnerable Code Scanner | On every file save, the plugin sends content to the agent which Codex-analyzes for severity, CWE category, and OWASP classification; highlights gutter with red/amber icons | ✅ Implemented |
| **3** | Dependency Checker | Audits `requirements.txt` against known CVEs; result injected back into Codex fix prompts for version-aware patches | ✅ Implemented |
| **4** | Remediation + Human Gate | AI generates a full diff; developer clicks **Approve** (patch applied + PR opened) or **Reject** (reason captured for policy tuning) | ✅ Implemented |
| **5** | Production Monitoring | Post-merge: watches Sentry for CWE recurrence over 48hrs; if same class of bug re-triggers, escalates severity and re-enters Module 2 | 🔜 Roadmap |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Developer's Machine                         │
│                                                                     │
│   ┌─────────────────────┐      SSE Stream      ┌─────────────────┐ │
│   │  JetBrains IDE      │◄─────────────────────│  SecureLoop     │ │
│   │  (Plugin)           │                      │  Agent          │ │
│   │                     │──POST /ide/analyze──►│  (FastAPI)      │ │
│   │  - IntentionAction  │◄── AnalyzeResponse ──│                 │ │
│   │  - SaveListener     │                      │  - SQLite store │ │
│   │  - ApproveButton    │──POST /ide/open-pr──►│  - SSE broker   │ │
│   │  - RejectButton     │                      │  - Codex client │ │
│   └─────────────────────┘                      └────────┬────────┘ │
│                                                         │           │
│   ┌─────────────────────┐              Sentry Webhook   │           │
│   │  Next.js Dashboard  │◄── /incidents ────────────── │           │
│   │  (port 3000)        │                      ┌────────┴────────┐ │
│   │                     │                      │  Target Service │ │
│   │  - Lifecycle flow   │                      │  (FastAPI)      │ │
│   │  - Incident queue   │                      │                 │ │
│   │  - Review history   │                      │  Intentionally  │ │
│   └─────────────────────┘                      │  Broken for Demo│ │
│                                                └─────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                            Sentry.io (Cloud)
                                    │
                             GitHub API (PRs)
```

---

## Repository Layout

```
JBHack/
├── apps/
│   ├── agent/                  # Python FastAPI companion service
│   │   └── src/
│   │       ├── main.py         # API routes + Sentry webhook verification
│   │       ├── codex_analysis.py  # Codex 5.3 integration (analyze + generate)
│   │       ├── codex_client.py    # OpenAI async HTTP client
│   │       ├── models.py          # Pydantic data models (CamelCase aliased)
│   │       ├── prompt_builder.py  # Security-policy-aware prompt templates
│   │       ├── validator.py       # AI response validation + diff generation
│   │       ├── storage.py         # SQLite incident store + SSE broker
│   │       ├── sentry_client.py   # Sentry Event API client
│   │       └── config.py          # Typed settings via Pydantic BaseSettings
│   │
│   ├── dashboard/              # Next.js 16 monitoring dashboard
│   │   └── app/
│   │       ├── page.tsx        # Lifecycle diagram + incident queue UI
│   │       └── globals.css     # Light theme + micro-animations
│   │
│   ├── jetbrains-plugin/       # Kotlin IntelliJ Platform plugin
│   │   └── src/main/kotlin/dev/secureloop/plugin/
│   │       ├── services/
│   │       │   ├── SecureLoopApplicationService.kt   # HTTP client (all agent calls)
│   │       │   ├── SecureLoopProjectService.kt       # Incident state + remediation
│   │       │   ├── SecureLoopSaveListener.kt         # Module 2: on-save file scan
│   │       │   └── SecureLoopIntentionAction.kt      # Module 1: Alt+Enter completions
│   │       ├── ui/
│   │       │   ├── SecureLoopToolWindowPanel.kt      # Main Approve/Reject UI
│   │       │   └── SecureLoopToolWindowFactory.kt
│   │       └── model/
│   │           ├── AnalysisModels.kt      # AnalyzeIncidentResponse + AnalysisState
│   │           └── IncidentPresentation.kt
│   │
│   └── target/                 # Demo target: intentionally vulnerable FastAPI app
│       └── src/main.py         # KeyError at line 45 — the demo crash site
│
├── security-policy.md          # Org-level policy injected into every Codex prompt
├── secureloop_plugin_vision.svg  # 5-module architecture diagram
└── .env.example                # All required environment variables
```

---

## Quick Start (Demo Mode)

The fastest way to see the full loop work end-to-end with zero external services:

### 1. Prerequisites

- [IntelliJ IDEA](https://www.jetbrains.com/idea/) or [PyCharm](https://www.jetbrains.com/pycharm/) (any recent version)
- Java 17+ (`JAVA_HOME` pointing to JDK 17+)
- Python 3.12+
- [pnpm](https://pnpm.io) (`npm install -g pnpm`)
- [uv](https://github.com/astral-sh/uv) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

### 2. Install Dependencies

```bash
git clone https://github.com/PeytonLi/JBHack.git
cd JBHack
git checkout Rahul

pnpm install
pnpm run install:python
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```dotenv
# Required for AI features (Modules 1–4)
OPENAI_API_KEY=sk-...

# Required for demo mode (no real Sentry needed)
SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1
```

### 4. Start All Services

```bash
pnpm dev
```

This concurrently launches:
- `http://127.0.0.1:8000` — Target service (broken FastAPI app)
- `http://127.0.0.1:8001` — SecureLoop agent (FastAPI + Codex)
- `http://127.0.0.1:3000` — Dashboard (Next.js)

### 5. Launch the IDE Plugin

```bash
cd apps/jetbrains-plugin
./gradlew runIde
```

> **Note:** Gradle requires Java 17+. Set `JAVA_HOME` or pass `-Dorg.gradle.java.home=/path/to/jdk17` if needed.

### 6. Run the Demo Loop

1. In the sandbox IDE, open the `JBHack` project root
2. Open the **SecureLoop** tool window (right panel)
3. Click **Run Demo** — a `KeyError: 999` incident from `apps/target/src/main.py:45` appears
4. Click **Analyze with Codex** — Codex 5.3 generates severity, CWE, fix plan, and a diff
5. Click **Approve Fix** — the patch is applied live in the editor via `WriteCommandAction`, and a PR link is generated
6. The **Dashboard** at `http://localhost:3000` shows the incident moving from *Action Required* → *Resolution History*

---

## Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for Codex 5.3 analysis and generation | For AI features |
| `SENTRY_DSN` | Sentry project DSN for the target service | For real Sentry flow |
| `SENTRY_AUTH_TOKEN` | Sentry auth token to fetch full event payloads | For real Sentry flow |
| `SENTRY_WEBHOOK_SECRET` | HMAC secret to verify incoming Sentry webhooks | For real Sentry flow |
| `GITHUB_TOKEN` | GitHub PAT for PR creation | For PR flow |
| `GITHUB_REPO` | `owner/repo` format target for PRs | For PR flow |
| `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS` | Set to `1` to enable `/debug/incidents` and demo mode | Development only |
| `AGENT_PORT` | Agent port (default: `8001`) | Optional |
| `TARGET_PORT` | Target service port (default: `8000`) | Optional |
| `SECURE_LOOP_AGENT_URL` | Dashboard's agent URL (default: `http://127.0.0.1:8001`) | Optional |

---

## Agent API Reference

The FastAPI companion service exposes the following endpoints. All `/ide/*` endpoints require `Authorization: Bearer <ide-token>`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Agent status, SQLite path, incident counts |
| `GET` | `/incidents` | Paginated incident feed (status: `all`/`open`/`reviewed`) |
| `POST` | `/sentry/webhook` | HMAC-verified Sentry issue alert ingestion |
| `GET` | `/ide/events/stream` | SSE stream of normalized incidents to the plugin |
| `POST` | `/ide/analyze` | Codex 5.3 vulnerability analysis for a given source context |
| `POST` | `/ide/analyze-file` | Module 2: full file scan triggered on save |
| `POST` | `/ide/generate` | Module 1: policy-aware secure code generation |
| `POST` | `/ide/scan-deps` | Module 3: dependency CVE audit for `requirements.txt` |
| `POST` | `/ide/open-pr` | Module 4: trigger GitHub PR creation post-approval |
| `POST` | `/ide/reject-fix` | Module 4: capture rejection reason for policy tuning |
| `POST` | `/ide/events/{id}/review` | Mark incident as reviewed |
| `POST` | `/debug/incidents` | Inject a synthetic demo incident (debug mode only) |

---

## How the Modules Work

### Module 1 — Secure Code Generation

Triggered by `Alt+Enter` on any code selection in the editor. SecureLoop fires `SecureLoopIntentionAction`, sends the selected context + the project's `security-policy.md` to Codex 5.3 at `/ide/generate`, and inserts the secure completion back inline. The model is instructed to output only code — no markdown, no explanations.

### Module 2 — On-Save Vulnerability Scanner

`SecureLoopSaveListener` implements `FileDocumentManagerListener`. On every document save, if the file belongs to the open project, it ships the entire file contents to `/ide/analyze-file`. The agent runs Codex 5.3 with a structured JSON prompt that classifies the vulnerability by severity (`Critical`/`High`/`Medium`/`Low`), CWE ID, and OWASP category. For `High` or `Critical` findings, the plugin highlights the affected line in the editor gutter with a wave underline.

### Module 3 — Dependency Checker

When the user hits **Scan Dependencies** in the tool window, the plugin posts `requirements.txt` content to `/ide/scan-deps`. The agent parses it for known vulnerable packages, surfacing CVEs and fix versions. Critically, those findings are also passed back into the Codex fix prompt — so when the AI generates a patch, it knows which version to upgrade to.

### Module 4 — Remediation + Human Gate

After Codex analysis, the tool window presents:
- **Severity, CWE, OWASP category**
- **Step-by-step fix plan**
- **A unified diff** showing exactly what will change

The developer clicks:
- **Approve Fix** → `WriteCommandAction` atomically applies the patch into the live editor document, saves it, then calls `/ide/open-pr` which creates a GitHub PR with the full diagnosis attached
- **Reject** → A dialog captures the reason; this is posted to `/ide/reject-fix` and logged for future policy tuning

---

## Running Tests

```bash
# Python agent tests
cd apps/agent
uv run pytest

# TypeScript type check
cd apps/dashboard
pnpm typecheck
```

The agent test suite covers:
- `test_analysis.py` — `/ide/analyze` auth, AI response validation
- `test_codex_analysis.py` — fallback patch generation behavior
- `test_ingress.py` — Sentry webhook ingestion, incident storage, SSE streaming

---

## Real Sentry Webhook Flow

Once demo mode works, switch to live signed Sentry alerts:

1. Configure your Sentry project: **Settings → Alerts → Create Alert Rule → Issue Alert → Send Webhook to URL**
2. Set the webhook URL to `https://<your-tunnel>/sentry/webhook` (use [ngrok](https://ngrok.com) or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) to expose your local agent)
3. Set the `.env` values: `SENTRY_DSN`, `SENTRY_AUTH_TOKEN`, `SENTRY_WEBHOOK_SECRET`
4. Trigger a real error in the target service: `curl http://localhost:8000/checkout?warehouse_id=999`
5. Watch the incident appear live in the SecureLoop tool window via SSE

---

## Security Design Notes

The agent uses **HMAC-SHA256** to verify every Sentry webhook — no request without a valid signature is processed. IDE requests require a shared bearer token stored in a local file, never in environment variables. The `.env` file is `.gitignore`-d and must never contain hard-coded secrets in public commits.

---

## What SecureLoop Does That No Other Tool Does

> *Snyk scans deps. SonarQube flags code. Sentry catches errors. None of them talk to each other.*

SecureLoop is the **first tool in the consequence layer**. Every other DevSecOps tool operates in isolation: it finds something, shows you a dashboard, and stops. SecureLoop is the connective tissue:

1. It receives the **production crash** from Sentry
2. Maps it to the **exact line** in your local source
3. Classifies it against your **org-specific security policy**
4. Generates the **exact patch** with Codex 5.3
5. Puts a **human in the loop** before anything ships
6. Opens the **GitHub PR** with full explainability attached
7. Watches Sentry **post-merge** to verify the fix held

That is: **write → scan → fix → ship → verify**. Fully closed.

---

## Future Vision & Roadmap

### Module 5 — Production Verification (Next Priority)

After a PR merges, SecureLoop registers a post-merge watcher for the same CWE category. If Sentry re-fires the same class of exception within 48 hours:
- The fix is flagged as **incomplete**
- Severity is auto-escalated (e.g., Medium → High)
- The loop re-enters at Module 2 with the exact production stack trace

### IDE Depth Improvements

- **Gutter icons with inline diff previews** — hover over the red gutter marker to see the Codex-generated patch without opening the tool window
- **Commit hook integration** — block git push if unresolved `Critical` findings exist in staged files
- **Multi-file incident correlation** — if a vulnerability spans two files (e.g., SQL in service layer + exposed endpoint), present a unified multi-file diff
- **Test generation** — after approving a fix, automatically generate a pytest/JUnit regression test targeting the exact vulnerable code path

### AI & Policy Improvements

- **Rejection learning loop** — today, rejections are logged. The next step is to aggregate them by violation pattern and automatically tighten `security-policy.md` entries when a category of suggestion is rejected ≥3 times
- **Multi-model comparison** — run the same incident through two Codex prompts and present a side-by-side diff, letting the developer pick the better fix strategy
- **Custom CWE policy overrides** — allow per-project configuration that elevates certain CWEs (e.g., CWE-89 SQL injection is always `Critical` regardless of Codex's base classification)

### Team & Enterprise Features

- **Team incident dashboard** — multi-developer view with assignment, SLA timers, and escalation paths
- **Supabase-backed cloud storage** — replace the local SQLite store with Supabase Postgres so the entire team shares the same incident queue and reviewed history
- **Slack/Teams notifications** — push `Critical` incidents to a security channel when they arrive, including the file path and AI-generated severity rationale
- **SOC 2 audit trail** — every approve/reject action is logged with developer identity, timestamp, and the specific policy clause that was triggered or violated

### Platform Expansion

- **VS Code extension** — port the plugin to the VS Code Extension API using TypeScript to reach the broader developer ecosystem
- **CI/CD integration** — a GitHub Action that runs the same Codex analysis pipeline on every PR diff, blocking merge if new `Critical` or `High` findings appear
- **Language-agnostic scanning** — today the agent is tuned for Python. Expand prompt templates to support TypeScript, Java, and Go with language-specific CWE mappings

### Organizational Intelligence

The most valuable long-term capability is **organizational security memory**. Over time, SecureLoop can build a knowledge graph of:
- Which CWE categories are most common in your codebase
- Which developers approve vs. reject which types of AI suggestions
- Which fixes hold in production vs. require follow-up patches
- Seasonal patterns (e.g., auth vulnerabilities spike after new API integrations)

This data powers genuinely adaptive AI — Codex prompts that improve automatically based on your team's specific codebase, coding patterns, and risk tolerance. SecureLoop becomes less of a tool and more of an institutional security advisor embedded in the development flow.

---

## Team

Built at **JetBrains Hackathon 2026** by:

- **Rahul Marri** — Agent backend, Codex integration, module architecture, codebase merge
- **Peyton Li** — JetBrains plugin core, Sentry ingestion, SSE streaming  
- Team SecureLoop

---

## Documentation

| File | Purpose |
|------|---------|
| `STORYBOARD.md` | 3-minute demo storyline and presentation flow |
| `CLAUDE.md` | Project context and developer conventions |
| `security-policy.md` | Org-level security policy injected into Codex prompts |
| `secureloop_plugin_vision.svg` | Full 5-module architecture vision diagram |
| `docs/PLUGIN_TESTING.md` | Smoke tests and verification steps |
| `docs/AGENT_CONTEXT.md` | Internal agent implementation notes |
| `docs/DESIGN_DOC.md` | Design rationale and architectural tradeoffs |
| `apps/jetbrains-plugin/README.md` | Plugin-specific setup and Gradle configuration |

---

<div align="center">

*"First tool to close the full loop: write → scan → fix → ship → verify"*

**SecureLoop — AI in the consequence layer, not the sandbox**

</div>
