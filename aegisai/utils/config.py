"""Configuration model for AegisAI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = True
    temperature: float = 0.0
    timeout_seconds: float = 3.0


@dataclass(frozen=True)
class HealingConfig:
    deterministic: bool = True
    llm: LLMConfig = field(default_factory=LLMConfig)


@dataclass(frozen=True)
class GuardrailConfig:
    confidence_threshold: float = 0.85


@dataclass(frozen=True)
class PersistenceConfig:
    strategy: str = "hybrid"
    suggestions_file: str = ".aegisai/HEAL_SUGGESTIONS.json"


@dataclass(frozen=True)
class MemoryConfig:
    type: str = "event_stream"
    remote_bucket: str | None = None
    local_dir: str = ".aegisai/memory"


@dataclass(frozen=True)
class CacheConfig:
    enabled: bool = True
    path: str = ".aegisai/cache/locator-cache.json"


@dataclass(frozen=True)
class ReportConfig:
    enabled: bool = False
    path: str = ".aegisai/reports/latest.json"


@dataclass(frozen=True)
class AegisConfig:
    mode: str = "safe"
    local_only: bool = False
    healing: HealingConfig = field(default_factory=HealingConfig)
    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    report: ReportConfig = field(default_factory=ReportConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AegisConfig":
        data = raw.get("aegisai", raw)
        llm = LLMConfig(**data.get("healing", {}).get("llm", {}))
        healing = HealingConfig(
            deterministic=data.get("healing", {}).get("deterministic", True),
            llm=llm,
        )
        return cls(
            mode=data.get("mode", "safe"),
            local_only=data.get("local_only", False),
            healing=healing,
            guardrails=GuardrailConfig(**data.get("guardrails", {})),
            persistence=PersistenceConfig(**data.get("persistence", {})),
            memory=MemoryConfig(**data.get("memory", {})),
            cache=CacheConfig(**data.get("cache", {})),
            report=ReportConfig(**data.get("report", {})),
        )


def load_config(path: str | Path) -> AegisConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return AegisConfig.from_dict(raw)
