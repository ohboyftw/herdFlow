"""Tests for alert rule engine."""

from __future__ import annotations

from agent.alerts.rules import (
    AlertRuleEngine,
    IsolationRule,
    MissedFeedingRule,
    ProlongedLyingRule,
)
from agent.config import settings
from agent.models import Severity
from tests.conftest import make_tracked_entity


def test_prolonged_lying_fires_above_threshold():
    rule = ProlongedLyingRule(threshold_s=3600)
    entity = make_tracked_entity(behavior="lying", behavior_duration_s=4320)
    alert = rule.check(entity)
    assert alert is not None
    assert alert.type == "prolonged_lying"
    assert alert.severity == Severity.WARNING


def test_prolonged_lying_does_not_fire_below_threshold():
    rule = ProlongedLyingRule(threshold_s=3600)
    entity = make_tracked_entity(behavior="lying", behavior_duration_s=1800)
    assert rule.check(entity) is None


def test_prolonged_lying_does_not_fire_for_standing():
    rule = ProlongedLyingRule(threshold_s=3600)
    entity = make_tracked_entity(behavior="standing", behavior_duration_s=5000)
    assert rule.check(entity) is None


def test_isolation_fires_above_threshold():
    rule = IsolationRule(threshold=0.7)
    entity = make_tracked_entity(isolation_score=0.82)
    alert = rule.check(entity)
    assert alert is not None
    assert alert.type == "isolation"


def test_isolation_does_not_fire_below_threshold():
    rule = IsolationRule(threshold=0.7)
    entity = make_tracked_entity(isolation_score=0.3)
    assert rule.check(entity) is None


def test_missed_feeding_fires_above_threshold():
    rule = MissedFeedingRule(threshold_s=14400)
    entity = make_tracked_entity(last_feed_visit_s=18000)
    alert = rule.check(entity)
    assert alert is not None
    assert alert.type == "missed_feeding"
    assert alert.severity == Severity.ALERT


def test_engine_dedup_same_alert():
    engine = AlertRuleEngine(settings)
    entity = make_tracked_entity(
        behavior="lying",
        behavior_duration_s=4320,
        isolation_score=0.82,
        last_feed_visit_s=18000,
    )
    alerts1 = engine.evaluate([entity])
    alerts2 = engine.evaluate([entity])  # same entity, same state
    # Second call should be suppressed by cooldown
    assert len(alerts2) == 0


def test_engine_auto_resolves_cleared_condition():
    engine = AlertRuleEngine(settings)
    # Fire alert
    entity_lying = make_tracked_entity(behavior="lying", behavior_duration_s=4320)
    engine.evaluate([entity_lying])
    assert len(engine._active) > 0

    # Condition clears — cow stands up
    entity_standing = make_tracked_entity(
        behavior="standing",
        behavior_duration_s=0,
        isolation_score=0.2,
        last_feed_visit_s=100,
    )
    engine.evaluate([entity_standing])
    # Active alerts for this entity should be resolved
