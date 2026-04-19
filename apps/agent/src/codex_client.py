from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from .config import Settings, load_settings


@dataclass(slots=True)
class CodexResult:
    raw_text: str
    success: bool
    error: str | None = None


def codex_available() -> bool:
    if os.getenv("SECURE_LOOP_USE_FAKE_CODEX", "").strip().lower() in {"1", "true", "yes"}:
        return False
    return bool(os.getenv("OPENAI_API_KEY"))


def _resolve_model(settings: Settings, override: str | None) -> str:
    """Resolve the OpenAI model name; override wins, else settings default."""
    return override or settings.openai_model


async def call_codex(
    *,
    system_prompt: str,
    user_message: str,
    response_format: dict[str, Any],
    model: str | None = None,
    max_output_tokens: int = 1200,
    settings: Settings | None = None,
) -> CodexResult:
    if not codex_available():
        return CodexResult(
            raw_text="",
            success=False,
            error="Codex unavailable: fake mode is enabled or OPENAI_API_KEY is missing.",
        )

    model_name = _resolve_model(settings or load_settings(), model)

    try:
        client = AsyncOpenAI()
        response = await client.responses.create(
            model=model_name,
            instructions=system_prompt,
            input=user_message,
            max_output_tokens=max_output_tokens,
            text={"format": response_format},
        )
        text = response.output_text.strip()
        if not text:
            return CodexResult(raw_text="", success=False, error="Codex returned no text output.")
        return CodexResult(raw_text=text, success=True)
    except Exception as exc:  # pragma: no cover - network/runtime edge
        return CodexResult(raw_text="", success=False, error=str(exc))
