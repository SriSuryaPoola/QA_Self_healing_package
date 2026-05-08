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
    layer_timings: dict[str, float] = field(default_factory=dict)
    total_ms: float = 0.0


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
        self._active_started = 0.0
        self._active_layer_timings: dict[str, float] = {}

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
        self._active_started = time.perf_counter()
        self._active_layer_timings = {}

        logger.info("[aegisai][L0] DOM readiness check for: %s", failing_locator)
        layers_tried.append("L0:dom_ready")
        layer_started = time.perf_counter()
        dom_ready, page_source = self._l0_dom_ready(driver, raw_locator)
        self._record_layer_time("L0:dom_ready", layer_started)
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
        layer_started = time.perf_counter()
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
                    self._record_layer_time("L1:translation", layer_started)
                    self._refresh_outcome_timing(outcome)
                    return outcome
                logger.info("[aegisai][L1] Guardrail blocked %s: %s", candidate.locator, outcome.reason)
        except Exception as exc:
            logger.debug("[aegisai][L1] error: %s", exc)
        self._record_layer_time("L1:translation", layer_started)

        logger.info("[aegisai][L2] Trying deterministic engine.")
        layers_tried.append("L2:deterministic")
        layer_started = time.perf_counter()
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
                        self._record_layer_time("L2:deterministic", layer_started)
                        self._refresh_outcome_timing(outcome)
                        return outcome
                    logger.info("[aegisai][L2] Guardrail blocked %s: %s", locator, outcome.reason)
            else:
                reason = decision.reason if not decision.allowed else "Confidence below threshold."
                logger.info("[aegisai][L2] skipped: %s", reason)
        except Exception as exc:
            logger.debug("[aegisai][L2] error: %s", exc)
        self._record_layer_time("L2:deterministic", layer_started)

        logger.info("[aegisai][L3] Trying heuristic structural search.")
        layers_tried.append("L3:heuristic")
        layer_started = time.perf_counter()
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
                    self._record_layer_time("L3:heuristic", layer_started)
                    self._refresh_outcome_timing(outcome)
                    return outcome
                logger.info("[aegisai][L3] Guardrail blocked %s: %s", candidate.locator, outcome.reason)
        except Exception as exc:
            logger.debug("[aegisai][L3] error: %s", exc)
        self._record_layer_time("L3:heuristic", layer_started)

        logger.info("[aegisai][L4] Trying live browser JS probing.")
        layers_tried.append("L4:js_probe")
        layer_started = time.perf_counter()
        try:
            from aegisai.engine.js_prober import probe

            probe_result = probe(failing_locator, driver)
            if probe_result.found and probe_result.css_locator:
                locator = probe_result.css_locator
                element = probe_result.element or self._quick_find(driver, "css", locator)
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
                        self._record_layer_time("L4:js_probe", layer_started)
                        self._refresh_outcome_timing(outcome)
                        return outcome
                    logger.info("[aegisai][L4] Guardrail blocked %s: %s", locator, outcome.reason)
        except Exception as exc:
            logger.debug("[aegisai][L4] error: %s", exc)
        self._record_layer_time("L4:js_probe", layer_started)

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
                layer_timings=dict(self._active_layer_timings),
                total_ms=self._total_ms(),
            )

        logger.info("[aegisai][L5] All free layers failed; invoking LLM.")
        layers_tried.append("L5:llm")
        llm_failure_reason = ""
        layer_started = time.perf_counter()
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
                self._record_layer_time("L5:llm", layer_started)
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
                    layer_timings=dict(self._active_layer_timings),
                    total_ms=self._total_ms(),
                )
            llm_failure_reason = outcome.reason
            logger.info("[aegisai][L5] unavailable: %s", outcome.reason)
        except Exception as exc:
            llm_failure_reason = f"L5 LLM fallback failed safely: {exc}"
            logger.error("[aegisai][L5] LLM heal failed: %s", exc)
        self._record_layer_time("L5:llm", layer_started)

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
            layer_timings=dict(self._active_layer_timings),
            total_ms=self._total_ms(),
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
        time.sleep(self._smart_wait_seconds(raw_locator))
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

    @staticmethod
    def _smart_wait_seconds(raw_locator: str) -> float:
        lowered = raw_locator.lower()
        if any(token in lowered for token in ("modal", "dialog", "drawer", "toast")):
            return 1.0
        if any(token in lowered for token in ("button", "submit", "login", "save")):
            return 0.6
        return 0.8

    def _quick_find(self, driver: Any, by_str: str, locator: str) -> Any:
        try:
            from selenium.webdriver.common.by import By

            by_obj = By.XPATH if by_str.lower() == "xpath" else By.CSS_SELECTOR
        except Exception:
            by_obj = "xpath" if by_str.lower() == "xpath" else "css selector"

        element = self._find_visible_element(driver, by_obj, locator)
        if element is not None:
            return element
        return self._quick_find_in_frames(driver, by_obj, locator, depth=0)

    def _find_visible_element(self, driver: Any, by_obj: Any, locator: str) -> Any:
        try:
            element = driver.find_element(by_obj, locator)
            if not hasattr(element, "is_displayed") or element.is_displayed():
                return element
        except Exception:
            return None
        return None

    def _quick_find_in_frames(self, driver: Any, by_obj: Any, locator: str, *, depth: int) -> Any:
        if depth >= 3 or not callable(getattr(driver, "find_elements", None)):
            return None
        try:
            from selenium.webdriver.common.by import By

            frame_by = By.CSS_SELECTOR
        except Exception:
            frame_by = "css selector"

        try:
            frames = driver.find_elements(frame_by, "iframe,frame")
        except Exception:
            return None

        switch_to = getattr(driver, "switch_to", None)
        if switch_to is None or not callable(getattr(switch_to, "frame", None)):
            return None

        for frame in frames:
            found_in_frame = False
            try:
                switch_to.frame(frame)
                element = self._find_visible_element(driver, by_obj, locator)
                if element is not None:
                    found_in_frame = True
                    return element
                nested = self._quick_find_in_frames(driver, by_obj, locator, depth=depth + 1)
                if nested is not None:
                    found_in_frame = True
                    return nested
            except Exception:
                pass
            finally:
                if not found_in_frame:
                    self._switch_to_parent_or_default(driver)
        return None

    @staticmethod
    def _switch_to_parent_or_default(driver: Any) -> None:
        switch_to = getattr(driver, "switch_to", None)
        if switch_to is None:
            return
        try:
            parent = getattr(switch_to, "parent_frame", None)
            if callable(parent):
                parent()
                return
        except Exception:
            pass
        try:
            default_content = getattr(switch_to, "default_content", None)
            if callable(default_content):
                default_content()
        except Exception:
            pass

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
            layer_timings=dict(self._active_layer_timings),
            total_ms=self._total_ms(),
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
        if layer > 0 and not persistence_allowed:
            self._write_review_suggestion(
                old_locator=raw_locator,
                new_locator=locator,
                confidence=confidence,
                source=label,
                reason="Runtime heal allowed, but source persistence requires review.",
            )
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
            layer_timings=dict(self._active_layer_timings),
            total_ms=self._total_ms(),
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

    def _write_review_suggestion(
        self,
        *,
        old_locator: str,
        new_locator: str,
        confidence: float,
        source: str,
        reason: str,
    ) -> None:
        try:
            from aegisai.persistence.suggestions import append_heal_suggestion, create_source_suggestion

            suggestion = create_source_suggestion(
                old_locator=old_locator,
                new_locator=new_locator,
                confidence=confidence,
                source_label=source,
                script_path=self.script_path,
                review_required=True,
                reason=reason,
            )
            append_heal_suggestion(suggestion)
        except Exception as exc:
            logger.debug("[aegisai] Suggestion artifact write skipped: %s", exc)

    def _record_layer_time(self, label: str, started: float) -> None:
        self._active_layer_timings[label] = round((time.perf_counter() - started) * 1000, 3)

    def _total_ms(self) -> float:
        if not self._active_started:
            return 0.0
        return round((time.perf_counter() - self._active_started) * 1000, 3)

    def _refresh_outcome_timing(self, outcome: OrchestratorOutcome) -> None:
        outcome.layer_timings = dict(self._active_layer_timings)
        outcome.total_ms = self._total_ms()
