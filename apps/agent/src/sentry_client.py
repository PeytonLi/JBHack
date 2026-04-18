from __future__ import annotations

from typing import Any

import httpx


class SentryEventClient:
    def __init__(self, auth_token: str | None) -> None:
        self._auth_token = auth_token

    async def fetch_event(self, event_url: str) -> dict[str, Any]:
        if not self._auth_token:
            msg = "SENTRY_AUTH_TOKEN is required to fetch full event details."
            raise RuntimeError(msg)

        headers = {
            "Authorization": f"Bearer {self._auth_token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(event_url, headers=headers)
            response.raise_for_status()
            return response.json()
