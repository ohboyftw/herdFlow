"""HerdFlow multi-agent system using Google Agent Development Kit.

Three-agent architecture:
- Concierge (Gemini 2.5 Flash): Voice interface, speaks to farmer
- Strategist (Gemini 3 Flash): Scene analysis, tool calls, data queries
- Monitor (Gemini 3 Flash): Proactive alert surveillance, triggers warnings
"""

from __future__ import annotations

from datetime import UTC, datetime

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from agent.models import (
    BehaviorRecord,
    DescriptionMatch,
    DescriptionSearchResult,
    EntityHistory,
    HerdStats,
    ZoneHistory,
    ZoneVisit,
)
from agent.reasoning.prompts import STATIC_PROMPT

# ── Tool functions for the Strategist (self-contained, no livekit imports) ──


def _t(hour: int, minute: int) -> datetime:
    return datetime(2026, 3, 15, hour, minute, 0, tzinfo=UTC)


async def search_entity_history(track_id: str, minutes: int = 60) -> dict:
    """Query behavior history for a specific animal by track ID (e.g. COW-003)."""
    if track_id == "COW-003":
        result = EntityHistory(
            track_id="COW-003",
            records=[
                BehaviorRecord(
                    behavior="walking", zone="feed_area", duration_s=600, started_at=_t(8, 0)
                ),
                BehaviorRecord(
                    behavior="feeding", zone="feed_area", duration_s=1200, started_at=_t(8, 10)
                ),
                BehaviorRecord(
                    behavior="walking", zone="rest_area", duration_s=300, started_at=_t(8, 30)
                ),
                BehaviorRecord(
                    behavior="lying", zone="rest_area", duration_s=4320, started_at=_t(8, 35)
                ),
            ],
            current_behavior="lying",
            current_duration_s=4320,
        )
    else:
        result = EntityHistory(
            track_id=track_id, records=[], current_behavior="standing", current_duration_s=300
        )
    return result.model_dump()


async def get_herd_stats(minutes: int = 60) -> dict:
    """Get aggregate herd statistics — how many fed, lying duration, behavior breakdown."""
    return HerdStats(
        period_minutes=minutes,
        total_animals=8,
        fed_in_period=6,
        not_fed=["COW-003", "COW-007"],
        avg_lying_duration_s=1800,
        alerts_fired=2,
        behavior_breakdown={"standing": 3, "lying": 2, "walking": 1, "feeding": 1, "drinking": 1},
    ).model_dump()


async def find_by_description(description: str) -> dict:
    """Find animals matching a natural language description like 'the brown cow near the fence'."""
    return DescriptionSearchResult(
        matches=[
            DescriptionMatch(
                track_id="COW-005",
                confidence=0.72,
                reason="Located near zone boundary (rest_area edge), closest to fence region",
                current_behavior="standing",
                zone="rest_area",
                centroid=[0.85, 0.45],
            )
        ]
    ).model_dump()


async def get_zone_history(zone: str, minutes: int = 120) -> dict:
    """Get zone occupancy history — who visited which zone and for how long."""
    return ZoneHistory(
        zone=zone,
        period_minutes=minutes,
        visits=[
            ZoneVisit(track_id="COW-001", entered_at=_t(7, 15), duration_s=120),
            ZoneVisit(track_id="COW-004", entered_at=_t(7, 30), duration_s=90),
            ZoneVisit(track_id="COW-002", entered_at=_t(8, 0), duration_s=150),
            ZoneVisit(track_id="COW-006", entered_at=_t(8, 45), duration_s=60),
        ],
        animals_not_visited=["COW-003", "COW-007", "COW-008"],
    ).model_dump()


# ── Agent Definitions ──


def create_strategist() -> Agent:
    """Strategist — data analysis and tool calls via Gemini 3 Flash."""
    return Agent(
        name="strategist",
        model="gemini-3-flash-preview",
        instruction=(
            "You are HerdFlow's data strategist. You analyze livestock scene data "
            "and answer detailed questions about herd health, animal history, zone "
            "occupancy, and feeding patterns.\n\n"
            "When asked a question, use your tools to query the tracking database. "
            "Return concise, factual answers with specific numbers. "
            "Reference animals by track ID (e.g. COW-003).\n\n"
            "Always include: the specific data point, whether it's concerning, "
            "and a recommended action if applicable."
        ),
        tools=[search_entity_history, get_herd_stats, find_by_description, get_zone_history],
        sub_agents=[],
    )


def create_monitor(scene_json: str = "{}") -> Agent:
    """Monitor — proactive alert surveillance via Gemini 3 Flash."""
    return Agent(
        name="monitor",
        model="gemini-3-flash-preview",
        instruction=(
            "You are HerdFlow's alert monitor. Analyze the scene graph for health concerns "
            "and generate brief alert messages.\n\n"
            "Focus on:\n"
            "- Animals lying > 4 hours (potential illness)\n"
            "- High isolation scores > 0.7 (illness or calving)\n"
            "- Animals not feeding > 4 hours\n"
            "- Unusual velocity patterns\n\n"
            "Generate a 1-2 sentence alert ONLY if something needs attention. "
            "If everything looks normal, respond with 'ALL_CLEAR'.\n\n"
            f"Current scene:\n```json\n{scene_json}\n```"
        ),
        tools=[get_herd_stats, search_entity_history],
        sub_agents=[],
    )


def create_concierge(strategist: Agent, scene_json: str = "{}") -> Agent:
    """Concierge — voice interface to the farmer via Gemini 2.5 Flash."""
    prompt = STATIC_PROMPT.replace("{scene_graph_json}", scene_json)
    full_instruction = (
        prompt + "\n\n"
        "DELEGATION RULES:\n"
        "- For specific data questions about animal history, feeding stats, "
        "zone visits, or finding specific animals, delegate to the 'strategist' tool. "
        "Say 'Let me check on that for you' while waiting.\n"
        "- For general observations about what you currently see, answer "
        "directly from the scene context above.\n"
        "- When you receive an alert from the monitor, proactively inform "
        "the farmer with appropriate urgency.\n"
    )
    return Agent(
        name="concierge",
        model="gemini-2.5-flash",
        static_instruction=full_instruction,
        tools=[AgentTool(agent=strategist)],
        sub_agents=[],
    )


def create_herdflow_agents(scene_json: str = "{}") -> dict[str, Agent]:
    """Create all HerdFlow agents and return them."""
    strategist = create_strategist()
    monitor = create_monitor(scene_json)
    concierge = create_concierge(strategist, scene_json)
    return {"concierge": concierge, "strategist": strategist, "monitor": monitor}
