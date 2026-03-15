"""Trace-debug the full perception pipeline with real video frames.

Runs the pipeline WITHOUT LiveKit — verifies:
1. Video source reads frames correctly
2. Detector produces detections (mock or real)
3. Tracker assigns persistent IDs
4. SceneGraphBuilder produces valid SceneGraph + SceneDelta
5. Alert engine evaluates entities
6. Temporal state accumulates (zone_dwell_s, behavior_duration_s)
7. GeminiContext serializes under size limit

Usage: uv run python -m scripts.trace_pipeline
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from agent.alerts.rules import AlertRuleEngine
from agent.config import settings
from agent.models import GeminiContext, SceneGraphSnapshot
from agent.perception.detector import MockDetector
from agent.perception.scene_graph import SceneGraphBuilder
from agent.perception.tracker import Tracker
from agent.perception.video_source import FileVideoSource


async def trace() -> bool:
    """Run N frames through the pipeline and print trace output."""
    n_frames = 30  # ~15 seconds at 2 FPS
    ok = True

    print("=" * 70)
    print("HerdFlow Pipeline Trace-Debug")
    print("=" * 70)

    # 1. Video source
    print("\n[1] Video Source")
    try:
        vs = FileVideoSource(settings.demo_video_path, target_fps=2.0)
        frame_gen = vs.frames()
        frame = next(frame_gen)
        print(f"    OK: {settings.demo_video_path} -> {frame.shape} {frame.dtype}")
    except FileNotFoundError:
        print(f"    WARN: {settings.demo_video_path} not found, using random frames")
        import numpy as np

        def random_frames():
            while True:
                yield np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

        frame_gen = random_frames()
        frame = next(frame_gen)
        print(f"    Fallback: random frame {frame.shape}")

    # 2. Build pipeline
    print("\n[2] Pipeline Setup")
    if settings.use_real_detector:
        from agent.perception.detector import RFDETRDetector

        detector = RFDETRDetector(
            model_name=settings.rfdetr_model,
            threshold=settings.rfdetr_detection_threshold,
        )
    else:
        detector = MockDetector()
    tracker = Tracker()
    alert_engine = AlertRuleEngine(settings)
    builder = SceneGraphBuilder(
        detector=detector,
        tracker=tracker,
        zone_config=settings.zone_config,
        alert_engine=alert_engine,
    )
    print(f"    Detector: {type(detector).__name__}")
    print(f"    Zones: {list(settings.zone_config.keys())}")
    print("    Alert rules: prolonged_lying, isolation, missed_feeding")

    # 3. Process frames
    print(f"\n[3] Processing {n_frames} frames...")
    prev_sg = None
    t0 = time.monotonic()

    for i in range(n_frames):
        frame = next(frame_gen)
        sg = await builder.process_frame(frame, frame_id=i + 1)
        delta = builder.get_delta(prev_sg, sg)

        if i == 0 or i == n_frames - 1 or (i + 1) % 10 == 0:
            print(f"\n    --- Frame {i + 1} ---")
            print(f"    Entities: {sg.herd_summary.total_visible}")
            hs = sg.herd_summary
            print(
                f"    Behaviors: standing={hs.standing} lying={hs.lying} "
                f"walking={hs.walking} feeding={hs.feeding} drinking={hs.drinking}"
            )
            print(f"    Zones: {dict((k, v.occupancy) for k, v in sg.zones.items())}")
            print(f"    Alerts: {len(sg.active_alerts)}")
            print(f"    Delta significant: {delta.is_significant}")

            if builder._prev_entities:
                eid = next(iter(builder._prev_entities))
                te = builder._prev_entities[eid]
                print(
                    f"    Entity[0]: {te.track_id} behavior={te.behavior} "
                    f"zone={te.zone} behavior_dur={te.behavior_duration_s:.1f}s "
                    f"zone_dwell={te.zone_dwell_s:.1f}s"
                )

        prev_sg = sg

    elapsed = time.monotonic() - t0
    fps = n_frames / elapsed
    print(f"\n    Processed {n_frames} frames in {elapsed:.2f}s ({fps:.1f} FPS)")

    # 4. Validate SceneGraph
    print("\n[4] SceneGraph Validation")
    assert sg is not None
    sg_json = sg.model_dump_json()
    sg_size = len(sg_json)
    print(f"    JSON size: {sg_size} bytes")
    parsed = json.loads(sg_json)
    assert "tracked_entities" in parsed
    assert "herd_summary" in parsed
    assert "active_alerts" in parsed
    print("    Fields present: tracked_entities, herd_summary, active_alerts, zones [ok]")

    # 5. GeminiContext
    print("\n[5] GeminiContext Validation")
    snapshot = SceneGraphSnapshot(
        timestamp=sg.timestamp,
        frame_id=sg.frame_id,
        herd_summary=sg.herd_summary,
        entity_count=len(sg.tracked_entities),
        alert_types=[a.type for a in sg.active_alerts],
    )
    ctx = GeminiContext(
        scene_graph=sg,
        recent_alerts=list(sg.active_alerts[:5]),
        history_snapshots=[snapshot],
    )
    ctx_json = ctx.to_prompt_injection()
    ctx_size = len(ctx_json)
    print(f"    Context JSON: {ctx_size} bytes ({ctx_size / 4:.0f} est. tokens)")
    if ctx_size > 50_000:
        print(f"    FAIL: Context too large ({ctx_size} > 50000)")
        ok = False
    else:
        print("    OK: Under 50KB limit [ok]")

    # 6. Temporal state check
    print("\n[6] Temporal State Check")
    entities = list(builder._prev_entities.values())
    if entities:
        has_zone_dwell = any(e.zone_dwell_s > 0 for e in entities)
        has_behavior_dur = any(e.behavior_duration_s > 0 for e in entities)
        max_dwell = max(e.zone_dwell_s for e in entities)
        max_dur = max(e.behavior_duration_s for e in entities)
        print(f"    Zone dwell accumulating: {has_zone_dwell} (max={max_dwell:.1f}s)")
        print(f"    Behavior duration accumulating: {has_behavior_dur} (max={max_dur:.1f}s)")
        if not has_zone_dwell and n_frames > 5:
            print("    WARN: zone_dwell_s not accumulating after multiple frames")
        if not has_behavior_dur and n_frames > 5:
            print("    WARN: behavior_duration_s not accumulating after multiple frames")
    else:
        print("    WARN: No entities tracked")

    # 7. Summary
    print("\n" + "=" * 70)
    if ok:
        print("TRACE PASSED — pipeline is functional")
    else:
        print("TRACE FAILED — see issues above")
    print("=" * 70)

    vs.close() if hasattr(vs, "close") else None
    return ok


def main() -> None:
    result = asyncio.run(trace())
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
