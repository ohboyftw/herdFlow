from __future__ import annotations

import pytest

from agent.reasoning.tools import MockTrackingHistory


@pytest.mark.asyncio
async def test_mock_search_entity_history():
    history = MockTrackingHistory()
    result = await history.search_entity_history("COW-003", 60)
    assert result.track_id == "COW-003"
    assert result.current_behavior == "lying"
    assert len(result.records) > 0


@pytest.mark.asyncio
async def test_mock_get_herd_stats():
    history = MockTrackingHistory()
    result = await history.get_herd_stats(60)
    assert result.total_animals == 8
    assert "COW-003" in result.not_fed


@pytest.mark.asyncio
async def test_mock_find_by_description():
    history = MockTrackingHistory()
    result = await history.find_by_description("the brown cow near the fence")
    assert len(result.matches) > 0


@pytest.mark.asyncio
async def test_mock_get_zone_history():
    history = MockTrackingHistory()
    result = await history.get_zone_history("water_trough", 120)
    assert result.zone == "water_trough"
    assert len(result.visits) > 0
    assert "COW-003" in result.animals_not_visited
