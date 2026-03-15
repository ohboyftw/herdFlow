"""Tests for SQLite tracking history."""

from __future__ import annotations

import pytest

from agent.models import EntityHistory, HerdStats, ZoneHistory
from agent.storage.history import TrackingHistory


@pytest.mark.asyncio
async def test_record_and_query_entity_history():
    history = TrackingHistory(":memory:")
    await history.initialize()
    await history.record_behavior("COW-003", "lying", "rest_area", 4320.0)
    result = await history.search_entity_history("COW-003", minutes=60)
    assert isinstance(result, EntityHistory)
    assert result.track_id == "COW-003"
    assert len(result.records) >= 1


@pytest.mark.asyncio
async def test_herd_stats():
    history = TrackingHistory(":memory:")
    await history.initialize()
    await history.record_behavior("COW-001", "feeding", "feed_area", 600.0)
    await history.record_behavior("COW-002", "standing", "rest_area", 300.0)
    result = await history.get_herd_stats(minutes=60)
    assert isinstance(result, HerdStats)
    assert result.total_animals >= 2


@pytest.mark.asyncio
async def test_zone_history():
    history = TrackingHistory(":memory:")
    await history.initialize()
    await history.record_zone_visit("COW-001", "water_trough", 120.0)
    result = await history.get_zone_history("water_trough", minutes=60)
    assert isinstance(result, ZoneHistory)
    assert result.zone == "water_trough"
    assert len(result.visits) >= 1
