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

_ANNOTATION_PROMPT = (
    "You are annotating a livestock camera feed. The tracking system has detected "
    "these animals with bounding boxes:\n\n{entities_json}\n\n"
    "For each tracked animal, provide a rich annotation based on what you SEE in the image. "
    "Return a JSON array with one object per animal:\n"
    '[{{"track_id": "COW-001", "label": "brown cow, standing calmly", '
    '"behavior": "standing", "health_notes": "appears healthy", '
    '"confidence": 0.9}}]\n\n'
    "Guidelines:\n"
    "- Match track_ids from the tracking data\n"
    "- 'label' = short visual description (color, size, posture)\n"
    "- 'behavior' = one of: standing, lying, walking, feeding, drinking, running\n"
    "- 'health_notes' = any visible health concerns or 'appears healthy'\n"
    "- If you can't see an animal clearly, set confidence low\n"
    "- Return ONLY the JSON array, no other text"
)

_ON_DEMAND_PROMPT = (
    "You are a veterinary visual analyst examining a livestock camera feed. "
    "A farmer is asking: {question}\n\n"
    "Analyze the image carefully. Reference specific animals by their track ID "
    "from the scene data when possible. Be detailed but concise.\n\n"
    "Scene tracking data:\n{scene_json}"
)

_ZONE_DETECTION_PROMPT = (
    "You are analyzing a livestock camera feed to identify functional zones. "
    "Look at this frame and identify distinct areas like:\n"
    "- feeding area (where feed troughs/hay are visible)\n"
    "- water trough (where water containers are visible)\n"
    "- resting area (where animals typically lie down)\n"
    "- open area / paddock\n"
    "- gate / entry area\n\n"
    "For each zone you can identify, return a JSON array with objects like:\n"
    '[{"name": "feeding area", "x1": 0.1, "y1": 0.3, "x2": 0.4, "y2": 0.8, "confidence": 0.85}]\n\n'
    "Coordinates are normalized 0-1 (x1,y1 = top-left, x2,y2 = bottom-right).\n"
    "Only include zones you can actually see in the image. "
    "If you can't identify specific zones, return an empty array: []\n"
    "Return ONLY the JSON array, no other text."
)


