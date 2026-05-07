"""Deterministic memory event merge and dedupe."""

from __future__ import annotations

from typing import Any


def merge_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in events:
        key = (str(event.get("key", "")), str(event.get("old", "")), str(event.get("new", "")))
        if key not in merged:
            merged[key] = dict(event)
            continue
        current = merged[key]
        if float(event.get("confidence", 0.0)) > float(current.get("confidence", 0.0)):
            merged[key] = dict(event)
    return [merged[key] for key in sorted(merged)]
