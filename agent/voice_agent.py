"""LiveKit Agent entrypoint for HerdFlow — voice process (two-pipe mode).

This is the voice-only process: ADK agent with Gemini Live for voice + tools,
but NO perception pipeline, NO RF-DETR, NO video publishing.

Visual awareness comes via AnalystBridge, which receives summaries and
annotations from the video process over LiveKit data channels.

Audio flow:
  Farmer mic → LiveKit → PCM frames → ADK LiveRequestQueue → Gemini Live
  Gemini Live → audio blobs → ADK events → LiveKit audio source → farmer speaker

Usage: uv run python -m agent.voice_agent dev
"""

from __future__ import annotations

import asyncio
import logging
import os
import time as _time
from pathlib import Path
from typing import Any

# Load .env before any LiveKit imports read os.environ
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# Log file — voice process gets its own log
_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = logging.FileHandler(_log_dir / "herdflow-voice.log", mode="a", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)s  %(message)s"))
_file_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_file_handler)

# Console: INFO only. File gets DEBUG.
logging.getLogger().setLevel(logging.DEBUG)
for _h in logging.getLogger().handlers:
    if isinstance(_h, logging.StreamHandler) and _h is not _file_handler:
        _h.setLevel(logging.INFO)
# Suppress DEBUG from noisy libs
for _name in (
    "asyncio",
    "urllib3",
    "httpcore",
    "httpx",
    "google",
    "grpc",
    "google_adk",
):
    logging.getLogger(_name).setLevel(logging.WARNING)
# Our loggers: INFO to console, DEBUG to file
logging.getLogger("herdflow").setLevel(logging.DEBUG)
logging.getLogger("agent").setLevel(logging.DEBUG)

from google.adk.agents import Agent, LiveRequestQueue  # noqa: E402
from google.adk.runners import RunConfig, Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types as genai_types  # noqa: E402
from livekit.agents import AgentServer, JobContext, JobProcess  # noqa: E402
from livekit.plugins import silero  # noqa: E402
from livekit.plugins.google import STT as GoogleSTT  # noqa: E402, N811
from livekit.rtc import AudioFrame, AudioSource, AudioStream, LocalAudioTrack  # noqa: E402

from agent.adk_agents import herd_tools, set_analyst_bridge  # noqa: E402
from agent.config import settings  # noqa: E402
from agent.reasoning.analyst_bridge import AnalystBridge  # noqa: E402
from agent.reasoning.prompts import STATIC_PROMPT  # noqa: E402

logger = logging.getLogger("herdflow")


# ---------------------------------------------------------------------------
# ADK callback: inject thinking_config into LiveConnectConfig
# ADK's GoogleLlm.connect() copies tools/speech_config but NOT thinking_config.
# ---------------------------------------------------------------------------
def _inject_thinking_config(callback_context: Any, llm_request: Any) -> None:
    """Inject thinking_config into LiveConnectConfig since ADK doesn't copy it."""
    if llm_request.live_connect_config is not None:
        llm_request.live_connect_config.thinking_config = genai_types.ThinkingConfig(
            thinking_budget=0
        )
    if llm_request.config is not None and llm_request.config.thinking_config is None:
        llm_request.config.thinking_config = genai_types.ThinkingConfig(thinking_budget=0)
    return None  # Don't short-circuit, let normal flow continue


server = AgentServer(initialize_process_timeout=60.0)

# Audio config matching Gemini Live API expectations
INPUT_SAMPLE_RATE = 16000  # Gemini Live expects 16kHz PCM input
OUTPUT_SAMPLE_RATE = 24000  # Gemini Live outputs 24kHz PCM audio
NUM_CHANNELS = 1


def setup(proc: JobProcess) -> None:
    """Pre-load models (runs once per worker process). Voice-only: VAD only."""
    # Suppress DEBUG on console in subprocess too
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.setLevel(logging.INFO)

    proc.userdata["vad"] = silero.VAD.load()
    logger.info("HerdFlow voice process started (voice-only, no perception)")


