"""Deterministic locator healing engine."""

from __future__ import annotations

import re

from aegisai.engine.confidence import ConfidenceScorer
from aegisai.models import DomElement, HealCandidate, HealRequest, HealResult


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_-]+")

# XPath / CSS structural keywords that carry no semantic meaning for attribute matching
_LOCATOR_NOISE = {
    "xpath", "css", "by", "and", "or", "not", "normalize", "space",
    "contains", "text", "following", "sibling", "preceding", "ancestor",
    "descendant", "child", "self", "axis", "node", "true", "false",
    "id", "name", "type", "class", "data", "field", "value", "attr",
}

_TOKEN_ALIASES = {
    "pass": "password",
    "pwd": "password",
    "btn": "button",
    "signin": "login",
    "logon": "login",
}


class DeterministicEngine:
    def __init__(self, confidence_threshold: float = 0.85) -> None:
        self.confidence_threshold = confidence_threshold
        self.scorer = ConfidenceScorer()

    def heal(self, request: HealRequest) -> HealResult:
        candidates: list[HealCandidate] = []
        tokens = self._locator_tokens(request.failing_locator)
        for element in request.elements:
            locator = element.stable_locator()
            if not locator:
                continue
            attribute_score = self._attribute_match(tokens, element)
            proximity_score = self._dom_proximity(request.context_path, element)
            history_score = request.historical_success.get(locator, 0.75)
            breakdown = self.scorer.score(
                attribute_match=attribute_score,
                dom_proximity=proximity_score,
                historical_success=history_score,
            )
            candidates.append(
                HealCandidate(
                    locator=locator,
                    confidence=breakdown.score,
                    element=element,
                    reason=self._reason(attribute_score, proximity_score, history_score),
                    confidence_breakdown=breakdown,
                )
            )

        candidates.sort(key=lambda item: item.confidence, reverse=True)
        candidate = candidates[0] if candidates else None
        return HealResult(
            candidate=candidate,
            alternatives=candidates[1:],
            source="deterministic",
            llm_used=False,
        )

    @staticmethod
    def _locator_tokens(locator: str) -> set[str]:
        expanded: set[str] = set()
        for token in TOKEN_PATTERN.findall(locator):
            for part in re.split(r"[-_]+", token.lower()):
                if part:
                    expanded.add(_TOKEN_ALIASES.get(part, part))
        return expanded - _LOCATOR_NOISE

    @staticmethod
    def _attribute_match(tokens: set[str], element: DomElement) -> float:
        if not tokens:
            return 0.0
        # Include tag name, all attribute keys AND values so XPath patterns like
        # //input[@type='email'] correctly match tag='input', key='type', value='email'
        value_pool = [
            element.tag,
            *element.attrs.keys(),
            *element.attrs.values(),
            element.text,
        ]
        normalized = " ".join(value_pool).replace("-", " ").replace("_", " ").lower()
        matched = sum(1 for token in tokens if token in normalized)
        ratio = matched / len(tokens)
        if element.attrs.get("data-testid"):
            return min(1.0, ratio + 0.2)
        return ratio

    @staticmethod
    def _dom_proximity(context_path: str | None, element: DomElement) -> float:
        if not context_path or not element.path:
            return 0.75
        if context_path == element.path:
            return 1.0
        shared = 0
        for left, right in zip(context_path.split("/"), element.path.split("/")):
            if left != right:
                break
            shared += 1
        return min(1.0, shared / max(len(context_path.split("/")), 1))

    @staticmethod
    def _reason(attribute: float, proximity: float, history: float) -> str:
        return (
            f"attribute_match={attribute:.2f}; "
            f"dom_proximity={proximity:.2f}; "
            f"historical_success={history:.2f}"
        )
