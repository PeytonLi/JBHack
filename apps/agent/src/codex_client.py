from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI


@dataclass(slots=True)
class CodexResult:
    raw_text: str
    success: bool
    error: str | None = None


def codex_available() -> bool:
    if os.getenv("SECURE_LOOP_USE_FAKE_CODEX", "").strip() == "1":
        return False
    return bool(os.getenv("OPENAI_API_KEY"))


async def call_codex(
    *,
    system_prompt: str,
    user_message: str,
    response_format: dict,
    model: str = "gpt-4o-mini",
    max_output_tokens: int = 1000,
) -> CodexResult:
    if not codex_available():
        return CodexResult(
            raw_text="",
            success=False,
            error="Codex unavailable: fake mode enabled or OPENAI_API_KEY missing.",
        )

    try:
        client = AsyncOpenAI()
        response = await client.responses.create(
            model=model,
            instructions=system_prompt,
            input=user_message,
            max_output_tokens=max_output_tokens,
            text={"format": response_format},
        )
        text = response.output_text.strip()
        if not text:
            return CodexResult(
                raw_text="",
                success=False,
                error="Codex returned no text output.",
            )
        return CodexResult(raw_text=text, success=True)
    except Exception as exc:  # pragma: no cover - network/runtime edge
        return CodexResult(raw_text="", success=False, error=str(exc))
