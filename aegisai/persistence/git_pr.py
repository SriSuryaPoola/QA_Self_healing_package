"""PR decision helpers.

Real provider calls are intentionally outside this first build slice.
"""

from __future__ import annotations

from dataclasses import dataclass

from aegisai.engine.confidence import route_for_score


@dataclass(frozen=True)
class PullRequestDecision:
    eligible: bool
    reason: str


def should_open_pr(confidence: float, confirmations: int = 1) -> PullRequestDecision:
    route = route_for_score(confidence)
    if route == "auto_pr":
        return PullRequestDecision(True, "Confidence is eligible for immediate PR.")
    if route == "confirm_across_runs" and confirmations >= 2:
        return PullRequestDecision(True, "Medium confidence was confirmed across runs.")
    return PullRequestDecision(False, "Confidence rules do not allow PR creation yet.")
