"""Optional replay/debug artifact capture."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aegisai.security import redact_payload
from aegisai.utils.dom_parser import parse_dom_subset

DEFAULT_ARTIFACT_DIR = Path(".aegisai/artifacts")


def capture_debug_artifacts(
    target: Any,
    *,
    directory: str | Path = DEFAULT_ARTIFACT_DIR,
    label: str = "failure",
    include_screenshot: bool = False,
) -> dict[str, str]:
    """Capture redacted DOM data and optionally a screenshot for debugging."""

    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    base = f"{stamp}-{label}-{uuid4().hex[:8]}"

    dom = _target_dom(target)
    dom_path = output_dir / f"{base}-dom.json"
    dom_payload = {
        "captured_at": stamp,
        "label": label,
        "elements": [
            {
                "tag": element.tag,
                "attrs": element.attrs,
                "text": element.text,
                "role": element.role,
                "path": element.path,
            }
            for element in parse_dom_subset(dom)
        ],
    }
    dom_path.write_text(json.dumps(redact_payload(dom_payload), indent=2, sort_keys=True), encoding="utf-8")

    result = {"dom": str(dom_path)}
    if include_screenshot:
        screenshot_path = output_dir / f"{base}.png"
        if _capture_screenshot(target, screenshot_path):
            result["screenshot"] = str(screenshot_path)
    return result


def _target_dom(target: Any) -> str:
    page_source = getattr(target, "page_source", None)
    if isinstance(page_source, str):
        return page_source
    content = getattr(target, "content", None)
    if callable(content):
        try:
            value = content()
        except Exception:
            return ""
        return value if isinstance(value, str) else ""
    return ""


def _capture_screenshot(target: Any, path: Path) -> bool:
    save_screenshot = getattr(target, "save_screenshot", None)
    if callable(save_screenshot):
        try:
            return bool(save_screenshot(str(path)))
        except Exception:
            return False
    screenshot = getattr(target, "screenshot", None)
    if callable(screenshot):
        try:
            screenshot(path=str(path))
            return path.exists()
        except Exception:
            return False
    return False
