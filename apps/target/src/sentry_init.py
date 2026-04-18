from __future__ import annotations

import os

from dotenv import load_dotenv
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration


_INITIALIZED = False


def init_sentry() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    load_dotenv()
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.0,
        send_default_pii=False,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
    )
    _INITIALIZED = True
