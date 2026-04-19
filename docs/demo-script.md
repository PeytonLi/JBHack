# SecureLoop Demo Script

## 3-Minute Demo

**Hook, 0:00-0:20**

Voiceover: "SecureLoop moves security left. The first place you see the problem is the IDE, not a pager."

On screen:
- open `apps/target/src/main.py`
- open the `SecureLoop` tool window
- click `Scan Current File`
- let the `Pre-Commit Scan` item load

**Aha, 0:20-0:50**

Voiceover: "Before anything ships, SecureLoop packages the active file, the repo policy, and the risky line into one IDE-native security review."

On screen:
- show the scan details
- point to `apps/target/src/main.py`, line 45, and the source context
- point to `security-policy.md` in the project tree

**Depth, 0:50-1:50**

Voiceover: "Codex analyzes the code in context. SecureLoop validates the structured response, shows the CWE, policy issue, fix plan, and patch, then waits for a human decision."

On screen:
- show the analysis state moving from loading to ready
- show severity, category, policy note, fix plan, diff, and patch
- click `Approve Fix` to apply the local patch

**Impact, 1:50-3:00**

Voiceover: "That changes the flow from find it after production to fix it before commit. If something still escapes, the Sentry path feeds the same review loop with a real stacktrace."

On screen:
- show the patched code in the editor
- click `Reject` on a rerun if time allows to show the human gate is real
- click `Run Demo` to show the Sentry-shaped backstop path
- click `Mark Reviewed`
- show the incident as reviewed

## 1-Minute Video Script

Voiceover:

"SecureLoop is a JetBrains-native security loop. Before code ships, the developer scans the active file, SecureLoop reads the repo policy and source context, and Codex returns a structured CWE-level analysis with a proposed patch. The developer approves or rejects the fix before anything changes. If something still escapes, Sentry feeds the same IDE-native loop with production stacktrace context."

On screen:
- `Scan Current File`
- `Pre-Commit Scan` appears
- rendered analysis
- `Approve Fix`
- patched code
- quick `Run Demo` shot for Sentry backstop
- `Mark Reviewed`

## Judge Q&A

**Why not real-time scanning on every keystroke?**

Because it creates noise, cost, and latency in the wrong part of the loop. SecureLoop is optimized for meaningful security events and deliberate scans at the decision points that matter: before commit, before merge, or when an incident is already known. That keeps the signal high and the developer in control.

**Why keep a human in the loop?**

Because the output is remediation guidance, not authority. The IDE can collect context, propose a patch, and explain the risk, but the developer owns correctness, policy exceptions, and code style. The human gate also makes the demo honest: the tool assists, it does not silently mutate code.

**Why use Sentry if the goal is pre-production?**

Because escaped issues still happen. SecureLoop's thesis is that Sentry should be the backstop, not the front door. Pre-production scanning and remediation are the primary workflow; Sentry is there to catch what got through and feed the same IDE-native review loop.
