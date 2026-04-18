# Auto-Scribe (JBHack)

Auto-Scribe is a self-healing AI SRE agent prototype: it receives a Sentry crash webhook, investigates context, proposes a fix, and prepares artifacts for a GitHub pull request plus a Correction of Error (COE) report.

## What is in this repository

This repo is a monorepo scaffold for three applications plus shared types:

- `apps/target`: intentionally broken FastAPI service (crash source)
- `apps/agent`: FastAPI companion service (signed Sentry webhook in, IDE SSE stream out)
- `apps/dashboard`: Next.js dashboard for session timeline and COE output
- `apps/jetbrains-plugin`: IntelliJ/PyCharm plugin for raw incident surfacing and line highlighting
- `packages/shared-types`: shared TypeScript contracts
- `docs/`: architecture and implementation context

## Prerequisites

- Node.js 20+
- pnpm 9+
- Python 3.11+
- uv (Python package manager)

## Quick Start

1. Install Node dependencies:

```bash
pnpm install
```

2. Install Python dependencies for both Python apps:

```bash
pnpm run install:python
```

3. Create local environment file:

```bash
cp .env.example .env
```

4. Fill required values in `.env`:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SENTRY_DSN`
- `SENTRY_AUTH_TOKEN`
- `GITHUB_TOKEN`
- `GITHUB_REPO`

5. Start all apps:

```bash
pnpm dev
```

Expected local ports:

- target: `http://localhost:8000`
- agent: `http://localhost:8001`
- dashboard: `http://localhost:3000`

The companion service writes an IDE auth token to `%USERPROFILE%/.secureloop/ide-token`. The JetBrains plugin reads that token and connects to the local SSE stream.

For plugin-only local testing, set `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1` and follow `docs/PLUGIN_TESTING.md`.

## Root Scripts

- `pnpm dev`: run target, agent, and dashboard concurrently
- `pnpm run install:python`: run `uv sync` in both Python apps
- `pnpm run build`: build dashboard
- `pnpm run typecheck`: TypeScript checks for dashboard and shared-types

## Canonical Demo Scenario

The intended demo path is one reproducible failure case:

- Trigger checkout with a warehouse reference that does not exist
- Emit Sentry event from target
- Receive the signed alert in the companion webhook
- Stream the normalized incident into the JetBrains plugin and highlight the affected line
- Produce investigation and fix artifacts
- Generate COE report and open PR

See `docs/AGENT_CONTEXT.md` for implementation checkpoints and cut-lines.

## Security Notes

- `.env` is ignored by git and must never be committed.
- Keep `.env.example` as placeholders only.
- If any real credential is ever exposed, rotate it immediately.

## Documentation

- `docs/AGENT_CONTEXT.md`: source-of-truth implementation plan
- `docs/DESIGN_DOC.md`: design rationale and tradeoffs
- `docs/PLUGIN_TESTING.md`: step-by-step plugin smoke test and full Sentry verification flow
- `STORYBOARD.md`: 3-minute demo storyline
