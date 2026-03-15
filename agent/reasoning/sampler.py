"""Adaptive frame sampler — event-driven context injection for Gemini.

Controls WHEN to inject scene graph context into the Gemini Live API session.
Consumes from an asyncio.Queue fed by the perception loop. Does NOT control
the video track (Gemini receives continuous video via LiveKit plugin).

Reference: docs/superpowers/specs/2026-03-15-herdflow-mvp-design.md Section 6.
"""

from __future__ import annotations

import asyncio
import logging
import time

from agent.models import GeminiContext, SceneDelta, SceneGraph

logger = logging.getLogger(__name__)


class AdaptiveFrameSampler:
    """Rate-limited, event-driven sampler for Gemini context injection.

    Trigger priority:
    1. CRITICAL: user_speaking — always send (farmer needs latest context)
    2. HIGH: significant delta (new entity, zone crossing, alert, behavior change)
    3. SUPPRESSED: no significant delta — zero cost

    Rate limits prevent flooding Gemini during rapid scene changes.
    """

    def __init__(self, max_fps: float = 2.0, min_interval_ms: int = 200) -> None:
        self.max_fps = max_fps
        self.min_interval_ms = min_interval_ms
        self._min_interval_s = min_interval_ms / 1000.0
        self._max_interval_s = 1.0 / max_fps if max_fps > 0 else float("inf")

    def should_send(
        self,
        delta: SceneDelta,
        *,
        user_speaking: bool = False,
        elapsed_ms: float = 0,
    ) -> bool:
        """Decide whether to inject context for this frame.

        Args:
            delta: Scene changes since last injection.
            user_speaking: Whether the farmer is currently speaking.
            elapsed_ms: Milliseconds since last injection.

        Returns:
            True if context should be injected into Gemini session.
        """
        # Priority 1: User speaking always gets latest context
        if user_speaking:
            return True

        # Priority 2: Significant delta + rate limit satisfied
        if delta.is_significant:
            return elapsed_ms >= self.min_interval_ms and elapsed_ms >= 1000 / self.max_fps

        # Priority 3: Quiet scene — no injection needed
        return False

    async def run(
        self,
        scene_queue: asyncio.Queue[tuple[SceneGraph, SceneDelta]],
        inject_callback: object,
    ) -> None:
        """Consume scene graphs from queue, inject context when appropriate.

        Args:
            scene_queue: Queue of (SceneGraph, SceneDelta) tuples from perception loop.
            inject_callback: Async callable to inject context into Gemini session.
        """
        last_send_time = 0.0

        while True:
            sg, delta = await scene_queue.get()
            now = time.monotonic()
            elapsed_ms = (now - last_send_time) * 1000

            # TODO: wire user_speaking from VAD state
            if self.should_send(delta, user_speaking=False, elapsed_ms=elapsed_ms):
                ctx = GeminiContext(
                    scene_graph=sg,
                    recent_alerts=sg.active_alerts[:5],
                    history_snapshots=[],  # populated by history manager
                )
                await inject_callback(ctx.to_prompt_injection())  # type: ignore[operator]
                last_send_time = now
                logger.debug("Injected context (delta significant, elapsed=%.0fms)", elapsed_ms)
