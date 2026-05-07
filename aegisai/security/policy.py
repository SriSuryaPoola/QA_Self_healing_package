"""Security policy value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SecurityPolicy:
    """Local package policy for autonomous healing decisions."""

    name: str = "balanced"
    allow_runtime_for_medium: bool = True
    allow_runtime_for_high: bool = True
    allow_llm_for_medium: bool = True
    allow_llm_for_high: bool = False
    auto_persist_low: bool = True
    audit_enabled: bool = True
    audit_dir: str = ".aegisai/audit"


@dataclass(frozen=True)
class SecurityDecision:
    runtime_allowed: bool
    llm_allowed: bool
    persistence_allowed: bool
    review_required: bool
    risk_level: RiskLevel
    reason: str
    sanitized: bool = True

    @property
    def policy_label(self) -> str:
        if self.persistence_allowed:
            return "auto_persist"
        if self.review_required:
            return "review_required"
        return "blocked"
