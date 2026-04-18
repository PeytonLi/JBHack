# SecureLoop JetBrains Plugin

This module contains the IntelliJ Platform plugin for SecureLoop. It listens to the local companion service at `http://127.0.0.1:8001` by default, reads the IDE auth token from `%USERPROFILE%/.secureloop/ide-token`, and surfaces raw Sentry incidents before any AI analysis runs.

## What it does

- opens a `SecureLoop` tool window
- listens to the companion service SSE stream
- shows raw incident cards with file, line, and exception details
- resolves repo-relative paths against the open project
- opens and highlights the affected line when a unique local match exists

## Running it

1. Start the companion service from `apps/agent`.
2. Open this plugin module as a Gradle project in IntelliJ IDEA or PyCharm.
3. Run the IntelliJ `runIde` Gradle task from the IDE.

The first version assumes the companion service and the IDE are running on the same machine.

## Testing it

Use `../../docs/PLUGIN_TESTING.md` for the full workflow.

The shortest proof that the plugin works is:

1. Set `SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS=1` in the repo `.env`.
2. Start `pnpm dev`.
3. Launch the sandbox IDE with `runIde`.
4. Open the JBHack repo inside the sandbox IDE.
5. Read `%USERPROFILE%/.secureloop/ide-token` or `~/.secureloop/ide-token`.
6. `POST` a debug incident to `http://127.0.0.1:8001/debug/incidents` with `Authorization: Bearer <token>`.
7. Verify the `SecureLoop` tool window updates and `apps/target/src/main.py:37` is highlighted.
