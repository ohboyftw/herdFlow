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
import os
from pathlib import Path

# Load .env before any LiveKit imports read os.environ
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())
import logging

# Log file — timestamped per session (avoids Windows file locking on rotation)
_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = logging.FileHandler(
    _log_dir / "herdflow.log", mode="a", encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)s  %(message)s"))
_file_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_file_handler)

# Console: INFO only. File gets DEBUG.
# Set root to DEBUG (file captures everything), then force all
# console/stream handlers to INFO. Also suppress noisy loggers.
logging.getLogger().setLevel(logging.DEBUG)
for _h in logging.getLogger().handlers:
    if isinstance(_h, logging.StreamHandler) and _h is not _file_handler:
        _h.setLevel(logging.INFO)
# Suppress DEBUG from noisy libs
for _name in ("asyncio", "urllib3", "httpcore", "httpx", "google", "grpc", "google_adk"):
    logging.getLogger(_name).setLevel(logging.WARNING)
# Our loggers: INFO to console, DEBUG to file
logging.getLogger("herdflow").setLevel(logging.DEBUG)
logging.getLogger("agent").setLevel(logging.DEBUG)

import numpy as np
from google.adk.agents import Agent, LiveRequestQueue
from google.adk.runners import RunConfig, Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from livekit.agents import AgentServer, JobContext, JobProcess
from livekit.plugins import silero
from livekit.rtc import AudioFrame, AudioSource, AudioStream, LocalAudioTrack

from agent.adk_agents import herd_tools, set_video_analyst
from agent.alerts.rules import AlertRuleEngine
from agent.config import settings
from agent.models import OverlayBox, OverlayData
from agent.perception.detector import MockDetector
from agent.perception.scene_graph import SceneGraphBuilder
from agent.perception.tracker import Tracker
from agent.perception.video_source import FileVideoSource
from agent.reasoning.prompts import STATIC_PROMPT
from agent.reasoning.video_analyst import VideoAnalyst

logger = logging.getLogger("herdflow")

server = AgentServer()

# Audio config matching Gemini Live API expectations
INPUT_SAMPLE_RATE = 16000   # Gemini Live expects 16kHz PCM input
OUTPUT_SAMPLE_RATE = 24000  # Gemini Live outputs 24kHz PCM audio
NUM_CHANNELS = 1


