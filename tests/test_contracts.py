"""Contract tests: round-trip serialization, boundary edge cases, and consumer-driven validation.

Tests the data contracts defined in agent/models.py. These tests validate
that every Pydantic model crossing a serialization boundary (7, 8, 9)
survives JSON round-trip without data loss or type drift.

Reference: Design doc Section 4 (Data Contracts) + Section 10 (Testing Strategy).
"""

from __future__ import annotations

import json

import pytest

from agent.models import (
    Alert,
    HerdSummary,
    OverlayBox,
    SceneGraph,
    SceneGraphSnapshot,
    Severity,
    ZoneOccupancy,
)
from tests.conftest import (
    FRONTEND_REQUIRED_FIELDS,
    make_alert,
    make_gemini_context,
    make_overlay_data,
    make_scene_delta,
    make_scene_graph,
    make_tracked_entity_model,
)

# ── Round-Trip Serialization ──


SERIALIZABLE_MODELS = [
    ("SceneGraph", lambda: make_scene_graph(entities=5, alerts=2)),
    ("Alert", lambda: make_alert()),
    ("Alert_resolved", lambda: make_alert(resolved=True)),
    ("SceneDelta_significant", lambda: make_scene_delta(new_entities=["COW-009"])),
    ("SceneDelta_empty", lambda: make_scene_delta()),
    ("TrackedEntityModel", lambda: make_tracked_entity_model()),
    (
        "HerdSummary",
        lambda: HerdSummary(total_visible=8, standing=3, lying=2, walking=1, feeding=1, drinking=1),
    ),
    ("ZoneOccupancy", lambda: ZoneOccupancy(occupancy=3)),
    ("OverlayData", lambda: make_overlay_data(entities=5)),
    (
        "OverlayBox",
        lambda: OverlayBox(
            track_id="COW-001", bbox=[120, 340, 280, 720], behavior="standing", flags=[]
        ),
    ),
    ("GeminiContext", lambda: make_gemini_context(entities=5, alerts=1)),
    (
        "SceneGraphSnapshot",
        lambda: SceneGraphSnapshot(
            timestamp=make_scene_graph().timestamp,
            frame_id=100,
            herd_summary=HerdSummary(
                total_visible=8, standing=3, lying=2, walking=1, feeding=1, drinking=1
            ),
            entity_count=8,
            alert_types=["prolonged_lying"],
        ),
    ),
]


@pytest.mark.parametrize(
    "name,factory",
    SERIALIZABLE_MODELS,
    ids=[m[0] for m in SERIALIZABLE_MODELS],
)
def test_roundtrip_serialization(name: str, factory):
    """Verify: deserialize(serialize(obj)) == obj for every serialization-boundary model."""
    original = factory()
    json_str = original.model_dump_json()
    roundtripped = type(original).model_validate_json(json_str)
    assert original == roundtripped, (
        f"Round-trip failed for {name}. Original: {original}\nRoundtripped: {roundtripped}"
    )


@pytest.mark.parametrize(
    "name,factory",
    SERIALIZABLE_MODELS,
    ids=[m[0] for m in SERIALIZABLE_MODELS],
)
def test_json_is_valid(name: str, factory):
    """Verify serialized output is valid JSON (not just Pydantic internal repr)."""
    original = factory()
    json_str = original.model_dump_json()
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)


# ── Boundary Edge Cases ──


def test_scene_graph_empty_herd():
    """SceneGraph with zero entities should serialize cleanly."""
    sg = make_scene_graph(entities=0, alerts=0)
    assert sg.herd_summary.total_visible == 0
    assert len(sg.tracked_entities) == 0
    assert len(sg.active_alerts) == 0
    roundtripped = SceneGraph.model_validate_json(sg.model_dump_json())
    assert roundtripped == sg


def test_scene_graph_no_zones():
    """SceneGraph with empty zones dict."""
    sg = make_scene_graph(entities=3)
    sg_dict = sg.model_dump()
    sg_dict["zones"] = {}
    sg2 = SceneGraph.model_validate(sg_dict)
    assert sg2.zones == {}
    assert SceneGraph.model_validate_json(sg2.model_dump_json()) == sg2


def test_scene_graph_single_critical_alert():
    """SceneGraph with one critical alert."""
    sg = make_scene_graph(entities=1, alerts=0)
    critical = make_alert(
        severity=Severity.CRITICAL,
        description="CRITICAL: COW-001 in distress",
    )
    sg_dict = sg.model_dump()
    sg_dict["active_alerts"] = [critical.model_dump()]
    sg2 = SceneGraph.model_validate(sg_dict)
    assert sg2.active_alerts[0].severity == Severity.CRITICAL


