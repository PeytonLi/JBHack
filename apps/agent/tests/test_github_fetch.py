from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest
from github import GithubException, UnknownObjectException

from src.github_client import FetchedFile, GitHubClient


def _make_client(monkeypatch: pytest.MonkeyPatch) -> tuple[GitHubClient, MagicMock]:
    repo = MagicMock()
    repo.default_branch = "main"

    def fake_init(self: GitHubClient, token: str, repo_name: str) -> None:
        self._gh = MagicMock()
        self._repo = repo
        self._default_branch_cache = None

    monkeypatch.setattr(GitHubClient, "__init__", fake_init)
    client = GitHubClient("token", "acme/repo")
    return client, repo


def test_fetch_file_decodes_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    client, repo = _make_client(monkeypatch)
    raw = "const x = 1;\n"
    contents = MagicMock()
    contents.content = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    contents.encoding = "base64"
    contents.sha = "abc123"
    contents.path = "apps/web/foo.ts"
    repo.get_contents.return_value = contents

    result = client.fetch_file("apps/web/foo.ts")
    assert isinstance(result, FetchedFile)
    assert result.content == raw
    assert result.sha == "abc123"
    assert result.ref == "main"
    assert result.path == "apps/web/foo.ts"


def test_fetch_file_raises_file_not_found_on_unknown_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, repo = _make_client(monkeypatch)
    repo.get_contents.side_effect = UnknownObjectException(404, "missing", None)

    with pytest.raises(FileNotFoundError):
        client.fetch_file("missing.txt")


def test_fetch_file_raises_file_not_found_on_404_github_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, repo = _make_client(monkeypatch)
    repo.get_contents.side_effect = GithubException(404, "not found", None)

    with pytest.raises(FileNotFoundError):
        client.fetch_file("missing.txt")


def test_fetch_file_propagates_non_404_github_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, repo = _make_client(monkeypatch)
    repo.get_contents.side_effect = GithubException(500, "boom", None)

    with pytest.raises(GithubException):
        client.fetch_file("any.txt")


def test_fetch_file_rejects_directory_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    client, repo = _make_client(monkeypatch)
    repo.get_contents.return_value = [MagicMock(), MagicMock()]

    with pytest.raises(FileNotFoundError):
        client.fetch_file("some-dir")


def test_fetch_default_branch_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    client, repo = _make_client(monkeypatch)
    repo.default_branch = "develop"

    first = client.fetch_default_branch()
    repo.default_branch = "changed"
    second = client.fetch_default_branch()

    assert first == "develop"
    assert second == "develop"


def test_fetch_file_uses_ref_override(monkeypatch: pytest.MonkeyPatch) -> None:
    client, repo = _make_client(monkeypatch)
    contents = MagicMock()
    contents.content = base64.b64encode(b"x").decode("ascii")
    contents.encoding = "base64"
    contents.sha = "sha"
    contents.path = "p"
    repo.get_contents.return_value = contents

    result = client.fetch_file("p", ref="feature-branch")
    assert result.ref == "feature-branch"
    repo.get_contents.assert_called_with("p", ref="feature-branch")
