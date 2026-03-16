"""Voice-side bridge to video process's analyst via LiveKit data channels.

Caches latest summary and annotations from the video process.
Handles request/response for on-demand analyze_frame calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

logger = logging.getLogger("herdflow.analyst_bridge")


class AnalystBridge:
    """Cache + request/response bridge for analyst data from video process."""

    def __init__(self, stale_threshold_s: float = 60.0) -> None:
        self.latest_summary: str = "No video feed available yet."
        self.latest_annotations: dict[str, dict] = {}
        self._last_update_time: float = 0.0
        self._stale_threshold_s = stale_threshold_s
        self._pending_requests: dict[str, asyncio.Future[str]] = {}
        self._room = None

    async def start(self, room) -> None:
        """Subscribe to analyst data channels from video process."""
        self._room = room
        room.on("data_received", self._on_data_received)
        logger.info("[BRIDGE] AnalystBridge started, listening for analyst channels")

    def _on_data_received(self, packet) -> None:
        """Handle LiveKit DataPacket — dispatch by topic."""
        topic = getattr(packet, "topic", None)
        data = getattr(packet, "data", b"")
        if not topic:
            return
        if topic == "analyst_summary":
            self._on_summary_received(data.decode("utf-8"))
        elif topic == "analyst_annotations":
            self._on_annotations_received(data.decode("utf-8"))
        elif topic == "analyst_response":
            self._on_response_received(data.decode("utf-8"))
        elif topic == "scene_graph":
            self._on_scene_graph_received(data.decode("utf-8"))

    def _on_summary_received(self, data: str) -> None:
        try:
            parsed = json.loads(data)
            self.latest_summary = parsed.get("summary", self.latest_summary)
            self._last_update_time = time.monotonic()
            logger.debug("[BRIDGE] Summary updated: %s", self.latest_summary[:80])
        except (json.JSONDecodeError, KeyError):
            logger.warning("[BRIDGE] Failed to parse analyst_summary")

    def _on_annotations_received(self, data: str) -> None:
        try:
            parsed = json.loads(data)
            self.latest_annotations = parsed.get("annotations", {})
            self._last_update_time = time.monotonic()
            logger.debug(
                "[BRIDGE] Annotations updated: %d entities",
                len(self.latest_annotations),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("[BRIDGE] Failed to parse analyst_annotations")

    def _on_scene_graph_received(self, data: str) -> None:
        """Build a fallback summary from scene_graph when no analyst_summary yet."""
        if self._last_update_time > 0:
            return  # already have analyst data, don't overwrite
        try:
            parsed = json.loads(data)
            hs = parsed.get("herd_summary", {})
            total = hs.get("total_visible", 0)
            if total > 0:
                self.latest_summary = (
                    f"{total} animals visible: "
                    f"{hs.get('standing', 0)} standing, "
                    f"{hs.get('lying', 0)} lying, "
                    f"{hs.get('walking', 0)} walking."
                )
                self._last_update_time = time.monotonic()
                logger.info("[BRIDGE] Scene graph fallback: %s", self.latest_summary)
        except (json.JSONDecodeError, KeyError):
            pass

    def _on_response_received(self, data: str) -> None:
        try:
            parsed = json.loads(data)
            request_id = parsed.get("request_id", "")
            answer = parsed.get("answer", "")
            if request_id in self._pending_requests:
                self._pending_requests[request_id].set_result(answer)
                logger.info("[BRIDGE] Response received for %s", request_id)
        except (json.JSONDecodeError, KeyError):
            logger.warning("[BRIDGE] Failed to parse analyst_response")

    def is_stale(self) -> bool:
        if self._last_update_time == 0.0:
            return True
        return (time.monotonic() - self._last_update_time) > self._stale_threshold_s

    def get_summary(self) -> str:
        if self.is_stale() and self._last_update_time > 0:
            return "Video feed unavailable — no recent data."
        return self.latest_summary

    def get_annotation(self, track_id: str) -> dict | None:
        return self.latest_annotations.get(track_id)

    async def request_analysis(self, question: str, timeout_s: float = 30.0) -> str:
        if self.is_stale():
            return "Video feed unavailable — cannot analyze frame."

        if self._room is None:
            return "Video feed unavailable — not connected."

        request_id = uuid.uuid4().hex[:8]
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            payload = json.dumps({"question": question, "request_id": request_id})
            await self._room.local_participant.publish_data(
                payload.encode(), topic="analyst_request"
            )
            logger.info(
                "[BRIDGE] Sent analyst_request %s: %s", request_id, question[:50]
            )

            result = await asyncio.wait_for(future, timeout=timeout_s)
            return result
        except TimeoutError:
            logger.warning("[BRIDGE] analyst_request %s timed out", request_id)
            return "Visual analysis timed out — video feed may be unavailable."
        finally:
            self._pending_requests.pop(request_id, None)
