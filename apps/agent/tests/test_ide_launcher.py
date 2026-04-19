from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.ide_launcher import IdeLauncher


def _fake_cwd_with_gradlew(tmp_path: Path) -> Path:
    (tmp_path / "gradlew.bat").write_text("", encoding="utf-8")
    (tmp_path / "gradlew").write_text("", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_ensure_running_spawns_once_under_concurrency(tmp_path: Path) -> None:
    cwd = _fake_cwd_with_gradlew(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 4242
    fake_proc.poll.return_value = None
    spawner = MagicMock(return_value=fake_proc)

    launcher = IdeLauncher(
        command=["gradlew.bat", "runIde"],
        cwd=cwd,
        enabled=True,
        spawner=spawner,
        clock=lambda: 0.0,
    )
    results = await asyncio.gather(
        launcher.ensure_running(),
        launcher.ensure_running(),
        launcher.ensure_running(),
    )
    launched = [r for r in results if r.launched]
    assert len(launched) == 1
    assert spawner.call_count == 1
    other = [r for r in results if not r.launched]
    assert all(r.reason == "already-running" for r in other)


@pytest.mark.asyncio
async def test_disabled_launcher_does_not_spawn(tmp_path: Path) -> None:
    cwd = _fake_cwd_with_gradlew(tmp_path)
    spawner = MagicMock()
    launcher = IdeLauncher(
        command=["gradlew.bat", "runIde"],
        cwd=cwd,
        enabled=False,
        spawner=spawner,
    )
    result = await launcher.ensure_running()
    assert result.launched is False
    assert result.reason == "disabled"
    spawner.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_running_returns_already_running_when_process_alive(
    tmp_path: Path,
) -> None:
    cwd = _fake_cwd_with_gradlew(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 1111
    fake_proc.poll.return_value = None
    spawner = MagicMock(return_value=fake_proc)
    launcher = IdeLauncher(
        command=["gradlew.bat", "runIde"],
        cwd=cwd,
        enabled=True,
        spawner=spawner,
        clock=lambda: 0.0,
    )
    first = await launcher.ensure_running()
    second = await launcher.ensure_running()
    assert first.launched is True
    assert second.launched is False
    assert second.reason == "already-running"
    assert spawner.call_count == 1


@pytest.mark.asyncio
async def test_ensure_running_debounced_after_exit(tmp_path: Path) -> None:
    cwd = _fake_cwd_with_gradlew(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 2222
    fake_proc.poll.return_value = 0  # exited
    spawner = MagicMock(return_value=fake_proc)
    times = iter([0.0, 5.0])
    launcher = IdeLauncher(
        command=["gradlew.bat", "runIde"],
        cwd=cwd,
        enabled=True,
        spawner=spawner,
        clock=lambda: next(times),
    )
    first = await launcher.ensure_running()
    second = await launcher.ensure_running()
    assert first.launched is True
    assert second.launched is False
    assert second.reason == "debounced"
    assert spawner.call_count == 1


@pytest.mark.asyncio
async def test_ensure_running_returns_not_found_when_gradle_missing(
    tmp_path: Path,
) -> None:
    spawner = MagicMock()
    launcher = IdeLauncher(
        command=["gradlew.bat", "runIde"],
        cwd=tmp_path,
        enabled=True,
        spawner=spawner,
        clock=lambda: 0.0,
    )
    result = await launcher.ensure_running()
    assert result.launched is False
    assert result.reason == "gradlew-not-found"
    spawner.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_running_handles_spawn_error(tmp_path: Path) -> None:
    cwd = _fake_cwd_with_gradlew(tmp_path)
    spawner = MagicMock(side_effect=FileNotFoundError("nope"))
    launcher = IdeLauncher(
        command=["gradlew.bat", "runIde"],
        cwd=cwd,
        enabled=True,
        spawner=spawner,
        clock=lambda: 0.0,
    )
    result = await launcher.ensure_running()
    assert result.launched is False
    assert result.reason == "spawn-error"
    assert launcher._last_attempt == 0.0  # debounce applies on retry
