"""Tests for adaptive frame sampler."""

from __future__ import annotations

from agent.reasoning.sampler import AdaptiveFrameSampler
from tests.conftest import make_scene_delta


def test_sampler_rate_limit():
    sampler = AdaptiveFrameSampler(max_fps=2.0, min_interval_ms=200)
    delta_sig = make_scene_delta(new_entities=["COW-009"])

    # First call should always send
    assert sampler.should_send(delta_sig, user_speaking=False, elapsed_ms=1000)

    # Within rate limit should not send
    assert not sampler.should_send(delta_sig, user_speaking=False, elapsed_ms=100)


def test_sampler_user_speaking_overrides_rate_limit():
    sampler = AdaptiveFrameSampler(max_fps=2.0, min_interval_ms=200)
    delta_sig = make_scene_delta(new_entities=["COW-009"])
    # User speaking overrides rate limit
    assert sampler.should_send(delta_sig, user_speaking=True, elapsed_ms=50)
    # Even with no delta, user speaking always triggers
    delta_quiet = make_scene_delta()
    assert sampler.should_send(delta_quiet, user_speaking=True, elapsed_ms=50)


def test_sampler_quiet_scene_no_send():
    sampler = AdaptiveFrameSampler(max_fps=2.0, min_interval_ms=200)
    delta_quiet = make_scene_delta()
    # No significant delta, not speaking — should not send
    assert not sampler.should_send(delta_quiet, user_speaking=False, elapsed_ms=5000)
