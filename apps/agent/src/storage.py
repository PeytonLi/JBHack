from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import aiosqlite

from .models import NormalizedIncident


class IncidentStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    sentry_event_id TEXT UNIQUE NOT NULL,
                    payload_json TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT
                )
                """
            )
            await db.commit()

    async def put_if_absent(self, incident: NormalizedIncident) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            try:
                await db.execute(
                    """
                    INSERT INTO incidents (
                        incident_id,
                        sentry_event_id,
                        payload_json,
                        acknowledged,
                        created_at
                    ) VALUES (?, ?, ?, 0, ?)
                    """,
                    (
                        incident.incident_id,
                        incident.sentry_event_id,
                        incident.model_dump_json(by_alias=True),
                        incident.received_at.isoformat(),
                    ),
                )
                await db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    async def list_unacknowledged(self) -> list[NormalizedIncident]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT payload_json
                FROM incidents
                WHERE acknowledged = 0
                ORDER BY created_at ASC
                """
            )
            rows = await cursor.fetchall()
        return [NormalizedIncident.model_validate_json(row[0]) for row in rows]

    async def acknowledge(self, incident_id: str) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                UPDATE incidents
                SET acknowledged = 1,
                    acknowledged_at = CURRENT_TIMESTAMP
                WHERE incident_id = ?
                """,
                (incident_id,),
            )
            await db.commit()
            return cursor.rowcount > 0


class IncidentBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(self, incident: NormalizedIncident) -> None:
        payload = incident.model_dump_json(by_alias=True)
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            queue.put_nowait(payload)
