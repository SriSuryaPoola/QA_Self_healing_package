"""Convenience Playwright integration helpers.

The Selenium adapter remains the most mature path, but this module gives
sync Playwright users the same low-friction adoption shape:

* helper functions such as ``heal_fill`` and ``heal_click``
* opt-in auto-activation for ``page.locator(...).fill()/click()`` style code

The adapter is intentionally local and reversible. It patches only the supplied
page instance and does not modify Playwright globally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MethodType
from typing import Any, Callable

from aegisai import AegisAI
from aegisai.dry_run import DryRunResult, audit_locator
from aegisai.engine.heuristic_searcher import search
from aegisai.engine.locator_translator import translate
from aegisai.interceptor.playwright_listener import AegisPlaywrightHooks
from aegisai.reporting import get_session_report


RETRYABLE_ACTIONS = {
    "check",
    "click",
    "clear",
    "dblclick",
    "dispatch_event",
    "drag_to",
    "evaluate",
    "fill",
    "focus",
    "get_attribute",
    "hover",
    "inner_text",
    "input_value",
    "is_enabled",
    "is_visible",
    "press",
    "scroll_into_view_if_needed",
    "select_option",
    "set_checked",
    "screenshot",
    "tap",
    "text_content",
    "type",
    "uncheck",
    "wait_for",
}

FALSE_CAN_TRIGGER_HEAL = {"is_visible", "is_enabled"}


@dataclass
class PlaywrightHealOutcome:
    success: bool
    action_name: str
    original_selector: str
    healed_selector: str | None = None
    layer_used: int | None = None
    layer_label: str = "none"
    confidence: float = 0.0
    reason: str = ""


@dataclass
class AegisPlaywrightPatch:
    """Handle returned by ``activate_aegis`` so users can restore the page."""

    page: Any
    original_locator: Callable[..., Any]
    app: AegisAI = field(default_factory=AegisAI)
    hooks: AegisPlaywrightHooks = field(default_factory=AegisPlaywrightHooks)
    report: Any = field(default_factory=get_session_report)
    active: bool = True
    _healing: bool = False
    last_outcome: PlaywrightHealOutcome | None = None
    outcomes: list[PlaywrightHealOutcome] = field(default_factory=list)

    def locator(self, selector: str, *args: Any, **kwargs: Any) -> Any:
        if not self.active or self._healing or not isinstance(selector, str):
            return self.original_locator(selector, *args, **kwargs)
        raw_locator = self.original_locator(selector, *args, **kwargs)
        return AegisPlaywrightLocator(
            patch=self,
            selector=selector,
            locator=raw_locator,
        )

    def retry_action(
        self,
        *,
        action_name: str,
        selector: str,
        original_error: BaseException,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        if self._healing:
            raise original_error

        self._healing = True
        self.hooks.record_action(action_name, locator=selector)
        self.hooks.capture_failure(original_error, locator=selector)
        try:
            l0_result = self._try_l0_original_again(action_name, selector, args, kwargs)
            if l0_result is not _UNHEALED:
                self._record(
                    PlaywrightHealOutcome(
                        success=True,
                        action_name=action_name,
                        original_selector=selector,
                        healed_selector=selector,
                        layer_used=0,
                        layer_label="L0:playwright_retry",
                        confidence=1.0,
                        reason="Original Playwright locator succeeded after load-state retry.",
                    )
                )
                return l0_result

            healed_selector, outcome = self._find_healed_selector(action_name, selector)
            if not healed_selector:
                self._record(outcome)
                raise original_error

            healed_locator = self.original_locator(healed_selector)
            method = getattr(healed_locator, action_name)
            result = method(*args, **kwargs)
            self._record(outcome)
            return result
        finally:
            self._healing = False

    def restore(self) -> None:
        """Restore the original ``page.locator`` method."""

        if not self.active:
            return
        self.page.locator = self.original_locator
        if getattr(self.page, "_aegisai_playwright_patch", None) is self:
            try:
                delattr(self.page, "_aegisai_playwright_patch")
            except Exception:
                pass
        self.active = False

    def _try_l0_original_again(
        self,
        action_name: str,
        selector: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        try:
            if hasattr(self.page, "wait_for_load_state"):
                self.page.wait_for_load_state("domcontentloaded", timeout=1000)
            locator = self.original_locator(selector)
            return getattr(locator, action_name)(*args, **kwargs)
        except Exception:
            return _UNHEALED

    def _find_healed_selector(self, action_name: str, selector: str) -> tuple[str | None, PlaywrightHealOutcome]:
        failing_locator = _selector_for_healing(selector)
        page_source = _safe_page_content(self.page)

        l1_selector, l1_label = self._try_l1_translation(failing_locator)
        if l1_selector:
            return l1_selector, PlaywrightHealOutcome(
                success=True,
                action_name=action_name,
                original_selector=selector,
                healed_selector=l1_selector,
                layer_used=1,
                layer_label=f"L1:{l1_label}",
                confidence=0.95,
                reason="Healed with Playwright locator translation.",
            )

        expected_role = _expected_role(action_name, failing_locator)
        result = self.app.heal_locator(
            failing_locator=failing_locator,
            dom=page_source,
            expected_role=expected_role,
        )
        if result.locator and self._selector_has_match(result.locator):
            return result.locator, PlaywrightHealOutcome(
                success=True,
                action_name=action_name,
                original_selector=selector,
                healed_selector=result.locator,
                layer_used=2,
                layer_label=f"L2:{result.source}",
                confidence=result.confidence,
                reason=result.guardrail.reason if result.guardrail else "Healed with deterministic SDK.",
            )

        l3_selector, l3_confidence, l3_label = self._try_l3_heuristic(failing_locator, page_source)
        if l3_selector:
            return l3_selector, PlaywrightHealOutcome(
                success=True,
                action_name=action_name,
                original_selector=selector,
                healed_selector=l3_selector,
                layer_used=3,
                layer_label=f"L3:{l3_label}",
                confidence=l3_confidence,
                reason="Healed with Playwright heuristic search.",
            )

        l4_selector, l4_label = self._try_l4_probe_strategies(failing_locator)
        if l4_selector:
            return l4_selector, PlaywrightHealOutcome(
                success=True,
                action_name=action_name,
                original_selector=selector,
                healed_selector=l4_selector,
                layer_used=4,
                layer_label=f"L4:{l4_label}",
                confidence=0.88,
                reason="Healed with Playwright live selector probe.",
            )

        reason = "L0-L4 exhausted. Playwright L5 is not started without an explicit LLM-backed workflow."
        if result.guardrail and result.guardrail.reason:
            reason = f"{reason} Last deterministic reason: {result.guardrail.reason}"
        return None, PlaywrightHealOutcome(
            success=False,
            action_name=action_name,
            original_selector=selector,
            reason=reason,
        )

    def _try_l1_translation(self, failing_locator: str) -> tuple[str | None, str]:
        for candidate in translate(failing_locator):
            selector = _to_playwright_selector(candidate.by, candidate.locator)
            if self._selector_has_match(selector):
                return selector, candidate.source
        return None, ""

    def _try_l3_heuristic(self, failing_locator: str, page_source: str) -> tuple[str | None, float, str]:
        for candidate in search(failing_locator, page_source):
            if candidate.confidence < 0.75:
                break
            selector = _to_playwright_selector(candidate.by, candidate.locator)
            if self._selector_has_match(selector):
                return selector, candidate.confidence, candidate.strategy
        return None, 0.0, ""

    def _try_l4_probe_strategies(self, failing_locator: str) -> tuple[str | None, str]:
        try:
            from aegisai.engine.js_prober import _build_strategies
        except Exception:
            return None, ""

        for strategy in _build_strategies(failing_locator):
            selector = strategy.get("selector")
            if selector and self._selector_has_match(selector):
                return selector, str(strategy.get("label") or strategy.get("strategy") or "selector_probe")
        return None, ""

    def _selector_has_match(self, selector: str) -> bool:
        try:
            return self.original_locator(selector).count() > 0
        except Exception:
            return False

    def _record(self, outcome: PlaywrightHealOutcome) -> None:
        self.last_outcome = outcome
        self.outcomes.append(outcome)
        self.report.record_attempt(
            original_locator=outcome.original_selector,
            healed_locator=outcome.healed_selector,
            success=outcome.success,
            source=outcome.layer_label,
            layer_label=outcome.layer_label,
            confidence=outcome.confidence,
            reason=outcome.reason,
            framework="playwright",
            action=outcome.action_name,
        )


class AegisPlaywrightLocator:
    """Thin wrapper around a Playwright Locator that retries failed actions."""

    def __init__(self, *, patch: AegisPlaywrightPatch, selector: str, locator: Any) -> None:
        self._patch = patch
        self._selector = selector
        self._locator = locator

    @property
    def raw_locator(self) -> Any:
        return self._locator

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._locator, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            if name not in RETRYABLE_ACTIONS or not self._patch.active:
                return attr(*args, **kwargs)
            try:
                result = attr(*args, **kwargs)
                if name in FALSE_CAN_TRIGGER_HEAL and result is False:
                    raise RuntimeError(f"Playwright locator returned False for {name}.")
                return result
            except BaseException as exc:
                return self._patch.retry_action(
                    action_name=name,
                    selector=self._selector,
                    original_error=exc,
                    args=args,
                    kwargs=kwargs,
                )

        return _wrapped


def activate_aegis(
    page: Any,
    *,
    app: AegisAI | None = None,
) -> AegisPlaywrightPatch:
    """Opt-in auto-healing for sync Playwright ``page.locator`` calls."""

    existing = getattr(page, "_aegisai_playwright_patch", None)
    if isinstance(existing, AegisPlaywrightPatch) and existing.active:
        return existing

    if not hasattr(page, "locator"):
        raise TypeError("Playwright page object must expose a locator method.")

    original_locator = page.locator
    patch = AegisPlaywrightPatch(
        page=page,
        original_locator=original_locator,
        app=app or AegisAI(),
    )

    def _patched_locator(self: Any, selector: str, *args: Any, **kwargs: Any) -> Any:
        return patch.locator(selector, *args, **kwargs)

    page.locator = MethodType(_patched_locator, page)
    page._aegisai_playwright_patch = patch
    return patch


def deactivate_aegis(page: Any) -> None:
    """Restore a page previously patched by ``activate_aegis``."""

    patch = getattr(page, "_aegisai_playwright_patch", None)
    if isinstance(patch, AegisPlaywrightPatch):
        patch.restore()


def heal_selector(page: Any, selector: str, *, app: AegisAI | None = None) -> str:
    """Return a healed selector for the current page DOM."""

    active_app = app or AegisAI()
    result = active_app.heal_locator(
        failing_locator=_selector_for_healing(selector),
        dom=_safe_page_content(page),
        expected_role=None,
    )
    if not result.locator:
        reason = result.guardrail.reason if result.guardrail else "No viable selector candidate was found."
        raise LookupError(reason)
    return result.locator


def heal_fill(page: Any, selector: str, value: str, **kwargs: Any) -> Any:
    """Fill a Playwright locator, healing the selector if the action fails."""

    patch = activate_aegis(page)
    return patch.locator(selector).fill(value, **kwargs)


def heal_click(page: Any, selector: str, **kwargs: Any) -> Any:
    """Click a Playwright locator, healing the selector if the action fails."""

    patch = activate_aegis(page)
    return patch.locator(selector).click(**kwargs)


def dry_run_selector(page: Any, selector: str, *, expected_role: str | None = None) -> DryRunResult:
    """Analyze a Playwright selector without creating a Locator or interacting."""

    return audit_locator(
        failing_locator=_selector_for_healing(selector),
        dom=_safe_page_content(page),
        expected_role=expected_role,
    )


def heal_frame_fill(page: Any, frame_selector: str, selector: str, value: str, **kwargs: Any) -> Any:
    """Fill a selector inside a Playwright iframe using the same healing logic."""

    frame = page.frame_locator(frame_selector)
    try:
        return frame.locator(selector).fill(value, **kwargs)
    except Exception:
        healed = heal_selector(_FrameContentAdapter(frame), selector)
        return frame.locator(healed).fill(value, **kwargs)


def heal_frame_click(page: Any, frame_selector: str, selector: str, **kwargs: Any) -> Any:
    """Click a selector inside a Playwright iframe using the same healing logic."""

    frame = page.frame_locator(frame_selector)
    try:
        return frame.locator(selector).click(**kwargs)
    except Exception:
        healed = heal_selector(_FrameContentAdapter(frame), selector)
        return frame.locator(healed).click(**kwargs)


def _selector_for_healing(selector: str) -> str:
    if selector.startswith("xpath="):
        return selector[len("xpath="):]
    if selector.startswith("css="):
        return selector[len("css="):]
    return selector


def _to_playwright_selector(by: str, locator: str) -> str:
    return f"xpath={locator}" if by.lower() == "xpath" else locator


def _safe_page_content(page: Any) -> str:
    try:
        return page.content()
    except Exception:
        return ""


def _expected_role(action_name: str, selector: str) -> str | None:
    if action_name in {"fill", "type", "input_value"}:
        return "textbox"
    lowered = selector.lower()
    if action_name in {"click", "dblclick"} and any(token in lowered for token in ("button", "btn", "submit")):
        return "button"
    return None


class _FrameContentAdapter:
    def __init__(self, frame_locator: Any) -> None:
        self.frame_locator = frame_locator

    def content(self) -> str:
        # Playwright FrameLocator has no direct content() API. This adapter keeps
        # iframe helpers compatible with test doubles and frameworks that expose
        # a custom content method on their frame wrapper.
        if hasattr(self.frame_locator, "content"):
            return self.frame_locator.content()
        return ""


class _Unhealed:
    pass


_UNHEALED = _Unhealed()