class VideoAnalyst:
    """Async video analysis — background summaries + on-demand deep analysis."""

    DEFAULT_SUMMARY = "No video feed available yet."

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
        self.latest_summary: str = self.DEFAULT_SUMMARY
        self._analyzing: bool = False
        self._last_analysis: str = ""
        self._client = None  # Lazy init
        self.detected_zones: list[dict] = []  # populated by detect_zones()
        self._zones_detected: bool = False
        self.entity_annotations: dict[str, dict] = {}  # track_id → annotation

    def _get_client(self):  # type: ignore[no-untyped-def]
        """Lazy-init the genai client."""
        if self._client is None:
            from google import genai  # type: ignore[attr-defined]

            self._client = genai.Client()
        return self._client

    def update(self, frame: np.ndarray | None, scene_graph: SceneGraph) -> None:
        """Update latest frame and scene graph. Called by perception_loop."""
        self.latest_frame = frame
        self.latest_scene_graph = scene_graph

    def get_summary(self) -> str:
        """Return the latest summary (instant, no API call)."""
        return self.latest_summary

    def format_scene_graph(self, sg: SceneGraph) -> str:
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
        entities = [f"{e.track_id}: {e.behavior} in {e.zone}" for e in sg.tracked_entities]
        if entities:
            parts.append(f"Entities: {'; '.join(entities)}")
        return " ".join(parts)

    def _encode_frame(self, frame: np.ndarray, quality: int = 40) -> bytes:
        """Encode numpy frame as JPEG bytes, resized to 640x360."""
        img = Image.fromarray(frame).resize((640, 360), Image.LANCZOS)  # type: ignore[attr-defined]
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    async def detect_zones(self) -> list[dict]:
        """Detect functional zones from the current frame via Gemini Flash.

        Runs once on the first available frame. Returns list of zone dicts
        with name, x1, y1, x2, y2, confidence — published via data channel.
        """
        if self._zones_detected or self.latest_frame is None:
            return self.detected_zones

        try:
            import json

            from google.genai import types

            jpeg = self._encode_frame(self.latest_frame, quality=70)
            logger.info("[ANALYST] Detecting zones from first frame...")

            response = await self._get_client().aio.models.generate_content(
                model=self.background_model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                            types.Part.from_text(text=_ZONE_DETECTION_PROMPT),
                        ]
                    )
                ],
            )
            text = self._strip_code_fences(response.text or "[]")

            self.detected_zones = json.loads(text)
            self._zones_detected = True
            logger.info(
                "[ANALYST] Detected %d zones: %s",
                len(self.detected_zones),
                [z["name"] for z in self.detected_zones],
            )
        except Exception:
            logger.exception("[ANALYST] Zone detection failed, using empty zones")
            self.detected_zones = []
            self._zones_detected = True

        return self.detected_zones

    def _strip_code_fences(self, text: str) -> str:
        """Strip markdown code fences from LLM response."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        return text

    async def annotate_entities(self) -> dict[str, dict]:
        """Annotate tracked entities with rich Gemini visual descriptions.

        Returns dict of track_id → {label, behavior, health_notes, confidence}.
        Called during background loop alongside summary.
        """
        if self.latest_frame is None or self.latest_scene_graph is None:
            return self.entity_annotations

        entities = self.latest_scene_graph.tracked_entities
        if not entities:
            return self.entity_annotations

        try:
            import json

            from google.genai import types

            # Build entity list for the prompt
            entity_data = [
                {
                    "track_id": e.track_id,
                    "bbox": list(e.bbox),
                    "behavior": e.behavior,
                    "zone": e.zone,
                    "isolation_score": e.isolation_score,
                }
                for e in entities
            ]

            jpeg = self._encode_frame(self.latest_frame, quality=60)
            prompt = _ANNOTATION_PROMPT.format(entities_json=json.dumps(entity_data, indent=2))

            response = await asyncio.wait_for(
                self._get_client().aio.models.generate_content(
                    model=self.background_model,
                    contents=[
                        types.Content(
                            parts=[
                                types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                                types.Part.from_text(text=prompt),
                            ]
                        )
                    ],
                ),
                timeout=30.0,
            )

            text = self._strip_code_fences(response.text or "[]")
            annotations = json.loads(text)

            # Update cache keyed by track_id
            for ann in annotations:
                tid = ann.get("track_id", "")
                if tid:
                    self.entity_annotations[tid] = ann

            logger.info(
                "[ANALYST] Annotated %d entities: %s",
                len(annotations),
                [(a.get("track_id"), a.get("label", "")[:30]) for a in annotations],
            )

        except Exception:
            logger.exception("[ANALYST] Entity annotation failed")

        return self.entity_annotations

    def get_annotation(self, track_id: str) -> dict | None:
        """Get cached Gemini annotation for a track_id, or None."""
        return self.entity_annotations.get(track_id)

    async def run_background_loop(self) -> None:
        """Background task: summarize the scene every N seconds."""
        logger.info(
            "[ANALYST] Background loop started (every %.0fs, model=%s)",
            self.summary_interval_s,
            self.background_model,
        )
        while True:
            await asyncio.sleep(self.summary_interval_s)
            logger.info(
                "[ANALYST] Background tick — frame=%s, sg=%s",
                self.latest_frame is not None,
                self.latest_scene_graph is not None,
            )
            try:
                if self.latest_frame is None:
                    if self.latest_scene_graph is not None:
                        self.latest_summary = self.format_scene_graph(self.latest_scene_graph)
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

                logger.info(
                    "[ANALYST] Calling %s with %d byte JPEG...", self.background_model, len(jpeg)
                )
                response = await asyncio.wait_for(
                    self._get_client().aio.models.generate_content(
                        model=self.background_model,
                        contents=[
                            types.Content(
                                parts=[
                                    types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                                    types.Part.from_text(text=prompt),
                                ]
                            )
                        ],
                    ),
                    timeout=25.0,
                )
                fallback = (
                    self.format_scene_graph(self.latest_scene_graph)
                    if self.latest_scene_graph is not None
                    else "No scene data available."
                )
                self.latest_summary = response.text or fallback
                logger.info("[ANALYST] Background summary: %s", self.latest_summary[:100])

                # Also annotate individual entities with rich descriptions
                await self.annotate_entities()

            except Exception:
                logger.exception("[ANALYST] Background summary failed, using fallback")
                if self.latest_scene_graph is not None:
                    self.latest_summary = self.format_scene_graph(self.latest_scene_graph)

    async def analyze(self, question: str) -> str:
        """On-demand deep analysis of current frame via Gemini 3 Pro."""
        if self.latest_frame is None:
            fallback = ""
            if self.latest_scene_graph is not None:
                fallback = self.format_scene_graph(self.latest_scene_graph)
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
            prompt = _ON_DEMAND_PROMPT.format(question=question, scene_json=scene_json)

            from google.genai import types

            response = await self._get_client().aio.models.generate_content(
                model=self.on_demand_model,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
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
                    f"{self.format_scene_graph(self.latest_scene_graph)}"
                )
            return "Visual analysis failed and no scene data available."
        finally:
            self._analyzing = False
