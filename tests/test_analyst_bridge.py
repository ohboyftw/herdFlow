"""Tests for AnalystBridge — voice-side cache for video analyst data."""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.reasoning.analyst_bridge import DEFAULT_SUMMARY, AnalystBridge


class FakePacket:
    """Simulate a LiveKit DataPacket object."""

    def __init__(self, data: bytes, topic: str) -> None:
        self.data = data
        self.topic = topic


class TestAnalystBridgeCache:
    def test_initial_summary_is_fallback(self) -> None:
        bridge = AnalystBridge()
        assert "No video feed" in bridge.get_summary()

    def test_default_summary_constant(self) -> None:
        bridge = AnalystBridge()
        assert bridge.get_summary() == DEFAULT_SUMMARY

    def test_update_summary(self) -> None:
        bridge = AnalystBridge()
        bridge._on_summary_received('{"summary": "3 cows standing"}')
        assert "3 cows standing" in bridge.get_summary()

    def test_update_annotations(self) -> None:
        bridge = AnalystBridge()
        bridge._on_annotations_received('{"annotations": {"COW-001": {"label": "brown cow"}}}')
        ann = bridge.get_annotation("COW-001")
        assert ann is not None
        assert ann["label"] == "brown cow"

    def test_get_annotation_missing(self) -> None:
        bridge = AnalystBridge()
        assert bridge.get_annotation("COW-999") is None

    def test_data_received_dispatches_analyst_summary(self) -> None:
        bridge = AnalystBridge()
        bridge._on_data_received(FakePacket(b'{"summary": "dispatched test"}', "analyst_summary"))
        assert "dispatched test" in bridge.get_summary()

    def test_data_received_dispatches_scene_graph(self) -> None:
        bridge = AnalystBridge()
        sg_data = json.dumps(
            {
                "herd_summary": {
                    "total_visible": 5,
                    "standing": 3,
                    "lying": 1,
                    "walking": 1,
                }
            }
        )
        bridge._on_data_received(FakePacket(sg_data.encode(), "scene_graph"))
        summary = bridge.get_summary()
        assert "5 animals visible" in summary
        assert "3 standing" in summary

    def test_data_received_ignores_unknown_topic(self) -> None:
        bridge = AnalystBridge()
        bridge._on_data_received(FakePacket(b"garbage", "unknown_topic"))
        assert bridge.get_summary() == DEFAULT_SUMMARY

    def test_data_received_ignores_no_topic(self) -> None:
        """Packet with no topic attribute should be silently ignored."""

        class NoTopicPacket:
            data = b"hello"

        bridge = AnalystBridge()
        bridge._on_data_received(NoTopicPacket())
        assert bridge.get_summary() == DEFAULT_SUMMARY

    def test_data_received_handles_missing_data(self) -> None:
        """Packet with topic but no data attribute should not crash."""

        class TopicOnlyPacket:
            topic = "analyst_summary"

        bridge = AnalystBridge()
        # getattr returns b"" default, decode succeeds, json.loads("") fails gracefully
        bridge._on_data_received(TopicOnlyPacket())
        assert bridge.get_summary() == DEFAULT_SUMMARY

    def test_data_received_handles_non_utf8(self) -> None:
        """Binary data that isn't valid UTF-8 should be logged and skipped."""
        bridge = AnalystBridge()
        bridge._on_data_received(FakePacket(b"\xff\xfe\x00\x01", "analyst_summary"))
        assert bridge.get_summary() == DEFAULT_SUMMARY

    def test_staleness_detection(self) -> None:
        bridge = AnalystBridge(stale_threshold_s=0.1)
        bridge._on_summary_received('{"summary": "fresh data"}')
        assert not bridge.is_stale()
        bridge._last_update_time = time.monotonic() - 1.0
        assert bridge.is_stale()

    def test_stale_summary_returns_fallback(self) -> None:
        bridge = AnalystBridge(stale_threshold_s=0.1)
        bridge._on_summary_received('{"summary": "old data"}')
        bridge._last_update_time = time.monotonic() - 1.0
        summary = bridge.get_summary()
        assert "unavailable" in summary.lower()


