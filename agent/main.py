"""LiveKit Agent entrypoint for HerdFlow.

Phase 2 (mock mode): Static scene graph, no perception pipeline.
Phases 4+: Real detection, tracking, adaptive sampling.
"""

from __future__ import annotations

import logging

from livekit.agents import AgentServer, AgentSession
from livekit.plugins import google, silero

from agent.herdflow_agent import HerdFlowAgent
from agent.reasoning.prompts import build_system_prompt

# Build a mock scene graph for Phase 2
from tests.conftest import make_scene_graph

logger = logging.getLogger("herdflow")

server = AgentServer()


@server.on_process_started
async def on_process_started(proc: AgentServer.Process) -> None:
    """Pre-load VAD model."""
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("HerdFlow agent process started (mock mode)")


@server.rtc_session()
async def entrypoint(ctx: AgentServer.SessionContext) -> None:
    vad = ctx.proc.userdata["vad"]

    # Mock scene graph for Phase 2
    mock_sg = make_scene_graph(entities=8, alerts=1)
    prompt = build_system_prompt(mock_sg.model_dump_json(indent=2))

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
    agent._instructions = prompt  # inject mock scene graph

    await session.start(
        room=ctx.room,
        agent=agent,
    )

    # Greet the farmer
    await session.generate_reply()
    logger.info("HerdFlow agent session started")
