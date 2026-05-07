"""Guardrails that favor safe blocking over false positives."""

from __future__ import annotations

from aegisai.engine.confidence import CONFIRM_THRESHOLD
from aegisai.models import GuardrailDecision, HealRequest, HealResult


class GuardrailValidator:
    ambiguity_delta = 0.05

    def validate(self, request: HealRequest, result: HealResult) -> GuardrailDecision:
        if not request.elements:
            return GuardrailDecision(False, "No DOM elements were available to heal.", "element_missing")
        if result.candidate is None:
            return GuardrailDecision(False, "No viable locator candidate was found.", "no_candidate")
        if result.candidate.confidence < CONFIRM_THRESHOLD:
            return GuardrailDecision(False, "Candidate confidence is below safe threshold.", "low_confidence")
        if request.expected_role:
            actual_role = result.candidate.element.role
            if actual_role != request.expected_role:
                return GuardrailDecision(
                    False,
                    f"Role mismatch: expected {request.expected_role}, got {actual_role or 'unknown'}.",
                    "role_mismatch",
                )
        if self._is_ambiguous(result):
            return GuardrailDecision(False, "Multiple candidates are too close to choose safely.", "ambiguous")
        return GuardrailDecision(True, "Candidate passed deterministic guardrails.", "allowed")

    def _is_ambiguous(self, result: HealResult) -> bool:
        if not result.candidate or not result.alternatives:
            return False
        second = result.alternatives[0]
        return abs(result.candidate.confidence - second.confidence) <= self.ambiguity_delta
