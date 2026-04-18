from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    sentry_auth_token: str | None
    sentry_webhook_secret: str | None
    allow_debug_endpoints: bool
    secure_loop_home: Path
    sqlite_path: Path
    ide_token_file: Path
    ide_token: str
    agent_port: int


def load_settings() -> Settings:
    configured_home = os.getenv("SECURE_LOOP_HOME", "").strip()
    secure_loop_home = Path(configured_home or (Path.home() / ".secureloop")).expanduser()
    secure_loop_home.mkdir(parents=True, exist_ok=True)

    ide_token_file = secure_loop_home / "ide-token"
    ide_token = os.getenv("SECURE_LOOP_IDE_TOKEN") or _load_or_create_token(ide_token_file)
    ide_token_file.write_text(ide_token, encoding="utf-8")

    return Settings(
        sentry_auth_token=os.getenv("SENTRY_AUTH_TOKEN"),
        sentry_webhook_secret=os.getenv("SENTRY_WEBHOOK_SECRET"),
        allow_debug_endpoints=os.getenv("SECURE_LOOP_ALLOW_DEBUG_ENDPOINTS", "0").strip()
        in {"1", "true", "TRUE", "yes", "YES"},
        secure_loop_home=secure_loop_home,
        sqlite_path=secure_loop_home / "ingress.db",
        ide_token_file=ide_token_file,
        ide_token=ide_token,
        agent_port=int(os.getenv("AGENT_PORT", "8001")),
    )


def _load_or_create_token(token_file: Path) -> str:
    if token_file.exists():
        existing = token_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    token = secrets.token_urlsafe(32)
    token_file.write_text(token, encoding="utf-8")
    return token
