"""Shared test fixtures for HerdFlow contract and integration tests.

All fixtures build sample instances matching the contracts defined in
docs/superpowers/specs/2026-03-15-herdflow-mvp-design.md Section 4.
These are consumers of the design — they do NOT define new interfaces.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pytest

from agent.models import (
    Alert,
    BehaviorChange,
    BehaviorRecord,
    DescriptionMatch,
    DescriptionSearchResult,
    Detection,
    EntityHistory,
    GeminiContext,
    HerdStats,
    HerdSummary,
    OverlayBox,
    OverlayData,
    SceneDelta,
    SceneGraph,
    SceneGraphSnapshot,
    Severity,
    TrackedEntity,
    TrackedEntityModel,
    TrackState,
    ZoneCrossing,
    ZoneHistory,
    ZoneOccupancy,
    ZoneVisit,
)

NOW = datetime(2026, 3, 15, 9, 23, 1, tzinfo=timezone.utc)


# ── Primitive Factories ──


def make_detection(
    class_name: str = "cow",
    class_id: int = 20,
    confidence: float = 0.94,
    bbox: tuple[int, int, int, int] = (120, 340, 280, 720),
) -> Detection:
    return Detection(
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        bbox=bbox,
        mask=None,
        embedding=None,
    )


def make_tracked_entity(
    track_id: str = "COW-003",
    behavior: str = "lying",
    confidence: float = 0.94,
    velocity: tuple[float, float] = (0.0, 0.0),
    zone: str = "rest_area",
    zone_dwell_s: float = 120.0,
    isolation_score: float = 0.82,
    bbox_aspect_ratio: float = 1.8,
    behavior_duration_s: float = 4320.0,
    last_feed_visit_s: float = 18000.0,
    flags: list[str] | None = None,
) -> TrackedEntity:
    return TrackedEntity(
        track_id=track_id,
        class_name="cow",
        confidence=confidence,
        bbox=(120, 340, 280, 720),
        centroid=(200.0, 530.0),
        velocity=velocity,
        behavior=behavior,
        behavior_duration_s=behavior_duration_s,
        zone=zone,
        zone_dwell_s=zone_dwell_s,
        last_feed_visit_s=last_feed_visit_s,
        isolation_score=isolation_score,
        bbox_aspect_ratio=bbox_aspect_ratio,
        flags=flags or [],
        first_seen=NOW,
        last_seen=NOW,
        age_frames=100,
        state=TrackState.ACTIVE,
    )


def make_tracked_entity_model(
    track_id: str = "COW-003",
    behavior: str = "lying",
    confidence: float = 0.94,
    flags: list[str] | None = None,
) -> TrackedEntityModel:
    return TrackedEntityModel(
        track_id=track_id,
        class_name="cow",
        confidence=confidence,
        bbox=[120, 340, 280, 720],
        centroid=[200.0, 530.0],
        velocity=[0.0, 0.0],
        behavior=behavior,
        behavior_duration_s=4320.0,
        zone="rest_area",
        last_feed_visit_s=18000.0,
        isolation_score=0.82,
        flags=flags or [],
    )


def make_alert(
    alert_type: str = "prolonged_lying",
    severity: Severity = Severity.WARNING,
    entity_track_id: str = "COW-003",
    description: str = "COW-003 has been lying for 1.2 hours",
    resolved: bool = False,
) -> Alert:
    return Alert(
        type=alert_type,
        severity=severity,
        entity_track_id=entity_track_id,
        description=description,
        timestamp=NOW,
        resolved=resolved,
        resolved_at=NOW if resolved else None,
    )


def make_herd_summary(
    total_visible: int = 8,
    standing: int = 3,
    lying: int = 2,
    walking: int = 1,
    feeding: int = 1,
    drinking: int = 1,
) -> HerdSummary:
    return HerdSummary(
        total_visible=total_visible,
        standing=standing,
        lying=lying,
        walking=walking,
        feeding=feeding,
        drinking=drinking,
    )


def make_scene_graph(
    entities: int = 8,
    alerts: int = 0,
    frame_id: int = 14523,
) -> SceneGraph:
    tracked = [
        make_tracked_entity_model(
            track_id=f"COW-{i:03d}",
            behavior=["standing", "lying", "walking", "feeding", "drinking"][i % 5],
        )
        for i in range(1, entities + 1)
    ]
    alert_list = [
        make_alert(entity_track_id=f"COW-{i:03d}")
        for i in range(1, alerts + 1)
    ]
    return SceneGraph(
        timestamp=NOW,
        frame_id=frame_id,
        herd_summary=make_herd_summary(total_visible=entities),
        tracked_entities=tracked,
        zones={
            "feed_area": ZoneOccupancy(occupancy=3),
            "water_trough": ZoneOccupancy(occupancy=1),
            "rest_area": ZoneOccupancy(occupancy=4),
        },
        active_alerts=alert_list,
    )


def make_scene_delta(
    new_entities: list[str] | None = None,
    exited_entities: list[str] | None = None,
    zone_crossings: list[ZoneCrossing] | None = None,
    new_alerts: list[Alert] | None = None,
    velocity_spikes: list[str] | None = None,
    behavior_changes: list[BehaviorChange] | None = None,
) -> SceneDelta:
    return SceneDelta(
        new_entities=new_entities or [],
        exited_entities=exited_entities or [],
        zone_crossings=zone_crossings or [],
        new_alerts=new_alerts or [],
        velocity_spikes=velocity_spikes or [],
        behavior_changes=behavior_changes or [],
    )


def make_overlay_data(entities: int = 8, frame_id: int = 14523) -> OverlayData:
    boxes = [
        OverlayBox(
            track_id=f"COW-{i:03d}",
            bbox=[120, 340, 280, 720],
            behavior="standing",
            flags=[],
        )
        for i in range(1, entities + 1)
    ]
    return OverlayData(frame_id=frame_id, boxes=boxes)


def make_gemini_context(
    entities: int = 8,
    alerts: int = 1,
    history_count: int = 3,
) -> GeminiContext:
    sg = make_scene_graph(entities=entities, alerts=alerts)
    snapshots = [
        SceneGraphSnapshot(
            timestamp=NOW,
            frame_id=14520 + i,
            herd_summary=make_herd_summary(),
            entity_count=entities,
            alert_types=["prolonged_lying"] if alerts > 0 else [],
        )
        for i in range(history_count)
    ]
    return GeminiContext(
        scene_graph=sg,
        recent_alerts=sg.active_alerts[:5],
        history_snapshots=snapshots,
    )


def sample_frame(width: int = 1280, height: int = 720) -> np.ndarray:
    """Generate a random test frame (H, W, 3) uint8."""
    rng = np.random.default_rng(42)
    return rng.integers(0, 255, size=(height, width, 3), dtype=np.uint8)


# ── Frontend consumer contract (from design doc) ──

FRONTEND_REQUIRED_FIELDS = {
    "tracked_entities": [
        "track_id", "bbox", "centroid", "behavior",
        "behavior_duration_s", "flags", "confidence", "zone",
    ],
    "active_alerts": [
        "id", "type", "severity", "entity_track_id", "description",
    ],
    "herd_summary": [
        "total_visible", "standing", "lying", "walking", "feeding", "drinking",
    ],
    "zones": None,
}


# ── Pytest fixtures ──


@pytest.fixture
def detection() -> Detection:
    return make_detection()


@pytest.fixture
def tracked_entity() -> TrackedEntity:
    return make_tracked_entity()


@pytest.fixture
def tracked_entity_model() -> TrackedEntityModel:
    return make_tracked_entity_model()


@pytest.fixture
def alert() -> Alert:
    return make_alert()


@pytest.fixture
def scene_graph() -> SceneGraph:
    return make_scene_graph()


@pytest.fixture
def scene_graph_with_alerts() -> SceneGraph:
    return make_scene_graph(alerts=2)


@pytest.fixture
def scene_delta_significant() -> SceneDelta:
    return make_scene_delta(new_entities=["COW-009"])


@pytest.fixture
def scene_delta_empty() -> SceneDelta:
    return make_scene_delta()


@pytest.fixture
def overlay_data() -> OverlayData:
    return make_overlay_data()


@pytest.fixture
def gemini_context() -> GeminiContext:
    return make_gemini_context()


@pytest.fixture
def frame() -> np.ndarray:
    return sample_frame()
