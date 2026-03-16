"""Tests for VideoAnalyst — async video analysis via Gemini API."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from agent.models import HerdSummary, SceneGraph
from agent.reasoning.video_analyst import VideoAnalyst


def _make_scene_graph(n_entities: int = 3) -> SceneGraph:
    """Create a minimal SceneGraph for testing."""
    return SceneGraph(
        frame_id=1,
        timestamp=datetime(2026, 3, 16, 12, 0, 0, tzinfo=UTC),
        tracked_entities=[],
        active_alerts=[],
        herd_summary=HerdSummary(
            total_visible=n_entities,
            standing=n_entities,
            lying=0,
            walking=0,
            feeding=0,
            drinking=0,
        ),
        zones={},
    )


class TestVideoAnalystUpdate:
    def test_update_stores_frame_and_scene_graph(self) -> None:
        analyst = VideoAnalyst()
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        sg = _make_scene_graph(5)
        analyst.update(frame, sg)
        assert analyst.latest_frame is not None
        assert analyst.latest_scene_graph is not None
        assert analyst.latest_scene_graph.herd_summary.total_visible == 5

    def test_update_with_none_frame(self) -> None:
        analyst = VideoAnalyst()
        analyst.update(None, _make_scene_graph())
        assert analyst.latest_frame is None


class TestVideoAnalystSummary:
    def test_get_summary_before_any_update(self) -> None:
        analyst = VideoAnalyst()
        summary = analyst.get_summary()
        assert "No video feed" in summary

    def test_get_summary_before_background_loop_runs(self) -> None:
        """Before background loop runs, summary is the initial default."""
        analyst = VideoAnalyst()
        analyst.update(np.zeros((360, 640, 3), dtype=np.uint8), _make_scene_graph(4))
        summary = analyst.get_summary()
        assert "No video feed" in summary

    def test_format_scene_graph_fallback(self) -> None:
        analyst = VideoAnalyst()
        sg = _make_scene_graph(6)
        text = analyst.format_scene_graph(sg)
        assert "6" in text
        assert "standing" in text.lower()


class TestVideoAnalystAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_no_frame_returns_fallback(self) -> None:
        analyst = VideoAnalyst()
        analyst.update(None, _make_scene_graph(3))
        result = await analyst.analyze("What do you see?")
        assert "No video feed" in result or "scene data" in result.lower()

    @pytest.mark.asyncio
    async def test_analyze_sets_analyzing_flag(self) -> None:
        """Verify the _analyzing guard flag is managed."""
        analyst = VideoAnalyst()
        analyst.update(np.zeros((360, 640, 3), dtype=np.uint8), _make_scene_graph())
        assert not analyst._analyzing


class TestVideoAnalystEncoding:
    def test_encode_frame_returns_bytes(self) -> None:
        analyst = VideoAnalyst()
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        jpeg = analyst._encode_frame(frame, quality=40)
        assert isinstance(jpeg, bytes)
        assert len(jpeg) > 0
        assert jpeg[:2] == b"\xff\xd8"

    def test_encode_frame_resizes(self) -> None:
        analyst = VideoAnalyst()
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        jpeg_low = analyst._encode_frame(frame, quality=40)
        jpeg_high = analyst._encode_frame(frame, quality=80)
        assert len(jpeg_high) > len(jpeg_low)
