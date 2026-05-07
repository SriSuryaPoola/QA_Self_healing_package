"""LLM fallback contract.

The first build slice intentionally avoids provider dependencies. It validates
strict JSON output from a caller-supplied adapter, keeping LLM behavior
fallback-only and testable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol


class LLMAdapter(Protocol):
    def complete_json(self, payload: dict[str, Any], *, timeout_seconds: float, temperature: float) -> str:
        ...


@dataclass(frozen=True)
class LLMResult:
    locator: str
    confidence: float


class StrictJsonLLMEngine:
    def __init__(self, adapter: LLMAdapter, timeout_seconds: float = 3.0, temperature: float = 0.0) -> None:
        self.adapter = adapter
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature

    def suggest(self, payload: dict[str, Any]) -> LLMResult:
        raw = self.adapter.complete_json(
            payload,
            timeout_seconds=self.timeout_seconds,
            temperature=self.temperature,
        )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM output must be valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("LLM output must be a JSON object.")
        locator = parsed.get("locator")
        confidence = parsed.get("confidence")
        if not isinstance(locator, str) or not locator:
            raise ValueError("LLM output must include a non-empty string locator.")
        if not isinstance(confidence, (int, float)):
            raise ValueError("LLM output must include numeric confidence.")
        return LLMResult(locator=locator, confidence=float(confidence))
