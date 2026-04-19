# Plan: Normalize & validate `GITHUB_REPO` at load time

## Why

Confirmed root cause of the "Sentry webhook arrives → incident card appears → pipeline stays on
idle" symptom:

- `.env` currently has `GITHUB_REPO=https://github.com/PeytonLi/JBHackThrowaway.git`.
- `Settings.autopilot_enabled()` uses plain `bool(self.github_repo)`, so a non-empty URL passes
  the truthiness gate and `/status` reports `autopilotEnabled: true`.
- `apps/agent/src/github_client.py::GitHubClient.__init__` calls
  `Github(token).get_repo(repo)`. PyGithub expects `"owner/repo"` (or an integer ID); a full
  `https://.../repo.git` URL raises `UnknownObjectException` / `GithubException(404)`.
- That exception propagates out of `_fetch_file_async` in `apps/agent/src/autopilot.py` and is
  swallowed by the top-level `except Exception` in `run_autopilot` (line 105), which publishes
  `pipeline.failed` with `reason=internal_error`. Depending on SSE subscription timing the
  dashboard may miss that event, so the card appears idle indefinitely.

Fix: reject bad shapes at startup (loud failure beats silent idle), and auto-normalize the
common "pasted the whole URL" mistake so autopilot just works.

## Scope

In scope:

- Add a pure helper `normalize_github_repo(value: str | None) -> str | None` in
  `apps/agent/src/config.py`.
- Use it inside `load_settings()` so `Settings.github_repo` is always either `None` or a
  validated `"owner/repo"` string.
- Tighten `Settings.autopilot_enabled()` to require a `"/"` in `github_repo` (belt-and-braces
  against a future caller that bypasses `load_settings`).
- Log at INFO when a URL form is normalized, and raise a clear `ValueError` at startup when the
  value is present but unparseable.
- Add `apps/agent/tests/test_config.py` covering the normalizer and the tightened
  `autopilot_enabled()`.
- Update `.env.example` comment on `GITHUB_REPO` to state the accepted formats explicitly.

Out of scope (explicitly, per user choice "Code fix"):

- No broader observability pass. We do not add logging at every silent branch in `main.py` /
  `autopilot.py`. That's the separate "observability fix" option the user declined.
- No change to the webhook handlers, broker, or SSE stream.
- No change to `GitHubClient` — it keeps trusting its input; the trust boundary is
  `load_settings()`.
- No migration of existing `.env` files. User edits their own `.env`; with normalization they
  don't have to.

## Accepted input shapes for `GITHUB_REPO`

Normalizer must accept all of these and produce `"PeytonLi/JBHackThrowaway"`:

| Input                                                      | Result                        |
| ---------------------------------------------------------- | ----------------------------- |
| `PeytonLi/JBHackThrowaway`                                  | `PeytonLi/JBHackThrowaway`    |
| `PeytonLi/JBHackThrowaway.git`                              | `PeytonLi/JBHackThrowaway`    |
| `https://github.com/PeytonLi/JBHackThrowaway`               | `PeytonLi/JBHackThrowaway`    |
| `https://github.com/PeytonLi/JBHackThrowaway.git`           | `PeytonLi/JBHackThrowaway`    |
| `http://github.com/PeytonLi/JBHackThrowaway/`               | `PeytonLi/JBHackThrowaway`    |
| `git@github.com:PeytonLi/JBHackThrowaway.git`               | `PeytonLi/JBHackThrowaway`    |
| `  PeytonLi/JBHackThrowaway  ` (whitespace)                | `PeytonLi/JBHackThrowaway`    |
| `""` / `None`                                               | `None` (autopilot disabled)   |

Must reject (raise `ValueError("GITHUB_REPO must be in 'owner/repo' form; got: ...")`):

- `PeytonLi` (no slash, not a URL)
- `https://gitlab.com/PeytonLi/JBHackThrowaway` (non-github host — we only support github.com)
- `https://github.com/PeytonLi` (missing repo segment)
- `https://github.com/PeytonLi/JBHackThrowaway/tree/main` (extra path segments — ambiguous)

Rationale for being strict on the reject cases: the whole point of this change is that invalid
values fail *loudly at startup* rather than silently at the `pipeline.failed` level.

## Implementation steps

### 1. `apps/agent/src/config.py`

Add the normalizer above `load_settings`:

