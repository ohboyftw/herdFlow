"""Alert rule engine for HerdFlow livestock monitoring."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from agent.config import Settings
from agent.models import Alert, Severity, TrackedEntity

logger = logging.getLogger(__name__)


class ProlongedLyingRule:
    """Fires when an entity has been lying longer than the threshold."""

    def __init__(self, threshold_s: float = 3600) -> None:
        self.threshold_s = threshold_s

    def check(self, entity: TrackedEntity) -> Alert | None:
        if entity.behavior == "lying" and entity.behavior_duration_s > self.threshold_s:
            hours = entity.behavior_duration_s / 3600
            return Alert(
                type="prolonged_lying",
                severity=Severity.WARNING,
                entity_track_id=entity.track_id,
                description=(f"{entity.track_id} has been lying for {hours:.1f} hours"),
            )
        return None


class IsolationRule:
    """Fires when an entity's isolation score exceeds the threshold."""

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = threshold

    def check(self, entity: TrackedEntity) -> Alert | None:
        if entity.isolation_score > self.threshold:
            return Alert(
                type="isolation",
                severity=Severity.WARNING,
                entity_track_id=entity.track_id,
                description=(
                    f"{entity.track_id} isolation score {entity.isolation_score:.2f}"
                    f" exceeds threshold {self.threshold:.2f}"
                ),
            )
        return None


class MissedFeedingRule:
    """Fires when an entity has not visited the feed area within the threshold."""

    def __init__(self, threshold_s: float = 14400) -> None:
        self.threshold_s = threshold_s

    def check(self, entity: TrackedEntity) -> Alert | None:
        if entity.last_feed_visit_s > self.threshold_s:
            hours = entity.last_feed_visit_s / 3600
            return Alert(
                type="missed_feeding",
                severity=Severity.ALERT,
                entity_track_id=entity.track_id,
                description=(
                    f"{entity.track_id} has not visited the feed area in {hours:.1f} hours"
                ),
            )
        return None


class AlertRuleEngine:
    """Evaluates all alert rules against tracked entities.

    Deduplicates alerts by key and auto-resolves when conditions clear.
    """

    def __init__(self, config: Settings) -> None:
        self._rules = [
            ProlongedLyingRule(threshold_s=config.alert_prolonged_lying_s),
            IsolationRule(threshold=config.alert_isolation_threshold),
            MissedFeedingRule(threshold_s=config.alert_missed_feeding_s),
        ]
        self._active: dict[str, Alert] = {}

    def evaluate(self, entities: list[TrackedEntity]) -> list[Alert]:
        """Run all rules on all entities, returning only new alerts.

        Deduplicates against active alerts (cooldown) and auto-resolves
        alerts whose conditions are no longer met.
        """
        # Collect all alerts fired in this evaluation pass
        fired: dict[str, Alert] = {}
        for entity in entities:
            for rule in self._rules:
                alert = rule.check(entity)
                if alert is not None:
                    fired[alert.key] = alert

        # Auto-resolve: mark active alerts whose condition is no longer met
        resolved_keys = set(self._active.keys()) - set(fired.keys())
        for key in resolved_keys:
            logger.info("[B5] alert resolved: %s", key)
            self._active[key].resolved = True
            self._active[key].resolved_at = datetime.now(UTC)
            del self._active[key]

        # Dedup: suppress alerts already active (cooldown)
        new_alerts: list[Alert] = []
        for key, alert in fired.items():
            if key not in self._active:
                self._active[key] = alert
                new_alerts.append(alert)
                logger.info("[B4->B5] new alert: %s (%s)", alert.key, alert.severity.value)

        logger.debug(
            "[B4->B5] evaluate: %d entities, %d fired, %d new, %d active",
            len(entities),
            len(fired),
            len(new_alerts),
            len(self._active),
        )
        return new_alerts
