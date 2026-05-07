"""State-poisoning support for failed heal attempts."""

from __future__ import annotations

from typing import Any

STATE_POISONED = False


def set_state_poisoned(value: bool = True) -> None:
    global STATE_POISONED
    STATE_POISONED = value


def is_state_poisoned() -> bool:
    return STATE_POISONED


def on_state_poisoned(reset_driver: bool = True, driver: Any | None = None) -> dict[str, Any]:
    """Expose the recovery hook described by the TDD.

    If a driver is supplied and reset is requested, the hook calls ``quit`` when
    available. The caller remains responsible for creating a fresh driver.
    """

    set_state_poisoned(True)
    reset_attempted = False
    reset_error = None
    if reset_driver and driver is not None and hasattr(driver, "quit"):
        reset_attempted = True
        try:
            driver.quit()
        except Exception as exc:  # pragma: no cover - defensive safety hook
            reset_error = str(exc)
    return {
        "state_poisoned": STATE_POISONED,
        "reset_requested": reset_driver,
        "reset_attempted": reset_attempted,
        "reset_error": reset_error,
    }
