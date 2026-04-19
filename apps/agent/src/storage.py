from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import aiosqlite

from .models import IncidentRecord, IncidentSummary, NormalizedIncident


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

    async def get_incident(self, incident_id: str) -> NormalizedIncident | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT payload_json FROM incidents WHERE incident_id = ?",
                (incident_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return NormalizedIncident.model_validate_json(row[0])

    async def list_unreviewed(self) -> list[NormalizedIncident]:
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

    async def list_incidents(
        self,
        *,
        status: Literal["all", "open", "reviewed"] = "all",
        limit: int = 50,
    ) -> list[IncidentRecord]:
        clauses: list[str] = []
        params: list[str | int] = []

        if status == "open":
            clauses.append("acknowledged = 0")
        elif status == "reviewed":
            clauses.append("acknowledged = 1")

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"""
                SELECT payload_json, acknowledged, created_at, acknowledged_at
                FROM incidents
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [*params, limit],
            )
            rows = await cursor.fetchall()

        incidents: list[IncidentRecord] = []
        for payload_json, acknowledged, created_at, acknowledged_at in rows:
            incidents.append(
                IncidentRecord(
                    incident=NormalizedIncident.model_validate_json(payload_json),
                    status="reviewed" if acknowledged else "open",
                    created_at=_parse_datetime(created_at),
                    reviewed_at=_parse_datetime(acknowledged_at),
                )
            )
        return incidents

    async def get_summary(self) -> IncidentSummary:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT
                    SUM(CASE WHEN acknowledged = 0 THEN 1 ELSE 0 END) AS open_count,
                    SUM(CASE WHEN acknowledged = 1 THEN 1 ELSE 0 END) AS reviewed_count,
                    COUNT(*) AS total_count
                FROM incidents
                """
            )
            row = await cursor.fetchone()

        open_count, reviewed_count, total_count = row or (0, 0, 0)
        return IncidentSummary(
            open_count=int(open_count or 0),
            reviewed_count=int(reviewed_count or 0),
            total_count=int(total_count or 0),
        )

    async def mark_reviewed(self, incident_id: str) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            exists_cursor = await db.execute(
                "SELECT acknowledged FROM incidents WHERE incident_id = ?",
                (incident_id,),
            )
            row = await exists_cursor.fetchone()
            if row is None:
                return False

            if row[0]:
                return True

            await db.execute(
                """
                UPDATE incidents
                SET acknowledged = 1,
                    acknowledged_at = ?
                WHERE incident_id = ?
                """,
                (datetime.now(UTC).isoformat(), incident_id),
            )
            await db.commit()
            return True

    async def acknowledge(self, incident_id: str) -> bool:
        return await self.mark_reviewed(incident_id)


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


def _parse_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None

    normalized = raw_value.strip().replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
