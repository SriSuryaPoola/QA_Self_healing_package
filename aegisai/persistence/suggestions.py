"""Review artifacts for healed locators that should not be auto-persisted."""

from __future__ import annotations

import difflib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_SUGGESTIONS_FILE = Path(".aegisai/HEAL_SUGGESTIONS.json")


@dataclass(frozen=True)
class HealSuggestion:
    old_locator: str
    new_locator: str
    confidence: float
    source: str
    risk_level: str = "unknown"
    review_required: bool = True
    script_path: str | None = None
    reason: str = ""
    diff: str | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def append_heal_suggestion(
    suggestion: HealSuggestion,
    path: str | Path = DEFAULT_SUGGESTIONS_FILE,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_payload(target)
    payload.setdefault("suggestions", []).append(suggestion.to_dict())
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def build_locator_diff(
    *,
    source: str,
    old_locator: str,
    new_locator: str,
    filename: str = "script.py",
) -> str:
    rewritten = source.replace(old_locator, new_locator, 1)
    return "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            rewritten.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )


def create_source_suggestion(
    *,
    old_locator: str,
    new_locator: str,
    confidence: float,
    source_label: str,
    script_path: str | Path | None = None,
    risk_level: str = "unknown",
    review_required: bool = True,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> HealSuggestion:
    diff = None
    script_label = str(script_path) if script_path else None
    if script_path:
        path = Path(script_path)
        try:
            source = path.read_text(encoding="utf-8")
            if old_locator in source:
                diff = build_locator_diff(
                    source=source,
                    old_locator=old_locator,
                    new_locator=new_locator,
                    filename=path.name,
                )
        except Exception:
            diff = None
    return HealSuggestion(
        old_locator=old_locator,
        new_locator=new_locator,
        confidence=confidence,
        source=source_label,
        risk_level=risk_level,
        review_required=review_required,
        script_path=script_label,
        reason=reason,
        diff=diff,
        metadata=metadata or {},
    )


def _read_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "suggestions": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "suggestions": []}
    if not isinstance(raw, dict):
        return {"version": 1, "suggestions": []}
    raw.setdefault("version", 1)
    raw.setdefault("suggestions", [])
    return raw
