"""HerdFlow data contracts — single source of truth.

All Pydantic models and dataclasses crossing module boundaries are defined here.
TypeScript types are auto-generated from these via scripts/generate_types.py.

Reference: docs/superpowers/specs/2026-03-15-herdflow-mvp-design.md Section 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, Field, field_validator

# ── Boundary 2: Detector → Tracker ──


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    mask: np.ndarray | None = None
    embedding: np.ndarray | None = None


# ── Boundary 3: Tracker → SceneGraphBuilder ──


class TrackState(StrEnum):
    ACTIVE = "active"
    TENTATIVE = "tentative"
    DELETED = "deleted"


@dataclass
class TrackedEntity:
    track_id: str
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]
    velocity: tuple[float, float]  # pixels/second (normalized to 1280x720)
    behavior: str
    behavior_duration_s: float
    zone: str
    zone_dwell_s: float  # seconds in current zone (for dwell-time gating)
    last_feed_visit_s: float
    isolation_score: float
    bbox_aspect_ratio: float  # width/height — lying cows typically > 1.5
    flags: list[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = field(default_factory=lambda: datetime.now(UTC))
    age_frames: int = 0
    state: TrackState = TrackState.ACTIVE


# ── Boundary 5: Alert output ──


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    severity: Severity
    entity_track_id: str
    description: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False
    resolved_at: datetime | None = None

    @property
    def key(self) -> str:
        """Dedup key: same alert type + same entity = same alert."""
        return f"{self.type}:{self.entity_track_id}"

    @field_validator("timestamp", "resolved_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        if v is not None and isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v


# ── Boundary 4+6: SceneGraph ──


class EntityAnnotation(BaseModel):
    """Rich annotation from Gemini visual analyst, keyed by track_id."""

    track_id: str
    label: str = ""  # "brown cow, standing calmly"
    behavior: str = ""  # Gemini's behavior classification
    health_notes: str = ""  # "appears healthy" or concern
    confidence: float = 0.0


class DetectedZone(BaseModel):
    """Zone detected by vision analyst from the actual video frame."""

    name: str
    x1: float  # normalized 0-1
    y1: float
    x2: float
    y2: float
    confidence: float = 1.0


class ZoneOccupancy(BaseModel):
    occupancy: int


class HerdSummary(BaseModel):
    total_visible: int
    standing: int
    lying: int
    walking: int
    feeding: int
    drinking: int


class TrackedEntityModel(BaseModel):
    track_id: str
    class_name: str
    confidence: float
    bbox: list[int]
    centroid: list[float]
    velocity: list[float]
    behavior: str
    behavior_duration_s: float
    zone: str
    last_feed_visit_s: float
    isolation_score: float
    flags: list[str]


class SceneGraph(BaseModel):
    timestamp: datetime
    frame_id: int
    herd_summary: HerdSummary
    tracked_entities: list[TrackedEntityModel]
    zones: dict[str, ZoneOccupancy]
    active_alerts: list[Alert]

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v


# ── Boundary 6: SceneDelta ──


class ZoneCrossing(BaseModel):
    track_id: str
    from_zone: str
    to_zone: str


class BehaviorChange(BaseModel):
    track_id: str
    from_behavior: str
    to_behavior: str


class SceneDelta(BaseModel):
    new_entities: list[str]
    exited_entities: list[str]
    zone_crossings: list[ZoneCrossing]
    new_alerts: list[Alert]
    velocity_spikes: list[str]
    behavior_changes: list[BehaviorChange]

    @property
    def is_significant(self) -> bool:
        return bool(
            self.new_entities
            or self.exited_entities
            or self.zone_crossings
            or self.new_alerts
            or self.velocity_spikes
            or self.behavior_changes
        )


# ── Boundary 7: Gemini context injection ──


class SceneGraphSnapshot(BaseModel):
    """Slim version of SceneGraph for history context. Keeps size manageable."""

    timestamp: datetime
    frame_id: int
    herd_summary: HerdSummary
    entity_count: int
    alert_types: list[str]  # just the type strings, not full Alert objects


class GeminiContext(BaseModel):
    scene_graph: SceneGraph
    recent_alerts: list[Alert]  # last 5
    history_snapshots: list[SceneGraphSnapshot]  # last 10, slim

    def to_prompt_injection(self) -> str:
        return self.model_dump_json(indent=2)


# ── Boundary 8-9: LiveKit data channels ──


class OverlayBox(BaseModel):
    """Overlay box for SVG rendering. Includes Gemini annotation when available."""

    track_id: str
    bbox: list[int]
    behavior: str
    flags: list[str]
    label: str = ""  # Gemini visual description (e.g. "brown cow, lying calmly")
    health_notes: str = ""  # Gemini health assessment


class OverlayData(BaseModel):
    frame_id: int
    boxes: list[OverlayBox]


# ── Gemini tool response models ──


class BehaviorRecord(BaseModel):
    behavior: str
    zone: str
    duration_s: float
    started_at: datetime


class EntityHistory(BaseModel):
    track_id: str
    records: list[BehaviorRecord]
    current_behavior: str
    current_duration_s: float


class HerdStats(BaseModel):
    period_minutes: int
    total_animals: int
    fed_in_period: int
    not_fed: list[str]
    avg_lying_duration_s: float
    alerts_fired: int
    behavior_breakdown: dict[str, int]


class DescriptionMatch(BaseModel):
    track_id: str
    confidence: float
    reason: str
    current_behavior: str
    zone: str
    centroid: list[float]


class DescriptionSearchResult(BaseModel):
    matches: list[DescriptionMatch]


class ZoneVisit(BaseModel):
    track_id: str
    entered_at: datetime
    duration_s: float


class ZoneHistory(BaseModel):
    zone: str
    period_minutes: int
    visits: list[ZoneVisit]
    current_occupancy: int = 0
    peak_occupancy: int = 0
    animals_not_visited: list[str] = []


# ── Frontend consumer contract ──

FRONTEND_REQUIRED_FIELDS: dict[str, list[str] | None] = {
    "tracked_entities": [
        "track_id",
        "bbox",
        "centroid",
        "behavior",
        "behavior_duration_s",
        "flags",
        "confidence",
        "zone",
    ],
    "active_alerts": [
        "id",
        "type",
        "severity",
        "entity_track_id",
        "description",
    ],
    "herd_summary": [
        "total_visible",
        "standing",
        "lying",
        "walking",
        "feeding",
        "drinking",
    ],
    "zones": None,
}
