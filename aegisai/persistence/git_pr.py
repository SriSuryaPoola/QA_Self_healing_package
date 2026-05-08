"""PR decision helpers.

Real provider calls are intentionally outside this first build slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def build_pr_body(suggestions: list[dict[str, Any]]) -> str:
    """Build a human-review PR body from local suggestion artifacts."""

    lines = [
        "## AegisAI locator healing suggestions",
        "",
        "This PR body was generated locally. Review every locator change before applying it.",
        "",
    ]
    for index, suggestion in enumerate(suggestions, start=1):
        lines.extend(
            [
                f"### Suggestion {index}",
                "",
                f"- Old locator: `{suggestion.get('old_locator', '')}`",
                f"- New locator: `{suggestion.get('new_locator', '')}`",
                f"- Confidence: `{suggestion.get('confidence', 0)}`",
                f"- Source: `{suggestion.get('source', '')}`",
                f"- Risk: `{suggestion.get('risk_level', 'unknown')}`",
                f"- Review required: `{suggestion.get('review_required', True)}`",
                "",
            ]
        )
        diff = suggestion.get("diff")
        if diff:
            lines.extend(["```diff", str(diff).rstrip(), "```", ""])
    return "\n".join(lines).rstrip() + "\n"
