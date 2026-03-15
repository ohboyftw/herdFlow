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
from agent.perception.detector import MockDetector, RFDETRDetector
from agent.perception.scene_graph import SceneGraphBuilder
from agent.perception.tracker import Tracker
from agent.reasoning.sampler import AdaptiveFrameSampler

logger = logging.getLogger("herdflow")

server = AgentServer()

# Use MockDetector for dev, RFDETRDetector for prod
USE_REAL_DETECTOR = False  # Toggle for GPU availability


@server.on_process_started
async def on_process_started(proc: AgentServer.Process) -> None:
    """Pre-load VAD and detector models."""
    proc.userdata["vad"] = silero.VAD.load()
    if USE_REAL_DETECTOR:
        proc.userdata["detector"] = RFDETRDetector(
            model_name=settings.rfdetr_model,
            threshold=settings.rfdetr_detection_threshold,
        )
    else:
        proc.userdata["detector"] = MockDetector()
    logger.info(
        "HerdFlow agent process started (detector=%s)",
        "RF-DETR" if USE_REAL_DETECTOR else "mock",
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
    asyncio.create_task(perception_loop(ctx, scene_builder, scene_queue))
    asyncio.create_task(sampler.run(scene_queue, session.update_chat_ctx))
    asyncio.create_task(data_channel_publisher(ctx, scene_builder))

    # Greet the farmer
    await session.generate_reply()
    logger.info("HerdFlow agent session started with full pipeline")


async def perception_loop(
    ctx: AgentServer.SessionContext,
    builder: SceneGraphBuilder,
    scene_queue: asyncio.Queue,  # type: ignore[type-arg]
) -> None:
    """Consume video frames from LiveKit, run perception pipeline."""
    frame_id = 0
    prev_sg = None

    # For now, generate mock frames at ~2 FPS when no video track
    while True:
        frame_id += 1
        # TODO: Get real frame from LiveKit video track
        # For now use mock frames
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

        sg = await builder.process_frame(frame, frame_id)
        delta = builder.get_delta(prev_sg, sg)
        prev_sg = sg

        # Feed to sampler queue (non-blocking, drop if full)
        with contextlib.suppress(asyncio.QueueFull):
            scene_queue.put_nowait((sg, delta))  # drop frame if sampler is behind

        await asyncio.sleep(0.5)  # ~2 FPS


async def data_channel_publisher(
    ctx: AgentServer.SessionContext,
    builder: SceneGraphBuilder,
) -> None:
    """Publish scene graph and overlay data to LiveKit data channels."""
    # TODO: Implement data channel publishing when LiveKit room is connected
    # For now this is a placeholder
    pass
