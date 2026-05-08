"""Security policy value objects."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from pathlib import Path
from typing import Any


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SecurityPolicy:
    """Local package policy for autonomous healing decisions."""

    name: str = "balanced"
    allow_runtime_for_medium: bool = True
    allow_runtime_for_high: bool = True
    allow_llm_for_medium: bool = True
    allow_llm_for_high: bool = False
    auto_persist_low: bool = True
    audit_enabled: bool = True
    audit_low_risk: bool = False
    audit_dir: str = ".aegisai/audit"
    min_confidence_low: float = 0.80
    min_confidence_medium: float = 0.80
    min_confidence_high: float = 0.90

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SecurityPolicy":
        data = raw.get("security", raw.get("aegisai_security", raw))
        allowed = {field.name for field in fields(cls)}
        cleaned = {key: _coerce_value(value) for key, value in data.items() if key in allowed}
        return cls(**cleaned)

    @classmethod
    def from_file(cls, path: str | Path) -> "SecurityPolicy":
        return load_security_policy(path)


@dataclass(frozen=True)
class SecurityDecision:
    runtime_allowed: bool
    llm_allowed: bool
    persistence_allowed: bool
    review_required: bool
    risk_level: RiskLevel
    reason: str
    sanitized: bool = True

    @property
    def policy_label(self) -> str:
        if self.persistence_allowed:
            return "auto_persist"
        if self.review_required:
            return "review_required"
        return "blocked"


def load_security_policy(path: str | Path) -> SecurityPolicy:
    """Load a small TOML, JSON, or simple YAML policy file."""

    target = Path(path)
    suffix = target.suffix.lower()
    text = target.read_text(encoding="utf-8")
    if suffix == ".json":
        import json

        return SecurityPolicy.from_dict(json.loads(text))
    if suffix == ".toml":
        import tomllib

        return SecurityPolicy.from_dict(tomllib.loads(text))
    if suffix in {".yml", ".yaml"}:
        return SecurityPolicy.from_dict(_parse_simple_yaml(text))
    raise ValueError("Security policy must be JSON, TOML, YAML, or YML.")


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the flat policy YAML shape shown in examples without PyYAML."""

    root: dict[str, Any] = {}
    current: dict[str, Any] = root
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, _, value = raw_line.strip().partition(":")
        while stack and indent < stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if not value.strip():
            child: dict[str, Any] = {}
            current[key] = child
            stack.append((indent + 2, child))
            continue
        current[key] = _coerce_value(value.strip())
    return root


def _coerce_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    lowered = value.strip().strip('"').strip("'").lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    try:
        return float(lowered) if "." in lowered else int(lowered)
    except ValueError:
        return value.strip().strip('"').strip("'")
