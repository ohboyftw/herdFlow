"""LiveKit Agent entrypoint for HerdFlow.

Full pipeline: video frames → RF-DETR → ByteTrack → SceneGraph → Gemini context injection.
Data channels: scene_graph, alerts, overlay sent to frontend.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import numpy as np
from livekit.agents import AgentServer, AgentSession
from livekit.plugins import google, silero

from agent.alerts.rules import AlertRuleEngine
from agent.config import settings
from agent.herdflow_agent import HerdFlowAgent
from agent.models import OverlayBox, OverlayData
from agent.perception.detector import MockDetector
from agent.perception.scene_graph import SceneGraphBuilder
from agent.perception.tracker import Tracker
from agent.perception.video_source import FileVideoSource
from agent.reasoning.sampler import AdaptiveFrameSampler

logger = logging.getLogger("herdflow")

server = AgentServer()


@server.on_process_started
async def on_process_started(proc: AgentServer.Process) -> None:
    """Pre-load VAD and detector models."""
    proc.userdata["vad"] = silero.VAD.load()

    if settings.use_real_detector:
        from agent.perception.detector import RFDETRDetector  # noqa: PLC0415

        proc.userdata["detector"] = RFDETRDetector(
            model_name=settings.rfdetr_model,
            threshold=settings.rfdetr_detection_threshold,
        )
    else:
        proc.userdata["detector"] = MockDetector()

    # Set up file-based video source for demo
    proc.userdata["video_source"] = FileVideoSource(
        path=settings.demo_video_path,
        target_fps=settings.max_fps,
    )

    logger.info(
        "HerdFlow process started (detector=%s, video=%s)",
        type(proc.userdata["detector"]).__name__,
        settings.demo_video_path,
    )


@server.rtc_session()
async def entrypoint(ctx: AgentServer.SessionContext) -> None:
    vad = ctx.proc.userdata["vad"]
    detector = ctx.proc.userdata["detector"]

    # Build perception pipeline
    tracker = Tracker()
    alert_engine = AlertRuleEngine(settings)
    scene_builder = SceneGraphBuilder(
        detector=detector,
        tracker=tracker,
        zone_config=settings.zone_config,
        alert_engine=alert_engine,
    )
    sampler = AdaptiveFrameSampler(
        max_fps=settings.max_fps,
        min_interval_ms=settings.min_interval_ms,
    )
    scene_queue: asyncio.Queue = asyncio.Queue(maxsize=10)

    # Create Gemini session
    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview",
            proactivity=True,
            enable_affective_dialog=True,
            thinking_config={"thinking_budget": 1024},
        ),
        vad=vad,
    )

    agent = HerdFlowAgent()

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    # Start background tasks
    video_source = ctx.proc.userdata["video_source"]
    asyncio.create_task(perception_loop(ctx, scene_builder, scene_queue, video_source))
    asyncio.create_task(sampler.run(scene_queue, session.update_chat_ctx))

    # Greet the farmer
    await session.generate_reply()
    logger.info("HerdFlow agent session started with full pipeline")


async def perception_loop(
    ctx: AgentServer.SessionContext,
    builder: SceneGraphBuilder,
    scene_queue: asyncio.Queue,  # type: ignore[type-arg]
    video_source: FileVideoSource | None = None,
) -> None:
    """Run perception pipeline on video frames (file or LiveKit)."""
    frame_id = 0
    prev_sg = None

    # Use file video source if available, otherwise fall back to random noise
    frame_iter = video_source.frames() if video_source else None

    while True:
        frame_id += 1
        if frame_iter is not None:
            frame = next(frame_iter)
        else:
            frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

        sg = await builder.process_frame(frame, frame_id)
        delta = builder.get_delta(prev_sg, sg)
        prev_sg = sg

        # Publish to LiveKit data channels (best-effort)
        try:
            room = ctx.room
            await room.local_participant.publish_data(
                sg.model_dump_json().encode(), topic="scene_graph"
            )
            overlay = OverlayData(
                frame_id=frame_id,
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
            await room.local_participant.publish_data(
                overlay.model_dump_json().encode(), topic="overlay"
            )
            for alert in sg.active_alerts:
                await room.local_participant.publish_data(
                    alert.model_dump_json().encode(), topic="alerts"
                )
        except Exception:  # noqa: BLE001
            logger.debug("No participants yet, skipping data publish")

        # Feed to sampler queue (non-blocking, drop if full)
        with contextlib.suppress(asyncio.QueueFull):
            scene_queue.put_nowait((sg, delta))

        await asyncio.sleep(0.5)  # ~2 FPS
