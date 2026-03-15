"""Tests for SceneGraphBuilder."""

from __future__ import annotations

import pytest

from agent.config import settings
from agent.models import SceneDelta, SceneGraph
from agent.perception.detector import MockDetector
from agent.perception.scene_graph import SceneGraphBuilder
from agent.perception.tracker import Tracker
from tests.conftest import sample_frame


class NullAlertEngine:
    """Stub alert engine for testing SGB without depending on alerts/rules.py."""

    def evaluate(self, entities: list) -> list:
        return []


@pytest.mark.asyncio
async def test_scene_graph_builder_produces_valid_graph():
    builder = SceneGraphBuilder(
        detector=MockDetector(),
        tracker=Tracker(),
        zone_config=settings.zone_config,
        alert_engine=NullAlertEngine(),
    )
    frame = sample_frame()
    sg = await builder.process_frame(frame, frame_id=1)
    assert isinstance(sg, SceneGraph)
    assert sg.frame_id == 1
    assert sg.herd_summary.total_visible == len(sg.tracked_entities)


@pytest.mark.asyncio
async def test_scene_graph_delta_first_frame_significant():
    builder = SceneGraphBuilder(
        detector=MockDetector(),
        tracker=Tracker(),
        zone_config=settings.zone_config,
        alert_engine=NullAlertEngine(),
    )
    frame = sample_frame()
    sg = await builder.process_frame(frame, frame_id=1)
    delta = builder.get_delta(None, sg)
    assert isinstance(delta, SceneDelta)
    assert delta.is_significant
