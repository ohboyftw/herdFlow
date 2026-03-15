"""HerdFlow agent — thin wrapper providing persona and tools to LiveKit AgentSession."""

from __future__ import annotations

from livekit.agents import Agent

from agent.reasoning.prompts import STATIC_PROMPT
from agent.reasoning.tools import herd_tools


class HerdFlowAgent(Agent):
    """LiveKit Agent with HerdFlow veterinary persona and scene-query tools."""

    def __init__(self) -> None:
        super().__init__(
            instructions=STATIC_PROMPT,
            tools=herd_tools,
        )
