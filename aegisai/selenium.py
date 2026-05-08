"""Convenience Selenium integration helpers.

The explicit listener remains the safest low-level API. This module adds two
friendlier adoption paths:

* helper functions such as ``heal_find`` for one-call protected lookups
* opt-in auto-activation for existing suites that call ``driver.find_element``
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MethodType
from typing import Any, Callable

from aegisai.interceptor.selenium_listener import AegisSeleniumListener
from aegisai.dry_run import DryRunResult, audit_locator

ConditionFactory = Callable[[tuple[Any, str]], Any]


def heal_find(
    driver: Any,
    wait: Any | None,
    by: Any,
    locator: str,
    condition: ConditionFactory | None = None,
    *,
    script_path: str | None = None,
    backup: bool = True,
    listener: AegisSeleniumListener | None = None,
    enable_llm: bool | None = None,
    security_policy: Any = None,
) -> Any:
    """Find an element, healing the locator if the normal lookup fails."""

    active_listener = listener or AegisSeleniumListener(
        script_path=script_path,
        backup=backup,
        enable_llm=enable_llm,
        security_policy=security_policy,
    )
    active_listener.before_find(by=_by_label(by), value=locator, driver=driver)
    try:
        if condition is not None:
            if wait is None:
                raise ValueError("wait is required when a Selenium expected-condition is provided.")
            return wait.until(condition((by, locator)))
        return driver.find_element(by, locator)
    except Exception as exc:
        return active_listener.autonomous_heal(
            exc,
            driver=driver,
            wait=wait,
            original_condition=condition,
        )


def heal_click(
    driver: Any,
    wait: Any | None,
    by: Any,
    locator: str,
    condition: ConditionFactory | None = None,
    **kwargs: Any,
) -> Any:
    """Find a clickable element through AegisAI and click it."""

    element = heal_find(driver, wait, by, locator, condition, **kwargs)
    element.click()
    return element


def heal_send_keys(
    driver: Any,
    wait: Any | None,
    by: Any,
    locator: str,
    text: str,
    condition: ConditionFactory | None = None,
    **kwargs: Any,
) -> Any:
    """Find an input through AegisAI and send keys to it."""

    element = heal_find(driver, wait, by, locator, condition, **kwargs)
    element.send_keys(text)
    return element


def dry_run_find(
    driver: Any,
    by: Any,
    locator: str,
    *,
    expected_role: str | None = None,
) -> DryRunResult:
    """Analyze a Selenium locator without calling ``find_element`` or interacting."""

    try:
        dom = driver.page_source
    except Exception:
        dom = ""
    return audit_locator(
        failing_locator=str(locator),
        dom=dom,
        expected_role=expected_role or _expected_role_from_locator(str(by), str(locator)),
    )


@dataclass
class AegisSeleniumPatch:
    """Handle returned by ``activate_aegis`` so users can restore the driver."""

    driver: Any
    listener: AegisSeleniumListener
    original_find_element: Callable[..., Any]
    active: bool = True
    _healing: bool = False

    def find_element(self, by: Any = "id", value: str | None = None) -> Any:
        if not self.active or self._healing:
            return _call_original_find(self.original_find_element, by, value)

        locator = str(value if value is not None else by)
        self.listener.before_find(by=_by_label(by), value=locator, driver=self.driver)
        try:
            return _call_original_find(self.original_find_element, by, value)
        except Exception as exc:
            self._healing = True
            try:
                return self.listener.autonomous_heal(
                    exc,
                    driver=self.driver,
                    wait=None,
                    original_condition=None,
                )
            finally:
                self._healing = False

    def restore(self) -> None:
        """Restore the original ``driver.find_element`` method."""

        if not self.active:
            return
        self.driver.find_element = self.original_find_element
        if getattr(self.driver, "_aegisai_patch", None) is self:
            try:
                delattr(self.driver, "_aegisai_patch")
            except Exception:
                pass
        self.active = False


def activate_aegis(
    driver: Any,
    *,
    script_path: str | None = None,
    backup: bool = True,
    enable_llm: bool | None = None,
    security_policy: Any = None,
) -> AegisSeleniumPatch:
    """Opt-in auto-healing for ``driver.find_element`` calls.

    This is intentionally explicit and reversible. It patches only the supplied
    driver instance, not Selenium globally.
    """

    existing = getattr(driver, "_aegisai_patch", None)
    if isinstance(existing, AegisSeleniumPatch) and existing.active:
        return existing

    if not hasattr(driver, "find_element"):
        raise TypeError("Selenium driver object must expose a find_element method.")

    listener = AegisSeleniumListener(
        script_path=script_path,
        backup=backup,
        enable_llm=enable_llm,
        security_policy=security_policy,
    )
    original_find_element = driver.find_element
    patch = AegisSeleniumPatch(
        driver=driver,
        listener=listener,
        original_find_element=original_find_element,
    )

    def _patched_find_element(self: Any, by: Any = "id", value: str | None = None) -> Any:
        return patch.find_element(by, value)

    driver.find_element = MethodType(_patched_find_element, driver)
    driver._aegisai_patch = patch
    return patch


def deactivate_aegis(driver: Any) -> None:
    """Restore a driver previously patched by ``activate_aegis``."""

    patch = getattr(driver, "_aegisai_patch", None)
    if isinstance(patch, AegisSeleniumPatch):
        patch.restore()


def _call_original_find(original_find: Callable[..., Any], by: Any, value: str | None) -> Any:
    if value is None:
        return original_find(by)
    return original_find(by, value)


def _by_label(by: Any) -> str:
    if isinstance(by, str):
        return by.upper()
    return str(by).upper()


def _expected_role_from_locator(by: str, locator: str) -> str | None:
    lowered = f"{by} {locator}".lower()
    if any(token in lowered for token in ("button", "submit", "login")):
        return "button"
    if any(token in lowered for token in ("input", "email", "password", "user")):
        return "textbox"
    return None
