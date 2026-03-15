"""LiveKit Agent entrypoint for HerdFlow.

Full pipeline: video frames -> RF-DETR -> ByteTrack -> SceneGraph -> Gemini context injection.
Data channels: scene_graph, alerts, overlay sent to frontend.

Usage: uv run python -m agent.main
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import numpy as np
from livekit.agents import AgentServer, AgentSession, JobContext, JobProcess
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


def setup(proc: JobProcess) -> None:
    """Pre-load VAD and detector models (runs once per worker process)."""
    proc.userdata["vad"] = silero.VAD.load()

    if settings.use_real_detector:
        from agent.perception.detector import RFDETRDetector  # noqa: PLC0415

        proc.userdata["detector"] = RFDETRDetector(
            model_name=settings.rfdetr_model,
            threshold=settings.rfdetr_detection_threshold,
        )
    else:
        proc.userdata["detector"] = MockDetector()

    # File-based video source for demo
    try:
        proc.userdata["video_source"] = FileVideoSource(
            path=settings.demo_video_path,
            target_fps=settings.max_fps,
        )
    except FileNotFoundError:
        proc.userdata["video_source"] = None
        logger.warning("Demo video not found at %s, using random frames", settings.demo_video_path)

    logger.info(
        "HerdFlow process started (detector=%s, video=%s)",
        type(proc.userdata["detector"]).__name__,
        settings.demo_video_path,
    )


server.setup_fnc = setup


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    """Main RTC session: wire perception pipeline -> Gemini Live session."""
    await ctx.connect()

    vad = ctx.proc.userdata["vad"]
    detector = ctx.proc.userdata["detector"]
    video_source = ctx.proc.userdata.get("video_source")

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

    # Create Gemini 3 session with separate STT + LLM + TTS
    from google.cloud import texttospeech  # noqa: PLC0415

    session = AgentSession(
        stt=google.STT(
            credentials_file=settings.google_credentials_file,
            languages="en-US",
        ),
        llm=google.LLM(
            model=settings.gemini_model,
            thinking_config={"thinking_budget": 256},
        ),
        tts=google.TTS(
            credentials_file=settings.google_credentials_file,
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            use_streaming=False,
            speaking_rate=1.1,
        ),
        vad=vad,
    )

    agent = HerdFlowAgent()

    # Run one frame to get initial scene context before greeting
    from agent.reasoning.prompts import build_system_prompt  # noqa: PLC0415

    frame_iter = video_source.frames() if video_source else None
    if frame_iter is not None:
        initial_frame = next(frame_iter)
    else:
        initial_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    initial_sg = await scene_builder.process_frame(initial_frame, frame_id=0)
    agent._instructions = build_system_prompt(initial_sg.model_dump_json(indent=2))
    logger.info("Initial scene context injected (%d entities)", len(initial_sg.tracked_entities))

    # Wait for a participant to join
    participant = await ctx.wait_for_participant()
    logger.info("Participant joined: %s", participant.identity)

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    # Context injection callback for adaptive sampler
    async def inject_context(scene_json: str) -> None:
        agent._instructions = build_system_prompt(scene_json)
        await session.update_agent(agent)

    # Start background tasks
    asyncio.create_task(perception_loop(ctx, scene_builder, scene_queue, video_source, session))
    asyncio.create_task(sampler.run(scene_queue, inject_context))

    # Greet the farmer
    await session.generate_reply()
    logger.info("HerdFlow agent session started with full pipeline")


async def perception_loop(
    ctx: JobContext,
    builder: SceneGraphBuilder,
    scene_queue: asyncio.Queue,  # type: ignore[type-arg]
    video_source: FileVideoSource | None = None,
    session: AgentSession | None = None,
) -> None:
    """Run perception pipeline on video frames (file or random)."""
    frame_id = 0
    prev_sg = None

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
            await ctx.room.local_participant.publish_data(
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
            await ctx.room.local_participant.publish_data(
                overlay.model_dump_json().encode(), topic="overlay"
            )
            for alert in sg.active_alerts:
                await ctx.room.local_participant.publish_data(
                    alert.model_dump_json().encode(), topic="alerts"
                )
            logger.debug(
                "[B8] published: scene_graph + overlay(%d boxes) + %d alerts",
                len(sg.tracked_entities),
                len(sg.active_alerts),
            )
        except Exception:  # noqa: BLE001
            logger.debug("Data channel publish failed (no participants?)")

        # Proactive alerts: speak critical/alert-level alerts immediately
        if session is not None:
            for alert in sg.active_alerts:
                if alert.severity.value in ("alert", "critical"):
                    await session.say(alert.description, allow_interruptions=True)

        # Feed to sampler queue (non-blocking, drop if full)
        with contextlib.suppress(asyncio.QueueFull):
            scene_queue.put_nowait((sg, delta))

        await asyncio.sleep(2.0)  # ~0.5 FPS for mock mode, saves event loop


if __name__ == "__main__":
    from livekit.agents.cli import run_app

    run_app(server)
