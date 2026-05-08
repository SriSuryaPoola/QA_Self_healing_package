"""Local healed-locator cache.

The cache is intentionally boring: a local JSON file keyed by scope, original
locator, and a redacted DOM fingerprint. There is no platform dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aegisai.utils.dom_parser import parse_dom_subset

CACHE_DISABLED_ENV = "AEGISAI_CACHE_DISABLED"
CACHE_PATH_ENV = "AEGISAI_CACHE_PATH"
DEFAULT_CACHE_PATH = Path(".aegisai/cache/locator-cache.json")


@dataclass(frozen=True)
class CachedLocator:
    original_locator: str
    healed_locator: str
    dom_fingerprint: str
    scope: str = "default"
    confidence: float = 1.0
    source: str = "cache"
    hits: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def with_hit(self) -> "CachedLocator":
        return CachedLocator(
            original_locator=self.original_locator,
            healed_locator=self.healed_locator,
            dom_fingerprint=self.dom_fingerprint,
            scope=self.scope,
            confidence=self.confidence,
            source=self.source,
            hits=self.hits + 1,
            created_at=self.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )


class LocatorCache:
    """Small local cache for successful deterministic heals."""

    def __init__(self, path: str | Path | None = None, *, disabled: bool | None = None) -> None:
        self.path = Path(path or os.environ.get(CACHE_PATH_ENV) or DEFAULT_CACHE_PATH)
        self.disabled = _cache_disabled() if disabled is None else disabled

    def get(self, *, original_locator: str, dom: str, scope: str = "default") -> CachedLocator | None:
        if self.disabled:
            return None
        data = self._read()
        key = self._key(scope, original_locator, dom_fingerprint(dom))
        raw = data.get(key)
        if not raw:
            return None
        cached = CachedLocator(**raw).with_hit()
        data[key] = asdict(cached)
        self._write(data)
        return cached

    def put(
        self,
        *,
        original_locator: str,
        healed_locator: str,
        dom: str,
        scope: str = "default",
        confidence: float = 1.0,
        source: str = "deterministic",
    ) -> CachedLocator | None:
        if self.disabled or not healed_locator:
            return None
        fingerprint = dom_fingerprint(dom)
        cached = CachedLocator(
            original_locator=original_locator,
            healed_locator=healed_locator,
            dom_fingerprint=fingerprint,
            scope=scope,
            confidence=confidence,
            source=source,
        )
        data = self._read()
        data[self._key(scope, original_locator, fingerprint)] = asdict(cached)
        self._write(data)
        return cached

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _key(scope: str, original_locator: str, fingerprint: str) -> str:
        material = json.dumps(
            {
                "scope": scope,
                "original_locator": original_locator,
                "dom_fingerprint": fingerprint,
            },
            sort_keys=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def dom_fingerprint(dom: str) -> str:
    """Fingerprint only the filtered DOM subset, never raw form values."""

    safe_elements = [
        {
            "tag": element.tag,
            "attrs": element.attrs,
            "text": element.text,
            "role": element.role,
            "path": element.path,
        }
        for element in parse_dom_subset(dom)
    ]
    material = json.dumps(safe_elements, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _cache_disabled() -> bool:
    return os.environ.get(CACHE_DISABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
