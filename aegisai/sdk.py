"""Top-level SDK facade."""

from __future__ import annotations

from .engine.deterministic import DeterministicEngine
from .engine.llm import LLMAdapter, StrictJsonLLMEngine
from .guardrails.validator import GuardrailValidator
from .models import (
    ConfidenceBreakdown,
    DomElement,
    GuardrailDecision,
    HealCandidate,
    HealRequest,
    HealResult,
)
from .security import SecurityOfficer, SecurityPolicy
from .utils.config import AegisConfig
from .utils.dom_parser import parse_dom_subset


class AegisAI:
    """Small facade that keeps the core package easy to consume."""

    def __init__(
        self,
        config: AegisConfig | None = None,
        llm_adapter: LLMAdapter | None = None,
        security_policy: SecurityPolicy | None = None,
    ) -> None:
        self.config = config or AegisConfig()
        self.deterministic = DeterministicEngine(
            confidence_threshold=self.config.guardrails.confidence_threshold
        )
        self.guardrails = GuardrailValidator()
        self.security_officer = SecurityOfficer(security_policy)
        self._llm_engine: StrictJsonLLMEngine | None = (
            StrictJsonLLMEngine(
                adapter=llm_adapter,
                timeout_seconds=self.config.healing.llm.timeout_seconds,
                temperature=self.config.healing.llm.temperature,
            )
            if llm_adapter and self.config.healing.llm.enabled
            else None
        )

    def heal_locator(
        self,
        failing_locator: str,
        dom: str,
        *,
        expected_role: str | None = None,
        historical_success: dict[str, float] | None = None,
    ) -> HealResult:
        """Attempt a deterministic, guarded heal for a failing locator.

        LLM fallback is only attempted after the deterministic path is blocked,
        and its output must still match the filtered DOM and pass guardrails.
        """

        elements = parse_dom_subset(dom)
        request = HealRequest(
            failing_locator=failing_locator,
            elements=elements,
            expected_role=expected_role,
            historical_success=historical_success or {},
        )
        result = self.deterministic.heal(request)
        decision = self.guardrails.validate(request, result)

        if decision.allowed and result.candidate:
            security = self.security_officer.review_candidate(
                old_locator=failing_locator,
                new_locator=result.candidate.locator,
                element=result.candidate.element,
                source=result.source,
                confidence=result.candidate.confidence,
            )
            if not security.runtime_allowed:
                return HealResult(
                    candidate=None,
                    alternatives=result.alternatives,
                    source=result.source,
                    guardrail=GuardrailDecision(False, security.reason, "security_blocked"),
                    llm_used=False,
                )
            return HealResult(
                candidate=result.candidate,
                alternatives=result.alternatives,
                source=result.source,
                guardrail=decision,
                llm_used=False,
            )

        if self._llm_engine is not None:
            return self._try_llm_fallback(
                failing_locator=failing_locator,
                expected_role=expected_role,
                elements=elements,
                request=request,
                deterministic_result=result,
            )

        return HealResult(
            candidate=None,
            alternatives=result.alternatives,
            source=result.source,
            guardrail=decision,
            llm_used=False,
        )

    def _try_llm_fallback(
        self,
        *,
        failing_locator: str,
        expected_role: str | None,
        elements: list[DomElement],
        request: HealRequest,
        deterministic_result: HealResult,
    ) -> HealResult:
        try:
            payload, llm_security = self.security_officer.build_llm_payload(
                failing_locator=failing_locator,
                elements=elements,
                expected_role=expected_role,
            )
            if not llm_security.llm_allowed:
                return HealResult(
                    candidate=None,
                    alternatives=deterministic_result.alternatives,
                    source="llm",
                    guardrail=GuardrailDecision(False, llm_security.reason, "llm_security_blocked"),
                    llm_used=True,
                )
            llm_out = self._llm_engine.suggest(  # type: ignore[union-attr]
                payload
            )
        except Exception as exc:
            return HealResult(
                candidate=None,
                alternatives=deterministic_result.alternatives,
                source="llm",
                guardrail=GuardrailDecision(
                    False,
                    f"LLM fallback failed safely: {exc}",
                    "llm_error",
                ),
                llm_used=True,
            )

        matched_element = self._element_for_locator(llm_out.locator, elements)
        if matched_element is None:
            return HealResult(
                candidate=None,
                alternatives=[],
                source="llm",
                guardrail=GuardrailDecision(
                    False,
                    "LLM locator did not match the filtered DOM subset.",
                    "llm_locator_unmatched",
                ),
                llm_used=True,
            )

        from .engine.confidence import route_for_score

        breakdown = ConfidenceBreakdown(
            attribute_match=0.0,
            dom_proximity=0.0,
            historical_success=0.0,
            score=llm_out.confidence,
            route=route_for_score(llm_out.confidence),
        )
        candidate = HealCandidate(
            locator=llm_out.locator,
            confidence=llm_out.confidence,
            element=matched_element,
            reason="llm_fallback",
            confidence_breakdown=breakdown,
        )
        llm_result = HealResult(
            candidate=candidate,
            alternatives=[],
            source="llm",
            llm_used=True,
        )
        llm_decision = self.guardrails.validate(request, llm_result)
        if llm_decision.allowed:
            security = self.security_officer.review_candidate(
                old_locator=failing_locator,
                new_locator=candidate.locator,
                element=candidate.element,
                source="llm",
                confidence=candidate.confidence,
            )
            if not security.runtime_allowed:
                return HealResult(
                    candidate=None,
                    alternatives=[],
                    source="llm",
                    guardrail=GuardrailDecision(False, security.reason, "security_blocked"),
                    llm_used=True,
                )
        return HealResult(
            candidate=candidate if llm_decision.allowed else None,
            alternatives=[],
            source="llm",
            guardrail=llm_decision,
            llm_used=True,
        )

    @staticmethod
    def _element_for_locator(locator: str, elements: list[DomElement]) -> DomElement | None:
        normalized_locator = _normalize_selector(locator)
        for element in elements:
            stable = element.stable_locator()
            if stable and _normalize_selector(stable) == normalized_locator:
                return element
        return None


def _normalize_selector(locator: str) -> str:
    return locator.strip().replace("'", '"')
