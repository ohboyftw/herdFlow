"""LiveKit Agent entrypoint for HerdFlow.

Deep ADK+LiveKit integration: ADK agent manages the Gemini Live session
with tool support. LiveKit provides the WebRTC audio transport.

Audio flow:
  Farmer mic → LiveKit → PCM frames → ADK LiveRequestQueue → Gemini Live
  Gemini Live → audio blobs → ADK events → LiveKit audio source → farmer speaker

This gives us voice + tool calls in a SINGLE Gemini session (no relay overhead).

Usage: uv run python -m agent.main dev
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import numpy as np
from google.adk.agents import Agent, LiveRequestQueue
from google.adk.runners import RunConfig, Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from livekit.agents import AgentServer, JobContext, JobProcess
from livekit.plugins import silero
from livekit.rtc import AudioFrame, AudioSource, AudioStream

from agent.adk_agents import (
    find_by_description,
    get_herd_stats,
    get_zone_history,
    search_entity_history,
)
from agent.alerts.rules import AlertRuleEngine
from agent.config import settings
from agent.models import OverlayBox, OverlayData
from agent.perception.detector import MockDetector
from agent.perception.scene_graph import SceneGraphBuilder
from agent.perception.tracker import Tracker
from agent.perception.video_source import FileVideoSource
from agent.reasoning.prompts import STATIC_PROMPT
from agent.reasoning.sampler import AdaptiveFrameSampler

logger = logging.getLogger("herdflow")

server = AgentServer()

# Audio config matching Gemini Live API expectations
SAMPLE_RATE = 16000
NUM_CHANNELS = 1
FRAME_DURATION_MS = 100  # 100ms chunks


def setup(proc: JobProcess) -> None:
    """Pre-load models (runs once per worker process)."""
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
        "HerdFlow started (detector=%s, video=%s)",
        type(proc.userdata["detector"]).__name__,
        settings.demo_video_path,
    )


server.setup_fnc = setup


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    """Main session: ADK agent as LiveKit participant with Gemini Live + tools."""
    await ctx.connect()

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

    # Get initial scene context
    frame_iter = video_source.frames() if video_source else None
    if frame_iter is not None:
        initial_frame = next(frame_iter)
    else:
        initial_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    initial_sg = await scene_builder.process_frame(initial_frame, frame_id=0)
    scene_json = initial_sg.model_dump_json(indent=2)
    logger.info("Initial scene: %d entities", len(initial_sg.tracked_entities))

    # Create ADK multi-agent system
    prompt = STATIC_PROMPT.replace("{scene_graph_json}", scene_json)

    # Gemini 3 Flash sub-agent for deep analysis
    analyst = Agent(
        name="analyst",
        model="gemini-3-flash-preview",
        static_instruction=(
            "You are a veterinary data analyst. When delegated a question, "
            "use your tools to query the tracking database and return a "
            "detailed, factual analysis. Include specific numbers, track IDs, "
            "time durations, and recommended actions."
        ),
        tools=[
            search_entity_history,
            get_herd_stats,
            find_by_description,
            get_zone_history,
        ],
        sub_agents=[],
    )

    # Root agent: Gemini 2.5 Flash Native Audio (voice + tools + delegation)
    adk_agent = Agent(
        name="herdflow",
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        static_instruction=(
            prompt + "\n\n"
            "TOOL USAGE:\n"
            "- For quick lookups (single animal status, herd count), use your "
            "tools directly and respond immediately.\n"
            "- For complex analysis (full health reports, trend analysis, "
            "cross-animal comparisons), delegate to the 'analyst' sub-agent "
            "who has deeper reasoning capabilities.\n"
        ),
        tools=[
            search_entity_history,
            get_herd_stats,
            find_by_description,
            get_zone_history,
        ],
        sub_agents=[analyst],
    )

    # Set up ADK runner
    adk_session_service = InMemorySessionService()
    adk_session = await adk_session_service.create_session(app_name="herdflow", user_id="farmer")
    adk_runner = Runner(
        agent=adk_agent,
        app_name="herdflow",
        session_service=adk_session_service,
    )

    # LiveKit audio source for sending agent speech to the room
    audio_source = AudioSource(SAMPLE_RATE, NUM_CHANNELS)
    track = await ctx.room.local_participant.publish_audio(audio_source)
    logger.info("Published audio track: %s", track.sid)

    # ADK live request queue — the audio bridge
    live_queue = LiveRequestQueue()

    # Run config for Gemini Live with audio (per best practices)
    run_config = RunConfig(
        response_modalities=["AUDIO"],
        speech_config=genai_types.SpeechConfig(
            voice_config=genai_types.VoiceConfig(
                prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        ),
        output_audio_transcription=genai_types.AudioTranscriptionConfig(),
        input_audio_transcription=genai_types.AudioTranscriptionConfig(),
        # Context window compression — audio tokens accumulate at ~25/sec
        # Without this, sessions limited to ~15 min audio-only
        context_window_compression=genai_types.ContextWindowCompressionConfig(
            sliding_window=genai_types.SlidingWindow(
                target_token_count=100_000,
            ),
        ),
        # Session resumption for reconnection without losing context
        session_resumption=genai_types.SessionResumptionConfig(handle=None),
        # Proactivity — agent can initiate speech on alerts
        proactivity=genai_types.ProactivityConfig(
            proactive_audio=True,
        ),
        # Affective dialog — natural emotional tone
        enable_affective_dialog=True,
    )

    # Wait for participant
    participant = await ctx.wait_for_participant()
    logger.info("Participant joined: %s", participant.identity)

    # Start the ADK live session (async generator)
    adk_events = adk_runner.run_live(
        user_id="farmer",
        session_id=adk_session.id,
        live_request_queue=live_queue,
        run_config=run_config,
    )

    # Task 1: Pipe LiveKit incoming audio → ADK
    async def audio_input_bridge() -> None:
        """Read audio from LiveKit participant and feed to ADK."""
        logger.info("[BRIDGE] Waiting for participant audio track...")
        # Wait for the participant's audio track
        for pub in participant.track_publications.values():
            if pub.track and pub.track.kind.name == "KIND_AUDIO":
                audio_stream = AudioStream(track=pub.track)
                logger.info("[BRIDGE] Subscribed to participant audio")
                async for frame_event in audio_stream:
                    frame: AudioFrame = frame_event.frame
                    pcm_data = bytes(frame.data)
                    blob = genai_types.Blob(
                        mime_type="audio/pcm;rate=16000",
                        data=pcm_data,
                    )
                    live_queue.send_realtime(blob)
                return

        # If no track yet, listen for new tracks
        import livekit.rtc as rtc

        @ctx.room.on("track_subscribed")
        def on_track(
            track: rtc.Track,
            publication: rtc.RemoteTrackPublication,
            remote_participant: rtc.RemoteParticipant,
        ) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                asyncio.create_task(_stream_audio(track))

        async def _stream_audio(audio_track: rtc.Track) -> None:
            audio_stream = AudioStream(track=audio_track)
            logger.info("[BRIDGE] Streaming participant audio to ADK")
            async for frame_event in audio_stream:
                frame: AudioFrame = frame_event.frame
                pcm_data = bytes(frame.data)
                blob = genai_types.Blob(
                    mime_type="audio/pcm;rate=16000",
                    data=pcm_data,
                )
                live_queue.send_realtime(blob)

    # Task 2: Pipe ADK output audio → LiveKit
    async def audio_output_bridge() -> None:
        """Read ADK events and send audio responses to LiveKit."""
        logger.info("[BRIDGE] Listening for ADK audio output...")
        async for event in adk_events:
            # Audio output comes as inline_data blobs in content parts
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                        pcm_bytes = part.inline_data.data
                        frame = AudioFrame(
                            data=pcm_bytes,
                            sample_rate=SAMPLE_RATE,
                            num_channels=NUM_CHANNELS,
                            samples_per_channel=len(pcm_bytes) // 2,
                        )
                        await audio_source.capture_frame(frame)
                    elif part.text:
                        logger.info("[ADK] Agent said: %s", part.text[:150])

            # Log transcriptions
            if event.input_transcription and event.input_transcription.text:
                logger.info("[ADK] Farmer: %s", event.input_transcription.text)
            if event.output_transcription and event.output_transcription.text:
                logger.info("[ADK] Agent: %s", event.output_transcription.text)

            # Log tool calls
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call:
                        logger.info("[ADK] Tool call: %s", part.function_call.name)

    # Context injection for scene updates
    async def inject_context(scene_json_str: str) -> None:
        new_prompt = STATIC_PROMPT.replace("{scene_graph_json}", scene_json_str)
        live_queue.send_content(
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=f"[SCENE UPDATE]\n{new_prompt}")],
            )
        )

    # Start all background tasks
    asyncio.create_task(audio_input_bridge())
    asyncio.create_task(audio_output_bridge())
    asyncio.create_task(perception_loop(ctx, scene_builder, scene_queue, video_source, live_queue))
    asyncio.create_task(sampler.run(scene_queue, inject_context))

    # Send initial greeting request
    live_queue.send_content(
        genai_types.Content(
            role="user",
            parts=[
                genai_types.Part(
                    text="Greet the farmer. Introduce yourself and briefly "
                    "describe what you see in the current scene."
                )
            ],
        )
    )

    logger.info("HerdFlow ADK Live session started (model=gemini-2.5-flash-native-audio)")

    # Keep the session alive
    while True:
        await asyncio.sleep(1)


async def perception_loop(
    ctx: JobContext,
    builder: SceneGraphBuilder,
    scene_queue: asyncio.Queue,  # type: ignore[type-arg]
    video_source: FileVideoSource | None = None,
    live_queue: LiveRequestQueue | None = None,
) -> None:
    """Run perception pipeline on video frames + send frames to Gemini Live."""
    import io

    from PIL import Image

    frame_id = 0
    prev_sg = None
    frame_iter = video_source.frames() if video_source else None

    # Adaptive video FPS for Gemini: send every Nth frame
    # Gemini Live processes ~25 tokens/sec for video; 1-2 FPS is optimal
    video_send_interval = 4  # send every 4th frame (~0.5 FPS at 2s loop)

    while True:
        frame_id += 1
        if frame_iter is not None:
            frame = next(frame_iter)
        else:
            frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

        # Send video frame to Gemini Live (adaptive FPS)
        if live_queue is not None and frame_id % video_send_interval == 0:
            try:
                img = Image.fromarray(frame)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=60)
                live_queue.send_realtime(
                    genai_types.Blob(
                        mime_type="image/jpeg",
                        data=buf.getvalue(),
                    )
                )
                logger.debug(
                    "[VIDEO] Sent frame %d to Gemini (%d bytes)",
                    frame_id,
                    buf.tell(),
                )
            except Exception:  # noqa: BLE001
                logger.debug("Video frame send failed")

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
        except Exception:  # noqa: BLE001
            logger.debug("Data channel publish failed")

        with contextlib.suppress(asyncio.QueueFull):
            scene_queue.put_nowait((sg, delta))

        await asyncio.sleep(2.0)


if __name__ == "__main__":
    from livekit.agents.cli import run_app

    run_app(server)
