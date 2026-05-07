"""Base interception primitives.

This module intentionally does not monkey patch any test framework. Framework
adapters can record actions and failures through explicit hooks/listeners.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


LOCATOR_FAILURE_NAMES = {
    "NoSuchElementException",
    "TimeoutException",
    "Error",
}


@dataclass(frozen=True)
class FailureContext:
    exception_type: str
    message: str
    locator: str | None
    last_actions: list[dict[str, Any]] = field(default_factory=list)


class BaseInterceptor:
    def __init__(self) -> None:
        self._last_actions: deque[dict[str, Any]] = deque(maxlen=3)

    @property
    def last_actions(self) -> list[dict[str, Any]]:
        return list(self._last_actions)

    def record_action(self, action: str, locator: str | None = None, **metadata: Any) -> None:
        self._last_actions.append(
            {
                "action": action,
                "locator": locator,
                "metadata": metadata,
            }
        )

    def capture_failure(self, exc: BaseException, locator: str | None = None) -> FailureContext:
        return FailureContext(
            exception_type=type(exc).__name__,
            message=str(exc),
            locator=locator,
            last_actions=self.last_actions,
        )

    def is_locator_failure(self, exc: BaseException) -> bool:
        name = type(exc).__name__
        return name in LOCATOR_FAILURE_NAMES or "locator" in str(exc).lower()
