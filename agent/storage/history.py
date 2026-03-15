"""SQLite-backed tracking history for HerdFlow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import aiosqlite

from agent.models import (
    BehaviorRecord,
    DescriptionMatch,
    DescriptionSearchResult,
    EntityHistory,
    HerdStats,
    ZoneHistory,
    ZoneVisit,
)

_CREATE_BEHAVIORS = """
CREATE TABLE IF NOT EXISTS behaviors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    behavior TEXT NOT NULL,
    zone TEXT NOT NULL,
    duration_s REAL NOT NULL,
    started_at TEXT NOT NULL
);
"""

_CREATE_ZONE_VISITS = """
CREATE TABLE IF NOT EXISTS zone_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id TEXT NOT NULL,
    zone TEXT NOT NULL,
    duration_s REAL NOT NULL,
    entered_at TEXT NOT NULL
);
"""


class TrackingHistory:
    """Async SQLite-backed storage for animal behavior and zone visit history.

    Uses a persistent connection (important for :memory: databases).
    """

    def __init__(self, db_path: str = "herdflow.db") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open persistent connection and create tables."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(_CREATE_BEHAVIORS)
        await self._db.execute(_CREATE_ZONE_VISITS)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            msg = "TrackingHistory not initialized — call await initialize() first"
            raise RuntimeError(msg)
        return self._db

    async def record_behavior(
        self, track_id: str, behavior: str, zone: str, duration_s: float
    ) -> None:
        """Insert a behavior record with the current UTC timestamp."""
        db = self._conn
        await db.execute(
            "INSERT INTO behaviors (track_id, behavior, zone, duration_s, started_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (track_id, behavior, zone, duration_s, datetime.now(UTC).isoformat()),
        )
        await db.commit()

    async def record_zone_visit(self, track_id: str, zone: str, duration_s: float) -> None:
        """Insert a zone visit record with the current UTC timestamp."""
        db = self._conn
        await db.execute(
            "INSERT INTO zone_visits (track_id, zone, duration_s, entered_at) VALUES (?, ?, ?, ?)",
            (track_id, zone, duration_s, datetime.now(UTC).isoformat()),
        )
        await db.commit()

    async def search_entity_history(self, track_id: str, minutes: int = 60) -> EntityHistory:
        """Return behavior records for a specific animal within the time window."""
        cutoff = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
        db = self._conn
        async with db.execute(
            "SELECT behavior, zone, duration_s, started_at FROM behaviors"
            " WHERE track_id = ? AND started_at >= ? ORDER BY started_at ASC",
            (track_id, cutoff),
        ) as cursor:
            rows = await cursor.fetchall()

        records = [
            BehaviorRecord(
                behavior=r["behavior"],
                zone=r["zone"],
                duration_s=r["duration_s"],
                started_at=_parse_dt(r["started_at"]),
            )
            for r in rows
        ]
        return EntityHistory(
            track_id=track_id,
            records=records,
            current_behavior=records[-1].behavior if records else "standing",
            current_duration_s=records[-1].duration_s if records else 0.0,
        )

    async def get_herd_stats(self, minutes: int = 60) -> HerdStats:
        """Return aggregate herd statistics over the given time window."""
        cutoff = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
        db = self._conn

        async with db.execute(
            "SELECT COUNT(DISTINCT track_id) AS cnt FROM behaviors WHERE started_at >= ?",
            (cutoff,),
        ) as cur:
            row = await cur.fetchone()
        total_animals: int = row["cnt"] if row else 0

        async with db.execute(
            "SELECT DISTINCT track_id FROM behaviors"
            " WHERE behavior = 'feeding' AND started_at >= ?",
            (cutoff,),
        ) as cur:
            fed_ids = {r["track_id"] for r in await cur.fetchall()}

        async with db.execute(
            "SELECT DISTINCT track_id FROM behaviors WHERE started_at >= ?", (cutoff,)
        ) as cur:
            all_ids = {r["track_id"] for r in await cur.fetchall()}
        not_fed = sorted(all_ids - fed_ids)

        async with db.execute(
            "SELECT AVG(duration_s) AS avg_dur FROM behaviors"
            " WHERE behavior = 'lying' AND started_at >= ?",
            (cutoff,),
        ) as cur:
            avg_row = await cur.fetchone()
        avg_lying = float(avg_row["avg_dur"]) if avg_row and avg_row["avg_dur"] else 0.0

        async with db.execute(
            "SELECT behavior, COUNT(*) AS cnt FROM behaviors"
            " WHERE started_at >= ? GROUP BY behavior",
            (cutoff,),
        ) as cur:
            breakdown = {r["behavior"]: r["cnt"] for r in await cur.fetchall()}

        return HerdStats(
            period_minutes=minutes,
            total_animals=total_animals,
            fed_in_period=len(fed_ids),
            not_fed=not_fed,
            avg_lying_duration_s=avg_lying,
            alerts_fired=0,
            behavior_breakdown=breakdown,
        )

    async def find_by_description(self, description: str) -> DescriptionSearchResult:
        """Simple text search across recent behavior records."""
        db = self._conn
        term = f"%{description.lower()}%"
        async with db.execute(
            "SELECT track_id, behavior, zone FROM behaviors"
            " WHERE behavior LIKE ? OR zone LIKE ?"
            " ORDER BY started_at DESC LIMIT 20",
            (term, term),
        ) as cur:
            rows = await cur.fetchall()

        seen: set[str] = set()
        matches: list[DescriptionMatch] = []
        for r in rows:
            if r["track_id"] in seen:
                continue
            seen.add(r["track_id"])
            matches.append(
                DescriptionMatch(
                    track_id=r["track_id"],
                    confidence=0.6,
                    reason=f"Matched '{description}' in behavior/zone data",
                    current_behavior=r["behavior"],
                    zone=r["zone"],
                    centroid=[0.0, 0.0],
                )
            )
        return DescriptionSearchResult(matches=matches)

    async def get_zone_history(self, zone: str, minutes: int = 120) -> ZoneHistory:
        """Return zone visit records within the time window."""
        cutoff = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
        db = self._conn
        async with db.execute(
            "SELECT track_id, entered_at, duration_s FROM zone_visits"
            " WHERE zone = ? AND entered_at >= ? ORDER BY entered_at ASC",
            (zone, cutoff),
        ) as cur:
            rows = await cur.fetchall()

        visits = [
            ZoneVisit(
                track_id=r["track_id"],
                entered_at=_parse_dt(r["entered_at"]),
                duration_s=r["duration_s"],
            )
            for r in rows
        ]
        return ZoneHistory(
            zone=zone,
            period_minutes=minutes,
            visits=visits,
            current_occupancy=0,
            peak_occupancy=len(visits),
            animals_not_visited=[],
        )


def _parse_dt(s: str) -> datetime:
    """Parse ISO 8601 string, ensuring UTC timezone."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
