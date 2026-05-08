"""Shared value objects for the AegisAI SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DomElement:
    """A small, filtered representation of an element in the local DOM subset."""

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    text: str = ""
    role: str | None = None
    index: int = 0
    path: str | None = None

    def stable_locator(self) -> str | None:
        """Return the safest locator available for persistence or execution."""

        if "data-testid" in self.attrs:
            return f'[data-testid="{self.attrs["data-testid"]}"]'
        if "id" in self.attrs:
            return f'#{self.attrs["id"]}'
        if "name" in self.attrs:
            return f'[name="{self.attrs["name"]}"]'
        if "aria-label" in self.attrs:
            return f'[aria-label="{self.attrs["aria-label"]}"]'
        if "href" in self.attrs and self.tag == "a":
            return f'a[href="{self.attrs["href"]}"]'
        # Fallback: use tag + type attribute so bare <input type="email"> elements
        # are never skipped entirely in the healing loop
        if self.tag == "input" and "type" in self.attrs:
            return f'input[type="{self.attrs["type"]}"]'
        return None


@dataclass(frozen=True)
class HealRequest:
    failing_locator: str
    elements: list[DomElement]
    expected_role: str | None = None
    context_path: str | None = None
    historical_success: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfidenceBreakdown:
    attribute_match: float
    dom_proximity: float
    historical_success: float
    score: float
    route: str


@dataclass(frozen=True)
class HealCandidate:
    locator: str
    confidence: float
    element: DomElement
    reason: str
    confidence_breakdown: ConfidenceBreakdown


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str
    code: str


@dataclass(frozen=True)
class HealResult:
    candidate: HealCandidate | None
    alternatives: list[HealCandidate] = field(default_factory=list)
    source: str = "deterministic"
    guardrail: GuardrailDecision | None = None
    llm_used: bool = False

    @property
    def locator(self) -> str | None:
        return self.candidate.locator if self.candidate else None

    @property
    def confidence(self) -> float:
        return self.candidate.confidence if self.candidate else 0.0


@dataclass(frozen=True)
class MemoryEvent:
    key: str
    old: str
    new: str
    confidence: float
    source: str
    node_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "old": self.old,
            "new": self.new,
            "confidence": self.confidence,
            "source": self.source,
            "node_id": self.node_id,
            "metadata": self.metadata,
        }
