"""Handshake tests: one test per module boundary edge in the dependency graph.

Validates that the output of each producer module is valid input for its
consumer. These tests use mock/sample data — they do NOT test module logic,
only interface compatibility.

Reference: Design doc Section 4 (Module Boundary Map), Section 10 (Handshake Tests).

Boundary map:
  1. VideoFrame → Detector           (np.ndarray)
  2. Detector → Tracker              (list[Detection])
  3. Tracker → SceneGraphBuilder     (list[TrackedEntity])
  4. SceneGraphBuilder → AlertEngine (SceneGraph)
  5. AlertEngine → SceneGraphBuilder (list[Alert])
  6. SceneGraphBuilder → Sampler     (SceneGraph + SceneDelta)
  7. Sampler → Gemini                (JSON string)
  8. Agent → LiveKit data channels   (JSON payloads)
  9. LiveKit → React components      (JSON → TypeScript types)
"""

from __future__ import annotations

import json

import numpy as np

from agent.models import (
    Alert,
    Severity,
    TrackedEntityModel,
    TrackState,
)
from tests.conftest import (
    FRONTEND_REQUIRED_FIELDS,
    make_alert,
    make_detection,
    make_gemini_context,
    make_overlay_data,
    make_scene_delta,
    make_scene_graph,
    make_tracked_entity,
    sample_frame,
)

# ── Boundary 1: VideoFrame → Detector ──


def test_boundary_1_video_frame_shape():
    """Video frames must be (H, W, 3) uint8 numpy arrays."""
    frame = sample_frame(width=1280, height=720)
    assert frame.shape == (720, 1280, 3)
    assert frame.dtype == np.uint8


# ── Boundary 2: Detector → Tracker ──


def test_boundary_2_detection_has_required_fields():
    """Detection output must have fields the Tracker needs for association."""
    det = make_detection()
    assert hasattr(det, "class_id")
    assert hasattr(det, "class_name")
    assert hasattr(det, "confidence")
    assert hasattr(det, "bbox")
    assert len(det.bbox) == 4
    assert all(isinstance(v, int) for v in det.bbox)


def test_boundary_2_multiple_detections():
    """Tracker receives a list of detections — verify list contract."""
    detections = [
        make_detection(confidence=0.94, bbox=(120, 340, 280, 720)),
        make_detection(confidence=0.87, bbox=(400, 200, 550, 600)),
        make_detection(confidence=0.35, bbox=(700, 100, 800, 400)),
    ]
    assert len(detections) == 3
    assert all(d.confidence >= 0.3 for d in detections)  # detector threshold


# ── Boundary 3: Tracker → SceneGraphBuilder ──


def test_boundary_3_tracked_entity_has_required_fields():
    """TrackedEntity must carry all fields SceneGraphBuilder needs."""
    entity = make_tracked_entity()
    assert entity.track_id.startswith("COW-")
    assert hasattr(entity, "confidence")
    assert hasattr(entity, "bbox")
    assert hasattr(entity, "centroid")
    assert hasattr(entity, "velocity")
    assert hasattr(entity, "behavior")
    assert hasattr(entity, "behavior_duration_s")
    assert hasattr(entity, "zone")
    assert hasattr(entity, "zone_dwell_s")
    assert hasattr(entity, "isolation_score")
    assert hasattr(entity, "bbox_aspect_ratio")
    assert hasattr(entity, "flags")
    assert hasattr(entity, "state")
    assert isinstance(entity.state, TrackState)


def test_boundary_3_tracked_entity_to_model_conversion():
    """SceneGraphBuilder converts TrackedEntity → TrackedEntityModel.
    Verify all shared fields transfer correctly.
    """
    entity = make_tracked_entity(
        track_id="COW-005",
        behavior="feeding",
        confidence=0.91,
    )
    # Simulate the conversion SceneGraphBuilder performs
    model = TrackedEntityModel(
        track_id=entity.track_id,
        class_name=entity.class_name,
        confidence=entity.confidence,
        bbox=list(entity.bbox),
        centroid=list(entity.centroid),
        velocity=list(entity.velocity),
        behavior=entity.behavior,
        behavior_duration_s=entity.behavior_duration_s,
        zone=entity.zone,
        last_feed_visit_s=entity.last_feed_visit_s,
        isolation_score=entity.isolation_score,
        flags=entity.flags,
    )
    assert model.track_id == entity.track_id
    assert model.confidence == entity.confidence
    assert model.behavior == entity.behavior
    assert model.bbox == list(entity.bbox)


# ── Boundary 4: SceneGraphBuilder → AlertRuleEngine ──


def test_boundary_4_scene_graph_entities_for_alert_evaluation():
    """AlertRuleEngine receives TrackedEntities (not models) for evaluation.
    Verify entities carry the fields alert rules check.
    """
    entity = make_tracked_entity(
        behavior="lying",
        behavior_duration_s=4320.0,
        isolation_score=0.82,
        last_feed_visit_s=18000.0,
    )
    # Alert rules check these fields
    assert entity.behavior == "lying"
    assert entity.behavior_duration_s > 3600  # prolonged_lying threshold
    assert entity.isolation_score > 0.7  # isolation threshold
    assert entity.last_feed_visit_s > 14400  # missed_feeding threshold


# ── Boundary 5: AlertRuleEngine → SceneGraphBuilder ──


