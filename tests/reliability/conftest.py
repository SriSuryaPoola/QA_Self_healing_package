from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv("AEGISAI_RUN_PUBLIC_REPO_TESTS") == "1":
        return

    skip_public = pytest.mark.skip(
        reason="Set AEGISAI_RUN_PUBLIC_REPO_TESTS=1 to run public repo reliability tests."
    )
    for item in items:
        if "tests/reliability" in str(item.path).replace("\\", "/"):
            item.add_marker(skip_public)
