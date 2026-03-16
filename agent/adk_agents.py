"""HerdFlow ADK tool functions and future agent scaffold.

Current (v1 — hackathon):
    Single root agent (Gemini 2.5 Flash Native Audio) in main.py owns
    voice + video + tools. These tool functions are used directly by it.

Future (v2 — system of records):
    Multi-agent split by trust level and latency:
    - Voice Agent: sees, hears, talks. Low trust (can hallucinate). <1s latency.
    - Analyst Agent: multi-step temporal analysis across days of data.
      Medium trust. 5-15s OK (farmer waits knowingly).
    - Records Agent: write ops (lab results, treatments, vaccinations).
      High trust (must be correct, auditable). Strict validation.
    - Embedding Pipeline: NOT an LLM agent. Gemini multimodal embeddings
      → vector DB → exposes similarity search tool to voice agent.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from google.adk.agents import Agent

if TYPE_CHECKING:
    from agent.reasoning.video_analyst import VideoAnalyst

logger = logging.getLogger("herdflow")

_video_analyst: VideoAnalyst | None = None


def set_video_analyst(analyst: VideoAnalyst) -> None:
    """Wire the video analyst instance for tool access."""
    global _video_analyst
    _video_analyst = analyst

from agent.models import (
    BehaviorRecord,
    DescriptionMatch,
    DescriptionSearchResult,
    EntityHistory,
    HerdStats,
    ZoneHistory,
    ZoneVisit,
)


# ── Tool functions (self-contained mock data, no livekit imports) ──


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


async def get_scene_summary() -> dict:
    """Get the latest visual summary of the camera feed.

    Returns a 2-3 sentence description of what the camera currently shows,
    including animal count, postures, and any notable observations.
    """
    if _video_analyst is None:
        logger.warning("get_scene_summary called but video analyst not initialized")
        return {"summary": "Video analyst not available."}
    return {"summary": _video_analyst.get_summary()}


async def analyze_frame(question: str) -> dict:
    """Analyze the current camera frame to answer a specific visual question.

    Use this for questions about what animals look like, their physical condition,
    or anything requiring visual inspection. Takes a few seconds to process.
    """
    if _video_analyst is None:
        logger.warning("analyze_frame called but video analyst not initialized")
        return {"analysis": "Video analyst not available."}
    result = await _video_analyst.analyze(question)
    return {"analysis": result}


# ── Exported tool list (used by root agent in main.py) ──

herd_tools = [
    search_entity_history, get_herd_stats, find_by_description, get_zone_history,
    get_scene_summary, analyze_frame,
]


# ── Future Agent Scaffold (v2 — system of records) ──
#
# These factories are not wired in yet. They document the planned multi-agent
# split for when HerdFlow evolves beyond real-time monitoring.
#
# Activation criteria:
#   - Analyst: when TrackingHistory spans days (not just current session)
#   - Records: when write operations exist (lab results, treatments, vaccinations)
#   - Embeddings: when Gemini multimodal embeddings are integrated


def create_analyst() -> Agent:
    """Analyst — multi-step temporal analysis via Gemini 3 Flash.

    Activated when the farmer asks questions that span multiple days
    or require correlating data across sources (behavior + labs + embeddings).
    The voice agent delegates here and fills the pause conversationally.

    Trust: medium (reasons over data, can be wrong).
    Latency: 5-15s acceptable (farmer waits knowingly).
    """
    return Agent(
        name="analyst",
        model="gemini-3-flash-preview",
        instruction=(
            "You are HerdFlow's veterinary data analyst. You perform deep, "
            "multi-step analysis across days of animal data.\n\n"
            "When delegated a question:\n"
            "1. Use tools to gather relevant data across the time window.\n"
            "2. Cross-reference behavior patterns with any lab results.\n"
            "3. Compare against breed-specific baselines.\n"
            "4. Return a concise analysis with specific numbers, track IDs, "
            "time ranges, and a recommended triage action.\n\n"
            "You may need multiple sequential tool calls. Take your time — "
            "accuracy matters more than speed."
        ),
        tools=herd_tools,  # Future: + lab_tools + embedding_search
        sub_agents=[],
    )


def create_records_agent() -> Agent:
    """Records Agent — validated write operations for system of records.

    Handles all mutations: registering animals, recording lab results,
    logging treatments, updating vaccination schedules.

    Trust: HIGH (must be correct, auditable). Every write is validated
    against business rules (drug interactions, withdrawal periods,
    compliance requirements) before committing.

    Latency: 2-5s acceptable.
    """
    return Agent(
        name="records",
        model="gemini-3-flash-preview",
        instruction=(
            "You are HerdFlow's records manager. You handle all data entry "
            "operations with strict validation.\n\n"
            "Before any write operation:\n"
            "1. Confirm the animal exists in the registry.\n"
            "2. Validate all fields against schema constraints.\n"
            "3. Check for conflicts (drug interactions, duplicate entries).\n"
            "4. Compute derived fields (withdrawal periods, next due dates).\n"
            "5. Return a confirmation summary for the voice agent to relay.\n\n"
            "NEVER skip validation. NEVER write partial records. If any check "
            "fails, return the specific reason so the farmer can correct it."
        ),
        tools=[],  # Future: register_animal, record_lab_result, log_treatment, etc.
        sub_agents=[],
    )