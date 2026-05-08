"""Minimal pytest integration.

Usage:
    pytest --aegis

The plugin does not guess browser lifecycles. It gives projects a fixture that
activates AegisAI on a supplied driver/page object inside their existing tests.
"""

from __future__ import annotations

import warnings
from typing import Any

try:
    import pytest
except Exception:  # pragma: no cover - pytest imports this module in real use.
    pytest = None


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("aegisai")
    group.addoption(
        "--aegis",
        action="store_true",
        default=False,
        help="Enable AegisAI helper fixtures for Selenium/Playwright objects.",
    )


def pytest_configure(config: Any) -> None:
    if config.getoption("--aegis"):
        config.addinivalue_line("markers", "aegis: test uses AegisAI self-healing helpers")


def pytest_runtest_setup(item: Any) -> None:
    if "aegis" in item.keywords and not item.config.getoption("--aegis"):
        warnings.warn("Test marked aegis but pytest was not run with --aegis.", stacklevel=2)


if pytest is not None:

    @pytest.fixture
    def aegis_activate(request: Any) -> Any:
        """Activate AegisAI on a supplied Selenium driver or Playwright page."""

        patches: list[Any] = []

        def _activate(target: Any, **kwargs: Any) -> Any:
            from aegisai import activate_aegis

            patch = activate_aegis(target, **kwargs)
            patches.append(target)
            return patch

        yield _activate

        from aegisai import deactivate_aegis

        for target in patches:
            try:
                deactivate_aegis(target)
            except Exception:
                pass
