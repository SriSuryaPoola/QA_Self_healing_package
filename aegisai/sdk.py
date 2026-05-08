"""Top-level SDK facade."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict

from .cache import LocatorCache
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
from .reporting import HealingReport, get_session_report
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
        self.report: HealingReport = get_session_report()
        self.cache = LocatorCache(self.config.cache.path, disabled=not self.config.cache.enabled)
        self._parsed_dom_cache: OrderedDict[str, list[DomElement]] = OrderedDict()
        self._parsed_dom_cache_size = 32
        self._deterministic_result_cache: OrderedDict[tuple[object, ...], HealResult] = OrderedDict()
        self._deterministic_result_cache_size = 64
        self._runtime_result_cache: OrderedDict[tuple[object, ...], HealResult] = OrderedDict()
        self._runtime_result_cache_size = 128
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
        cache_scope: str | None = None,
        use_cache: bool | None = None,
    ) -> HealResult:
        """Attempt a deterministic, guarded heal for a failing locator.

        LLM fallback is only attempted after the deterministic path is blocked,
        and its output must still match the filtered DOM and pass guardrails.
        """

        started = time.perf_counter()
        dom_key = self._dom_cache_key(dom)
        elements = self._parse_dom(dom, dom_key)
        scope = cache_scope or "default"
        history = historical_success or {}
        runtime_cache_key = self._runtime_cache_key(
            failing_locator=failing_locator,
            dom_key=dom_key,
            expected_role=expected_role,
            historical_success=history,
        )
        if use_cache is False and not self.config.report.enabled:
            cached_runtime_result = self._runtime_result_cache.get(runtime_cache_key)
            if cached_runtime_result is not None:
                self._runtime_result_cache.move_to_end(runtime_cache_key)
                return cached_runtime_result

        request = HealRequest(
            failing_locator=failing_locator,
            elements=elements,
            expected_role=expected_role,
            historical_success=history,
        )

        if use_cache is not False:
            cached = self.cache.get(original_locator=failing_locator, dom=dom, scope=scope)
            if cached is not None:
                cached_result = self._result_from_cache(
                    request=request,
                    locator=cached.healed_locator,
                    source=cached.source,
                    confidence=cached.confidence,
                )
                if cached_result.locator:
                    self._record_result(
                        failing_locator=failing_locator,
                        result=cached_result,
                        started=started,
                        layer_label="cache",
                        reason="Reused local healed-locator cache entry.",
                    )
                    return cached_result

        result = self._deterministic_heal(request, dom_key)
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
                blocked = HealResult(
                    candidate=None,
                    alternatives=result.alternatives,
                    source=result.source,
                    guardrail=GuardrailDecision(False, security.reason, "security_blocked"),
                    llm_used=False,
                )
                self._record_result(
                    failing_locator=failing_locator,
                    result=blocked,
                    started=started,
                    layer_label="deterministic",
                    reason=security.reason,
                )
                return blocked
            healed = HealResult(
                candidate=result.candidate,
                alternatives=result.alternatives,
                source=result.source,
                guardrail=decision,
                llm_used=False,
            )
            if use_cache is not False:
                self.cache.put(
                    original_locator=failing_locator,
                    healed_locator=result.candidate.locator,
                    dom=dom,
                    scope=scope,
                    confidence=result.candidate.confidence,
                    source=result.source,
                )
            self._record_result(
                failing_locator=failing_locator,
                result=healed,
                started=started,
                layer_label="deterministic",
                risk_level=security.risk_level.value,
                persistence_decision=security.policy_label,
                reason=decision.reason,
            )
            if use_cache is False and not self.config.report.enabled and not healed.llm_used:
                self._remember_runtime_result(runtime_cache_key, healed)
            return healed

        if self._llm_engine is not None:
            llm_result = self._try_llm_fallback(
                failing_locator=failing_locator,
                expected_role=expected_role,
                elements=elements,
                request=request,
                deterministic_result=result,
            )
            self._record_result(
                failing_locator=failing_locator,
                result=llm_result,
                started=started,
                layer_label="llm",
                reason=llm_result.guardrail.reason if llm_result.guardrail else "",
            )
            return llm_result

        blocked = HealResult(
            candidate=None,
            alternatives=result.alternatives,
            source=result.source,
            guardrail=decision,
            llm_used=False,
        )
        self._record_result(
            failing_locator=failing_locator,
            result=blocked,
            started=started,
            layer_label="deterministic",
            reason=decision.reason,
        )
        return blocked

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
    def _dom_cache_key(dom: str) -> str:
        return hashlib.blake2s(dom.encode("utf-8", errors="surrogatepass"), digest_size=16).hexdigest()

    def _parse_dom(self, dom: str, key: str | None = None) -> list[DomElement]:
        key = key or self._dom_cache_key(dom)
        cached = self._parsed_dom_cache.get(key)
        if cached is not None:
            self._parsed_dom_cache.move_to_end(key)
            return cached

        elements = parse_dom_subset(dom)
        self._parsed_dom_cache[key] = elements
        if len(self._parsed_dom_cache) > self._parsed_dom_cache_size:
            self._parsed_dom_cache.popitem(last=False)
        return elements

    def _deterministic_heal(self, request: HealRequest, dom_key: str) -> HealResult:
        cache_key = (
            request.failing_locator,
            dom_key,
            request.context_path,
            tuple(sorted(request.historical_success.items())),
        )
        cached = self._deterministic_result_cache.get(cache_key)
        if cached is not None:
            self._deterministic_result_cache.move_to_end(cache_key)
            return cached

        result = self.deterministic.heal(request)
        self._deterministic_result_cache[cache_key] = result
        if len(self._deterministic_result_cache) > self._deterministic_result_cache_size:
            self._deterministic_result_cache.popitem(last=False)
        return result

    def _runtime_cache_key(
        self,
        *,
        failing_locator: str,
        dom_key: str,
        expected_role: str | None,
        historical_success: dict[str, float],
    ) -> tuple[object, ...]:
        return (
            failing_locator,
            dom_key,
            expected_role,
            tuple(sorted(historical_success.items())),
            self.config.guardrails.confidence_threshold,
            self.security_officer.policy,
        )

    def _remember_runtime_result(self, cache_key: tuple[object, ...], result: HealResult) -> None:
        self._runtime_result_cache[cache_key] = result
        if len(self._runtime_result_cache) > self._runtime_result_cache_size:
            self._runtime_result_cache.popitem(last=False)

    @staticmethod
    def _element_for_locator(locator: str, elements: list[DomElement]) -> DomElement | None:
        normalized_locator = _normalize_selector(locator)
        for element in elements:
            stable = element.stable_locator()
            if stable and _normalize_selector(stable) == normalized_locator:
                return element
        return None

    def _result_from_cache(
        self,
        *,
        request: HealRequest,
        locator: str,
        source: str,
        confidence: float,
    ) -> HealResult:
        element = self._element_for_locator(locator, request.elements)
        if element is None:
            return HealResult(
                candidate=None,
                alternatives=[],
                source="cache",
                guardrail=GuardrailDecision(False, "Cached locator no longer matches the DOM fingerprint.", "cache_stale"),
                llm_used=False,
            )

        from .engine.confidence import route_for_score

        candidate = HealCandidate(
            locator=locator,
            confidence=confidence,
            element=element,
            reason="local_cache_hit",
            confidence_breakdown=ConfidenceBreakdown(
                attribute_match=1.0,
                dom_proximity=1.0,
                historical_success=1.0,
                score=confidence,
                route=route_for_score(confidence),
            ),
        )
        result = HealResult(candidate=candidate, alternatives=[], source=source, llm_used=False)
        decision = self.guardrails.validate(request, result)
        if not decision.allowed:
            return HealResult(candidate=None, alternatives=[], source="cache", guardrail=decision, llm_used=False)
        return HealResult(candidate=candidate, alternatives=[], source="cache", guardrail=decision, llm_used=False)

    def _record_result(
        self,
        *,
        failing_locator: str,
        result: HealResult,
        started: float,
        layer_label: str,
        risk_level: str = "unknown",
        persistence_decision: str = "not_applicable",
        reason: str = "",
    ) -> None:
        if not self.config.report.enabled:
            return
        guardrail_reason = result.guardrail.reason if result.guardrail else reason
        self.report.record_attempt(
            original_locator=failing_locator,
            healed_locator=result.locator,
            success=bool(result.locator),
            source=result.source,
            layer_label=layer_label,
            confidence=result.confidence,
            risk_level=risk_level,
            duration_ms=(time.perf_counter() - started) * 1000,
            persistence_decision=persistence_decision,
            reason=reason or guardrail_reason,
            framework="sdk",
            action="heal_locator",
        )


def _normalize_selector(locator: str) -> str:
    return locator.strip().replace("'", '"')