server.setup_fnc = setup


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    """Voice session: ADK agent with Gemini Live + tools, visual data via AnalystBridge."""
    await ctx.connect()

    # AnalystBridge replaces VideoAnalyst — receives data from video process
    bridge = AnalystBridge()
    set_analyst_bridge(bridge)

    # Scene data available via get_scene_summary tool (bridge will cache updates)
    prompt = STATIC_PROMPT.replace(
        "{scene_graph_json}",
        "Scene data available via get_scene_summary tool.",
    )
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

    # Root agent: Gemini 2.5 Flash Native Audio (voice + tools)
    # Disable thinking to reduce latency — thinking adds ~5-10s before audio output
    # NOTE: before_model_callback ensures thinking_config reaches LiveConnectConfig
    # (ADK's GoogleLlm.connect copies tools but NOT thinking_config)
    adk_agent = Agent(
        name="herdflow",
        model="gemini-2.5-flash-native-audio-preview-12-2025",
        static_instruction=prompt + "\n\n" + tool_instruction,
        tools=herd_tools,
        sub_agents=sub_agents,
        before_model_callback=_inject_thinking_config,
        generate_content_config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        ),
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
    )

    # Wait for participant
    participant = await ctx.wait_for_participant()
    logger.info("Participant joined: %s", participant.identity)

    # Start AnalystBridge — subscribe to data channels from video process
    await bridge.start(ctx.room)

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
        _first_audio_logged = False
        _turn_start: float | None = None
        async for event in adk_events:
            try:
                # Handle interruption — clear audio queue when farmer speaks
                if event.interrupted:
                    audio_source.clear_queue()
                    _first_audio_logged = False
                    _turn_start = None
                    logger.info("[ADK] Interrupted — cleared audio queue")
                    continue

                # Audio output comes as inline_data blobs in content parts
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if (
                            part.inline_data
                            and part.inline_data.mime_type
                            and part.inline_data.mime_type.startswith("audio/")
                        ):
                            if part.inline_data.data is None:
                                continue
                            pcm_bytes = part.inline_data.data
                            if not _first_audio_logged:
                                logger.info(
                                    "[LATENCY] First audio frame at %.3f",
                                    _time.monotonic(),
                                )
                                _first_audio_logged = True
                            frame = AudioFrame(
                                data=pcm_bytes,
                                sample_rate=OUTPUT_SAMPLE_RATE,
                                num_channels=NUM_CHANNELS,
                                samples_per_channel=len(pcm_bytes) // 2,
                            )
                            await audio_source.capture_frame(frame)
                        elif part.text:
                            text = part.text.strip()
                            # Filter out thinking/reasoning text
                            if text.startswith("**") or text.startswith("#"):
                                logger.debug("[ADK] Suppressed thinking text: %s", text[:80])
                            else:
                                logger.info("[ADK] Agent said: %s", text[:150])

                # Log tool calls with latency tracking
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.function_call:
                            _turn_start = _time.monotonic()
                            logger.info(
                                "[ADK] Tool call: %s at %.3f",
                                part.function_call.name,
                                _turn_start,
                            )
                        if part.function_response and _turn_start is not None:
                            elapsed = _time.monotonic() - _turn_start
                            logger.info(
                                "[LATENCY] Tool response in %.3fs",
                                elapsed,
                            )
                            _turn_start = None
            except Exception:
                logger.exception("[ADK] Error processing event")

    # Task 3: Async transcription via LiveKit Google STT (parallel, non-blocking)
    async def transcription_loop() -> None:
        """Run STT on farmer's audio, publish transcripts via data channel."""
        import livekit.rtc as rtc

        stt = GoogleSTT(sample_rate=INPUT_SAMPLE_RATE)
        logger.info("[STT] Starting async transcription")

        # Wait for participant audio track
        audio_track = None
        for pub in participant.track_publications.values():
            if pub.track and pub.track.kind == rtc.TrackKind.KIND_AUDIO:
                audio_track = pub.track
                break

        if audio_track is None:
            logger.warning("[STT] No audio track found, waiting for subscription")

            async def _wait_for_track() -> rtc.Track | None:
                event = asyncio.Event()
                found_track: list[rtc.Track] = []

                @ctx.room.on("track_subscribed")
                def _on_track(
                    track: rtc.Track, pub: rtc.RemoteTrackPublication, rp: rtc.RemoteParticipant
                ) -> None:
                    if track.kind == rtc.TrackKind.KIND_AUDIO:
                        found_track.append(track)
                        event.set()

                await asyncio.wait_for(event.wait(), timeout=30)
                return found_track[0] if found_track else None

            audio_track = await _wait_for_track()
            if audio_track is None:
                logger.warning("[STT] Timed out waiting for audio track")
                return

        # Stream audio through STT
        audio_stream = AudioStream(
            track=audio_track, sample_rate=INPUT_SAMPLE_RATE, num_channels=NUM_CHANNELS
        )
        stt_stream = stt.stream()

        async def _feed_stt() -> None:
            async for frame_event in audio_stream:
                stt_stream.push_frame(frame_event.frame)

        asyncio.create_task(_feed_stt())

        import json

        from livekit.agents.stt import SpeechEventType

        async for stt_event in stt_stream:
            if stt_event.type == SpeechEventType.FINAL_TRANSCRIPT:
                text = stt_event.alternatives[0].text if stt_event.alternatives else ""
                if text.strip():
                    logger.info("[STT] FINAL: %s", text)
                    transcript = json.dumps(
                        {
                            "speaker": "farmer",
                            "text": text,
                            "final": True,
                        }
                    )
                    try:
                        await ctx.room.local_participant.publish_data(
                            transcript.encode(), topic="transcript"
                        )
                    except Exception:
                        logger.debug("[STT] Failed to publish transcript")
            elif stt_event.type == SpeechEventType.INTERIM_TRANSCRIPT:
                text = stt_event.alternatives[0].text if stt_event.alternatives else ""
                if text.strip():
                    logger.debug("[STT] interim: %s", text)

    # Scene context: no more periodic injection loop.
    # The agent uses get_scene_summary tool on demand (eliminates thinking loops
    # and context overflow that caused 1011 "Deadline expired" crashes).

    # Start audio-only background tasks (no perception, no video publish)
    asyncio.create_task(audio_input_bridge())
    asyncio.create_task(audio_output_bridge())
    asyncio.create_task(transcription_loop())

    # Pre-fetch scene data for a context-aware greeting
    await asyncio.sleep(5.0)
    scene = bridge.get_summary()
    if "No video feed" not in scene:
        greeting_text = (
            f"You are now connected. The camera currently shows: {scene}. "
            "Greet the farmer briefly and ask what they need."
        )
    else:
        greeting_text = (
            "Greet the farmer. You don't have camera data yet — "
            "mention you're still connecting to the video feed."
        )

    live_queue.send_content(
        genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=greeting_text)],
        )
    )

    logger.info("HerdFlow voice ADK Live session started")

    # Keep the session alive
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    from livekit.agents.cli import run_app

    run_app(server)
