"""unittest helpers for activating AegisAI inside existing test cases."""

from __future__ import annotations

from typing import Any

from aegisai import activate_aegis, deactivate_aegis


class AegisTestMixin:
    """Mixin that tracks AegisAI patches and restores them during tearDown."""

    def activate_aegis_for(self, target: Any, **kwargs: Any) -> Any:
        patch = activate_aegis(target, **kwargs)
        patches = getattr(self, "_aegisai_patches", [])
        patches.append(target)
        self._aegisai_patches = patches
        return patch

    def tearDown(self) -> None:  # noqa: N802 - unittest API
        for target in getattr(self, "_aegisai_patches", []):
            try:
                deactivate_aegis(target)
            except Exception:
                pass
        super_teardown = getattr(super(), "tearDown", None)
        if callable(super_teardown):
            super_teardown()
