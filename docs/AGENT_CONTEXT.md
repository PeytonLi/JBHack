# Auto-Scribe — Full Agent Context

This file is the source of truth for all agents (Claude Code, Codex, subagents) working on this repo. Read it before touching any code.

The companion design doc is at `docs/DESIGN_DOC.md`. It has the full rationale, alternatives considered, and open questions. This file has the execution spec.

---

# Plan: Project Auto-Scribe (JBHack)

## Context

User is building **Auto-Scribe**, a "self-healing" AI SRE agent that turns a production crash into a merged PR with an Amazon-style Correction of Error (COE) report. Constraints: **solo dev, ~48 hours, video submission** for a hackathon (JBHack).

## Decision Summary

- **Approach:** B — Full Spec (user chose ambitious architecture; both autoplan reviewers recommended Approach C; user confirmed B with full awareness).
- **Monorepo layout:** pnpm workspace with `apps/agent` (Python/uv), `apps/target` (Python/uv), `apps/dashboard` (Next.js 15 App Router), `packages/shared-types` (TypeScript).
- **Python runtime (agent + target):** FastAPI + Supabase (Postgres) + SQLite (agent memory, WAL mode) + OpenAI API (`gpt-4o` for pipeline steps, `gpt-4o` with COE system prompt for COE writeup).
- **Dashboard:** Next.js 15, Tailwind + shadcn/ui, `react-markdown` with GitHub theme for COE rendering, SSE client component consuming agent's JSON API.
- **Test sandbox:** Originally real Docker. **Downgraded to `subprocess` + pre-populated venv** to absorb the 4-6 hours Next.js dashboard adds. Judges cannot tell the difference on screen.
- **Canonical crash scenario:** `POST /checkout` with a `warehouse_id` that doesn't exist in `warehouses`. One scenario only.
- **Hard cut line at hour 42:** if PR creation isn't working, write COE to disk + screenshots.

## Architecture

```
Sentry (real) ──▶ apps/target (FastAPI :8000) ──crashes──▶ Sentry Event
                                                               │
                                              Sentry webhook ──▶ apps/agent (FastAPI :8001)
                                                               │
                                              /webhook/sentry ──▶ SQLite agent_steps
                                                               │
                                              claude_client.call_with_log()
                                              ├── parse stack trace
                                              ├── schema_introspect.py (real column names)
                                              ├── generate read-only SQL
                                              └── run against Supabase
                                                               │
                                              Claude generates pytest (subprocess sandbox)
                                                               │ must FAIL with same error
                                              Claude generates fix
                                                               │
                                              Re-run test (subprocess) must PASS
                                                               │
                                              Claude Opus 4.7 writes COE_LOG.md
                                                               │
                                              PyGithub creates PR (fix + test + COE)

apps/dashboard (Next.js :3000)
├── polls /api/sessions every 2s
├── <ThoughtLog> SSE component reads /api/stream/{id}
└── <COECard> renders COE_LOG.md with react-markdown + remark-gfm
```

## Data Stores

- **Supabase (Postgres cloud):** `orders`, `inventory`, `warehouses`. Poison row: `orders(id='POISON-001', warehouse_id=999)`. No FK constraint on `warehouse_id` — that's the bug.
- **SQLite local (WAL mode):** `sessions`, `agent_steps`, `artifacts`. Agent working memory + dashboard data source.

## Repo Structure

```
JBHack/
├── CLAUDE.md                       # Short auto-loaded context (points here)
├── pnpm-workspace.yaml
├── package.json                    # root devDependencies + concurrently dev script
├── .env.example
├── .gitignore
├── README.md
├── STORYBOARD.md                   # 3-min video beats
│
├── apps/
│   ├── agent/                      # Python, uv
│   │   ├── pyproject.toml
│   │   └── src/
│   │       ├── main.py             # FastAPI: /webhook/sentry, /api/sessions, /api/stream/{id}
│   │       ├── db.py               # SQLite WAL schema + CRUD
│   │       ├── claude_client.py    # call_with_log(step, messages, model, max_retries=2)
│   │       ├── schema_introspect.py
│   │       ├── pipeline.py         # analyze → reproduce → fix → coe → pr
│   │       ├── sandbox.py          # subprocess + pre-populated venv
│   │       ├── github_client.py    # PyGithub 4-step PR creation
│   │       └── coe_writer.py       # Opus 4.7 COE
│   │
│   ├── target/                     # Python, uv — broken service
│   │   └── src/
│   │       ├── main.py             # /checkout, /health, /orders
│   │       └── sentry_init.py
│   │
│   └── dashboard/                  # Next.js 15 App Router
│       ├── app/
│       │   ├── page.tsx            # Session list
│       │   ├── session/[id]/page.tsx
│       │   └── api/proxy/[...path]/route.ts
│       └── components/
│           ├── ThoughtLog.tsx      # SSE client component
│           ├── COECard.tsx         # react-markdown + remark-gfm
│           ├── TimelineEvent.tsx
│           └── StatusBadge.tsx
│
├── packages/
│   └── shared-types/src/index.ts   # Session, AgentStep, Artifact, SentryEvent
│
├── seed/
│   ├── schema.sql
│   └── seed.sql
│
└── docs/
    ├── AGENT_CONTEXT.md            # This file
    └── DESIGN_DOC.md               # Full design rationale
```