def test_scene_delta_is_significant_with_new_entity():
    """SceneDelta with a new entity should be significant."""
    delta = make_scene_delta(new_entities=["COW-009"])
    assert delta.is_significant is True


def test_scene_delta_is_not_significant_when_empty():
    """Empty SceneDelta should not be significant."""
    delta = make_scene_delta()
    assert delta.is_significant is False


def test_scene_delta_significant_on_alert():
    """SceneDelta with a new alert should be significant."""
    delta = make_scene_delta(new_alerts=[make_alert()])
    assert delta.is_significant is True


def test_scene_delta_significant_on_zone_crossing():
    """SceneDelta with a zone crossing should be significant."""
    from agent.models import ZoneCrossing

    delta = make_scene_delta(
        zone_crossings=[
            ZoneCrossing(track_id="COW-001", from_zone="rest_area", to_zone="feed_area")
        ]
    )
    assert delta.is_significant is True


def test_scene_delta_significant_on_behavior_change():
    """SceneDelta with a behavior change should be significant."""
    from agent.models import BehaviorChange

    delta = make_scene_delta(
        behavior_changes=[
            BehaviorChange(track_id="COW-001", from_behavior="standing", to_behavior="lying")
        ]
    )
    assert delta.is_significant is True


def test_alert_key_property():
    """Alert.key should return type:entity_track_id for dedup."""
    alert = make_alert(alert_type="isolation", entity_track_id="COW-007")
    assert alert.key == "isolation:COW-007"


def test_alert_id_auto_generated():
    """Alert.id should auto-generate a UUID if not provided."""
    a1 = make_alert()
    a2 = make_alert()
    assert a1.id != a2.id
    assert len(a1.id) == 36  # UUID format


def test_alert_utc_enforcement():
    """Alert timestamps without timezone should be coerced to UTC."""
    from datetime import datetime

    naive = datetime(2026, 3, 15, 9, 0, 0)
    alert = Alert(
        type="test",
        severity=Severity.INFO,
        entity_track_id="COW-001",
        description="test",
        timestamp=naive,
    )
    assert alert.timestamp.tzinfo is not None


def test_overlay_box_slim():
    """OverlayBox should only have track_id, bbox, behavior, flags."""
    box = OverlayBox(track_id="COW-001", bbox=[1, 2, 3, 4], behavior="standing", flags=[])
    dumped = box.model_dump()
    assert set(dumped.keys()) == {"track_id", "bbox", "behavior", "flags"}


def test_gemini_context_prompt_injection_is_valid_json():
    """GeminiContext.to_prompt_injection() should produce valid JSON."""
    ctx = make_gemini_context()
    json_str = ctx.to_prompt_injection()
    parsed = json.loads(json_str)
    assert "scene_graph" in parsed
    assert "recent_alerts" in parsed
    assert "history_snapshots" in parsed


def test_gemini_context_size_reasonable():
    """GeminiContext with 8 entities, 2 alerts, 10 history snapshots should be < 50KB."""
    ctx = make_gemini_context(entities=8, alerts=2, history_count=10)
    json_str = ctx.to_prompt_injection()
    assert len(json_str) < 50_000, f"GeminiContext too large: {len(json_str)} bytes"


# ── Consumer-Driven Contract Validation ──


def test_producer_satisfies_frontend_contract():
    """Verify backend never drops a field the frontend depends on."""
    sg = make_scene_graph(entities=5, alerts=2)
    payload = sg.model_dump(mode="json")

    for section, fields in FRONTEND_REQUIRED_FIELDS.items():
        assert section in payload, f"Missing section: {section}"

        if fields is None:
            # Full dict required (e.g., zones)
            continue

        items = payload[section]
        if not isinstance(items, list):
            items = [items]

        for item in items:
            for field in fields:
                assert field in item, (
                    f"Frontend needs {section}.{field} but producer dropped it. "
                    f"Available keys: {list(item.keys())}"
                )


def test_herd_summary_includes_all_behaviors():
    """HerdSummary must include feeding and drinking counts."""
    hs = HerdSummary(total_visible=8, standing=3, lying=2, walking=1, feeding=1, drinking=1)
    dumped = hs.model_dump()
    assert "feeding" in dumped
    assert "drinking" in dumped
