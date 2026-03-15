"""Gemini tool definitions and mock tracking history for HerdFlow agent."""

from __future__ import annotations

from datetime import UTC, datetime

from agent.models import (
    BehaviorRecord,
    DescriptionMatch,
    DescriptionSearchResult,
    EntityHistory,
    HerdStats,
    ZoneHistory,
    ZoneVisit,
)

# ── Reference timestamp for mock data ──
_BASE = datetime(2026, 3, 15, 8, 0, 0, tzinfo=UTC)
_MINS = 60  # seconds per minute


def _t(h: int, m: int) -> datetime:
    """Return a UTC datetime at 2026-03-15 HH:MM."""
    return datetime(2026, 3, 15, h, m, 0, tzinfo=UTC)


class MockTrackingHistory:
    """In-memory mock of the TrackingHistory storage interface.

    Returns deterministic responses for testing and development
    without requiring a live database or video feed.
    """

    async def search_entity_history(self, track_id: str, minutes: int = 60) -> EntityHistory:
        """Return behavior history for a specific animal.

        Known mock: COW-003 — extended lying session after feeding.
        Unknown track_ids return a minimal default history.
        """
        if track_id == "COW-003":
            return EntityHistory(
                track_id="COW-003",
                records=[
                    BehaviorRecord(
                        behavior="walking",
                        zone="feed_area",
                        duration_s=600.0,
                        started_at=_t(8, 0),
                    ),
                    BehaviorRecord(
                        behavior="feeding",
                        zone="feed_area",
                        duration_s=1200.0,
                        started_at=_t(8, 10),
                    ),
                    BehaviorRecord(
                        behavior="walking",
                        zone="rest_area",
                        duration_s=300.0,
                        started_at=_t(8, 30),
                    ),
                    BehaviorRecord(
                        behavior="lying",
                        zone="rest_area",
                        duration_s=4320.0,
                        started_at=_t(8, 35),
                    ),
                ],
                current_behavior="lying",
                current_duration_s=4320.0,
            )
        # Default: unknown entity, minimal standing record
        return EntityHistory(
            track_id=track_id,
            records=[],
            current_behavior="standing",
            current_duration_s=300.0,
        )

    async def get_herd_stats(self, minutes: int = 60) -> HerdStats:
        """Return aggregate herd statistics over the given time window."""
        return HerdStats(
            period_minutes=minutes,
            total_animals=8,
            fed_in_period=6,
            not_fed=["COW-003", "COW-007"],
            avg_lying_duration_s=1800.0,
            alerts_fired=2,
            behavior_breakdown={
                "standing": 3,
                "lying": 2,
                "walking": 1,
                "feeding": 1,
                "drinking": 1,
            },
        )

    async def find_by_description(self, description: str) -> DescriptionSearchResult:
        """Return animals matching a natural language description."""
        return DescriptionSearchResult(
            matches=[
                DescriptionMatch(
                    track_id="COW-005",
                    confidence=0.72,
                    reason="Located near zone boundary (rest_area edge), closest to fence region",
                    current_behavior="standing",
                    zone="rest_area",
                    centroid=[0.85, 0.45],
                )
            ]
        )

    async def get_zone_history(self, zone: str, minutes: int = 120) -> ZoneHistory:
        """Return zone occupancy history over the given time window."""
        return ZoneHistory(
            zone=zone,
            period_minutes=minutes,
            visits=[
                ZoneVisit(track_id="COW-001", entered_at=_t(7, 15), duration_s=120.0),
                ZoneVisit(track_id="COW-004", entered_at=_t(7, 30), duration_s=90.0),
                ZoneVisit(track_id="COW-002", entered_at=_t(8, 0), duration_s=150.0),
                ZoneVisit(track_id="COW-006", entered_at=_t(8, 45), duration_s=60.0),
            ],
            current_occupancy=0,
            peak_occupancy=1,
            animals_not_visited=["COW-003", "COW-007", "COW-008"],
        )


# ── Module-level singleton and tool functions ──

mock_history = MockTrackingHistory()


async def search_entity_history(track_id: str, minutes: int = 60) -> dict:
    """Query behavior history for a specific animal."""
    return (await mock_history.search_entity_history(track_id, minutes)).model_dump()


async def get_herd_stats(minutes: int = 60) -> dict:
    """Get aggregate herd statistics over a time window."""
    return (await mock_history.get_herd_stats(minutes)).model_dump()


async def find_by_description(description: str) -> dict:
    """Find animals matching a natural language description."""
    return (await mock_history.find_by_description(description)).model_dump()


async def get_zone_history(zone: str, minutes: int = 120) -> dict:
    """Get zone occupancy history."""
    return (await mock_history.get_zone_history(zone, minutes)).model_dump()


herd_tools = [
    search_entity_history,
    get_herd_stats,
    find_by_description,
    get_zone_history,
]