def test_boundary_5_alert_conforms_to_model():
    """Alerts produced by rules must conform to the Alert Pydantic model."""
    alert = make_alert(
        alert_type="prolonged_lying",
        severity=Severity.WARNING,
        entity_track_id="COW-003",
        description="COW-003 has been lying for 1.2 hours",
    )
    assert isinstance(alert.severity, Severity)
    assert alert.key == "prolonged_lying:COW-003"
    # Must be JSON-serializable for boundaries 7-9
    json_str = alert.model_dump_json()
    roundtripped = Alert.model_validate_json(json_str)
    assert roundtripped == alert


# ── Boundary 6: SceneGraphBuilder → AdaptiveFrameSampler ──


def test_boundary_6_scene_delta_drives_sampling():
    """Sampler receives (SceneGraph, SceneDelta) and checks is_significant."""
    make_scene_graph(entities=8)  # scene graph exists for context
    delta_significant = make_scene_delta(new_entities=["COW-009"])
    delta_quiet = make_scene_delta()

    assert delta_significant.is_significant is True
    assert delta_quiet.is_significant is False


def test_boundary_6_first_frame_always_significant():
    """Delta from None → first SceneGraph should be significant (new entities)."""
    sg = make_scene_graph(entities=5)
    # Simulate get_delta(None, sg) — all entities are new
    delta = make_scene_delta(new_entities=[e.track_id for e in sg.tracked_entities])
    assert delta.is_significant is True
    assert len(delta.new_entities) == 5


# ── Boundary 7: AdaptiveFrameSampler → Gemini Live API ──


def test_boundary_7_gemini_context_is_valid_json():
    """Context injected into Gemini must be valid JSON string."""
    ctx = make_gemini_context(entities=8, alerts=2)
    json_str = ctx.to_prompt_injection()
    parsed = json.loads(json_str)
    assert "scene_graph" in parsed
    assert len(parsed["scene_graph"]["tracked_entities"]) == 8


def test_boundary_7_gemini_context_under_token_limit():
    """Context should be reasonably sized for Gemini's context window."""
    ctx = make_gemini_context(entities=20, alerts=5, history_count=10)
    json_str = ctx.to_prompt_injection()
    # 50KB is ~12,500 tokens at 4 chars/token — well within limits
    assert len(json_str) < 50_000, f"Context too large: {len(json_str)} bytes"


# ── Boundary 8: Agent → LiveKit Data Channels ──


def test_boundary_8_scene_graph_channel_payload():
    """scene_graph channel: SceneGraph serialized directly (no wrapper)."""
    sg = make_scene_graph(entities=5, alerts=1)
    payload = sg.model_dump_json()
    parsed = json.loads(payload)
    assert "tracked_entities" in parsed
    assert "active_alerts" in parsed
    assert "herd_summary" in parsed


def test_boundary_8_alerts_channel_payload():
    """alerts channel: Alert serialized directly."""
    alert = make_alert()
    payload = alert.model_dump_json()
    parsed = json.loads(payload)
    assert "type" in parsed
    assert "severity" in parsed
    assert "entity_track_id" in parsed


def test_boundary_8_overlay_channel_payload():
    """overlay channel: OverlayData with slim OverlayBox models."""
    overlay = make_overlay_data(entities=8)
    payload = overlay.model_dump_json()
    parsed = json.loads(payload)
    assert "frame_id" in parsed
    assert "boxes" in parsed
    # OverlayBox should be slim — only 4 fields
    box = parsed["boxes"][0]
    assert {"track_id", "bbox", "behavior", "flags"}.issubset(set(box.keys()))


def test_boundary_8_overlay_payload_size_at_30fps():
    """At 30 FPS with 20 animals, overlay payload should be manageable."""
    overlay = make_overlay_data(entities=20)
    payload_bytes = len(overlay.model_dump_json().encode())
    # 20 entities * ~100 bytes each = ~2KB per frame
    # At 30 FPS = ~60 KB/s — well within SCTP limits
    assert payload_bytes < 5_000, f"Overlay too large for 30 FPS: {payload_bytes} bytes"


# ── Boundary 9: LiveKit Data Channels → React Components ──


def test_boundary_9_python_to_typescript_contract():
    """Python SceneGraph JSON must contain all fields TypeScript expects."""
    sg = make_scene_graph(entities=5, alerts=2)
    payload = sg.model_dump(mode="json")

    for section, fields in FRONTEND_REQUIRED_FIELDS.items():
        assert section in payload, f"Missing section: {section}"
        if fields is None:
            continue
        items = payload[section]
        if not isinstance(items, list):
            items = [items]
        for item in items:
            for field in fields:
                assert field in item, f"Frontend needs {section}.{field} but backend dropped it"


def test_boundary_9_alert_severity_is_string():
    """TypeScript expects severity as lowercase string, not enum object."""
    alert = make_alert(severity=Severity.WARNING)
    payload = alert.model_dump(mode="json")
    assert payload["severity"] == "warning"
    assert isinstance(payload["severity"], str)


def test_boundary_9_timestamp_is_iso_string():
    """TypeScript expects timestamps as ISO 8601 strings."""
    sg = make_scene_graph()
    payload = sg.model_dump(mode="json")
    ts = payload["timestamp"]
    assert isinstance(ts, str)
    # Should be parseable as ISO 8601
    from datetime import datetime

    datetime.fromisoformat(ts)
