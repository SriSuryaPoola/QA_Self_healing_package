"""Append-only memory event writer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from aegisai.models import MemoryEvent


def write_event(event: MemoryEvent, directory: str | Path) -> Path:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    filename = f"run-{event.node_id}-{timestamp}-{uuid4().hex[:8]}.json"
    target = path / filename
    target.write_text(json.dumps([event.to_dict()], indent=2, sort_keys=True), encoding="utf-8")
    return target