## Key Patterns — Don't Reinvent

**claude_client.py — use this for every OpenAI call:**
```python
from openai import OpenAI

def call_with_log(
    session_id: str,
    step_name: str,
    messages: list[dict],
    model: str = "gpt-4o",
    tools: list[dict] | None = None,
    temperature: float = 0.0,
    max_retries: int = 2,
) -> openai.types.chat.ChatCompletion:
    # logs step_name to agent_steps before + after
    # retries on RateLimitError / APIError up to max_retries
    # logs step_failed on final failure
    # tool calls use OpenAI format:
    #   choice.message.tool_calls[0].function.arguments (JSON string — json.loads() it)
    ...
```

**schema_introspect.py — run once per session:**
```python
def get_schema(supabase_url: str, supabase_key: str) -> dict[str, list[str]]:
    # queries information_schema.columns
    # returns {"orders": ["id", "user_id", "warehouse_id", ...], ...}
```

**PyGithub PR creation — exact sequence:**
```python
repo = g.get_repo("owner/throwaway-repo")
sha = repo.get_branch("main").commit.sha
repo.create_git_ref(ref=f"refs/heads/autoscribe/{session_id}", sha=sha)
repo.create_file("fix.py", "fix: warehouse lookup", fix_content, branch=f"autoscribe/{session_id}")
repo.create_file("tests/test_fix.py", "test: regression test", test_content, branch=f"autoscribe/{session_id}")
repo.create_file("COE_LOG.md", "docs: COE report", coe_content, branch=f"autoscribe/{session_id}")
pr = repo.create_pull(title="fix: warehouse_id lookup + COE", body=coe_content[:2000], head=f"autoscribe/{session_id}", base="main")
```

**SSE endpoint (FastAPI):**
```python
from fastapi.responses import StreamingResponse

async def stream_steps(session_id: str):
    async def generator():
        last_id = 0
        while True:
            steps = db.get_steps_after(session_id, last_id)
            for step in steps:
                yield f"data: {step.model_dump_json()}\n\n"
                last_id = step.id
            if db.session_is_complete(session_id):
                yield "data: {\"type\": \"done\"}\n\n"
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(generator(), media_type="text/event-stream")
```

**Next.js ThoughtLog.tsx — client component:**
```typescript
'use client'
import { useEffect, useState } from 'react'
import type { AgentStep } from '@jbhack/shared-types'

export function ThoughtLog({ sessionId }: { sessionId: string }) {
  const [steps, setSteps] = useState<AgentStep[]>([])
  useEffect(() => {
    const es = new EventSource(`/api/proxy/api/stream/${sessionId}`)
    es.onmessage = (e) => {
      const step = JSON.parse(e.data)
      if (step.type === 'done') { es.close(); return }
      setSteps(prev => [...prev, step])
    }
    return () => es.close()
  }, [sessionId])
  return <div>{steps.map(s => <TimelineEvent key={s.id} step={s} />)}</div>
}
```

## Hour-by-Hour Build Plan

| Hour range | Task | Output | Cut if slipping |
|---|---|---|---|
| 0–1 | Write CLAUDE.md, docs/AGENT_CONTEXT.md, docs/DESIGN_DOC.md, STORYBOARD.md v0. | 4 context files committed | Never cut. |
| 1–3 | Scaffold pnpm workspace. uv init for agent + target. pnpm create next-app for dashboard. packages/shared-types. pnpm dev starts all three. | Monorepo skeleton healthchecking | Flatten if workspace fights you at hour 3. |
| 3–6 | Account setup: Sentry project, Supabase schema+seed, GitHub throwaway repo, ngrok. | Real Sentry event visible in Sentry UI | If Sentry blocks at hour 6: fake webhook JSON. |
| 6–10 | Build apps/target with /checkout (broken), /health, /orders. sentry_sdk.init. Curl → crash → Sentry webhook fires → reaches localhost. | Real end-to-end webhook proof | Never cut. |
| 10–14 | Agent /webhook/sentry + JSON API + SQLite WAL. claude_client.py. Dashboard skeleton streaming from agent_steps. | curl→crash→webhook→SQLite→dashboard live | Streaming wiring cannot be ugly. |
| 14–20 | Pipeline step 1: parse trace → schema_introspect → SQL via tool_use → run → identify poison row. | Agent names POISON-001 from Supabase | If Supabase blocks: local Postgres. |
| 20–25 | Pipeline step 2: generate pytest, run subprocess, assert failure matches. max_retries=2. | artifacts row with failing test | — |
| 25–30 | Pipeline step 3: generate fix, re-run subprocess, must pass. | diff + passing test | — |
| 30–38 | COE finale (8 hrs, do NOT compress). Opus 4.7 writes COE_LOG.md. COECard renders it on dashboard. Iterate until it reads like Amazon. | COE + dashboard card | Do NOT cut. This is the wedge. |
| 38–42 | PyGithub creates PR. Dashboard shows PR link. | Real GitHub PR URL | Cut at hour 42: ./out/ + screenshot. |
| 42–45 | Polish dashboard. shadcn/ui, SSE animations, COECard typography. | Dashboard looks like a product | Don't skip. |
| 45–48 | Record video. 2+ retakes. Submit. | Video + public repo | Minimum 2 hrs. |