```python
import logging
import re

_logger = logging.getLogger("secureloop.agent.config")

_OWNER_REPO_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$")


def normalize_github_repo(value: str | None) -> str | None:
    """Return a validated ``owner/repo`` string, or ``None`` when unset.

    Accepts the plain ``owner/repo`` form, full https/ssh github.com URLs, and an
    optional ``.git`` suffix. Raises ``ValueError`` when the value is present but
    cannot be reduced to a single ``owner/repo`` pair.
    """
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None

    candidate = raw
    if candidate.startswith(("http://", "https://")):
        stripped = candidate.split("://", 1)[1]
        host, _, path = stripped.partition("/")
        if host.lower() not in {"github.com", "www.github.com"}:
            raise ValueError(
                f"GITHUB_REPO must point at github.com; got host '{host}' in '{raw}'."
            )
        candidate = path
    elif candidate.startswith("git@"):
        _, _, path = candidate.partition(":")
        candidate = path

    candidate = candidate.strip("/")
    match = _OWNER_REPO_RE.match(candidate)
    if not match:
        raise ValueError(
            f"GITHUB_REPO must be in 'owner/repo' form; got: {raw!r}."
        )
    normalized = f"{match.group(1)}/{match.group(2)}"
    if normalized != raw:
        _logger.info("Normalized GITHUB_REPO %r -> %r", raw, normalized)
    return normalized
```

Then in `load_settings()` replace:

```python
github_repo=os.getenv("GITHUB_REPO") or None,
```

with:

```python
github_repo=normalize_github_repo(os.getenv("GITHUB_REPO")),
```

Tighten `Settings.autopilot_enabled`:

```python
def autopilot_enabled(self) -> bool:
    return (
        bool(self.github_token)
        and bool(self.github_repo)
        and "/" in (self.github_repo or "")
        and bool(self.openai_api_key)
    )
```

(The `"/"` check is redundant once `load_settings` is the only producer, but it guards tests
and other callers that construct `Settings(...)` directly.)

### 2. `.env.example`

Update the comment/example around `GITHUB_REPO` to explicitly state accepted formats so users
don't paste a clone URL blindly again:

```
# Required for autopilot. Use 'owner/repo'. Full https/ssh URLs are accepted and
# will be normalized automatically. Example:
GITHUB_REPO=your-github-username/autoscribe-throwaway
```

### 3. `apps/agent/tests/test_config.py` (new)

New test file, following the `monkeypatch`+`load_settings` style already used by
`test_codex_client.py`. Covers:

- `normalize_github_repo` happy paths: each row in the "accepted" table above.
- `normalize_github_repo` rejects: each row in the "reject" table raises `ValueError`.
- `normalize_github_repo(None)` → `None`, `normalize_github_repo("")` → `None`,
  `normalize_github_repo("   ")` → `None`.
- `load_settings()` with `GITHUB_REPO=https://github.com/foo/bar.git` yields
  `settings.github_repo == "foo/bar"`.
- `load_settings()` with `GITHUB_REPO=not-a-repo` raises at load time.
- `Settings.autopilot_enabled()` returns False when `github_repo` is a bare token without `/`
  (direct-construct path, does not go through `load_settings`).
- `Settings.autopilot_enabled()` returns True when all three env vars are set and repo is
  valid.

Target: ~10 test cases, single file, no new fixtures.

### 4. Running the new tests

From `apps/agent/`:

```bash
uv run pytest tests/test_config.py -v
```

Also re-run the full agent suite to catch incidental breakage (the autopilot tests monkeypatch
settings directly; the tightened `autopilot_enabled` should not affect them because they
already use `owner/repo`-shaped values in fixtures):

```bash
uv run pytest -v
```

## Risk & rollout

- **Startup crash risk**: `create_app` calls `load_settings()` at import/boot. Raising here
  means a misconfigured `.env` will fail `uvicorn` startup with a clear `ValueError` message
  instead of silently running with autopilot half-broken. That's the desired behaviour — "fail
  loudly" is the whole point of this task. No separate feature flag.
- **Backward compatibility**: Existing correctly-configured deployments (`owner/repo` form)
  pass through the regex unchanged; normalized value equals input, no log line emitted.
- **No DB / schema / API changes.** No migrations.
- **`GITHUB_REPO` unset** keeps today's behaviour (autopilot disabled, dashboard works, no
  crash). The normalizer returns `None` for missing/blank values.

## Verification plan (post-implementation, run by user)

1. `uv run pytest apps/agent/tests/test_config.py -v` passes.
2. Set `GITHUB_REPO=https://github.com/PeytonLi/JBHackThrowaway.git` in `.env`, start the
   agent. Expect a log line: `Normalized GITHUB_REPO 'https://.../.git' -> 'PeytonLi/JBHackThrowaway'`.
3. `curl http://localhost:8001/status` → `{"githubRepo": "PeytonLi/JBHackThrowaway",
   "autopilotEnabled": true, ...}`.
4. Replay the Sentry webhook. Expect the dashboard to transition out of "idle" and show
   `pipeline.step` events (`fetch_source → analyze → open_pr`).
5. Set `GITHUB_REPO=garbage` in `.env`, restart. Expect the agent to refuse to start with
   `ValueError: GITHUB_REPO must be in 'owner/repo' form; got: 'garbage'.` on stderr.

## Files touched

| File                                      | Change    |
| ----------------------------------------- | --------- |
| `apps/agent/src/config.py`                | Modified  |
| `apps/agent/tests/test_config.py`         | New       |
| `.env.example`                            | Modified  |

Three files. No changes to `main.py`, `autopilot.py`, `github_client.py`, or any dashboard /
plugin code.
