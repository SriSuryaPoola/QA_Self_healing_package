"""Redaction helpers for DOM, LLM payloads, logs, and audit events."""

from __future__ import annotations

from typing import Any

from aegisai.models import DomElement

MASK = "***MASKED***"
SECRET_KEYS = {
    "value",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "cookie",
    "session",
    "authorization",
}


def redact_dom_element(element: DomElement) -> dict[str, Any]:
    return {
        "tag": element.tag,
        "attrs": {key: _redact_attr(key, value) for key, value in element.attrs.items()},
        "text": _redact_text(element.text),
        "role": element.role,
        "locator": element.stable_locator(),
    }


def redact_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: _redact_value(key, value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload


def _redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(secret in lowered for secret in SECRET_KEYS):
        return MASK
    return redact_payload(value)


def _redact_attr(key: str, value: str) -> str:
    lowered = key.lower()
    if lowered == "value" or lowered in {"authorization", "cookie"}:
        return MASK
    return value


def _redact_text(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    if any(secret in lowered for secret in ("password", "token", "secret", "api key")):
        return MASK
    return text[:120]
