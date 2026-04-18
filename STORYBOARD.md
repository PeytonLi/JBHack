# STORYBOARD — Auto-Scribe 3-Minute Demo Video

Reference this every time you check the plan. If what you're building doesn't appear in a beat, it's optional.

## Beats

**Beat 1 (0:00–0:20) — The crash**
- Screen: terminal with target service running
- Narration: "Charlie tries to checkout. The system crashes."
- Action: `curl -X POST http://localhost:8000/checkout -d '{"order_id": "POISON-001"}'`
- Shows: 500 error in terminal + Sentry event appearing in Sentry web UI

**Beat 2 (0:20–0:35) — Dashboard lights up**
- Screen: Auto-Scribe dashboard at localhost:3000
- Narration: "Auto-Scribe receives the Sentry webhook and opens a new session."
- Shows: New session card appears live on dashboard (no refresh needed)

**Beat 3 (0:35–1:10) — The agent thinks**
- Screen: Session detail view, ThoughtLog streaming
- Narration: "The agent reads the stack trace, queries the real database, and finds the broken row."
- Shows: Thought log items appearing one by one — "parsing stack trace", "introspecting schema", "running SQL query", "found poison row: POISON-001 with warehouse_id=999 (nonexistent)"

**Beat 4 (1:10–1:30) — Reproduce the bug**
- Screen: ThoughtLog continuing + test code visible in dashboard artifacts panel
- Narration: "It generates a regression test that proves the bug."
- Shows: Generated pytest file visible, subprocess run output showing FAILED with the same exception class

**Beat 5 (1:30–1:50) — Fix it**
- Screen: ThoughtLog + diff artifact panel
- Narration: "Then it writes the fix."
- Shows: Generated diff visible, subprocess run output showing PASSED

**Beat 6 (1:50–2:30) — The COE**
- Screen: COECard on dashboard (markdown-rendered, GitHub theme)
- Narration: "The real deliverable: a complete Correction of Error report."
- Shows: COE with Root Cause, 5 Whys, Impact Estimate, Prevention items rendered beautifully
- Zoom in on Prevention: "Add FK constraint on orders.warehouse_id. Add Pydantic validator at API boundary."

**Beat 7 (2:30–3:00) — The PR**
- Screen: GitHub PR page (opened by the agent)
- Narration: "Auto-Scribe opens a PR with the fix, the test, and the COE attached."
- Shows: PR with 3 files (fix.py, tests/test_fix.py, COE_LOG.md), PR description is the COE summary

## What the Judges See

| Criterion | Evidence in video |
|---|---|
| Working demo | Real crash → real Sentry event → real pipeline |
| AI integration | Claude thought log streaming live |
| Polish | Dashboard with dark theme, typography, animated timeline |
| Differentiation | COE card (nobody else ships this) |
| Code quality | GitHub PR with test + COE in separate commits |

## Fallback Beats

If PyGithub PR creation fails (cut at hour 42):
- Beat 7 becomes: "Here's what the PR would look like" + screenshot of GitHub's new PR compose screen with the fields pre-filled
- Show `./out/COE_LOG.md`, `./out/fix.py`, `./out/test_fix.py` in VS Code explorer

If dashboard SSE is polling instead of SSE:
- No change to script — polling at 1500ms interval looks live on video
