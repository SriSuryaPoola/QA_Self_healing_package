"""Session-level healing reports for local debugging and CI artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class HealingEvent:
    """One attempted healing decision."""

    original_locator: str
    healed_locator: str | None
    success: bool
    source: str
    layer_label: str = "sdk"
    confidence: float = 0.0
    risk_level: str = "unknown"
    duration_ms: float = 0.0
    persistence_decision: str = "not_applicable"
    reason: str = ""
    framework: str = "generic"
    action: str = "heal"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HealingReport:
    """Collect healing activity for a single local run."""

    session_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    events: list[HealingEvent] = field(default_factory=list)

    def record(self, event: HealingEvent) -> HealingEvent:
        self.events.append(event)
        return event

    def record_attempt(
        self,
        *,
        original_locator: str,
        healed_locator: str | None,
        success: bool,
        source: str,
        layer_label: str = "sdk",
        confidence: float = 0.0,
        risk_level: str = "unknown",
        duration_ms: float = 0.0,
        persistence_decision: str = "not_applicable",
        reason: str = "",
        framework: str = "generic",
        action: str = "heal",
        metadata: dict[str, Any] | None = None,
    ) -> HealingEvent:
        return self.record(
            HealingEvent(
                original_locator=original_locator,
                healed_locator=healed_locator,
                success=success,
                source=source,
                layer_label=layer_label,
                confidence=confidence,
                risk_level=risk_level,
                duration_ms=round(duration_ms, 3),
                persistence_decision=persistence_decision,
                reason=reason,
                framework=framework,
                action=action,
                metadata=metadata or {},
            )
        )

    @property
    def success_count(self) -> int:
        return sum(1 for event in self.events if event.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for event in self.events if not event.success)

    @property
    def success_rate(self) -> float:
        return _rate(self.success_count, len(self.events))

    @property
    def average_confidence(self) -> float:
        return _average(event.confidence for event in self.events)

    @property
    def average_duration_ms(self) -> float:
        return _average(event.duration_ms for event in self.events)

    @property
    def p95_duration_ms(self) -> float:
        return _percentile([event.duration_ms for event in self.events], 95)

    def layer_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.layer_label] = counts.get(event.layer_label, 0) + 1
        return counts

    def layer_metrics(self) -> dict[str, dict[str, float | int]]:
        grouped: dict[str, list[HealingEvent]] = {}
        for event in self.events:
            grouped.setdefault(event.layer_label, []).append(event)

        metrics: dict[str, dict[str, float | int]] = {}
        for layer, events in sorted(grouped.items()):
            successes = sum(1 for event in events if event.success)
            metrics[layer] = {
                "total": len(events),
                "success": successes,
                "failure": len(events) - successes,
                "success_rate": _rate(successes, len(events)),
                "avg_confidence": _average(event.confidence for event in events),
                "avg_duration_ms": _average(event.duration_ms for event in events),
                "p95_duration_ms": _percentile([event.duration_ms for event in events], 95),
            }
        return metrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "summary": {
                "total": len(self.events),
                "success": self.success_count,
                "failure": self.failure_count,
                "success_rate": self.success_rate,
                "avg_confidence": self.average_confidence,
                "avg_duration_ms": self.average_duration_ms,
                "p95_duration_ms": self.p95_duration_ms,
                "layers": self.layer_counts(),
                "layer_metrics": self.layer_metrics(),
            },
            "events": [event.to_dict() for event in self.events],
        }

    def write_json(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return target


_SESSION_REPORT = HealingReport()


def get_session_report() -> HealingReport:
    """Return the process-wide report used by convenience integrations."""

    return _SESSION_REPORT


def reset_session_report() -> HealingReport:
    """Reset and return the process-wide report."""

    global _SESSION_REPORT
    _SESSION_REPORT = HealingReport()
    return _SESSION_REPORT


def summarize_report(report: HealingReport | dict[str, Any]) -> dict[str, Any]:
    """Return the compact summary used by the CLI."""

    payload = report.to_dict() if isinstance(report, HealingReport) else report
    summary = payload.get("summary", {})
    return {
        "session_id": payload.get("session_id"),
        "total": summary.get("total", 0),
        "success": summary.get("success", 0),
        "failure": summary.get("failure", 0),
        "success_rate": summary.get("success_rate", 0.0),
        "avg_confidence": summary.get("avg_confidence", 0.0),
        "avg_duration_ms": summary.get("avg_duration_ms", 0.0),
        "p95_duration_ms": summary.get("p95_duration_ms", 0.0),
        "layers": summary.get("layers", {}),
        "layer_metrics": summary.get("layer_metrics", {}),
    }


def _average(values: Any) -> float:
    numeric = [float(value) for value in values]
    if not numeric:
        return 0.0
    return round(sum(numeric) / len(numeric), 4)


def _percentile(values: list[float], percentile: int) -> float:
    numeric = sorted(float(value) for value in values)
    if not numeric:
        return 0.0
    if len(numeric) == 1:
        return round(numeric[0], 4)

    position = (len(numeric) - 1) * (percentile / 100)
    lower = int(position)
    upper = min(lower + 1, len(numeric) - 1)
    weight = position - lower
    value = numeric[lower] * (1 - weight) + numeric[upper] * weight
    return round(value, 4)


def _rate(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total, 4)