def setup(proc: JobProcess) -> None:
    """Pre-load models (runs once per worker process)."""
    # Suppress DEBUG on console in subprocess too
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.setLevel(logging.INFO)

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
    # Get initial scene context
    frame_iter = video_source.frames() if video_source else None
    if frame_iter is not None:
        initial_frame = await asyncio.to_thread(next, frame_iter)
    else:
        initial_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    initial_sg = await scene_builder.process_frame(initial_frame, frame_id=0)
    scene_json = initial_sg.model_dump_json(indent=2)
    logger.info("Initial scene: %d entities", len(initial_sg.tracked_entities))

    video_analyst = VideoAnalyst(
        background_model=settings.video_analyst_background_model,
        on_demand_model=settings.video_analyst_on_demand_model,
        summary_interval_s=settings.video_analyst_summary_interval_s,
    )
    set_video_analyst(video_analyst)

    # Create ADK agent system
    prompt = STATIC_PROMPT.replace("{scene_graph_json}", scene_json)
    # herd_tools imported from adk_agents (6 tools including visual analysis)

    # Optional: Gemini 3 Flash sub-agent for deep multi-step analysis (v2)
    sub_agents: list[Agent] = []
    tool_instruction = (
        "TOOL USAGE:\n"
        "Use your tools directly to answer data questions about animals, "
        "herd stats, zone history, and finding specific animals.\n"
    )
    if settings.enable_analyst_subagent:
        analyst = Agent(
            name="analyst",
            model="gemini-3-flash-preview",
            static_instruction=(
                "You are a veterinary data analyst. When delegated a question, "
                "use your tools to query the tracking database and return a "
                "detailed, factual analysis. Include specific numbers, track IDs, "
                "time durations, and recommended actions."
            ),
            tools=herd_tools,
            sub_agents=[],
        )
        sub_agents = [analyst]
        tool_instruction = (
            "TOOL USAGE:\n"
            "- For quick lookups (single animal status, herd count), use your "
            "tools directly and respond immediately.\n"
            "- For complex analysis (full health reports, trend analysis, "
            "cross-animal comparisons), delegate to the 'analyst' sub-agent "
            "who has deeper reasoning capabilities.\n"
        )
        logger.info("Analyst sub-agent enabled (gemini-3-flash-preview)")

    # Root agent: Gemini 2.5 Flash Native Audio (voice + video + tools)
    adk_agent = Agent(
        name="herdflow",
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        static_instruction=prompt + "\n\n" + tool_instruction,
        tools=herd_tools,
        sub_agents=sub_agents,
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
    audio_source = AudioSource(OUTPUT_SAMPLE_RATE, NUM_CHANNELS)
    audio_track = LocalAudioTrack.create_audio_track("agent-voice", audio_source)
    publication = await ctx.room.local_participant.publish_track(audio_track)
    logger.info("Published audio track: %s", publication.sid)

    # ADK live request queue — the audio bridge
    live_queue = LiveRequestQueue()

    # Run config for Gemini Live with audio
    run_config = RunConfig(
        response_modalities=["AUDIO"],
        speech_config=genai_types.SpeechConfig(
            voice_config=genai_types.VoiceConfig(
                prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        ),
        output_audio_transcription=genai_types.AudioTranscriptionConfig(),
        input_audio_transcription=genai_types.AudioTranscriptionConfig(),
        # Context compression — without this, audio tokens fill the window and session drops
        context_window_compression=genai_types.ContextWindowCompressionConfig(
            sliding_window=genai_types.SlidingWindow(
                target_tokens=100_000,
            ),
        ),
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
        import livekit.rtc as rtc

        async def _stream_audio(audio_track: rtc.Track) -> None:
            audio_stream = AudioStream(
                track=audio_track, sample_rate=INPUT_SAMPLE_RATE, num_channels=NUM_CHANNELS
            )
            logger.info("[BRIDGE] Streaming participant audio to ADK")
            async for frame_event in audio_stream:
                frame: AudioFrame = frame_event.frame
                pcm_data = bytes(frame.data)
                blob = genai_types.Blob(
                    mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}",
                    data=pcm_data,
                )
                live_queue.send_realtime(blob)

        logger.info("[BRIDGE] Waiting for participant audio track...")
        # Check existing tracks first
        for pub in participant.track_publications.values():
            if pub.track and pub.track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info("[BRIDGE] Found existing audio track, subscribing")
                asyncio.create_task(_stream_audio(pub.track))
                return

        # If no track yet, listen for new tracks
        logger.info("[BRIDGE] No audio track yet, waiting for track_subscribed event")

        @ctx.room.on("track_subscribed")
        def on_track(
            track: rtc.Track,
            publication: rtc.RemoteTrackPublication,
            remote_participant: rtc.RemoteParticipant,
        ) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info("[BRIDGE] Audio track subscribed via event")
                asyncio.create_task(_stream_audio(track))

    # Task 2: Pipe ADK output audio → LiveKit
    async def audio_output_bridge() -> None:
        """Read ADK events and send audio responses to LiveKit."""
        logger.info("[BRIDGE] Listening for ADK audio output...")
        async for event in adk_events:
            try:
                # Audio output comes as inline_data blobs in content parts
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                            pcm_bytes = part.inline_data.data
                            frame = AudioFrame(
                                data=pcm_bytes,
                                sample_rate=OUTPUT_SAMPLE_RATE,
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
            except Exception:
                logger.exception("[ADK] Error processing event")

    # Start all background tasks
    asyncio.create_task(audio_input_bridge())
    asyncio.create_task(audio_output_bridge())
    asyncio.create_task(
        perception_loop(ctx, scene_builder, video_source, video_analyst=video_analyst)
    )
    asyncio.create_task(video_analyst.run_background_loop())

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
    video_source: FileVideoSource | None = None,
    video_analyst: VideoAnalyst | None = None,
) -> None:
    """Run perception pipeline on video frames and feed VideoAnalyst."""
    frame_id = 0
    frame_iter = video_source.frames() if video_source else None

    while True:
        frame_id += 1
        if frame_iter is not None:
            frame = await asyncio.to_thread(next, frame_iter)
        else:
            frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

        sg = await builder.process_frame(frame, frame_id)
        if video_analyst is not None:
            video_analyst.update(frame, sg)


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

        await asyncio.sleep(2.0)


if __name__ == "__main__":
    from livekit.agents.cli import run_app

    run_app(server)
