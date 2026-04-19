from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LaunchResult:
    launched: bool
    reason: str
    pid: int | None = None


class IdeLauncher:
    def __init__(
        self,
        command: list[str],
        cwd: Path,
        enabled: bool,
        *,
        spawner: Callable[..., subprocess.Popen] | None = None,
        clock: Callable[[], float] | None = None,
        debounce_seconds: float = 30.0,
    ) -> None:
        self._command = list(command)
        self._cwd = cwd
        self._enabled = enabled
        self._spawner = spawner or subprocess.Popen
        self._clock = clock or time.monotonic
        self._debounce_seconds = debounce_seconds
        self._lock = asyncio.Lock()
        self._process: subprocess.Popen | None = None
        self._last_attempt: float | None = None

    async def ensure_running(self) -> LaunchResult:
        if not self._enabled:
            return LaunchResult(launched=False, reason="disabled")
        async with self._lock:
            if self._process is not None and self._process.poll() is None:
                return LaunchResult(False, "already-running", self._process.pid)
            now = self._clock()
            if self._last_attempt is not None and (now - self._last_attempt) < self._debounce_seconds:
                return LaunchResult(launched=False, reason="debounced")
            if not self._cwd.exists():
                return LaunchResult(launched=False, reason="gradlew-not-found")
            gradlew = "gradlew.bat" if sys.platform.startswith("win") else "gradlew"
            if not (self._cwd / gradlew).exists():
                return LaunchResult(launched=False, reason="gradlew-not-found")

            kwargs: dict[str, object] = {
                "cwd": str(self._cwd),
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
            }
            if sys.platform.startswith("win"):
                kwargs["creationflags"] = (
                    subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                kwargs["start_new_session"] = True

            try:
                self._process = self._spawner(self._command, **kwargs)
            except (OSError, FileNotFoundError) as exc:
                logger.warning("IDE launch failed: %s", exc)
                self._last_attempt = now
                return LaunchResult(launched=False, reason="spawn-error")
            self._last_attempt = now
            logger.info("Spawned sandbox IDE pid=%s", self._process.pid)
            return LaunchResult(launched=True, reason="spawned", pid=self._process.pid)