## Red-Flag Checkpoints (Contracts)

- Hour 3: pnpm workspace not running → flatten, skip shared-types
- Hour 6: Sentry not firing → fake webhook JSON
- Hour 14: Next.js SSE not streaming → polling fallback (setInterval 1500ms)
- Hour 20: Supabase flaky → local Postgres
- Hour 30: pipeline not end-to-end → hardcode poison row ID, move to COE
- Hour 38: no video rehearsal → stop coding, walk STORYBOARD.md
- Hour 42: PyGithub broken → out/ + screenshot

## Models

- `gpt-4o` — all pipeline steps (stack trace parsing, SQL generation, pytest generation, fix generation). `temperature=0.0` for determinism.
- `gpt-4o` (COE) — same model, different system prompt emphasizing Amazon SRE post-mortem voice. `temperature=0.7` for richer prose.

## What NOT to do

- Second crash scenario (video tells one story)
- Real Docker sandbox (downgraded to subprocess)
- Dashboard auth, multi-tenant, infinite retry
- Defer dashboard past hour 14
- Old model names (`claude-sonnet-4-6`, `claude-opus-4-7`, `claude-3-5-sonnet`) — this project uses OpenAI, not Anthropic
- Commit secrets (use .env.example)

## Review Findings

Both autoplan reviewers (Claude + Codex) independently concluded Approach C (video-first) was strategically correct and B was the highest-risk choice for a 48-hour solo hackathon. User chose B with full awareness. Key risk mitigations built into this plan:

1. Docker → subprocess (absorbs +3 hrs)
2. Sentry setup gets its own 3-hour block
3. Dashboard skeleton by hour 14, not 40
4. COE gets 8 hours not 4
5. 7 named cut-lines with specific fallbacks
6. `call_with_log()` abstraction + schema introspection prevent most Claude failure modes

## SecureLoop 9-Step Pipeline (gap-closure)

The companion agent + JetBrains plugin implement the full 9-step reference
pipeline. Files wired into the flow:

- `apps/agent/src/codex_analysis.py` — LLM-driven analysis, schema now
  includes `reasoningSteps` and `depCheck`.
- `apps/agent/src/dep_check.py` — wraps `pip-audit --format json`. Honors
  `SECURELOOP_PIP_AUDIT_BIN`. Returns `DepCheckResult` or `None` when the
  binary/timeout fails; result is fed into the Codex prompt and surfaced in
  the analysis response.
- `apps/agent/src/github_client.py` — `GitHubClient.open_pr_for_incident()`
  creates the branch, commits the patched file, and opens a PR. Commit
  messages follow `fix(security): <CWE> <category> in <path>`.
- `apps/agent/src/main.py` — `/ide/events/{incident_id}/open-pr` endpoint.
  When `GITHUB_TOKEN` or `GITHUB_REPO` are missing (or PyGithub raises),
  `_write_local_artifacts()` writes `fix.patch`, `COE.md`, and `meta.json`
  under `_PR_ARTIFACTS_ROOT` (`apps/agent/out/pr-<incident-id>/`).
- `apps/agent/src/storage.py` — `analysis_records` table persists the JSON
  blob of the latest `AnalyzeIncidentResponse` per incident so the plugin
  can open a PR after an editor restart.
- `apps/jetbrains-plugin/.../SecureLoopProjectService.kt` — `approveFix`
  stages the patched file via `Git4Idea` (reflection; optional dep),
  `showDiff` launches IntelliJ's `DiffManager`, `openPullRequest` calls the
  agent endpoint and shows success/fallback notifications.
- `apps/jetbrains-plugin/.../SecureLoopToolWindowPanel.kt` — severity
  badge + CWE pill rendered via HTML `JBLabel`, reasoning-step list,
  dep-check block, and "Show Diff" / "Open Pull Request" buttons.

Tests: `tests/test_dep_check.py` (pip-audit parsing + fallback prompts),
`tests/test_github_pr.py` (auth, 404 on missing analysis, local fallback,
client success, client exception fallback). Run with `uv run pytest`.
