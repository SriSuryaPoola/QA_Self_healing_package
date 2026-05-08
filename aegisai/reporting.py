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

    def layer_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.events:
            counts[event.layer_label] = counts.get(event.layer_label, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "summary": {
                "total": len(self.events),
                "success": self.success_count,
                "failure": self.failure_count,
                "layers": self.layer_counts(),
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
        "layers": summary.get("layers", {}),
    }
