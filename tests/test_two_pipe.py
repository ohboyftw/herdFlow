"""Import tests for two-pipe architecture modules."""

from __future__ import annotations


def test_voice_agent_imports() -> None:
    from agent.voice_agent import server
    assert server is not None


def test_video_agent_imports() -> None:
    from agent.video_agent import main
    assert callable(main)


def test_analyst_bridge_wiring() -> None:
    from agent.adk_agents import set_analyst_bridge, herd_tools
    assert callable(set_analyst_bridge)
    assert len(herd_tools) == 6


def test_launcher_imports() -> None:
    from agent.main import main
    assert callable(main)
