"""Rolling conversation memory for session rotation.

Captures key facts from tool results and user queries so they can be
carried forward when the ADK session is recycled (every ~8 min to avoid
the Gemini Live API 10-minute session deadline).

This is the "why" layer for voice context — lightweight enough to inject
into a system prompt, rich enough to maintain conversation continuity.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("herdflow.memory")


class ConversationMemory:
    """Lightweight rolling memory — survives ADK session rotation."""

    def __init__(
        self,
        max_observations: int = 5,
        max_questions: int = 3,
        max_alerts: int = 3,
    ) -> None:
        self.observations: list[str] = []
        self.active_alerts: list[str] = []
        self.farmer_questions: list[str] = []
        self._max_obs = max_observations
        self._max_q = max_questions
        self._max_alerts = max_alerts

    def add_observation(self, text: str) -> None:
        """Record a scene observation or tool result summary."""
        short = text[:200]
        if self.observations and self.observations[-1] == short:
            return  # dedup consecutive identical observations
        self.observations.append(short)
        self.observations = self.observations[-self._max_obs :]

    def add_question(self, question: str) -> None:
        """Record a farmer question for context continuity."""
        short = question[:150]
        self.farmer_questions.append(short)
        self.farmer_questions = self.farmer_questions[-self._max_q :]

    def set_alerts(self, alerts: list[str]) -> None:
        """Replace current alert list."""
        self.active_alerts = alerts[-self._max_alerts :]

    def get_carry_over(self) -> str:
        """Build a compact carry-over prompt for session rotation."""
        parts: list[str] = []
        if self.observations:
            parts.append("Recent observations: " + "; ".join(self.observations))
        if self.active_alerts:
            parts.append("Active alerts: " + "; ".join(self.active_alerts))
        if self.farmer_questions:
            parts.append(
                "Farmer recently asked about: " + "; ".join(self.farmer_questions)
            )
        if not parts:
            return ""
        return (
            "[SESSION MEMORY — carried from previous session]\n"
            + "\n".join(parts)
            + "\nContinue the conversation naturally. "
            "Do not re-introduce yourself."
        )

    def clear(self) -> None:
        """Reset all memory."""
        self.observations.clear()
        self.active_alerts.clear()
        self.farmer_questions.clear()
