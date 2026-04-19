from __future__ import annotations

import os
import secrets
import sys
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
    github_token: str | None = None
    github_repo: str | None = None
    openai_api_key: str | None = None
    ide_auto_launch: bool = True
    ide_launch_command: list[str] | None = None
    ide_launch_cwd: Path | None = None

    def autopilot_enabled(self) -> bool:
        return bool(self.github_token) and bool(self.github_repo) and bool(self.openai_api_key)


def load_settings() -> Settings:
    configured_home = os.getenv("SECURE_LOOP_HOME", "").strip()
    secure_loop_home = Path(configured_home or (Path.home() / ".secureloop")).expanduser()
    secure_loop_home.mkdir(parents=True, exist_ok=True)

    ide_token_file = secure_loop_home / "ide-token"
    ide_token = os.getenv("SECURE_LOOP_IDE_TOKEN") or _load_or_create_token(ide_token_file)
    ide_token_file.write_text(ide_token, encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[3]
    ide_launch_cwd = repo_root / "apps" / "jetbrains-plugin"
    if sys.platform.startswith("win"):
        ide_launch_command = ["cmd.exe", "/c", "gradlew.bat", "runIde", "--daemon"]
    else:
        ide_launch_command = ["./gradlew", "runIde", "--daemon"]
    ide_auto_launch = os.getenv("SECURE_LOOP_IDE_AUTO_LAUNCH", "1").strip().lower() \
        not in {"0", "false", "no"}

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
        github_token=os.getenv("GITHUB_TOKEN") or None,
        github_repo=os.getenv("GITHUB_REPO") or None,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        ide_auto_launch=ide_auto_launch,
        ide_launch_command=ide_launch_command,
        ide_launch_cwd=ide_launch_cwd,
    )


def _load_or_create_token(token_file: Path) -> str:
    if token_file.exists():
        existing = token_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    token = secrets.token_urlsafe(32)
    token_file.write_text(token, encoding="utf-8")
    return token
