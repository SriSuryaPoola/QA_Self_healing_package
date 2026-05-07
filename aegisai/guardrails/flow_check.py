"""Post-heal flow validation helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlowExpectation:
    expected_url: str | None = None
    expected_dom_marker: str | None = None


@dataclass(frozen=True)
class FlowValidation:
    passed: bool
    reason: str


class FlowChecker:
    def validate(
        self,
        expectation: FlowExpectation,
        *,
        actual_url: str | None = None,
        actual_dom: str | None = None,
    ) -> FlowValidation:
        if expectation.expected_url and expectation.expected_url != actual_url:
            return FlowValidation(False, "URL validation failed.")
        if expectation.expected_dom_marker and expectation.expected_dom_marker not in (actual_dom or ""):
            return FlowValidation(False, "Expected DOM mutation was not observed.")
        return FlowValidation(True, "Flow validation passed.")
