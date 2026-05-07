"""Autonomous healer - the full L5 self-healing pipeline.

The L5 path is intentionally governance-first: code intent and the live DOM are
sanitized by the Security Officer before any context reaches an LLM, and script
persistence only happens for policy-approved low-risk fixes.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aegisai.engine.code_reader import CodeContext, extract_context
from aegisai.engine.llm import StrictJsonLLMEngine
from aegisai.engine.universal_llm_adapter import UniversalLLMAdapter
from aegisai.guardrails.validator import GuardrailValidator
from aegisai.models import (
    ConfidenceBreakdown,
    DomElement,
    HealCandidate,
    HealRequest,
    HealResult,
)
from aegisai.persistence.ast_rewrite import rewrite_static_locator
from aegisai.security import SecurityOfficer, SecurityPolicy
from aegisai.utils.dom_parser import parse_dom_subset

logger = logging.getLogger(__name__)

_BY_MAP = {
    "css": ("CSS_SELECTOR", "css selector"),
    "css_selector": ("CSS_SELECTOR", "css selector"),
    "xpath": ("XPATH", "xpath"),
    "id": ("ID", "id"),
    "name": ("NAME", "name"),
    "class_name": ("CLASS_NAME", "class name"),
    "tag_name": ("TAG_NAME", "tag name"),
    "link_text": ("LINK_TEXT", "link text"),
}


@dataclass
class HealOutcome:
    """Result returned by the autonomous healer."""

    success: bool
    element: Any | None
    healed_locator: str | None
    by_strategy: str | None
    confidence: float
    script_patched: bool
    reason: str


def _build_llm_prompt(
    code_ctx: CodeContext | None,
    security_payload: dict[str, Any],
    failing_locator: str,
) -> str:
    """Build a compact prompt from Security-Officer-approved context."""

    dom_summary = security_payload.get("elements", [])[:30]
    security_summary = security_payload.get("security", {})
    code_fragment = code_ctx.to_prompt_fragment() if code_ctx else f"Failing locator: {failing_locator}"

    return (
        f"{code_fragment}\n\n"
        f"Security context:\n{json.dumps(security_summary, indent=2)}\n\n"
        f"Sanitized live DOM candidates (up to 30 elements):\n"
        f"{json.dumps(dom_summary, indent=2)}\n\n"
        "Based on the code intent and the DOM, return the single best CSS selector "
        "to locate the target element. Respond ONLY with valid JSON:\n"
        '{"locator": "<css_selector>", "by": "css", "confidence": 0.95, "reason": "<short explanation>"}'
    )


def _selenium_by(by_str: str) -> Any:
    """Return the Selenium By constant for a strategy string."""

    try:
        from selenium.webdriver.common.by import By

        key = by_str.lower().replace(" ", "_").replace("-", "_")
        mapped_name, _ = _BY_MAP.get(key, ("CSS_SELECTOR", "css selector"))
        return getattr(By, mapped_name)
    except ImportError:
        return "css selector"


def _element_for_locator(locator: str, elements: list[DomElement]) -> DomElement | None:
    normalized_locator = locator.strip().replace("'", '"')
    for element in elements:
        stable = element.stable_locator()
        if stable and stable.strip().replace("'", '"') == normalized_locator:
            return element
    return None


class AutonomousHealer:
    """Full autonomous self-healing pipeline for the L5 LLM fallback."""

    def __init__(
        self,
        script_path: str | Path | None = None,
        backup: bool = True,
        security_policy: SecurityPolicy | None = None,
    ) -> None:
        self.script_path = Path(script_path) if script_path else None
        self.backup = backup
        self.guardrails = GuardrailValidator()
        self.security_officer = SecurityOfficer(security_policy)
        self._adapter = UniversalLLMAdapter() if UniversalLLMAdapter.is_configured() else None
        if not self._adapter:
            issue = UniversalLLMAdapter.configuration_issue() or "the LLM adapter is not configured."
            logger.warning(
                "[aegisai] L5 LLM fallback is unavailable because %s",
                issue,
            )

    def heal(
        self,
        exception: BaseException,
        *,
        driver: Any,
        wait: Any,
        failing_locator: str,
        original_condition: Any = None,
    ) -> HealOutcome:
        """Run the full autonomous heal pipeline."""

        if not self._adapter:
            issue = UniversalLLMAdapter.configuration_issue() or "the LLM adapter is not configured."
            return HealOutcome(
                success=False,
                element=None,
                healed_locator=None,
                by_strategy=None,
                confidence=0.0,
                script_patched=False,
                reason=f"L5 LLM fallback is unavailable because {issue}",
            )

        logger.info("[aegisai] AutonomousHealer starting for: %s", failing_locator)

        code_ctx = None
        if self.script_path:
            code_ctx = extract_context(self.script_path, failing_locator)
            if code_ctx:
                logger.info(
                    "[aegisai] Code intent: action='%s' variable='%s'",
                    code_ctx.intended_action,
                    code_ctx.variable_name,
                )

        try:
            page_source = driver.page_source
        except Exception:
            page_source = ""
        elements = parse_dom_subset(page_source)
        logger.info("[aegisai] DOM parsed: %d candidate elements found.", len(elements))

        security_payload, context_decision = self.security_officer.build_llm_payload(
            failing_locator=failing_locator,
            elements=elements,
        )
        if not context_decision.llm_allowed:
            return HealOutcome(
                success=False,
                element=None,
                healed_locator=None,
                by_strategy=None,
                confidence=0.0,
                script_patched=False,
                reason=f"LLM blocked by Security Officer: {context_decision.reason}",
            )

        prompt = _build_llm_prompt(code_ctx, security_payload, failing_locator)
        try:
            engine = StrictJsonLLMEngine(
                adapter=self._adapter,
                timeout_seconds=10.0,
                temperature=0.0,
            )
            llm_result = engine.suggest({"prompt": prompt})
        except Exception as exc:
            logger.error("[aegisai] LLM call failed: %s", exc)
            return HealOutcome(
                success=False,
                element=None,
                healed_locator=None,
                by_strategy=None,
                confidence=0.0,
                script_patched=False,
                reason=f"LLM error: {exc}",
            )

        logger.info(
            "[aegisai] LLM suggested locator: %s (confidence=%.2f)",
            llm_result.locator,
            llm_result.confidence,
        )

        matched_element = _element_for_locator(llm_result.locator, elements)
        if matched_element is None:
            return HealOutcome(
                success=False,
                element=None,
                healed_locator=llm_result.locator,
                by_strategy="css",
                confidence=llm_result.confidence,
                script_patched=False,
                reason="LLM locator did not match the filtered DOM subset.",
            )

        security_decision = self.security_officer.review_candidate(
            old_locator=failing_locator,
            new_locator=llm_result.locator,
            element=matched_element,
            source="llm",
            confidence=llm_result.confidence,
        )
        if not security_decision.runtime_allowed:
            return HealOutcome(
                success=False,
                element=None,
                healed_locator=llm_result.locator,
                by_strategy="css",
                confidence=llm_result.confidence,
                script_patched=False,
                reason=f"Security Officer blocked runtime heal: {security_decision.reason}",
            )

        heal_candidate = HealCandidate(
            locator=llm_result.locator,
            confidence=llm_result.confidence,
            element=matched_element,
            reason="llm_autonomous",
            confidence_breakdown=ConfidenceBreakdown(
                attribute_match=0.0,
                dom_proximity=0.0,
                historical_success=0.0,
                score=llm_result.confidence,
                route="confirm_across_runs" if llm_result.confidence >= 0.8 else "block",
            ),
        )
        heal_result_obj = HealResult(candidate=heal_candidate, alternatives=[], source="llm", llm_used=True)
        raw_locator = failing_locator.split("=", 1)[-1] if "=" in failing_locator else failing_locator
        request = HealRequest(failing_locator=raw_locator, elements=elements)
        decision = self.guardrails.validate(request, heal_result_obj)

        if not decision.allowed:
            logger.warning("[aegisai] Guardrail blocked LLM suggestion: %s", decision.reason)
            return HealOutcome(
                success=False,
                element=None,
                healed_locator=llm_result.locator,
                by_strategy="css",
                confidence=llm_result.confidence,
                script_patched=False,
                reason=f"Guardrail blocked: {decision.reason}",
            )

        by_key = "css"
        by_obj = _selenium_by(by_key)
        try:
            if original_condition and wait:
                element = wait.until(original_condition((by_obj, llm_result.locator)))
            else:
                element = driver.find_element(by_obj, llm_result.locator)
            logger.info("[aegisai] Browser retry succeeded with: %s", llm_result.locator)
        except Exception as retry_exc:
            logger.error("[aegisai] Browser retry failed: %s", retry_exc)
            return HealOutcome(
                success=False,
                element=None,
                healed_locator=llm_result.locator,
                by_strategy=by_key,
                confidence=llm_result.confidence,
                script_patched=False,
                reason=f"Browser retry failed: {retry_exc}",
            )

        patched = (
            self._patch_script(raw_locator, llm_result.locator)
            if security_decision.persistence_allowed
            else False
        )

        return HealOutcome(
            success=True,
            element=element,
            healed_locator=llm_result.locator,
            by_strategy=by_key,
            confidence=llm_result.confidence,
            script_patched=patched,
            reason=(
                "Autonomous heal succeeded."
                if security_decision.persistence_allowed
                else "Autonomous heal succeeded; persistence requires Security Officer review."
            ),
        )

    def _patch_script(self, old_locator: str, new_locator: str) -> bool:
        """Rewrite the user's script to permanently fix the locator."""

        if not self.script_path or not self.script_path.exists():
            return False
        try:
            source = self.script_path.read_text(encoding="utf-8")

            if self.backup:
                bak_path = self.script_path.with_suffix(".py.bak")
                shutil.copy2(self.script_path, bak_path)
                logger.info("[aegisai] Backup written to: %s", bak_path)

            result = rewrite_static_locator(source, old_locator, new_locator)
            if result.changed:
                self.script_path.write_text(result.source, encoding="utf-8")
                logger.info("[aegisai] Script rewritten: %s -> %s", old_locator, new_locator)
                return True
            logger.warning("[aegisai] Script rewrite skipped: %s", result.reason)
        except Exception as exc:
            logger.error("[aegisai] Script patch error: %s", exc)
        return False
