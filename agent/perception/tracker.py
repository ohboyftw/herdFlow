"""ByteTrack tracker wrapping the supervision library."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import numpy as np
import supervision as sv

from agent.config import settings
from agent.models import Detection, TrackedEntity, TrackState

logger = logging.getLogger(__name__)


class Tracker:
    """Persistent multi-object tracker using ByteTrack.

    Uses minimum_consecutive_frames=1 so every matched detection is returned
    immediately, avoiding the confirmation delay of the default setting.
    """

    def __init__(self, entity_id_prefix: str = "") -> None:
        self.entity_id_prefix = entity_id_prefix or settings.entity_id_prefix
        self._tracker = sv.ByteTrack(
            track_activation_threshold=0.3,
            minimum_consecutive_frames=1,
        )
        self._id_map: dict[int, str] = {}  # ByteTrack external ID -> our track ID
        self._next_id = 1
        self._entity_state: dict[str, TrackedEntity] = {}

    def _get_track_id(self, bt_id: int) -> str:
        if bt_id not in self._id_map:
            self._id_map[bt_id] = f"{self.entity_id_prefix}{self._next_id:03d}"
            self._next_id += 1
        return self._id_map[bt_id]

    def update(self, detections: list[Detection], frame_id: int) -> list[TrackedEntity]:
        """Update tracker with new detections, return tracked entities."""
        if not detections:
            return []

        # Convert to supervision Detections
        xyxy = np.array([list(d.bbox) for d in detections], dtype=np.float32)
        confidence = np.array([d.confidence for d in detections], dtype=np.float32)
        class_id = np.array([d.class_id for d in detections], dtype=np.int32)

        sv_dets = sv.Detections(
            xyxy=xyxy,
            confidence=confidence,
            class_id=class_id,
        )

        # Run ByteTrack
        tracked = self._tracker.update_with_detections(sv_dets)

        # Convert back to TrackedEntity
        entities: list[TrackedEntity] = []
        now = datetime.now(UTC)
        class_name = detections[0].class_name if detections else "cow"

        for i in range(len(tracked)):
            bt_id = int(tracked.tracker_id[i])
            track_id = self._get_track_id(bt_id)
            x1, y1, x2, y2 = tracked.xyxy[i].astype(int)
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            w = x2 - x1
            h = y2 - y1
            aspect_ratio = w / h if h > 0 else 1.0

            # Get previous state for velocity calculation
            prev = self._entity_state.get(track_id)
            if prev:
                vx = cx - prev.centroid[0]
                vy = cy - prev.centroid[1]
                age = prev.age_frames + 1
                first_seen = prev.first_seen
            else:
                vx, vy = 0.0, 0.0
                age = 1
                first_seen = now

            entity = TrackedEntity(
                track_id=track_id,
                class_name=class_name,
                confidence=float(tracked.confidence[i]),
                bbox=(int(x1), int(y1), int(x2), int(y2)),
                centroid=(cx, cy),
                velocity=(vx, vy),
                behavior="standing",  # default — SceneGraphBuilder classifies
                behavior_duration_s=0.0,
                zone="unknown",
                zone_dwell_s=0.0,
                last_feed_visit_s=0.0,
                isolation_score=0.0,
                bbox_aspect_ratio=aspect_ratio,
                flags=[],
                first_seen=first_seen,
                last_seen=now,
                age_frames=age,
                state=TrackState.ACTIVE,
            )
            self._entity_state[track_id] = entity
            entities.append(entity)

        new_ids = [e.track_id for e in entities if e.age_frames == 1]
        if new_ids:
            logger.info("[B2->B3] tracker: new tracks %s", new_ids)
        logger.debug("[B2->B3] tracker: %d in -> %d tracked", len(detections), len(entities))
        return entities
