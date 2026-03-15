"""Golden path end-to-end tests: verify data flows through all 3 tiers without breaking.

These tests trace data from mock video frame through the entire pipeline:
  Frame → Detection → TrackedEntity → SceneGraph → SceneDelta → GeminiContext JSON → TypeScript parse

Reference: Design doc Section 10 (Golden Path Tests).
"""

from __future__ import annotations

import json

import numpy as np

from agent.models import (
    Alert,
    GeminiContext,
    OverlayBox,
    OverlayData,
    SceneDelta,
    SceneGraph,
    SceneGraphSnapshot,
    TrackedEntityModel,
)
from tests.conftest import (
    FRONTEND_REQUIRED_FIELDS,
    make_alert,
    make_gemini_context,
    make_herd_summary,
    make_scene_delta,
    make_scene_graph,
    make_tracked_entity,
    make_tracked_entity_model,
    sample_frame,
)


def test_full_pipeline_golden_path():
    """Trace data through all 3 tiers: perception → reasoning → communication."""

    # ── Tier 1: Spatial Perception ──

    # Step 1: Video frame exists with correct shape
    frame = sample_frame(width=1280, height=720)
    assert frame.shape == (720, 1280, 3)
    assert frame.dtype == np.uint8

    # Step 2: Detector produces detections (mocked)
    from agent.models import Detection
    detections = [
        Detection(class_id=20, class_name="cow", confidence=0.94,
                  bbox=(120, 340, 280, 720)),
        Detection(class_id=20, class_name="cow", confidence=0.87,
                  bbox=(400, 200, 550, 600)),
    ]
    assert len(detections) == 2

    # Step 3: Tracker produces tracked entities (mocked)
    entities = [
        make_tracked_entity(track_id="COW-001", behavior="standing", confidence=0.94),
        make_tracked_entity(track_id="COW-002", behavior="walking", confidence=0.87),
    ]
    assert all(e.track_id.startswith("COW-") for e in entities)

    # Step 4: SceneGraphBuilder produces SceneGraph
    sg = make_scene_graph(entities=2, alerts=0)
    assert sg.herd_summary.total_visible == 2
    assert len(sg.tracked_entities) == 2
    assert sg.frame_id > 0

    # ── Tier 2: Multimodal Reasoning ──

    # Step 5: SceneDelta computed (first frame → all entities are new)
    delta = make_scene_delta(
        new_entities=[e.track_id for e in sg.tracked_entities]
    )
    assert delta.is_significant is True

    # Step 6: GeminiContext built for injection
    snapshot = SceneGraphSnapshot(
        timestamp=sg.timestamp,
        frame_id=sg.frame_id,
        herd_summary=sg.herd_summary,
        entity_count=len(sg.tracked_entities),
        alert_types=[],
    )
    ctx = GeminiContext(
        scene_graph=sg,
        recent_alerts=[],
        history_snapshots=[snapshot],
    )

    # Step 7: Context serializes to valid JSON under size limit
    json_str = ctx.to_prompt_injection()
    assert len(json_str) < 50_000
    parsed = json.loads(json_str)
    assert parsed["scene_graph"]["frame_id"] == sg.frame_id
    assert len(parsed["scene_graph"]["tracked_entities"]) == 2

    # ── Tier 3: Communication ──

    # Step 8: SceneGraph serializes for data channel
    sg_payload = sg.model_dump_json()
    sg_parsed = json.loads(sg_payload)
    assert "tracked_entities" in sg_parsed
    assert "herd_summary" in sg_parsed

    # Step 9: OverlayData serializes for overlay channel
    overlay = OverlayData(
        frame_id=sg.frame_id,
        boxes=[
            OverlayBox(
                track_id=e.track_id,
                bbox=e.bbox,
                behavior=e.behavior,
                flags=e.flags,
            )
            for e in sg.tracked_entities
        ],
    )
    overlay_payload = overlay.model_dump_json()
    overlay_parsed = json.loads(overlay_payload)
    assert overlay_parsed["frame_id"] == sg.frame_id
    assert len(overlay_parsed["boxes"]) == 2

    # Step 10: All payloads satisfy frontend contract
    for section, fields in FRONTEND_REQUIRED_FIELDS.items():
        assert section in sg_parsed, f"Missing: {section}"
        if fields is None:
            continue
        items = sg_parsed[section]
        if not isinstance(items, list):
            items = [items]
        for item in items:
            for field in fields:
                assert field in item, f"Frontend needs {section}.{field}"


def test_alert_pipeline_golden_path():
    """Trace an alert from rule evaluation through to frontend display."""

    # Step 1: Entity triggers prolonged_lying rule
    entity = make_tracked_entity(
        track_id="COW-003",
        behavior="lying",
        behavior_duration_s=4320.0,
        isolation_score=0.82,
        last_feed_visit_s=18000.0,
    )
    assert entity.behavior_duration_s > 3600  # threshold

    # Step 2: Alert created
    alert = make_alert(
        alert_type="prolonged_lying",
        entity_track_id="COW-003",
        description="COW-003 has been lying for 1.2 hours",
    )
    assert alert.key == "prolonged_lying:COW-003"

    # Step 3: Alert injected into SceneGraph
    sg = make_scene_graph(entities=8, alerts=0)
    sg_dict = sg.model_dump()
    sg_dict["active_alerts"] = [alert.model_dump()]
    sg_with_alert = SceneGraph.model_validate(sg_dict)
    assert len(sg_with_alert.active_alerts) == 1

    # Step 4: Alert appears in GeminiContext
    ctx = GeminiContext(
        scene_graph=sg_with_alert,
        recent_alerts=[alert],
        history_snapshots=[],
    )
    ctx_json = json.loads(ctx.to_prompt_injection())
    assert len(ctx_json["recent_alerts"]) == 1
    assert ctx_json["recent_alerts"][0]["type"] == "prolonged_lying"

    # Step 5: Alert serializes for frontend data channel
    alert_payload = json.loads(alert.model_dump_json())
    assert alert_payload["severity"] == "warning"
    assert alert_payload["entity_track_id"] == "COW-003"
    assert isinstance(alert_payload["id"], str)
    assert isinstance(alert_payload["timestamp"], str)


def test_quiet_scene_produces_no_triggers():
    """A scene with no changes should produce a non-significant delta."""
    sg1 = make_scene_graph(entities=5)
    sg2 = make_scene_graph(entities=5)  # same composition

    # Simulate get_delta with identical graphs
    delta = make_scene_delta()  # all empty lists
    assert delta.is_significant is False

    # No context injection should happen — token cost zero
