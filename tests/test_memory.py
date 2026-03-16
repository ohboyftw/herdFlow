"""Tests for ConversationMemory — rolling memory for session rotation."""

from __future__ import annotations

from agent.reasoning.memory import ConversationMemory


class TestConversationMemory:
    def test_empty_carry_over(self) -> None:
        mem = ConversationMemory()
        assert mem.get_carry_over() == ""

    def test_add_observation(self) -> None:
        mem = ConversationMemory(max_observations=3)
        mem.add_observation("5 cows standing")
        mem.add_observation("1 cow lying")
        assert len(mem.observations) == 2
        assert "5 cows standing" in mem.observations

    def test_observation_rolling_window(self) -> None:
        mem = ConversationMemory(max_observations=2)
        mem.add_observation("obs1")
        mem.add_observation("obs2")
        mem.add_observation("obs3")
        assert len(mem.observations) == 2
        assert mem.observations == ["obs2", "obs3"]

    def test_observation_dedup_consecutive(self) -> None:
        mem = ConversationMemory()
        mem.add_observation("same thing")
        mem.add_observation("same thing")
        assert len(mem.observations) == 1

    def test_observation_truncation(self) -> None:
        mem = ConversationMemory()
        long_text = "x" * 500
        mem.add_observation(long_text)
        assert len(mem.observations[0]) == 200

    def test_add_question(self) -> None:
        mem = ConversationMemory(max_questions=2)
        mem.add_question("How are the cows?")
        mem.add_question("Which cow is limping?")
        mem.add_question("What about the weather?")
        assert len(mem.farmer_questions) == 2
        assert "What about the weather?" in mem.farmer_questions

    def test_question_truncation(self) -> None:
        mem = ConversationMemory()
        long_q = "q" * 300
        mem.add_question(long_q)
        assert len(mem.farmer_questions[0]) == 150

    def test_set_alerts(self) -> None:
        mem = ConversationMemory(max_alerts=2)
        mem.set_alerts(["alert1", "alert2", "alert3"])
        assert len(mem.active_alerts) == 2
        assert mem.active_alerts == ["alert2", "alert3"]

    def test_carry_over_with_data(self) -> None:
        mem = ConversationMemory()
        mem.add_observation("5 cows in pasture")
        mem.set_alerts(["COW-005 isolation"])
        mem.add_question("How are the cows?")
        carry = mem.get_carry_over()
        assert "[SESSION MEMORY" in carry
        assert "5 cows in pasture" in carry
        assert "COW-005 isolation" in carry
        assert "How are the cows?" in carry
        assert "Do not re-introduce yourself" in carry

    def test_carry_over_partial_data(self) -> None:
        mem = ConversationMemory()
        mem.add_observation("3 cows standing")
        carry = mem.get_carry_over()
        assert "3 cows standing" in carry
        assert "alerts" not in carry.lower()

    def test_clear(self) -> None:
        mem = ConversationMemory()
        mem.add_observation("obs")
        mem.add_question("q")
        mem.set_alerts(["a"])
        mem.clear()
        assert mem.observations == []
        assert mem.farmer_questions == []
        assert mem.active_alerts == []
        assert mem.get_carry_over() == ""
