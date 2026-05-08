"""Embedded AI Security Officer.

This is local package code, not a platform service. It risk-scores healing
candidates, redacts LLM context, and decides whether runtime heal, LLM fallback,
and persistence are allowed.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from aegisai.models import DomElement

from .audit import write_audit_event
from .policy import RiskLevel, SecurityDecision, SecurityPolicy
from .redactor import redact_dom_element, redact_payload


class SecurityOfficer:
    def __init__(self, policy: SecurityPolicy | None = None) -> None:
        self.policy = policy or SecurityPolicy()
        self._audit_keys: set[tuple[Any, ...]] = set()
        self._decision_cache: OrderedDict[tuple[Any, ...], SecurityDecision] = OrderedDict()
        self._decision_cache_size = 128

    def review_candidate(
        self,
        *,
        old_locator: str,
        new_locator: str,
        element: DomElement,
        source: str,
        confidence: float,
    ) -> SecurityDecision:
        cache_key = self._decision_cache_key(
            old_locator=old_locator,
            new_locator=new_locator,
            element=element,
            source=source,
            confidence=confidence,
        )
        if self.policy.audit_deduplicate:
            cached = self._decision_cache.get(cache_key)
            if cached is not None:
                self._decision_cache.move_to_end(cache_key)
                return cached

        risk = self.classify_risk(old_locator=old_locator, new_locator=new_locator, element=element)
        threshold_reason = self._confidence_reason(risk, confidence)
        runtime_allowed = self._runtime_allowed(risk) and threshold_reason is None
        llm_allowed = self._llm_allowed(risk)
        persistence_allowed = risk == RiskLevel.LOW and self.policy.auto_persist_low
        review_required = risk in {RiskLevel.MEDIUM, RiskLevel.HIGH} or (
            runtime_allowed and not persistence_allowed
        )
        decision = SecurityDecision(
            runtime_allowed=runtime_allowed,
            llm_allowed=llm_allowed,
            persistence_allowed=persistence_allowed,
            review_required=review_required,
            risk_level=risk,
            reason=threshold_reason or self._reason(risk, runtime_allowed, persistence_allowed),
            sanitized=True,
        )
        event = {
            "event": "candidate_review",
            "old_locator": old_locator,
            "new_locator": new_locator,
            "source": source,
            "confidence": confidence,
            "element": redact_dom_element(element),
            "risk_level": risk.value,
            "runtime_allowed": runtime_allowed,
            "llm_allowed": llm_allowed,
            "persistence_allowed": persistence_allowed,
            "review_required": review_required,
            "reason": decision.reason,
        }
        if self._should_audit(decision) and self._remember_audit_event(event):
            self.audit(event)
        if self.policy.audit_deduplicate:
            self._decision_cache[cache_key] = decision
            if len(self._decision_cache) > self._decision_cache_size:
                self._decision_cache.popitem(last=False)
        return decision

    def build_llm_payload(
        self,
        *,
        failing_locator: str,
        elements: list[DomElement],
        expected_role: str | None = None,
    ) -> tuple[dict[str, Any], SecurityDecision]:
        representative = self._representative_element(failing_locator, elements)
        decision = self.review_candidate(
            old_locator=failing_locator,
            new_locator=representative.stable_locator() or "",
            element=representative,
            source="llm_context",
            confidence=0.0,
        )
        payload = {
            "failing_locator": failing_locator,
            "elements": [redact_dom_element(element) for element in elements if element.stable_locator()],
            "expected_role": expected_role,
            "security": {
                "risk_level": decision.risk_level.value,
                "sanitized": True,
                "raw_values_included": False,
            },
        }
        return redact_payload(payload), decision

    def classify_risk(self, *, old_locator: str, new_locator: str, element: DomElement) -> RiskLevel:
        haystack = " ".join(
            [
                old_locator,
                new_locator,
                element.tag,
                element.text,
                *(str(item) for pair in element.attrs.items() for item in pair),
            ]
        ).lower()
        if any(marker in haystack for marker in ("token", "csrf", "session", "cookie", "authorization", "api_key")):
            return RiskLevel.CRITICAL
        if "password" in haystack:
            return RiskLevel.MEDIUM
        if any(marker in haystack for marker in ("payment", "delete", "admin", "production", "danger")):
            return RiskLevel.HIGH
        return RiskLevel.LOW

    def audit(self, event: dict[str, Any]) -> None:
        if not self.policy.audit_enabled:
            return
        try:
            write_audit_event(event, self.policy.audit_dir)
        except Exception:
            # Audit must never break test execution.
            return

    def _should_audit(self, decision: SecurityDecision) -> bool:
        if not self.policy.audit_enabled:
            return False
        if decision.risk_level != RiskLevel.LOW:
            return True
        if not decision.runtime_allowed or not decision.persistence_allowed:
            return True
        return self.policy.audit_low_risk

    def _remember_audit_event(self, event: dict[str, Any]) -> bool:
        if not self.policy.audit_deduplicate:
            return True
        element = event.get("element") or {}
        attrs = element.get("attrs") or {}
        key = (
            event.get("event"),
            event.get("old_locator"),
            event.get("new_locator"),
            event.get("source"),
            event.get("confidence"),
            event.get("risk_level"),
            event.get("runtime_allowed"),
            event.get("llm_allowed"),
            event.get("persistence_allowed"),
            event.get("review_required"),
            event.get("reason"),
            element.get("tag"),
            tuple(sorted(attrs.items())),
            element.get("text"),
            element.get("role"),
            element.get("locator"),
        )
        if key in self._audit_keys:
            return False
        self._audit_keys.add(key)
        return True

    @staticmethod
    def _decision_cache_key(
        *,
        old_locator: str,
        new_locator: str,
        element: DomElement,
        source: str,
        confidence: float,
    ) -> tuple[Any, ...]:
        redacted = redact_dom_element(element)
        attrs = redacted.get("attrs") or {}
        return (
            old_locator,
            new_locator,
            source,
            confidence,
            redacted.get("tag"),
            tuple(sorted(attrs.items())),
            redacted.get("text"),
            redacted.get("role"),
            redacted.get("locator"),
        )

    def _runtime_allowed(self, risk: RiskLevel) -> bool:
        if risk == RiskLevel.CRITICAL:
            return False
        if risk == RiskLevel.HIGH:
            return self.policy.allow_runtime_for_high
        if risk == RiskLevel.MEDIUM:
            return self.policy.allow_runtime_for_medium
        return True

    def _llm_allowed(self, risk: RiskLevel) -> bool:
        if risk == RiskLevel.CRITICAL:
            return False
        if risk == RiskLevel.HIGH:
            return self.policy.allow_llm_for_high
        if risk == RiskLevel.MEDIUM:
            return self.policy.allow_llm_for_medium
        return True

    def _confidence_reason(self, risk: RiskLevel, confidence: float) -> str | None:
        minimum = {
            RiskLevel.LOW: self.policy.min_confidence_low,
            RiskLevel.MEDIUM: self.policy.min_confidence_medium,
            RiskLevel.HIGH: self.policy.min_confidence_high,
            RiskLevel.CRITICAL: 1.0,
        }[risk]
        if confidence < minimum:
            return (
                f"{risk.value} risk candidate confidence {confidence:.2f} is below "
                f"the policy minimum {minimum:.2f}."
            )
        return None

    @staticmethod
    def _reason(risk: RiskLevel, runtime_allowed: bool, persistence_allowed: bool) -> str:
        if not runtime_allowed:
            return f"{risk.value} risk candidate blocked by local security policy."
        if not persistence_allowed:
            return f"{risk.value} risk candidate allowed at runtime; persistence requires review."
        return "Low risk candidate allowed for runtime healing and persistence."

    @staticmethod
    def _representative_element(failing_locator: str, elements: list[DomElement]) -> DomElement:
        lowered = failing_locator.lower()
        for element in elements:
            stable = (element.stable_locator() or "").lower()
            if stable and any(token in stable for token in ("password", "email", "login")):
                return element
            if "password" in lowered and element.attrs.get("type") == "password":
                return element
            if "email" in lowered and element.attrs.get("type") == "email":
                return element
        return elements[0] if elements else DomElement(tag="unknown")
