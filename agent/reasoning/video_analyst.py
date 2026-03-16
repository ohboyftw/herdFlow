"""Async video analyst — background summaries + on-demand deep analysis.

Replaces direct video-to-Gemini-Live (which caused 1007 errors) with
standard Gemini API calls. Two modes:
- Background: Gemini 3 Flash every 30s for scene summaries
- On-demand: Gemini 3 Pro when farmer asks a visual question
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from agent.models import SceneGraph

logger = logging.getLogger("herdflow.video_analyst")

_BACKGROUND_PROMPT = (
    "You are a livestock camera analyst. Describe what you see in this frame. "
    "Focus on: number of animals, their posture (standing/lying/walking), "
    "any unusual behavior, and spatial distribution. Be concise (2-3 sentences).\n\n"
    "Scene tracking data:\n{scene_json}"
)

_ON_DEMAND_PROMPT = (
    "You are a veterinary visual analyst examining a livestock camera feed. "
    "A farmer is asking: {question}\n\n"
    "Analyze the image carefully. Reference specific animals by their track ID "
    "from the scene data when possible. Be detailed but concise.\n\n"
    "Scene tracking data:\n{scene_json}"
)


class VideoAnalyst:
    """Async video analysis — background summaries + on-demand deep analysis."""

    def __init__(
        self,
        background_model: str = "gemini-3-flash-preview",
        on_demand_model: str = "gemini-3-pro-preview",
        summary_interval_s: float = 30.0,
    ) -> None:
        self.background_model = background_model
        self.on_demand_model = on_demand_model
        self.summary_interval_s = summary_interval_s

        self.latest_frame: np.ndarray | None = None
        self.latest_scene_graph: SceneGraph | None = None
        self.latest_summary: str = "No video feed available yet."
        self._analyzing: bool = False
        self._last_analysis: str = ""
        self._client = None  # Lazy init

    def _get_client(self):
        """Lazy-init the genai client."""
        if self._client is None:
            from google import genai
            self._client = genai.Client()
        return self._client

    def update(self, frame: np.ndarray | None, scene_graph: SceneGraph) -> None:
        """Update latest frame and scene graph. Called by perception_loop."""
        self.latest_frame = frame
        self.latest_scene_graph = scene_graph

    def get_summary(self) -> str:
        """Return the latest summary (instant, no API call)."""
        return self.latest_summary

    def _format_scene_graph(self, sg: SceneGraph) -> str:
        """Format scene graph as human-readable text fallback."""
        hs = sg.herd_summary
        parts = [
            f"{hs.total_visible} animals visible:",
            f"{hs.standing} standing, {hs.lying} lying, {hs.walking} walking,",
            f"{hs.feeding} feeding, {hs.drinking} drinking.",
        ]
        if sg.active_alerts:
            alerts = [f"{a.type}:{a.entity_track_id}" for a in sg.active_alerts]
            parts.append(f"Active alerts: {', '.join(alerts)}.")
        entities = [
            f"{e.track_id}: {e.behavior} in {e.zone}"
            for e in sg.tracked_entities
        ]
        if entities:
            parts.append(f"Entities: {'; '.join(entities)}")
        return " ".join(parts)

    def _encode_frame(self, frame: np.ndarray, quality: int = 40) -> bytes:
        """Encode numpy frame as JPEG bytes, resized to 640x360."""
        img = Image.fromarray(frame).resize((640, 360), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    async def run_background_loop(self) -> None:
        """Background task: summarize the scene every N seconds."""
        logger.info(
            "[ANALYST] Background loop started (every %.0fs, model=%s)",
            self.summary_interval_s,
            self.background_model,
        )
        while True:
            await asyncio.sleep(self.summary_interval_s)
            logger.info("[ANALYST] Background tick — frame=%s, sg=%s",
                        self.latest_frame is not None,
                        self.latest_scene_graph is not None)
            try:
                if self.latest_frame is None:
                    if self.latest_scene_graph is not None:
                        self.latest_summary = self._format_scene_graph(
                            self.latest_scene_graph
                        )
                    else:
                        self.latest_summary = "No video feed available."
                    continue

                jpeg = self._encode_frame(self.latest_frame, quality=40)
                scene_json = (
                    self.latest_scene_graph.model_dump_json(indent=2)
                    if self.latest_scene_graph
                    else "{}"
                )
                prompt = _BACKGROUND_PROMPT.format(scene_json=scene_json)

                from google.genai import types

                logger.info("[ANALYST] Calling %s with %d byte JPEG...", self.background_model, len(jpeg))
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._get_client().models.generate_content,
                        model=self.background_model,
                        contents=[
                            types.Content(
                                parts=[
                                    types.Part.from_bytes(
                                        data=jpeg, mime_type="image/jpeg"
                                    ),
                                    types.Part.from_text(text=prompt),
                                ]
                            )
                        ],
                    ),
                    timeout=25.0,
                )
                self.latest_summary = response.text or self._format_scene_graph(
                    self.latest_scene_graph
                )
                logger.info("[ANALYST] Background summary: %s", self.latest_summary[:100])

            except Exception:
                logger.exception("[ANALYST] Background summary failed, using fallback")
                if self.latest_scene_graph is not None:
                    self.latest_summary = self._format_scene_graph(
                        self.latest_scene_graph
                    )

    async def analyze(self, question: str) -> str:
        """On-demand deep analysis of current frame via Gemini 3 Pro."""
        if self.latest_frame is None:
            fallback = ""
            if self.latest_scene_graph is not None:
                fallback = self._format_scene_graph(self.latest_scene_graph)
            return f"No video feed available. Scene data: {fallback}"

        if self._analyzing:
            return (
                f"Analysis already in progress. Last result: {self._last_analysis}"
                if self._last_analysis
                else "Analysis in progress, please wait."
            )

        self._analyzing = True
        try:
            jpeg = self._encode_frame(self.latest_frame, quality=80)
            scene_json = (
                self.latest_scene_graph.model_dump_json(indent=2)
                if self.latest_scene_graph
                else "{}"
            )
            prompt = _ON_DEMAND_PROMPT.format(
                question=question, scene_json=scene_json
            )

            from google.genai import types

            response = await asyncio.to_thread(
                self._get_client().models.generate_content,
                model=self.on_demand_model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_image(
                                image=types.Blob(
                                    data=jpeg, mime_type="image/jpeg"
                                )
                            ),
                            types.Part.from_text(text=prompt),
                        ]
                    )
                ],
            )
            self._last_analysis = response.text or "Analysis returned empty."
            logger.info("[ANALYST] On-demand: %s", self._last_analysis[:150])
            return self._last_analysis

        except Exception:
            logger.exception("[ANALYST] On-demand analysis failed")
            if self.latest_scene_graph is not None:
                return (
                    f"Visual analysis failed. Scene data: "
                    f"{self._format_scene_graph(self.latest_scene_graph)}"
                )
            return "Visual analysis failed and no scene data available."
        finally:
            self._analyzing = False
