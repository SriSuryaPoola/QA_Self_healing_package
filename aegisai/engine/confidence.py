"""Confidence scoring and routing."""

from __future__ import annotations

from dataclasses import dataclass

from aegisai.models import ConfidenceBreakdown

AUTO_PR_THRESHOLD = 0.9
CONFIRM_THRESHOLD = 0.8


def route_for_score(score: float) -> str:
    if score >= AUTO_PR_THRESHOLD:
        return "auto_pr"
    if score >= CONFIRM_THRESHOLD:
        return "confirm_across_runs"
    return "block"


@dataclass(frozen=True)
class ConfidenceScorer:
    attribute_weight: float = 1 / 3
    proximity_weight: float = 1 / 3
    history_weight: float = 1 / 3

    def score(
        self,
        *,
        attribute_match: float,
        dom_proximity: float,
        historical_success: float,
    ) -> ConfidenceBreakdown:
        values = (
            self._clamp(attribute_match),
            self._clamp(dom_proximity),
            self._clamp(historical_success),
        )
        score = (
            self.attribute_weight * values[0]
            + self.proximity_weight * values[1]
            + self.history_weight * values[2]
        )
        rounded = round(score, 4)
        return ConfidenceBreakdown(
            attribute_match=values[0],
            dom_proximity=values[1],
            historical_success=values[2],
            score=rounded,
            route=route_for_score(rounded),
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
