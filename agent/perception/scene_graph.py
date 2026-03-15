"""SceneGraphBuilder — orchestrates detection → tracking → behavior → alerts → graph."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime

from agent.models import (
    Alert,
    HerdSummary,
    SceneDelta,
    SceneGraph,
    TrackedEntity,
    TrackedEntityModel,
    ZoneOccupancy,
)

logger = logging.getLogger(__name__)


class SceneGraphBuilder:
    """Orchestrates the full per-frame pipeline and maintains scene state."""

    def __init__(self, detector, tracker, zone_config: dict, alert_engine) -> None:
        self.detector = detector
        self.tracker = tracker
        self.zone_config = zone_config
        self.alert_engine = alert_engine
        self._prev_graph: SceneGraph | None = None
        self._prev_entities: dict[str, TrackedEntity] = {}

    async def process_frame(self, frame, frame_id: int) -> SceneGraph:
        """Full pipeline: detect → track → classify → alert → build graph."""
        # Detect (async preferred, fall back to sync mock)
        if hasattr(self.detector, "detect") and asyncio.iscoroutinefunction(self.detector.detect):
            detections = await self.detector.detect(frame)
        else:
            detections = self.detector.detect_sync(frame)

        # Track
        entities = self.tracker.update(detections, frame_id)

        # Order matters: zone → behavior (depends on zone) → temporal (depends on both)
        for entity in entities:
            self._assign_zone(entity)
            self._classify_behavior(entity)
            self._accumulate_temporal_state(entity)

        for entity in entities:
            self._compute_isolation(entity, entities)

        # Alert evaluation
        alerts: list[Alert] = self.alert_engine.evaluate(entities)
        if alerts:
            logger.info("[B4->B5] alerts fired: %s", [a.key for a in alerts])

        # Build SceneGraph
        sg = self._build_graph(entities, alerts, frame_id)
        behaviors = {e.behavior for e in entities}
        logger.debug(
            "[B3->B6] frame=%d entities=%d behaviors=%s alerts=%d",
            frame_id,
            len(entities),
            behaviors,
            len(alerts),
        )
        self._prev_entities = {e.track_id: e for e in entities}
        return sg

    def _accumulate_temporal_state(self, entity: TrackedEntity) -> None:
        """Carry forward temporal fields from previous frame's entity state."""
        prev = self._prev_entities.get(entity.track_id)
        if prev is None:
            return

        # Assume ~0.5s per frame (2 FPS pipeline)
        dt = 0.5

        # Zone dwell: accumulate if same zone, reset on change
        if entity.zone == prev.zone:
            entity.zone_dwell_s = prev.zone_dwell_s + dt
        else:
            entity.zone_dwell_s = 0.0

        # Behavior duration: accumulate if same behavior, reset on change
        if entity.behavior == prev.behavior:
            entity.behavior_duration_s = prev.behavior_duration_s + dt
        else:
            entity.behavior_duration_s = 0.0

        # Last feed visit: track time since entity was last in feed_area
        if entity.zone == "feed_area":
            entity.last_feed_visit_s = 0.0
        else:
            entity.last_feed_visit_s = prev.last_feed_visit_s + dt

    def _classify_behavior(self, entity: TrackedEntity) -> None:
        """Priority chain: walking → feeding/drinking → lying → standing."""
        speed = math.sqrt(entity.velocity[0] ** 2 + entity.velocity[1] ** 2)

        if speed > 5.0:
            entity.behavior = "walking"
        elif entity.zone == "feed_area" and entity.zone_dwell_s >= 10.0:
            entity.behavior = "feeding"
        elif entity.zone == "water_trough" and entity.zone_dwell_s >= 10.0:
            entity.behavior = "drinking"
        elif entity.bbox_aspect_ratio > 1.5:
            entity.behavior = "lying"
        else:
            entity.behavior = "standing"

    def _assign_zone(self, entity: TrackedEntity) -> None:
        """Assign entity to a zone based on centroid position (normalized coords)."""
        cx, cy = entity.centroid
        # Normalize to 0-1 range (assuming 1280x720 frame)
        nx = cx / 1280.0
        ny = cy / 720.0

        for zone_name, bounds in self.zone_config.items():
            if bounds["x1"] <= nx <= bounds["x2"] and bounds["y1"] <= ny <= bounds["y2"]:
                entity.zone = zone_name
                return
        entity.zone = "unknown"

    def _compute_isolation(self, entity: TrackedEntity, all_entities: list[TrackedEntity]) -> None:
        """Compute isolation score: 0 = tightly grouped, 1 = fully isolated."""
        if len(all_entities) <= 1:
            entity.isolation_score = 0.0
            return

        min_dist = float("inf")
        for other in all_entities:
            if other.track_id == entity.track_id:
                continue
            dx = entity.centroid[0] - other.centroid[0]
            dy = entity.centroid[1] - other.centroid[1]
            dist = math.sqrt(dx * dx + dy * dy)
            min_dist = min(min_dist, dist)

        # Normalize: 200px = isolation score 1.0
        entity.isolation_score = min(1.0, min_dist / 200.0)

    def _build_graph(
        self, entities: list[TrackedEntity], alerts: list[Alert], frame_id: int
    ) -> SceneGraph:
        """Build SceneGraph from entities and alerts."""
        behavior_counts: dict[str, int] = {
            "standing": 0,
            "lying": 0,
            "walking": 0,
            "feeding": 0,
            "drinking": 0,
        }
        zone_counts: dict[str, int] = {}
        tracked_models: list[TrackedEntityModel] = []

        for e in entities:
            behavior_counts[e.behavior] = behavior_counts.get(e.behavior, 0) + 1
            zone_counts[e.zone] = zone_counts.get(e.zone, 0) + 1
            tracked_models.append(
                TrackedEntityModel(
                    track_id=e.track_id,
                    class_name=e.class_name,
                    confidence=e.confidence,
                    bbox=list(e.bbox),
                    centroid=list(e.centroid),
                    velocity=list(e.velocity),
                    behavior=e.behavior,
                    behavior_duration_s=e.behavior_duration_s,
                    zone=e.zone,
                    last_feed_visit_s=e.last_feed_visit_s,
                    isolation_score=e.isolation_score,
                    flags=e.flags,
                )
            )

        return SceneGraph(
            timestamp=datetime.now(UTC),
            frame_id=frame_id,
            herd_summary=HerdSummary(
                total_visible=len(entities),
                **behavior_counts,
            ),
            tracked_entities=tracked_models,
            zones={name: ZoneOccupancy(occupancy=count) for name, count in zone_counts.items()},
            active_alerts=alerts,
        )

    def get_delta(self, prev: SceneGraph | None, current: SceneGraph) -> SceneDelta:
        """Compute delta between two scene graphs."""
        if prev is None:
            return SceneDelta(
                new_entities=[e.track_id for e in current.tracked_entities],
                exited_entities=[],
                zone_crossings=[],
                new_alerts=list(current.active_alerts),
                velocity_spikes=[],
                behavior_changes=[],
            )

        prev_ids = {e.track_id for e in prev.tracked_entities}
        curr_ids = {e.track_id for e in current.tracked_entities}

        return SceneDelta(
            new_entities=list(curr_ids - prev_ids),
            exited_entities=list(prev_ids - curr_ids),
            zone_crossings=[],  # TODO: compare zones between frames
            new_alerts=[a for a in current.active_alerts if a not in prev.active_alerts],
            velocity_spikes=[],
            behavior_changes=[],
        )
