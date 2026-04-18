# SecureLoop JetBrains Plugin

The SecureLoop plugin surfaces production-style incidents inside IntelliJ IDEA or PyCharm before any AI analysis runs. For v1, the supported happy path is the JBHack demo repo opened locally with the SecureLoop companion service running on the same machine.

## What It Does

- opens a `SecureLoop` tool window
- checks the local agent connection automatically
- shows whether the current project matches the supported demo repo
- lets the user click `Run Demo` instead of posting incidents manually
- streams raw incidents from the local agent over SSE
- resolves repo-relative paths and highlights the affected line in the editor
- keeps incidents open until the user explicitly clicks `Mark Reviewed`

## Recommended First-Run Flow

1. Start the repo from the root with `pnpm dev`.
2. Open this module as a Gradle project in IntelliJ IDEA or PyCharm.
3. Run the `runIde` Gradle task.
4. In the sandbox IDE, open the JBHack repo root.
5. Open the `SecureLoop` tool window.
6. Wait for `Demo ready`.
7. Click `Run Demo`.
8. Click `Mark Reviewed` after confirming the file highlight.

If the tool window does not show `Demo ready`, use `Retry Connection` and follow the status message in the panel.

## Connection Rules

- default agent URL: `http://127.0.0.1:8001`
- token file: `%USERPROFILE%/.secureloop/ide-token` or `~/.secureloop/ide-token`
- demo mode requires `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1`

The plugin reads the token automatically. A new user should not need to fetch it manually.

## Supported Project Scope

v1 supports the SecureLoop demo repo only. The tool window expects:

- `apps/target/src/main.py`
- `security-policy.md`

If those files are not present, the plugin stays usable but marks the project as unsupported for demo mode.

## Incident Lifecycle

- new incidents stay in the local queue as `open`
- reconnecting the plugin replays open incidents, but the plugin deduplicates them locally
- `Mark Reviewed` is the only action that clears an incident from the replay queue
- the dashboard shows both open incidents and reviewed history using the same agent data

## Advanced Testing

Use `../../docs/PLUGIN_TESTING.md` for the full smoke test and real signed webhook flow.
