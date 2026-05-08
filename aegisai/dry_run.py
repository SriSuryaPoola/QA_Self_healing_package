"""Audit-only and dry-run healing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aegisai.sdk import AegisAI


@dataclass(frozen=True)
class DryRunResult:
    original_locator: str
    suggested_locator: str | None
    confidence: float
    source: str
    allowed: bool
    reason: str
    alternatives: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_locator": self.original_locator,
            "suggested_locator": self.suggested_locator,
            "confidence": self.confidence,
            "source": self.source,
            "allowed": self.allowed,
            "reason": self.reason,
            "alternatives": self.alternatives,
        }


def audit_locator(
    *,
    failing_locator: str,
    dom: str,
    expected_role: str | None = None,
    app: AegisAI | None = None,
) -> DryRunResult:
    """Analyze a locator against a DOM snapshot without interacting or patching."""

    active_app = app or AegisAI()
    result = active_app.heal_locator(
        failing_locator=failing_locator,
        dom=dom,
        expected_role=expected_role,
        use_cache=False,
    )
    guardrail = result.guardrail
    return DryRunResult(
        original_locator=failing_locator,
        suggested_locator=result.locator,
        confidence=result.confidence,
        source=result.source,
        allowed=bool(guardrail.allowed) if guardrail else False,
        reason=guardrail.reason if guardrail else "No guardrail result.",
        alternatives=[
            {
                "locator": candidate.locator,
                "confidence": candidate.confidence,
                "reason": candidate.reason,
            }
            for candidate in result.alternatives[:5]
        ],
    )
