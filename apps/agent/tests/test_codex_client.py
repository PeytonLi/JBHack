from __future__ import annotations

from src.codex_client import _resolve_model
from src.config import load_settings


def test_resolve_model_prefers_openai_model(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.delenv("SECURE_LOOP_OPENAI_MODEL", raising=False)
    assert _resolve_model(load_settings(), None) == "gpt-4o-mini"


def test_resolve_model_defaults_to_gpt_4o_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("SECURE_LOOP_OPENAI_MODEL", raising=False)
    assert _resolve_model(load_settings(), None) == "gpt-4o"


def test_resolve_model_falls_back_to_secure_loop_var(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("SECURE_LOOP_OPENAI_MODEL", "gpt-4-turbo")
    assert _resolve_model(load_settings(), None) == "gpt-4-turbo"


def test_resolve_model_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    assert _resolve_model(load_settings(), "o1-preview") == "o1-preview"
