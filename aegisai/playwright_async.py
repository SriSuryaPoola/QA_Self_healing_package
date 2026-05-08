"""Async Playwright helpers for AegisAI.

These helpers intentionally start with explicit calls. They cover the common
async ``page.locator(selector).fill()/click()`` path without requiring teams to
change their framework structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MethodType
from typing import Any, Callable

from aegisai import AegisAI
from aegisai.playwright import _selector_for_healing


ASYNC_RETRYABLE_ACTIONS = {
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
    "press",
    "select_option",
    "set_checked",
    "screenshot",
    "tap",
    "type",
    "uncheck",
    "wait_for",
}


@dataclass
class AsyncPlaywrightHealOutcome:
    success: bool
    action_name: str
    original_selector: str
    healed_selector: str | None = None
    confidence: float = 0.0
    reason: str = ""


@dataclass
class AegisAsyncPlaywrightPatch:
    page: Any
    original_locator: Callable[..., Any]
    app: AegisAI = field(default_factory=AegisAI)
    active: bool = True
    _healing: bool = False
    last_outcome: AsyncPlaywrightHealOutcome | None = None

    def locator(self, selector: str, *args: Any, **kwargs: Any) -> Any:
        if not self.active or self._healing or not isinstance(selector, str):
            return self.original_locator(selector, *args, **kwargs)
        return AegisAsyncPlaywrightLocator(
            patch=self,
            selector=selector,
            locator=self.original_locator(selector, *args, **kwargs),
        )

    async def retry_action(
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
        try:
            healed_selector = await async_heal_selector(self.page, selector, app=self.app)
            healed_locator = self.original_locator(healed_selector)
            result = await getattr(healed_locator, action_name)(*args, **kwargs)
            self.last_outcome = AsyncPlaywrightHealOutcome(
                success=True,
                action_name=action_name,
                original_selector=selector,
                healed_selector=healed_selector,
                confidence=1.0,
                reason="Async Playwright action healed with deterministic DOM analysis.",
            )
            return result
        except Exception:
            self.last_outcome = AsyncPlaywrightHealOutcome(
                success=False,
                action_name=action_name,
                original_selector=selector,
                reason=str(original_error),
            )
            raise original_error
        finally:
            self._healing = False

    def restore(self) -> None:
        if not self.active:
            return
        self.page.locator = self.original_locator
        if getattr(self.page, "_aegisai_async_playwright_patch", None) is self:
            try:
                delattr(self.page, "_aegisai_async_playwright_patch")
            except Exception:
                pass
        self.active = False


class AegisAsyncPlaywrightLocator:
    def __init__(self, *, patch: AegisAsyncPlaywrightPatch, selector: str, locator: Any) -> None:
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

        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            if name not in ASYNC_RETRYABLE_ACTIONS or not self._patch.active:
                return await attr(*args, **kwargs)
            try:
                return await attr(*args, **kwargs)
            except BaseException as exc:
                return await self._patch.retry_action(
                    action_name=name,
                    selector=self._selector,
                    original_error=exc,
                    args=args,
                    kwargs=kwargs,
                )

        return _wrapped


def activate_aegis_async(page: Any, *, app: AegisAI | None = None) -> AegisAsyncPlaywrightPatch:
    existing = getattr(page, "_aegisai_async_playwright_patch", None)
    if isinstance(existing, AegisAsyncPlaywrightPatch) and existing.active:
        return existing
    if not hasattr(page, "locator"):
        raise TypeError("Async Playwright page object must expose a locator method.")

    original_locator = page.locator
    patch = AegisAsyncPlaywrightPatch(page=page, original_locator=original_locator, app=app or AegisAI())

    def _patched_locator(self: Any, selector: str, *args: Any, **kwargs: Any) -> Any:
        return patch.locator(selector, *args, **kwargs)

    page.locator = MethodType(_patched_locator, page)
    page._aegisai_async_playwright_patch = patch
    return patch


def deactivate_aegis_async(page: Any) -> None:
    patch = getattr(page, "_aegisai_async_playwright_patch", None)
    if isinstance(patch, AegisAsyncPlaywrightPatch):
        patch.restore()


async def async_heal_selector(page: Any, selector: str, *, app: AegisAI | None = None) -> str:
    active_app = app or AegisAI()
    dom = await page.content()
    result = active_app.heal_locator(failing_locator=_selector_for_healing(selector), dom=dom)
    if not result.locator:
        reason = result.guardrail.reason if result.guardrail else "No viable selector candidate was found."
        raise LookupError(reason)
    return result.locator


async def async_heal_fill(page: Any, selector: str, value: str, **kwargs: Any) -> Any:
    patch = activate_aegis_async(page)
    return await patch.locator(selector).fill(value, **kwargs)


async def async_heal_click(page: Any, selector: str, **kwargs: Any) -> Any:
    patch = activate_aegis_async(page)
    return await patch.locator(selector).click(**kwargs)
