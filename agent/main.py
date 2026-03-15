"""LiveKit Agent entrypoint for HerdFlow.

Dual-model architecture:
- Gemini 2.5 Flash Native Audio: voice concierge (handles conversation)
- Gemini 3 Flash via ADK: strategist (tool calls, data analysis)

The concierge speaks to the farmer. When data questions arise, they are
relayed to the ADK strategist which calls tools and returns answers.
The concierge then speaks the answer.

Usage: uv run python -m agent.main dev
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import numpy as np
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from livekit.agents import AgentServer, AgentSession, JobContext, JobProcess
from livekit.plugins import google, silero

from agent.adk_agents import create_herdflow_agents
from agent.alerts.rules import AlertRuleEngine
from agent.config import settings
from agent.herdflow_agent import HerdFlowAgent
from agent.models import OverlayBox, OverlayData
from agent.perception.detector import MockDetector
from agent.perception.scene_graph import SceneGraphBuilder
from agent.perception.tracker import Tracker
from agent.perception.video_source import FileVideoSource
from agent.reasoning.prompts import build_system_prompt
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

    try:
        proc.userdata["video_source"] = FileVideoSource(
            path=settings.demo_video_path,
            target_fps=settings.max_fps,
        )
    except FileNotFoundError:
        proc.userdata["video_source"] = None
        logger.warning("Demo video not found at %s", settings.demo_video_path)

    logger.info(
        "HerdFlow process started (detector=%s, video=%s)",
        type(proc.userdata["detector"]).__name__,
        settings.demo_video_path,
    )


server.setup_fnc = setup


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    """Main RTC session: dual-model voice + data pipeline."""
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

    # Run one frame to get initial scene context
    frame_iter = video_source.frames() if video_source else None
    if frame_iter is not None:
        initial_frame = next(frame_iter)
    else:
        initial_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    initial_sg = await scene_builder.process_frame(initial_frame, frame_id=0)
    scene_json = initial_sg.model_dump_json(indent=2)
    logger.info("Initial scene: %d entities", len(initial_sg.tracked_entities))

    # Create ADK strategist for tool calls
    adk_agents = create_herdflow_agents(scene_json)
    adk_session_service = InMemorySessionService()
    adk_session = await adk_session_service.create_session(
        app_name="herdflow", user_id="farmer"
    )
    adk_runner = Runner(
        agent=adk_agents["strategist"],
        app_name="herdflow",
        session_service=adk_session_service,
    )

    # Create LiveKit voice session with Gemini 2.5 Native Audio
    agent = HerdFlowAgent()
    agent._instructions = build_system_prompt(scene_json)

    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-latest",
            thinking_config={"thinking_budget": 128},
        ),
        vad=vad,
    )

    # Wait for participant
    participant = await ctx.wait_for_participant()
    logger.info("Participant joined: %s", participant.identity)

    await session.start(room=ctx.room, agent=agent)

    # Context injection callback
    async def inject_context(scene_json_str: str) -> None:
        agent._instructions = build_system_prompt(scene_json_str)
        # Also update ADK monitor's scene context
        adk_agents["monitor"]._instruction = (
            adk_agents["monitor"]._instruction.split("Current scene:")[0]
            + f"Current scene:\n```json\n{scene_json_str}\n```"
        )

    # Strategist relay: relay data questions to ADK strategist
    async def relay_to_strategist(question: str) -> str:
        """Send a question to the ADK Strategist and return the answer."""
        logger.info("[RELAY] Farmer asked: %s", question[:100])
        msg = genai_types.Content(
            role="user", parts=[genai_types.Part(text=question)]
        )
        answer_parts: list[str] = []
        for event in adk_runner.run(
            user_id="farmer", session_id=adk_session.id, new_message=msg
        ):
            if (
                hasattr(event, "content")
                and event.content
                and event.content.parts
            ):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        answer_parts.append(part.text)
        answer = " ".join(answer_parts) if answer_parts else "I couldn't find that data."
        logger.info("[RELAY] Strategist answered: %s", answer[:200])
        return answer

    # Monitor loop: periodically check for alerts via ADK monitor
    async def monitor_loop() -> None:
        """Run ADK monitor periodically to check for proactive alerts."""
        monitor_session = await adk_session_service.create_session(
            app_name="herdflow-monitor", user_id="system"
        )
        monitor_runner = Runner(
            agent=adk_agents["monitor"],
            app_name="herdflow-monitor",
            session_service=adk_session_service,
        )
        while True:
            await asyncio.sleep(30)  # check every 30 seconds
            try:
                msg = genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text="Analyze the current scene for concerns.")],
                )
                for event in monitor_runner.run(
                    user_id="system", session_id=monitor_session.id, new_message=msg
                ):
                    if (
                        hasattr(event, "content")
                        and event.content
                        and event.content.parts
                    ):
                        for part in event.content.parts:
                            if (
                                hasattr(part, "text")
                                and part.text
                                and "ALL_CLEAR" not in part.text
                            ):
                                logger.info("[MONITOR] Alert: %s", part.text[:200])
                                await session.say(
                                    f"Attention farmer. {part.text}",
                                    allow_interruptions=True,
                                )
            except Exception:  # noqa: BLE001
                logger.debug("Monitor check failed, will retry")

    # Start background tasks
    asyncio.create_task(
        perception_loop(ctx, scene_builder, scene_queue, video_source, session)
    )
    asyncio.create_task(sampler.run(scene_queue, inject_context))
    asyncio.create_task(monitor_loop())

    # Store relay function for use by the agent's tool handling
    ctx.proc.userdata["relay_to_strategist"] = relay_to_strategist

    # Greet the farmer
    await session.generate_reply()
    logger.info("HerdFlow dual-model session started (voice=2.5-flash, strategy=gemini-3)")


async def perception_loop(
    ctx: JobContext,
    builder: SceneGraphBuilder,
    scene_queue: asyncio.Queue,  # type: ignore[type-arg]
    video_source: FileVideoSource | None = None,
    session: AgentSession | None = None,
) -> None:
    """Run perception pipeline on video frames."""
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

        # Publish to data channels
        try:
            await ctx.room.local_participant.publish_data(
                sg.model_dump_json().encode(), topic="scene_graph"
            )
            overlay = OverlayData(
                frame_id=frame_id,
                boxes=[
                    OverlayBox(
                        track_id=e.track_id, bbox=e.bbox,
                        behavior=e.behavior, flags=e.flags,
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
                "[B8] published: scene_graph + overlay(%d) + %d alerts",
                len(sg.tracked_entities), len(sg.active_alerts),
            )
        except Exception:  # noqa: BLE001
            logger.debug("Data channel publish failed")

        # Proactive alerts via voice
        if session is not None:
            for alert in sg.active_alerts:
                if alert.severity.value in ("alert", "critical"):
                    await session.say(alert.description, allow_interruptions=True)

        with contextlib.suppress(asyncio.QueueFull):
            scene_queue.put_nowait((sg, delta))

        await asyncio.sleep(2.0)


if __name__ == "__main__":
    from livekit.agents.cli import run_app

    run_app(server)
