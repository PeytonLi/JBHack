# Auto-Scribe — Agent Context

**Read `docs/AGENT_CONTEXT.md` before doing anything in this repo.**

## gstack

Use gstack skills when the request matches one of those workflows. Prefer `/browse` for web browsing instead of ad hoc browser tooling.

Available gstack skills include `/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/open-gstack-browser`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/cso`, `/autoplan`, `/pair-agent`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, and `/learn`.

## What this is

Auto-Scribe is a self-healing AI SRE agent: Sentry webhook in, GitHub PR with COE report out. Built for JBHack hackathon, 48-hour solo build.

## Stack

| Layer | Tech |
|---|---|
| Monorepo | pnpm workspace (`apps/*`, `packages/*`) |
| Agent (Python) | FastAPI + uv, `apps/agent/` — port 8001 |
| Target service (Python) | FastAPI + uv, `apps/target/` — port 8000 |
| Dashboard | Next.js 15 App Router, Tailwind + shadcn/ui, `apps/dashboard/` — port 3000 |
| Agent memory | SQLite WAL (`sessions`, `agent_steps`, `artifacts`) |
| DB | Supabase (Postgres) — `orders`, `inventory`, `warehouses` |
| AI | `gpt-4o` (pipeline), `gpt-4o` (COE writeup — with higher temp + reasoning prompt) |
| Test sandbox | `subprocess` + pre-populated venv (not Docker) |
| Shared types | TypeScript, `packages/shared-types/` |

## Decision summary

- **Approach B (full spec)**: Real Sentry webhook, real Supabase, real GitHub PR.
- Both autoplan reviewers recommended Approach C (video-first). User chose B with full awareness.
- Docker sandbox downgraded to subprocess to absorb Next.js overhead.
- Hard cut at hour 42: if PyGithub PR fails, write artifacts to `./out/` and screenshot.

## Canonical crash scenario

`POST /checkout` with `order.warehouse_id = 999` (does not exist in `warehouses`). One scenario, resist adding more.

## Run the project

```bash
cp .env.example .env   # fill in OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY, GITHUB_TOKEN, SENTRY_DSN
pnpm install
pnpm dev               # starts all three apps in parallel
```

## Key files

- `docs/AGENT_CONTEXT.md` — full plan + review findings + reasoning
- `docs/DESIGN_DOC.md` — design doc with alternatives and open questions
- `STORYBOARD.md` — 3-min video beat-by-beat
- `apps/agent/src/pipeline.py` — main AI pipeline
- `apps/agent/src/claude_client.py` — `call_with_log()` abstraction (all Claude calls go here)
- `apps/agent/src/coe_writer.py` — Opus 4.7 COE generation
- `apps/dashboard/app/session/[id]/page.tsx` — live thought log + COE card
