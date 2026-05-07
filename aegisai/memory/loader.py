"""Load append-only memory event files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_events(directory: str | Path) -> list[dict[str, Any]]:
    path = Path(directory)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for file_path in sorted(path.glob("run-*.json")):
        loaded = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            events.extend(item for item in loaded if isinstance(item, dict))
    return events
