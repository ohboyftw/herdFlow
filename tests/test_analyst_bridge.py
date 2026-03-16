"""Tests for AnalystBridge — voice-side cache for video analyst data."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.reasoning.analyst_bridge import AnalystBridge


class TestAnalystBridgeCache:
    def test_initial_summary_is_fallback(self) -> None:
        bridge = AnalystBridge()
        assert "No video feed" in bridge.get_summary()

    def test_update_summary(self) -> None:
        bridge = AnalystBridge()
        bridge._on_summary_received('{"summary": "3 cows standing"}')
        assert "3 cows standing" in bridge.get_summary()

    def test_update_annotations(self) -> None:
        bridge = AnalystBridge()
        bridge._on_annotations_received(
            '{"annotations": {"COW-001": {"label": "brown cow"}}}'
        )
        ann = bridge.get_annotation("COW-001")
        assert ann is not None
        assert ann["label"] == "brown cow"

    def test_get_annotation_missing(self) -> None:
        bridge = AnalystBridge()
        assert bridge.get_annotation("COW-999") is None

    def test_data_received_dispatches_by_topic(self) -> None:
        bridge = AnalystBridge()

        # Simulate a LiveKit DataPacket-like object
        class FakePacket:
            def __init__(self, data: bytes, topic: str) -> None:
                self.data = data
                self.topic = topic

        bridge._on_data_received(
            FakePacket(b'{"summary": "dispatched test"}', "analyst_summary")
        )
        assert "dispatched test" in bridge.get_summary()

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
