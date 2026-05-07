"""Playwright hook adapter.

This module keeps registration explicit. It does not patch Playwright page or
locator objects.
"""

from __future__ import annotations

from typing import Any, Callable

from .base_interceptor import BaseInterceptor


class AegisPlaywrightHooks(BaseInterceptor):
    def install(self, page: Any) -> None:
        """Register safe page-level hooks when the page supports ``on``."""

        if not hasattr(page, "on"):
            raise TypeError("Playwright page object must expose an 'on' method.")
        page.on("requestfailed", self._record_request_failed)
        page.on("pageerror", self._record_page_error)

    def wrap_action(self, action_name: str, locator: str, action: Callable[[], Any]) -> Any:
        """Run an action while recording recent context for failure capture."""

        self.record_action(action_name, locator=locator)
        try:
            return action()
        except BaseException as exc:
            self.capture_failure(exc, locator=locator)
            raise

    def _record_request_failed(self, request: Any) -> None:
        self.record_action("requestfailed", metadata=str(request))

    def _record_page_error(self, error: Any) -> None:
        self.record_action("pageerror", metadata=str(error))
