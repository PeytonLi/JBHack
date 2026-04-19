from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Settings, load_settings, normalize_github_repo


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PeytonLi/JBHackThrowaway", "PeytonLi/JBHackThrowaway"),
        ("PeytonLi/JBHackThrowaway.git", "PeytonLi/JBHackThrowaway"),
        ("https://github.com/PeytonLi/JBHackThrowaway", "PeytonLi/JBHackThrowaway"),
        ("https://github.com/PeytonLi/JBHackThrowaway.git", "PeytonLi/JBHackThrowaway"),
        ("http://github.com/PeytonLi/JBHackThrowaway/", "PeytonLi/JBHackThrowaway"),
        ("https://www.github.com/PeytonLi/JBHackThrowaway", "PeytonLi/JBHackThrowaway"),
        ("git@github.com:PeytonLi/JBHackThrowaway.git", "PeytonLi/JBHackThrowaway"),
        ("  PeytonLi/JBHackThrowaway  ", "PeytonLi/JBHackThrowaway"),
    ],
)
def test_normalize_github_repo_accepts(raw: str, expected: str) -> None:
    assert normalize_github_repo(raw) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
    ],
)
def test_normalize_github_repo_returns_none_for_blank(value: str | None) -> None:
    assert normalize_github_repo(value) is None


@pytest.mark.parametrize(
    "raw",
    [
        "PeytonLi",
        "https://gitlab.com/PeytonLi/JBHackThrowaway",
        "https://github.com/PeytonLi",
        "https://github.com/PeytonLi/JBHackThrowaway/tree/main",
        "foo bar/baz",
        "foo/bar/baz",
    ],
)
def test_normalize_github_repo_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_github_repo(raw)


def test_load_settings_normalizes_full_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECURE_LOOP_HOME", str(tmp_path))
    monkeypatch.setenv("GITHUB_REPO", "https://github.com/foo/bar.git")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    settings = load_settings()

    assert settings.github_repo == "foo/bar"
    assert settings.autopilot_enabled() is True


def test_load_settings_rejects_invalid_repo(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECURE_LOOP_HOME", str(tmp_path))
    monkeypatch.setenv("GITHUB_REPO", "not-a-repo")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    with pytest.raises(ValueError):
        load_settings()


def test_load_settings_allows_missing_repo(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECURE_LOOP_HOME", str(tmp_path))
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    settings = load_settings()

    assert settings.github_repo is None
    assert settings.autopilot_enabled() is False


def _make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "sentry_auth_token": None,
        "sentry_webhook_secret": None,
        "allow_debug_endpoints": False,
        "secure_loop_home": Path("."),
        "sqlite_path": Path("./ingress.db"),
        "ide_token_file": Path("./ide-token"),
        "ide_token": "ide-token",
        "agent_port": 8001,
        "github_token": "tok",
        "github_repo": "foo/bar",
        "openai_api_key": "key",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_autopilot_enabled_requires_slash_in_repo() -> None:
    settings = _make_settings(github_repo="orphan-value")
    assert settings.autopilot_enabled() is False


def test_autopilot_enabled_true_when_all_set() -> None:
    settings = _make_settings()
    assert settings.autopilot_enabled() is True


def test_autopilot_enabled_false_when_token_missing() -> None:
    settings = _make_settings(github_token=None)
    assert settings.autopilot_enabled() is False


def test_autopilot_enabled_false_when_openai_key_missing() -> None:
    settings = _make_settings(openai_api_key=None)
    assert settings.autopilot_enabled() is False
