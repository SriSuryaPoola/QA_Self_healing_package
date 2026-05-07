"""User-level LLM configuration helpers.

The package never prompts during installation. Users opt in explicitly with
``aegisai configure llm``, which writes a small .env file outside the project
repository by default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR_ENV = "AEGISAI_CONFIG_DIR"
CONFIG_FILE_NAME = ".env"
VALID_PROVIDERS = {"openai", "gemini", "grok", "claude", "ollama", "custom"}
DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-pro",
    "grok": "grok-2",
    "claude": "claude-3-5-sonnet-latest",
    "ollama": "llama3.1",
    "custom": "gpt-4o",
}

PLACEHOLDER_SECRET_VALUES = {
    "api-key",
    "apikey",
    "change-me",
    "changeme",
    "dummy",
    "example",
    "placeholder",
    "replace-me",
    "replace_me",
    "test",
    "your-api-key",
    "your_api_key",
    "your-key",
    "your_api_key_here",
}


@dataclass(frozen=True)
class LLMSettings:
    enabled: bool
    provider: str = "openai"
    api_key: str = ""
    model: str = "gpt-4o"
    base_url: str = ""


def user_config_dir() -> Path:
    override = os.getenv(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        root = os.getenv("APPDATA")
        if root:
            return Path(root) / "AegisAI"
        return Path.home() / "AppData" / "Roaming" / "AegisAI"

    if os.name == "posix" and os.uname().sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "AegisAI"

    return Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "aegisai"


def user_env_path() -> Path:
    return user_config_dir() / CONFIG_FILE_NAME


def read_env_file(path: str | Path | None = None) -> dict[str, str]:
    target = Path(path) if path else user_env_path()
    if not target.exists():
        return {}
    return _parse_env_text(target.read_text(encoding="utf-8"))


def load_llm_env(path: str | Path | None = None) -> dict[str, str]:
    """Load stored config, then overlay complete process env settings.

    Environment variables remain the best option for CI. Incomplete placeholder
    env keys are ignored when a real user-level config is present, so a project
    template .env does not accidentally disable a saved credential.
    """

    values = read_env_file(path)
    env_values = {
        key: os.getenv(key, "")
        for key in (
            "AEGIS_LLM_ENABLED",
            "AEGIS_LLM_PROVIDER",
            "AEGIS_LLM_API_KEY",
            "AEGIS_LLM_MODEL",
            "AEGIS_LLM_BASE_URL",
        )
    }

    if env_values["AEGIS_LLM_ENABLED"]:
        values["AEGIS_LLM_ENABLED"] = env_values["AEGIS_LLM_ENABLED"]

    provider = env_values["AEGIS_LLM_PROVIDER"].lower()
    has_complete_env = _has_real_secret(env_values["AEGIS_LLM_API_KEY"])
    has_complete_env = has_complete_env or provider == "ollama"
    has_complete_env = has_complete_env or (
        provider == "custom" and bool(env_values["AEGIS_LLM_BASE_URL"])
    )

    if has_complete_env or not _has_real_secret(values.get("AEGIS_LLM_API_KEY", "")):
        for key, value in env_values.items():
            if value and key != "AEGIS_LLM_ENABLED":
                values[key] = value

    return values


def is_llm_enabled(default: bool = False, path: str | Path | None = None) -> bool:
    raw = load_llm_env(path).get("AEGIS_LLM_ENABLED")
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def write_llm_settings(settings: LLMSettings, path: str | Path | None = None) -> Path:
    target = Path(path) if path else user_env_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AegisAI user-level LLM configuration",
        "# Created by: aegisai configure llm",
        _format_env_line("AEGIS_LLM_ENABLED", "true" if settings.enabled else "false"),
        _format_env_line("AEGIS_LLM_PROVIDER", settings.provider),
        _format_env_line("AEGIS_LLM_MODEL", settings.model),
    ]
    if settings.api_key:
        lines.append(_format_env_line("AEGIS_LLM_API_KEY", settings.api_key))
    if settings.base_url:
        lines.append(_format_env_line("AEGIS_LLM_BASE_URL", settings.base_url))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _restrict_permissions(target)
    return target


def settings_from_env(path: str | Path | None = None) -> LLMSettings:
    values = load_llm_env(path)
    provider = values.get("AEGIS_LLM_PROVIDER", "openai").lower()
    return LLMSettings(
        enabled=is_llm_enabled(default=False, path=path),
        provider=provider,
        api_key=values.get("AEGIS_LLM_API_KEY", ""),
        model=values.get("AEGIS_LLM_MODEL", DEFAULT_MODELS.get(provider, "gpt-4o")),
        base_url=values.get("AEGIS_LLM_BASE_URL", ""),
    )


def redacted_status(path: str | Path | None = None) -> dict[str, str]:
    settings = settings_from_env(path)
    config_path = Path(path) if path else user_env_path()
    return {
        "config_file": str(config_path),
        "enabled": "yes" if settings.enabled else "no",
        "provider": settings.provider,
        "model": settings.model,
        "api_key": "configured" if _has_real_secret(settings.api_key) else "not configured",
        "base_url": "configured" if settings.base_url else "not configured",
    }


def _parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value.replace("\\n", "\n").replace('\\"', '"')
    return values


def _format_env_line(key: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'{key}="{escaped}"'


def _restrict_permissions(path: Path) -> None:
    try:
        if os.name != "nt":
            path.chmod(0o600)
    except Exception:
        return


def _has_real_secret(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip().strip("'\"").lower()
    if not normalized:
        return False
    if normalized in PLACEHOLDER_SECRET_VALUES:
        return False
    if normalized.startswith("your") and "key" in normalized:
        return False
    if normalized.startswith("<") and normalized.endswith(">"):
        return False
    return True
