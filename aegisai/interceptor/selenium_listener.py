"""Selenium safe-mode listener with 5-layer autonomous healing.

Healing cascade (triggered by autonomous_heal()):
  L0  DOM readiness guard     - wait/scroll/retry checks
  L1  Locator Translator      - rule-based XPath/CSS conversion
  L2  Deterministic Engine    - confidence-scored attribute matching
  L3  Heuristic Searcher      - label/proximity/fuzzy text search
  L4  JS Browser Prober       - live browser JavaScript queries
  L5  LLM                     - optional final fallback
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base_interceptor import BaseInterceptor, FailureContext

logger = logging.getLogger(__name__)


class AegisSeleniumListener(BaseInterceptor):
    """Capture Selenium failures and heal them via a 5-layer cascade.

    Args:
        script_path: Path to the user's automation script. When provided, the
            package reads this file for code intent (L5) and can rewrite it with
            a permanent fix when policy allows persistence.
        backup: Create a .py.bak backup before rewriting the script.
        enable_llm: Allow L5 after L0-L4 fail. When omitted, the saved
            ``aegisai configure llm`` preference is used.
        security_policy: Optional local Security Officer policy.
    """

    def __init__(
        self,
        script_path: str | Path | None = None,
        backup: bool = True,
        enable_llm: bool | None = None,
        security_policy: Any = None,
    ) -> None:
        super().__init__()
        self._script_path = str(script_path) if script_path else None
        self._backup = backup
        if enable_llm is None:
            from aegisai.utils.llm_config import is_llm_enabled

            self._enable_llm = is_llm_enabled(default=False)
        else:
            self._enable_llm = enable_llm
        self._security_policy = security_policy
        self._orchestrator: Any = None
        self.last_outcome: Any = None

    def before_find(self, by: str, value: str, driver: Any | None = None) -> None:
        self.record_action("find", locator=f"{by}={value}", driver=bool(driver))

    def on_exception(self, exception: BaseException, driver: Any | None = None) -> FailureContext:
        locator = self.last_actions[-1]["locator"] if self.last_actions else None
        return self.capture_failure(exception, locator=locator)

    def autonomous_heal(
        self,
        exception: BaseException,
        *,
        driver: Any,
        wait: Any | None = None,
        original_condition: Any = None,
    ) -> Any:
        """Trigger the 5-layer self-healing cascade."""

        failure_ctx = self.on_exception(exception, driver=driver)
        failing_locator = failure_ctx.locator or ""

        logger.warning(
            "[aegisai] Failure detected - starting 5-layer heal for: %s",
            failing_locator,
        )

        orchestrator = self._get_orchestrator()
        outcome = orchestrator.orchestrate(
            exception,
            driver=driver,
            wait=wait,
            failing_locator=failing_locator,
            original_condition=original_condition,
        )
        self.last_outcome = outcome

        if outcome.success:
            logger.info(
                "[aegisai] Healed at %s -> %s | layers tried: %s | patched: %s",
                outcome.layer_label,
                outcome.healed_locator,
                " -> ".join(outcome.layers_tried),
                outcome.script_patched,
            )
            return outcome.element

        logger.error(
            "[aegisai] Healing stopped. Layers tried: %s | reason: %s",
            " -> ".join(outcome.layers_tried),
            outcome.reason,
        )
        raise exception

    def _get_orchestrator(self) -> Any:
        if self._orchestrator is None:
            from aegisai.engine.healing_orchestrator import HealingOrchestrator

            self._orchestrator = HealingOrchestrator(
                script_path=self._script_path,
                backup=self._backup,
                enable_llm=self._enable_llm,
                security_policy=self._security_policy,
            )
        return self._orchestrator


def is_selenium_available() -> bool:
    try:
        import selenium  # noqa: F401
    except Exception:
        return False
    return True
