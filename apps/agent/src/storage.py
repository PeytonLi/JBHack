from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import aiosqlite

from .models import (
    AnalyzeIncidentResponse,
    IncidentRecord,
    IncidentSummary,
    NavigateRequest,
    NormalizedIncident,
)


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
            cursor = await db.execute("PRAGMA table_info(incidents)")
            existing_cols = {row[1] for row in await cursor.fetchall()}
            if "sentry_status" not in existing_cols:
                await db.execute(
                    "ALTER TABLE incidents ADD COLUMN sentry_status TEXT NOT NULL DEFAULT 'unresolved'"
                )
            if "assignee" not in existing_cols:
                await db.execute("ALTER TABLE incidents ADD COLUMN assignee TEXT")
            if "issue_id" not in existing_cols:
                await db.execute("ALTER TABLE incidents ADD COLUMN issue_id TEXT")
                await db.execute(
                    "UPDATE incidents SET issue_id = json_extract(payload_json, '$.issueId') "
                    "WHERE issue_id IS NULL"
                )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_incidents_issue_id ON incidents(issue_id)"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_records (
                    incident_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE
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
                        issue_id,
                        payload_json,
                        acknowledged,
                        created_at,
                        sentry_status,
                        assignee
                    ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        incident.incident_id,
                        incident.sentry_event_id,
                        incident.issue_id,
                        incident.model_dump_json(by_alias=True),
                        incident.received_at.isoformat(),
                        incident.sentry_status or "unresolved",
                        incident.assignee,
                    ),
                )
                await db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

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
                SELECT payload_json, acknowledged, created_at, acknowledged_at,
                       sentry_status, assignee
                FROM incidents
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                [*params, limit],
            )
            rows = await cursor.fetchall()

        incidents: list[IncidentRecord] = []
        for (
            payload_json,
            acknowledged,
            created_at,
            acknowledged_at,
            sentry_status,
            assignee,
        ) in rows:
            incident = NormalizedIncident.model_validate_json(payload_json)
            incident = _hydrate_sentry_columns(incident, sentry_status, assignee)
            incidents.append(
                IncidentRecord(
                    incident=incident,
                    status="reviewed" if acknowledged else "open",
                    created_at=_parse_datetime(created_at),
                    reviewed_at=_parse_datetime(acknowledged_at),
                )
            )
        return incidents

    async def get_record(self, incident_id: str) -> IncidentRecord | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT payload_json, acknowledged, created_at, acknowledged_at,
                       sentry_status, assignee
                FROM incidents
                WHERE incident_id = ?
                """,
                (incident_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        (
            payload_json,
            acknowledged,
            created_at,
            acknowledged_at,
            sentry_status,
            assignee,
        ) = row
        incident = NormalizedIncident.model_validate_json(payload_json)
        incident = _hydrate_sentry_columns(incident, sentry_status, assignee)
        return IncidentRecord(
            incident=incident,
            status="reviewed" if acknowledged else "open",
            created_at=_parse_datetime(created_at),
            reviewed_at=_parse_datetime(acknowledged_at),
        )

    async def update_sentry_status(
        self,
        *,
        issue_id: str,
        sentry_status: Literal["unresolved", "resolved", "ignored"] | None = None,
        assignee: str | None = None,
    ) -> list[IncidentRecord]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT incident_id, payload_json, sentry_status, assignee
                FROM incidents
                WHERE issue_id = ?
                """,
                (issue_id,),
            )
            rows = await cursor.fetchall()
            if not rows:
                return []

            updated_ids: list[str] = []
            for incident_id, payload_json, current_status, current_assignee in rows:
                new_status = sentry_status or current_status or "unresolved"
                new_assignee = assignee if assignee is not None else current_assignee
                incident = NormalizedIncident.model_validate_json(payload_json)
                incident = incident.model_copy(
                    update={
                        "sentry_status": new_status,
                        "assignee": new_assignee,
                    }
                )
                await db.execute(
                    """
                    UPDATE incidents
                    SET sentry_status = ?,
                        assignee = ?,
                        payload_json = ?
                    WHERE incident_id = ?
                    """,
                    (
                        new_status,
                        new_assignee,
                        incident.model_dump_json(by_alias=True),
                        incident_id,
                    ),
                )
                updated_ids.append(incident_id)
            await db.commit()

        updated: list[IncidentRecord] = []
        for incident_id in updated_ids:
            record = await self.get_record(incident_id)
            if record is not None:
                updated.append(record)
        return updated

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

    async def delete_incidents(
        self,
        *,
        status: Literal["all", "open", "reviewed"] = "all",
    ) -> list[str]:
        if status == "open":
            where_sql = "WHERE acknowledged = 0"
        elif status == "reviewed":
            where_sql = "WHERE acknowledged = 1"
        else:
            where_sql = ""

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"SELECT incident_id FROM incidents {where_sql}"
            )
            rows = await cursor.fetchall()
            ids = [row[0] for row in rows]
            if not ids:
                return []
            placeholders = ",".join("?" for _ in ids)
            await db.execute(
                f"DELETE FROM analysis_records WHERE incident_id IN ({placeholders})",
                ids,
            )
            await db.execute(
                f"DELETE FROM incidents WHERE incident_id IN ({placeholders})",
                ids,
            )
            await db.commit()
        return ids

    async def put_analysis(
        self,
        incident_id: str,
        analysis: AnalyzeIncidentResponse,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        payload = analysis.model_dump_json(by_alias=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO analysis_records (
                    incident_id, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (incident_id, payload, now, now),
            )
            await db.commit()

    async def get_analysis(self, incident_id: str) -> AnalyzeIncidentResponse | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT payload_json FROM analysis_records WHERE incident_id = ?",
                (incident_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return AnalyzeIncidentResponse.model_validate_json(row[0])


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

    async def publish(
        self,
        record: IncidentRecord,
        *,
        event_type: Literal["incident.created", "incident.updated"] = "incident.created",
    ) -> int:
        envelope = {
            "type": event_type,
            "incident": json.loads(record.model_dump_json(by_alias=True)),
        }
        payload = json.dumps(envelope)
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            queue.put_nowait(payload)
        return len(subscribers)

    async def publish_pipeline(
        self,
        *,
        incident_id: str,
        event_type: Literal["pipeline.step", "pipeline.completed", "pipeline.failed"],
        payload: dict[str, object] | None = None,
    ) -> int:
        envelope = {
            "type": event_type,
            "pipeline": {
                "incidentId": incident_id,
                **(payload or {}),
            },
        }
        serialized = json.dumps(envelope)
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            queue.put_nowait(serialized)
        return len(subscribers)

    async def publish_navigate(self, navigate: NavigateRequest) -> int:
        envelope = {
            "type": "ide.navigate",
            "navigate": json.loads(navigate.model_dump_json(by_alias=True)),
        }
        payload = json.dumps(envelope)
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            queue.put_nowait(payload)
        return len(subscribers)

    async def publish_cleared(
        self,
        *,
        status: Literal["all", "open", "reviewed"],
        incident_ids: list[str],
    ) -> int:
        envelope = {
            "type": "incidents.cleared",
            "cleared": {
                "status": status,
                "incidentIds": incident_ids,
                "deletedCount": len(incident_ids),
            },
        }
        payload = json.dumps(envelope)
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            queue.put_nowait(payload)
        return len(subscribers)


def _hydrate_sentry_columns(
    incident: NormalizedIncident,
    sentry_status: str | None,
    assignee: str | None,
) -> NormalizedIncident:
    updates: dict[str, object] = {}
    if sentry_status and not incident.sentry_status:
        updates["sentry_status"] = sentry_status
    elif sentry_status and incident.sentry_status != sentry_status:
        updates["sentry_status"] = sentry_status
    if assignee and incident.assignee is None:
        updates["assignee"] = assignee
    return incident.model_copy(update=updates) if updates else incident


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
