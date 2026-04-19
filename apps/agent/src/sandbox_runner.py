"""Run Codex-generated pytest against original and patched source in a tempdir."""
from __future__ import annotations

import asyncio
import os
import signal
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxResult:
    reproduced_bug: bool
    fix_passes: bool
    original_exit_code: int
    patched_exit_code: int
    original_stdout: str
    original_stderr: str
    patched_stdout: str
    patched_stderr: str
    elapsed_s: float
    timed_out: bool = False


async def run_sandbox_test(
    *,
    original_content: str,
    patched_content: str,
    repo_relative_path: str,
    test_code: str,
    timeout_s: float = 30.0,
) -> SandboxResult:
    """Run the generated pytest against original and patched sources.

    reproduced_bug is True only when pytest exited with code 1 against the
    original source (a real test failure). All other non-zero codes mean
    the generated test was broken (collection error, usage error, no tests
    collected) and do NOT count as a reproduction. fix_passes is True when
    pytest exited 0 against the patched source.
    """
    loop = asyncio.get_event_loop()
    start = loop.time()

    with tempfile.TemporaryDirectory(prefix="autopilot_sandbox_") as tmp:
        root = Path(tmp)
        orig_root = root / "original"
        patched_root = root / "patched"
        orig_root.mkdir()
        patched_root.mkdir()

        _write_source(orig_root, repo_relative_path, original_content)
        _write_source(patched_root, repo_relative_path, patched_content)

        test_rel = Path("tests") / "autopilot" / "test_incident.py"
        _write_source(orig_root, str(test_rel), test_code)
        _write_source(patched_root, str(test_rel), test_code)

        try:
            orig = await asyncio.wait_for(
                _run_pytest(orig_root, test_rel), timeout=timeout_s
            )
            patched = await asyncio.wait_for(
                _run_pytest(patched_root, test_rel), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            return SandboxResult(
                reproduced_bug=False,
                fix_passes=False,
                original_exit_code=-1,
                patched_exit_code=-1,
                original_stdout="",
                original_stderr="TIMEOUT",
                patched_stdout="",
                patched_stderr="TIMEOUT",
                elapsed_s=loop.time() - start,
                timed_out=True,
            )

        return SandboxResult(
            reproduced_bug=orig.exit_code == 1,
            fix_passes=patched.exit_code == 0,
            original_exit_code=orig.exit_code,
            patched_exit_code=patched.exit_code,
            original_stdout=orig.stdout,
            original_stderr=orig.stderr,
            patched_stdout=patched.stdout,
            patched_stderr=patched.stderr,
            elapsed_s=loop.time() - start,
        )


@dataclass
class _PytestRun:
    exit_code: int
    stdout: str
    stderr: str


async def _run_pytest(cwd: Path, test_rel: Path) -> _PytestRun:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    creation_kwargs: dict[str, object] = {}
    if sys.platform == "win32":
        creation_kwargs["creationflags"] = getattr(
            __import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        creation_kwargs["start_new_session"] = True
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pytest",
        str(test_rel),
        "-q",
        "--no-header",
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **creation_kwargs,
    )
    try:
        stdout, stderr = await proc.communicate()
    except asyncio.CancelledError:
        try:
            if sys.platform != "win32":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except Exception:
            pass
        raise
    return _PytestRun(
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


def _write_source(root: Path, repo_relative_path: str, content: str) -> None:
    target = root / repo_relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