class TestSceneGraphFallback:
    """Tests for the scene_graph → fallback summary path."""

    def test_scene_graph_builds_fallback_when_no_analyst(self) -> None:
        bridge = AnalystBridge()
        sg = json.dumps(
            {
                "herd_summary": {
                    "total_visible": 8,
                    "standing": 5,
                    "lying": 2,
                    "walking": 1,
                }
            }
        )
        bridge._on_scene_graph_received(sg)
        summary = bridge.get_summary()
        assert "8 animals visible" in summary
        assert "5 standing" in summary
        assert "2 lying" in summary
        assert "1 walking" in summary

    def test_scene_graph_ignored_after_analyst_summary(self) -> None:
        bridge = AnalystBridge()
        # Analyst summary arrives first
        bridge._on_summary_received('{"summary": "Gemini says 4 cows"}')
        assert bridge._has_analyst_summary is True

        # Scene graph arrives after — should be ignored
        sg = json.dumps(
            {"herd_summary": {"total_visible": 8, "standing": 5, "lying": 2, "walking": 1}}
        )
        bridge._on_scene_graph_received(sg)
        assert "Gemini says 4 cows" in bridge.get_summary()

    def test_analyst_summary_overwrites_scene_graph_fallback(self) -> None:
        bridge = AnalystBridge()
        # Scene graph arrives first
        sg = json.dumps(
            {"herd_summary": {"total_visible": 3, "standing": 2, "lying": 1, "walking": 0}}
        )
        bridge._on_scene_graph_received(sg)
        assert "3 animals visible" in bridge.get_summary()

        # Analyst summary arrives later — should overwrite
        bridge._on_summary_received('{"summary": "3 cows, one limping"}')
        assert "3 cows, one limping" in bridge.get_summary()

    def test_scene_graph_updates_continue_until_analyst_arrives(self) -> None:
        bridge = AnalystBridge()
        # First scene graph
        sg1 = json.dumps(
            {"herd_summary": {"total_visible": 3, "standing": 2, "lying": 1, "walking": 0}}
        )
        bridge._on_scene_graph_received(sg1)
        assert "3 animals visible" in bridge.get_summary()

        # Second scene graph should NOT update (first one set _last_update_time)
        # This is current behavior — first scene_graph locks further scene_graph updates
        # until analyst_summary arrives (which resets via _has_analyst_summary)
        sg2 = json.dumps(
            {"herd_summary": {"total_visible": 6, "standing": 4, "lying": 1, "walking": 1}}
        )
        bridge._on_scene_graph_received(sg2)
        # After fix: guard is _has_analyst_summary (False), so update SHOULD go through
        # But _last_update_time > 0 is no longer the guard — _has_analyst_summary is.
        # Since no analyst_summary has arrived, this should update.
        assert "6 animals visible" in bridge.get_summary()

    def test_scene_graph_malformed_json(self) -> None:
        bridge = AnalystBridge()
        bridge._on_scene_graph_received("not json at all")
        assert bridge.get_summary() == DEFAULT_SUMMARY

    def test_scene_graph_missing_herd_summary(self) -> None:
        bridge = AnalystBridge()
        bridge._on_scene_graph_received('{"tracked_entities": []}')
        # total_visible defaults to 0, so no summary update
        assert bridge.get_summary() == DEFAULT_SUMMARY

    def test_scene_graph_zero_animals(self) -> None:
        bridge = AnalystBridge()
        sg = json.dumps(
            {"herd_summary": {"total_visible": 0, "standing": 0, "lying": 0, "walking": 0}}
        )
        bridge._on_scene_graph_received(sg)
        # total == 0, so no update
        assert bridge.get_summary() == DEFAULT_SUMMARY


class TestAnnotationDedup:
    """Tests for annotation deduplication."""

    def test_duplicate_annotations_not_updated(self) -> None:
        bridge = AnalystBridge()
        data = '{"annotations": {"COW-001": {"label": "brown cow"}}}'
        bridge._on_annotations_received(data)
        first_update = bridge._last_update_time

        # Same data again — should not update timestamp
        import time

        time.sleep(0.01)
        bridge._on_annotations_received(data)
        assert bridge._last_update_time == first_update

    def test_changed_annotations_are_updated(self) -> None:
        bridge = AnalystBridge()
        bridge._on_annotations_received('{"annotations": {"COW-001": {"label": "brown cow"}}}')
        first_update = bridge._last_update_time

        import time

        time.sleep(0.01)
        bridge._on_annotations_received('{"annotations": {"COW-001": {"label": "spotted cow"}}}')
        assert bridge._last_update_time > first_update

    def test_empty_to_populated_annotations_updated(self) -> None:
        bridge = AnalystBridge()
        assert bridge.latest_annotations == {}
        bridge._on_annotations_received('{"annotations": {"COW-001": {"label": "cow"}}}')
        assert len(bridge.latest_annotations) == 1


class TestAnalystBridgeRequestResponse:
    @pytest.mark.asyncio
    async def test_request_analysis_timeout_returns_fallback(self) -> None:
        bridge = AnalystBridge()
        result = await bridge.request_analysis("what do you see?", timeout_s=0.1)
        assert "timed out" in result.lower() or "unavailable" in result.lower()

    @pytest.mark.asyncio
    async def test_request_response_matching(self) -> None:
        bridge = AnalystBridge()
        bridge._last_update_time = time.monotonic()  # mark as not stale
        mock_room = MagicMock()
        mock_room.local_participant.publish_data = AsyncMock()
        bridge._room = mock_room

        async def _send_response() -> None:
            await asyncio.sleep(0.05)
            for req_id in bridge._pending_requests:
                bridge._on_response_received(
                    f'{{"answer": "brown cow lying", "request_id": "{req_id}"}}'
                )
                break

        asyncio.create_task(_send_response())
        result = await bridge.request_analysis("describe cow 3", timeout_s=1.0)
        assert "brown cow" in result

    @pytest.mark.asyncio
    async def test_stale_bridge_returns_immediate_fallback(self) -> None:
        bridge = AnalystBridge(stale_threshold_s=0.1)
        bridge._last_update_time = time.monotonic() - 1.0
        result = await bridge.request_analysis("what?", timeout_s=5.0)
        assert "unavailable" in result.lower()
