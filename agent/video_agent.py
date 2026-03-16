"""Standalone video/perception process for HerdFlow two-pipe architecture.

Connects to a LiveKit room using raw rtc.Room (no AgentServer/ADK).
Runs RF-DETR perception, VideoAnalyst background analysis, and publishes
scene_graph/overlay/alerts/analyst data channels.

Usage: uv run python -m agent.video_agent
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

# Load .env before any imports read os.environ
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# Log file — separate from voice agent
_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = logging.FileHandler(_log_dir / "herdflow-video.log", mode="a", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)s  %(message)s"))
_file_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_file_handler)

# Console: INFO only. File gets DEBUG.
logging.getLogger().setLevel(logging.DEBUG)
for _h in logging.getLogger().handlers:
    if isinstance(_h, logging.StreamHandler) and _h is not _file_handler:
        _h.setLevel(logging.INFO)
# Suppress noisy libs
for _name in ("asyncio", "urllib3", "httpcore", "httpx", "google", "grpc"):
    logging.getLogger(_name).setLevel(logging.WARNING)
logging.getLogger("herdflow").setLevel(logging.DEBUG)
logging.getLogger("agent").setLevel(logging.DEBUG)

import numpy as np  # noqa: E402
from livekit.rtc import (  # noqa: E402
    LocalVideoTrack,
    Room,
    VideoBufferType,
    VideoFrame,
    VideoSource,
)

from agent.alerts.rules import AlertRuleEngine  # noqa: E402
from agent.config import settings  # noqa: E402
from agent.models import OverlayBox, OverlayData  # noqa: E402
from agent.perception.detector import MockDetector  # noqa: E402
from agent.perception.scene_graph import SceneGraphBuilder  # noqa: E402
from agent.perception.tracker import Tracker  # noqa: E402
from agent.perception.video_source import FileVideoSource  # noqa: E402
from agent.reasoning.video_analyst import VideoAnalyst  # noqa: E402

logger = logging.getLogger("herdflow.video_agent")


async def video_publish_loop(
    video_path: str,
    video_src: VideoSource,
    shared_frame: dict[str, np.ndarray | None],
    target_fps: float = 5.0,
) -> None:
    """Publish video frames to LiveKit at smooth FPS, share latest with perception."""
    source = FileVideoSource(path=video_path, target_fps=target_fps)
    interval = 1.0 / target_fps
    logger.info("[VIDEO] Publishing at ~%.0f FPS from %s", target_fps, video_path)

    try:
        frame_iter = source.frames()
        next_time = asyncio.get_event_loop().time()
        while True:
            try:
                frame = await asyncio.to_thread(next, frame_iter)
            except StopIteration:
                logger.warning("[VIDEO] Frame iterator exhausted, restarting")
                frame_iter = source.frames()
                frame = await asyncio.to_thread(next, frame_iter)

            # Share with perception loop (same frame = synced bounding boxes)
            shared_frame["frame"] = frame

            h, w = frame.shape[:2]
            lk_frame = VideoFrame(w, h, VideoBufferType.RGB24, frame.tobytes())
            video_src.capture_frame(lk_frame)

            next_time += interval
            now = asyncio.get_event_loop().time()
            await asyncio.sleep(max(0, next_time - now))
    finally:
        source.close()
        logger.info("[VIDEO] Publish loop stopped, video source closed")


async def perception_loop(
    room: Room,
    builder: SceneGraphBuilder,
    shared_frame: dict[str, np.ndarray | None],
    video_analyst: VideoAnalyst,
) -> None:
    """Run perception on the latest video frame (shared with video publisher)."""
    frame_id = 0

    while True:
        frame_id += 1
        frame = shared_frame.get("frame")
        if frame is None:
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        sg = await builder.process_frame(frame, frame_id)
        video_analyst.update(frame, sg)

        # Detect zones once from first frame, publish to frontend
        if not video_analyst._zones_detected:
            zones = await video_analyst.detect_zones()
            if zones:
                await room.local_participant.publish_data(
                    json.dumps(zones).encode(), topic="zone_config"
                )

        # Publish to data channels
        try:
            await room.local_participant.publish_data(
                sg.model_dump_json().encode(), topic="scene_graph"
            )
            # Merge RF-DETR spatial data with Gemini annotations
            boxes = []
            for e in sg.tracked_entities:
                ann = video_analyst.get_annotation(e.track_id)
                boxes.append(
                    OverlayBox(
                        track_id=e.track_id,
                        bbox=e.bbox,
                        behavior=ann.get("behavior", e.behavior) if ann else e.behavior,
                        flags=e.flags,
                        label=ann.get("label", "") if ann else "",
                        health_notes=ann.get("health_notes", "") if ann else "",
                    )
                )
            overlay = OverlayData(frame_id=frame_id, boxes=boxes)
            await room.local_participant.publish_data(
                overlay.model_dump_json().encode(), topic="overlay"
            )
            for alert in sg.active_alerts:
                await room.local_participant.publish_data(
                    alert.model_dump_json().encode(), topic="alerts"
                )
        except Exception:  # noqa: BLE001
            logger.debug("Data channel publish failed")

        await asyncio.sleep(2.0)


async def publish_analyst_data(room: Room, video_analyst: VideoAnalyst) -> None:
    """Publish analyst data to data channels. Publishes scene graph text
    immediately when available, then switches to Gemini summaries after
    the first background cycle completes."""
    last_summary = ""

    while True:
        await asyncio.sleep(5.0)  # check every 5s
        try:
            # Use Gemini summary if available, otherwise format scene graph
            summary = video_analyst.get_summary()
            if (
                summary == video_analyst.DEFAULT_SUMMARY
                and video_analyst.latest_scene_graph is not None
            ):
                summary = video_analyst.format_scene_graph(video_analyst.latest_scene_graph)

            # Only publish if summary changed
            if summary and summary != last_summary:
                await room.local_participant.publish_data(
                    json.dumps({"summary": summary}).encode(),
                    topic="analyst_summary",
                )
                last_summary = summary
                logger.info("[VIDEO] Published analyst_summary: %s", summary[:80])

            # Always publish latest annotations
            if video_analyst.entity_annotations:
                await room.local_participant.publish_data(
                    json.dumps({"annotations": video_analyst.entity_annotations}).encode(),
                    topic="analyst_annotations",
                )
        except Exception:
            logger.exception("[VIDEO] Failed to publish analyst data")


async def handle_analyst_request(
    room: Room,
    video_analyst: VideoAnalyst,
    payload: bytes,
) -> None:
    """Handle an on-demand analyst request from the voice agent."""
    try:
        data = json.loads(payload.decode())
        question = data["question"]
        request_id = data["request_id"]
        logger.info("[ANALYST] On-demand request %s: %s", request_id, question[:100])

        answer = await video_analyst.analyze(question)
        response = json.dumps({"answer": answer, "request_id": request_id})
        await room.local_participant.publish_data(response.encode(), topic="analyst_response")
        logger.info("[ANALYST] Response sent for %s", request_id)
    except Exception:
        logger.exception("[ANALYST] Failed to handle analyst request")


async def main() -> None:
    """Video agent entrypoint — connects to LiveKit room and runs perception."""
    livekit_url = os.environ.get("LIVEKIT_URL", settings.livekit_url)
    video_token = os.environ["VIDEO_AGENT_TOKEN"]

    # Load detector
    if settings.use_real_detector:
        from agent.perception.detector import RFDETRDetector

        detector = RFDETRDetector(
            model_name=settings.rfdetr_model,
            threshold=settings.rfdetr_detection_threshold,
        )
    else:
        detector = MockDetector()

    # Load video source
    try:
        video_source = FileVideoSource(
            path=settings.demo_video_path,
            target_fps=settings.max_fps,
        )
    except FileNotFoundError:
        video_source = None
        logger.warning("Demo video not found at %s", settings.demo_video_path)

    logger.info(
        "Video agent starting (detector=%s, video=%s)",
        type(detector).__name__,
        settings.demo_video_path,
    )

    # Build perception pipeline
    tracker = Tracker()
    alert_engine = AlertRuleEngine(settings)
    scene_builder = SceneGraphBuilder(
        detector=detector,
        tracker=tracker,
        zone_config=settings.zone_config,
        alert_engine=alert_engine,
    )

    # Get initial frame for scene context
    frame_iter = video_source.frames() if video_source else None
    if frame_iter is not None:
        initial_frame = await asyncio.to_thread(next, frame_iter)
    else:
        initial_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    initial_sg = await scene_builder.process_frame(initial_frame, frame_id=0)
    logger.info("Initial scene: %d entities", len(initial_sg.tracked_entities))

    # Create VideoAnalyst
    video_analyst = VideoAnalyst(
        background_model=settings.video_analyst_background_model,
        on_demand_model=settings.video_analyst_on_demand_model,
        summary_interval_s=settings.video_analyst_summary_interval_s,
    )

    # Connect to LiveKit room (raw rtc.Room, no AgentServer)
    room = Room()
    await room.connect(livekit_url, video_token)
    logger.info("Connected to LiveKit room as video agent")

    # Shared frame holder — video publisher writes, perception reads
    shared_frame: dict[str, np.ndarray | None] = {"frame": None}

    # Publish video track
    video_src = VideoSource(1280, 720)
    video_track = LocalVideoTrack.create_video_track("camera-feed", video_src)
    video_pub = await room.local_participant.publish_track(video_track)
    logger.info("Published video track: %s", video_pub.sid)

    # Subscribe to analyst_request data channel
    @room.on("data_received")
    def on_data(packet) -> None:  # noqa: ANN001
        topic = getattr(packet, "topic", None)
        if topic == "analyst_request":
            data = getattr(packet, "data", b"")
            asyncio.create_task(handle_analyst_request(room, video_analyst, data))

    # Start background tasks
    tasks = [
        asyncio.create_task(perception_loop(room, scene_builder, shared_frame, video_analyst)),
        asyncio.create_task(video_analyst.run_background_loop()),
        asyncio.create_task(publish_analyst_data(room, video_analyst)),
    ]
    if video_source is not None:
        tasks.append(
            asyncio.create_task(
                video_publish_loop(settings.demo_video_path, video_src, shared_frame)
            )
        )

    logger.info("Video agent running — perception + analyst active")

    try:
        # Wait forever (or until a task crashes)
        await asyncio.gather(*tasks)
    finally:
        await room.disconnect()
        logger.info("Video agent disconnected from room")


if __name__ == "__main__":
    asyncio.run(main())
