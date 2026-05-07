"""Healing orchestrator for the Selenium self-healing cascade."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorOutcome:
    success: bool
    element: Any | None
    layer_used: int | None
    layer_label: str
    healed_locator: str | None
    by_strategy: str | None
    confidence: float
    script_patched: bool
    layers_tried: list[str] = field(default_factory=list)
    reason: str = ""


class HealingOrchestrator:
    """Run fast/free healing layers before falling back to LLM."""

    def __init__(
        self,
        script_path: str | None = None,
        backup: bool = True,
        confidence_l2: float = 0.80,
        confidence_l3: float = 0.75,
        probe_wait_seconds: float = 3.0,
        enable_llm: bool = False,
        security_policy: Any = None,
    ) -> None:
        self.script_path = script_path
        self.backup = backup
        self.conf_l2 = confidence_l2
        self.conf_l3 = confidence_l3
        self.probe_wait = probe_wait_seconds
        self.enable_llm = enable_llm
        self.security_policy = security_policy
        from aegisai.security import SecurityOfficer

        self.security_officer = SecurityOfficer(security_policy)

    def orchestrate(
        self,
        exception: BaseException,
        *,
        driver: Any,
        wait: Any,
        failing_locator: str,
        original_condition: Any = None,
    ) -> OrchestratorOutcome:
        raw_locator = failing_locator.split("=", 1)[-1] if "=" in failing_locator else failing_locator
        layers_tried: list[str] = []

        logger.info("[aegisai][L0] DOM readiness check for: %s", failing_locator)
        layers_tried.append("L0:dom_ready")
        dom_ready, page_source = self._l0_dom_ready(driver, raw_locator)
        if dom_ready is not None:
            return self._succeed(
                dom_ready,
                layer=0,
                label="L0:dom_ready",
                by="original",
                locator=raw_locator,
                confidence=1.0,
                raw_locator=raw_locator,
                layers_tried=layers_tried,
            )

        page_source = self._safe_page_source(driver) or page_source

        logger.info("[aegisai][L1] Trying locator translation.")
        layers_tried.append("L1:translation")
        try:
            from aegisai.engine.locator_translator import translate

            for candidate in translate(failing_locator):
                element = self._quick_find(driver, candidate.by, candidate.locator)
                if element is None:
                    continue
                outcome = self._guarded_succeed(
                    element,
                    layer=1,
                    label=f"L1:{candidate.source}",
                    by=candidate.by,
                    locator=candidate.locator,
                    confidence=0.95,
                    raw_locator=raw_locator,
                    layers_tried=layers_tried,
                )
                if outcome.success:
                    return outcome
                logger.info("[aegisai][L1] Guardrail blocked %s: %s", candidate.locator, outcome.reason)
        except Exception as exc:
            logger.debug("[aegisai][L1] error: %s", exc)

        logger.info("[aegisai][L2] Trying deterministic engine.")
        layers_tried.append("L2:deterministic")
        try:
            from aegisai.engine.deterministic import DeterministicEngine
            from aegisai.guardrails.validator import GuardrailValidator
            from aegisai.models import HealRequest
            from aegisai.utils.dom_parser import parse_dom_subset

            elements = parse_dom_subset(page_source)
            request = HealRequest(failing_locator=raw_locator, elements=elements)
            result = DeterministicEngine().heal(request)
            decision = GuardrailValidator().validate(request, result)
            if decision.allowed and result.candidate and result.candidate.confidence >= self.conf_l2:
                locator = result.candidate.locator
                element = self._quick_find(driver, "css", locator)
                if element is not None:
                    outcome = self._guarded_succeed(
                        element,
                        layer=2,
                        label="L2:deterministic",
                        by="css",
                        locator=locator,
                        confidence=result.candidate.confidence,
                        raw_locator=raw_locator,
                        layers_tried=layers_tried,
                    )
                    if outcome.success:
                        return outcome
                    logger.info("[aegisai][L2] Guardrail blocked %s: %s", locator, outcome.reason)
            else:
                reason = decision.reason if not decision.allowed else "Confidence below threshold."
                logger.info("[aegisai][L2] skipped: %s", reason)
        except Exception as exc:
            logger.debug("[aegisai][L2] error: %s", exc)

        logger.info("[aegisai][L3] Trying heuristic structural search.")
        layers_tried.append("L3:heuristic")
        try:
            from aegisai.engine.heuristic_searcher import search

            for candidate in search(failing_locator, page_source):
                if candidate.confidence < self.conf_l3:
                    break
                element = self._quick_find(driver, candidate.by, candidate.locator)
                if element is None:
                    continue
                outcome = self._guarded_succeed(
                    element,
                    layer=3,
                    label=f"L3:{candidate.strategy}",
                    by=candidate.by,
                    locator=candidate.locator,
                    confidence=candidate.confidence,
                    raw_locator=raw_locator,
                    layers_tried=layers_tried,
                )
                if outcome.success:
                    return outcome
                logger.info("[aegisai][L3] Guardrail blocked %s: %s", candidate.locator, outcome.reason)
        except Exception as exc:
            logger.debug("[aegisai][L3] error: %s", exc)

        logger.info("[aegisai][L4] Trying live browser JS probing.")
        layers_tried.append("L4:js_probe")
        try:
            from aegisai.engine.js_prober import probe

            probe_result = probe(failing_locator, driver)
            if probe_result.found and probe_result.css_locator:
                locator = probe_result.css_locator
                element = self._quick_find(driver, "css", locator)
                if element is not None:
                    outcome = self._guarded_succeed(
                        element,
                        layer=4,
                        label=f"L4:{probe_result.strategy_label}",
                        by="css",
                        locator=locator,
                        confidence=0.88,
                        raw_locator=raw_locator,
                        layers_tried=layers_tried,
                    )
                    if outcome.success:
                        return outcome
                    logger.info("[aegisai][L4] Guardrail blocked %s: %s", locator, outcome.reason)
        except Exception as exc:
            logger.debug("[aegisai][L4] error: %s", exc)

        if not self.enable_llm:
            reason = self._llm_disabled_reason()
            logger.info("[aegisai][L5] skipped. %s", reason)
            return OrchestratorOutcome(
                success=False,
                element=None,
                layer_used=None,
                layer_label="none",
                healed_locator=None,
                by_strategy=None,
                confidence=0.0,
                script_patched=False,
                layers_tried=layers_tried,
                reason=reason,
            )

        logger.info("[aegisai][L5] All free layers failed; invoking LLM.")
        layers_tried.append("L5:llm")
        llm_failure_reason = ""
        try:
            from aegisai.engine.autonomous_healer import AutonomousHealer

            outcome = AutonomousHealer(
                script_path=self.script_path,
                backup=self.backup,
                security_policy=self.security_policy,
            ).heal(
                exception,
                driver=driver,
                wait=wait,
                failing_locator=failing_locator,
                original_condition=original_condition,
            )
            if outcome.success:
                return OrchestratorOutcome(
                    success=True,
                    element=outcome.element,
                    layer_used=5,
                    layer_label="L5:llm",
                    healed_locator=outcome.healed_locator,
                    by_strategy=outcome.by_strategy,
                    confidence=outcome.confidence,
                    script_patched=outcome.script_patched,
                    layers_tried=layers_tried,
                    reason="LLM heal succeeded.",
                )
            llm_failure_reason = outcome.reason
            logger.info("[aegisai][L5] unavailable: %s", outcome.reason)
        except Exception as exc:
            llm_failure_reason = f"L5 LLM fallback failed safely: {exc}"
            logger.error("[aegisai][L5] LLM heal failed: %s", exc)

        return OrchestratorOutcome(
            success=False,
            element=None,
            layer_used=None,
            layer_label="none",
            healed_locator=None,
            by_strategy=None,
            confidence=0.0,
            script_patched=False,
            layers_tried=layers_tried,
            reason=llm_failure_reason or "All healing layers exhausted.",
        )

    @staticmethod
    def _llm_disabled_reason() -> str:
        try:
            from aegisai.engine.universal_llm_adapter import UniversalLLMAdapter

            issue = UniversalLLMAdapter.configuration_issue()
        except Exception:
            issue = "LLM configuration could not be inspected."

        if issue:
            return f"L0-L4 exhausted. L5 LLM fallback was not started because {issue}"

        return (
            "L0-L4 exhausted. L5 LLM fallback is disabled by configuration. "
            "Pass enable_llm=True to AegisSeleniumListener to allow L5 after deterministic layers fail."
        )

    def _l0_dom_ready(self, driver: Any, raw_locator: str) -> tuple[Any, str]:
        time.sleep(0.8)
        page_source = self._safe_page_source(driver)
        by = "xpath" if raw_locator.startswith("//") else "css"
        element = self._quick_find(driver, by, raw_locator)
        if element is not None:
            return element, page_source

        try:
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.3)
            element = self._quick_find(driver, by, raw_locator)
            if element is not None:
                return element, self._safe_page_source(driver)
        except Exception:
            pass
        return None, page_source

    def _quick_find(self, driver: Any, by_str: str, locator: str) -> Any:
        try:
            from selenium.webdriver.common.by import By

            by_obj = By.XPATH if by_str.lower() == "xpath" else By.CSS_SELECTOR
        except Exception:
            by_obj = "xpath" if by_str.lower() == "xpath" else "css selector"

        try:
            element = driver.find_element(by_obj, locator)
            if not hasattr(element, "is_displayed") or element.is_displayed():
                return element
        except Exception:
            return None
        return None

    def _safe_page_source(self, driver: Any) -> str:
        try:
            return driver.page_source
        except Exception:
            return ""

    def _guarded_succeed(
        self,
        element: Any,
        *,
        layer: int,
        label: str,
        by: str,
        locator: str,
        confidence: float,
        raw_locator: str,
        layers_tried: list[str],
    ) -> OrchestratorOutcome:
        decision, persistence_allowed = self._review_live_candidate(
            element=element,
            locator=locator,
            confidence=confidence,
            raw_locator=raw_locator,
            source=label,
        )
        if not decision.allowed:
            return OrchestratorOutcome(
                success=False,
                element=None,
                layer_used=layer,
                layer_label=label,
                healed_locator=locator,
                by_strategy=by,
                confidence=confidence,
                script_patched=False,
                layers_tried=layers_tried,
                reason=f"Guardrail blocked: {decision.reason}",
            )
        return self._succeed(
            element,
            layer=layer,
            label=label,
            by=by,
            locator=locator,
            confidence=confidence,
            raw_locator=raw_locator,
            layers_tried=layers_tried,
            persistence_allowed=persistence_allowed,
        )

    def _validate_live_candidate(
        self,
        *,
        element: Any,
        locator: str,
        confidence: float,
        raw_locator: str,
    ) -> Any:
        decision, _ = self._review_live_candidate(
            element=element,
            locator=locator,
            confidence=confidence,
            raw_locator=raw_locator,
        )
        return decision

    def _review_live_candidate(
        self,
        *,
        element: Any,
        locator: str,
        confidence: float,
        raw_locator: str,
        source: str = "orchestrator",
    ) -> Any:
        from aegisai.engine.confidence import route_for_score
        from aegisai.guardrails.validator import GuardrailValidator
        from aegisai.models import GuardrailDecision
        from aegisai.models import ConfidenceBreakdown, HealCandidate, HealRequest, HealResult

        dom_element = self._dom_element_from_web_element(element)
        security = self.security_officer.review_candidate(
            old_locator=raw_locator,
            new_locator=locator,
            element=dom_element,
            source=source,
            confidence=confidence,
        )
        if not security.runtime_allowed:
            return (
                GuardrailDecision(False, security.reason, "security_blocked"),
                False,
            )
        candidate = HealCandidate(
            locator=locator,
            confidence=confidence,
            element=dom_element,
            reason="orchestrator_candidate",
            confidence_breakdown=ConfidenceBreakdown(
                attribute_match=0.0,
                dom_proximity=0.0,
                historical_success=0.0,
                score=confidence,
                route=route_for_score(confidence),
            ),
        )
        request = HealRequest(failing_locator=raw_locator, elements=[dom_element])
        guardrail = GuardrailValidator().validate(
            request,
            HealResult(candidate=candidate, alternatives=[], source="orchestrator"),
        )
        return guardrail, security.persistence_allowed

    def _dom_element_from_web_element(self, element: Any) -> Any:
        from aegisai.models import DomElement

        tag = self._safe_element_attr(element, "tagName") or getattr(element, "tag_name", "") or "unknown"
        tag = str(tag).lower()
        attrs: dict[str, str] = {}
        for name in ("data-testid", "id", "name", "aria-label", "role", "type"):
            value = self._safe_element_attr(element, name)
            if value:
                attrs[name] = str(value)
        text = getattr(element, "text", "") or ""
        role = attrs.get("role") or self._implicit_role(tag, attrs)
        return DomElement(tag=tag, attrs=attrs, text=str(text), role=role, path="live")

    @staticmethod
    def _safe_element_attr(element: Any, name: str) -> str | None:
        try:
            value = element.get_attribute(name)
        except Exception:
            return None
        return str(value) if value else None

    @staticmethod
    def _implicit_role(tag: str, attrs: dict[str, str]) -> str | None:
        if tag == "button":
            return "button"
        if tag == "input":
            input_type = attrs.get("type", "text")
            if input_type in {"button", "submit"}:
                return "button"
            return "textbox"
        return None

    def _succeed(
        self,
        element: Any,
        *,
        layer: int,
        label: str,
        by: str,
        locator: str,
        confidence: float,
        raw_locator: str,
        layers_tried: list[str],
        persistence_allowed: bool = True,
    ) -> OrchestratorOutcome:
        patched = self._patch_script(raw_locator, locator) if layer > 0 and persistence_allowed else False
        return OrchestratorOutcome(
            success=True,
            element=element,
            layer_used=layer,
            layer_label=label,
            healed_locator=locator,
            by_strategy=by,
            confidence=confidence,
            script_patched=patched,
            layers_tried=layers_tried,
            reason=f"Healed at {label}.",
        )

    def _patch_script(self, old_locator: str, new_locator: str) -> bool:
        if not self.script_path or old_locator == new_locator:
            return False
        try:
            import shutil
            from pathlib import Path

            from aegisai.persistence.ast_rewrite import rewrite_static_locator

            path = Path(self.script_path)
            source = path.read_text(encoding="utf-8")
            result = rewrite_static_locator(source, old_locator, new_locator)
            if not result.changed:
                return False
            if self.backup:
                shutil.copy2(path, path.with_suffix(".py.bak"))
            path.write_text(result.source, encoding="utf-8")
            logger.info("[aegisai] Script patched: '%s' -> '%s'", old_locator, new_locator)
            return True
        except Exception as exc:
            logger.warning("[aegisai] Script patch failed: %s", exc)
        return False
