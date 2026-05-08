"""Universal framework detection and activation.

This module is the package-level entry point for teams that do not want to
remember whether to import ``aegisai.selenium`` or ``aegisai.playwright``.
Detection is deterministic:

* inspect the supplied live object first
* inspect caller locals for a Selenium driver or Playwright page
* inspect the caller script/imports only as a diagnostic fallback
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class FrameworkKind(StrEnum):
    SELENIUM = "selenium"
    PLAYWRIGHT = "playwright"


@dataclass(frozen=True)
class FrameworkDetection:
    kind: FrameworkKind
    target: Any | None
    source: str
    reason: str
    script_path: str | None = None


def detect_framework(
    target: Any | None = None,
    *,
    script_path: str | Path | None = None,
) -> FrameworkDetection:
    """Detect whether the current integration target is Selenium or Playwright."""

    frame = inspect.currentframe()
    caller = frame.f_back if frame else None
    return _detect(target=target, script_path=script_path, caller_frame=caller)


def activate_aegis(
    target: Any | None = None,
    *,
    script_path: str | Path | None = None,
    backup: bool = True,
    enable_llm: bool | None = None,
    security_policy: Any = None,
    app: Any = None,
) -> Any:
    """Auto-detect Selenium vs Playwright and activate the matching adapter.

    ``target`` may be a Selenium ``driver`` or sync Playwright ``page``. If it is
    omitted, AegisAI searches the caller's local variables for a likely
    ``driver`` or ``page`` object.
    """

    frame = inspect.currentframe()
    caller = frame.f_back if frame else None
    detection = _detect(target=target, script_path=script_path, caller_frame=caller)
    if detection.target is None:
        raise ValueError(
            f"AegisAI detected a {detection.kind.value} script, but no live browser object was found. "
            "Call activate_aegis(driver_or_page) after creating the Selenium driver or Playwright page."
        )

    if detection.kind == FrameworkKind.SELENIUM:
        from aegisai.selenium import activate_aegis as activate_selenium

        resolved_script_path = str(script_path) if script_path else detection.script_path
        return activate_selenium(
            detection.target,
            script_path=resolved_script_path,
            backup=backup,
            enable_llm=enable_llm,
            security_policy=security_policy,
        )

    if detection.kind == FrameworkKind.PLAYWRIGHT:
        if _looks_like_async_playwright_page(detection.target):
            from aegisai.playwright_async import activate_aegis_async

            return activate_aegis_async(detection.target, app=app)
        from aegisai.playwright import activate_aegis as activate_playwright

        return activate_playwright(detection.target, app=app)

    raise TypeError(f"Unsupported framework detection: {detection.kind}")


def deactivate_aegis(target: Any | None = None) -> None:
    """Auto-detect Selenium vs Playwright and restore the matching adapter."""

    frame = inspect.currentframe()
    caller = frame.f_back if frame else None
    detection = _detect(target=target, script_path=None, caller_frame=caller)
    if detection.target is None:
        raise ValueError("No live Selenium driver or Playwright page object was found to deactivate.")

    if detection.kind == FrameworkKind.SELENIUM:
        from aegisai.selenium import deactivate_aegis as deactivate_selenium

        deactivate_selenium(detection.target)
        return

    if detection.kind == FrameworkKind.PLAYWRIGHT:
        if _looks_like_async_playwright_page(detection.target):
            from aegisai.playwright_async import deactivate_aegis_async

            deactivate_aegis_async(detection.target)
            return
        from aegisai.playwright import deactivate_aegis as deactivate_playwright

        deactivate_playwright(detection.target)
        return

    raise TypeError(f"Unsupported framework detection: {detection.kind}")


def _detect(
    *,
    target: Any | None,
    script_path: str | Path | None,
    caller_frame: Any | None,
) -> FrameworkDetection:
    caller_script = _caller_script_path(caller_frame)
    explicit_script = str(Path(script_path)) if script_path else None
    detection_script = explicit_script or caller_script

    if target is not None:
        detected = _detect_object(target, source="object", script_path=detection_script)
        if detected:
            return detected
        raise TypeError(
            "AegisAI could not recognize the supplied target. "
            "Expected a Selenium WebDriver-like object or sync Playwright Page-like object."
        )

    local_detection = _detect_from_locals(caller_frame, script_path=detection_script)
    if local_detection:
        return local_detection

    script_detection = _detect_from_script(detection_script)
    if script_detection:
        return script_detection

    raise ValueError(
        "AegisAI could not detect Selenium or Playwright. "
        "Pass activate_aegis(driver) or activate_aegis(page) after creating the browser object."
    )


def _detect_object(target: Any, *, source: str, script_path: str | None) -> FrameworkDetection | None:
    module_name = type(target).__module__.lower()
    type_name = type(target).__name__

    if "playwright" in module_name or _looks_like_playwright_page(target):
        return FrameworkDetection(
            kind=FrameworkKind.PLAYWRIGHT,
            target=target,
            source=source,
            reason=f"{type_name} exposes Playwright page-style locator/content APIs.",
            script_path=script_path,
        )

    if "selenium" in module_name or _looks_like_selenium_driver(target):
        return FrameworkDetection(
            kind=FrameworkKind.SELENIUM,
            target=target,
            source=source,
            reason=f"{type_name} exposes Selenium driver-style find/execute/page APIs.",
            script_path=script_path,
        )

    return None


def _detect_from_locals(caller_frame: Any | None, *, script_path: str | None) -> FrameworkDetection | None:
    if caller_frame is None:
        return None

    candidates: list[tuple[int, str, FrameworkDetection]] = []
    for name, value in caller_frame.f_locals.items():
        detected = _detect_object(value, source=f"caller local '{name}'", script_path=script_path)
        if detected:
            candidates.append((_candidate_score(name, detected.kind), name, detected))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score = candidates[0][0]
    best = [item for item in candidates if item[0] == best_score]
    if len(best) == 1:
        return best[0][2]

    labels = ", ".join(f"{name}:{detected.kind.value}" for _, name, detected in best)
    raise ValueError(
        "AegisAI found multiple possible browser objects in the caller scope "
        f"({labels}). Pass the intended driver/page explicitly."
    )


def _detect_from_script(script_path: str | None) -> FrameworkDetection | None:
    if not script_path:
        return None

    path = Path(script_path)
    if not path.exists() or not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return None

    selenium_score = text.count("selenium") + text.count("webdriver") + text.count("find_element")
    playwright_score = text.count("playwright") + text.count("sync_playwright") + text.count(".locator(")

    if selenium_score > playwright_score and selenium_score > 0:
        return FrameworkDetection(
            kind=FrameworkKind.SELENIUM,
            target=None,
            source="script imports",
            reason="Script text references Selenium/WebDriver APIs.",
            script_path=str(path),
        )

    if playwright_score > selenium_score and playwright_score > 0:
        return FrameworkDetection(
            kind=FrameworkKind.PLAYWRIGHT,
            target=None,
            source="script imports",
            reason="Script text references Playwright APIs.",
            script_path=str(path),
        )

    return None


def _looks_like_playwright_page(target: Any) -> bool:
    return callable(getattr(target, "locator", None)) and callable(getattr(target, "content", None))


def _looks_like_async_playwright_page(target: Any) -> bool:
    content = getattr(target, "content", None)
    return callable(getattr(target, "locator", None)) and inspect.iscoroutinefunction(content)


def _looks_like_selenium_driver(target: Any) -> bool:
    return callable(getattr(target, "find_element", None)) and (
        callable(getattr(target, "execute_script", None))
        or hasattr(target, "page_source")
        or hasattr(target, "current_url")
    )


def _candidate_score(name: str, kind: FrameworkKind) -> int:
    lowered = name.lower()
    if kind == FrameworkKind.SELENIUM and lowered in {"driver", "webdriver", "browser", "selenium_driver"}:
        return 100
    if kind == FrameworkKind.PLAYWRIGHT and lowered in {"page", "pw_page", "playwright_page"}:
        return 100
    if kind == FrameworkKind.SELENIUM and "driver" in lowered:
        return 80
    if kind == FrameworkKind.PLAYWRIGHT and "page" in lowered:
        return 80
    return 10


def _caller_script_path(caller_frame: Any | None) -> str | None:
    if caller_frame is None:
        return None
    filename = caller_frame.f_code.co_filename
    if not filename or filename.startswith("<"):
        return None
    return filename
