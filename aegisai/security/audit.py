"""Append-only local audit logging for security-governed heals."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .redactor import redact_payload


def write_audit_event(event: dict[str, Any], directory: str | Path) -> Path:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = path / f"audit-{timestamp}-{uuid4().hex[:8]}.json"
    safe_event = redact_payload({**event, "timestamp": timestamp})
    target.write_text(json.dumps(safe_event, indent=2, sort_keys=True), encoding="utf-8")
    return target
