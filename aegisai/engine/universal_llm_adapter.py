"""Universal LLM adapter that reads environment or user-level config."""

from __future__ import annotations

import json
from typing import Any

from aegisai.utils.llm_config import _has_real_secret, load_llm_env

_PROVIDER_ENDPOINTS: dict[str, tuple[str, bool]] = {
    "openai": ("https://api.openai.com/v1", True),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", True),
    "grok": ("https://api.x.ai/v1", True),
    "ollama": ("http://localhost:11434/v1", False),
}


def _load_env() -> tuple[str, str | None, str, str | None]:
    """Read LLM config from process env and the AegisAI user config file."""

    values = load_llm_env()
    provider = (values.get("AEGIS_LLM_PROVIDER") or "openai").lower().strip()
    api_key = values.get("AEGIS_LLM_API_KEY") or None
    model = values.get("AEGIS_LLM_MODEL") or "gpt-4o"
    base_url = values.get("AEGIS_LLM_BASE_URL") or None
    return provider, api_key, model, base_url


def _call_openai_compatible(
    prompt: str,
    *,
    base_url: str,
    api_key: str | None,
    model: str,
    timeout: float,
) -> str:
    """Call any OpenAI-compatible endpoint and return raw JSON string."""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The 'openai' package is required. Run: pip install openai") from exc

    client = OpenAI(
        api_key=api_key or "no-key-needed",
        base_url=base_url,
        timeout=timeout,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a Selenium locator healing assistant. "
                    "You MUST respond with ONLY valid JSON, no markdown, no explanation. "
                    "Format: {\"locator\": \"<css_selector>\", \"by\": \"css\", "
                    "\"confidence\": 0.95, \"reason\": \"...\"}"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return response.choices[0].message.content or "{}"


def _call_claude(
    prompt: str,
    *,
    api_key: str,
    model: str,
    timeout: float,
) -> str:
    """Call Anthropic Claude via native API."""

    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("The 'anthropic' package is required for Claude. Run: pip install anthropic") from exc

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
        system=(
            "You are a Selenium locator healing assistant. "
            "Respond with ONLY valid JSON: "
            "{\"locator\": \"<css_selector>\", \"by\": \"css\", "
            "\"confidence\": 0.95, \"reason\": \"...\"}"
        ),
    )
    return message.content[0].text


class UniversalLLMAdapter:
    """Provider-agnostic LLM adapter."""

    def __init__(self) -> None:
        self.provider, self.api_key, self.model, self.base_url = _load_env()

    def complete_json(
        self,
        payload: dict[str, Any],
        *,
        timeout_seconds: float = 10.0,
        temperature: float = 0.0,
    ) -> str:
        """Send the payload as a prompt and return a JSON string response."""

        prompt = payload.get("prompt") or json.dumps(payload, indent=2)

        if self.provider == "claude":
            if not _has_real_secret(self.api_key):
                raise ValueError("AEGIS_LLM_API_KEY must be set for Claude.")
            return _call_claude(prompt, api_key=str(self.api_key), model=self.model, timeout=timeout_seconds)

        if self.provider == "custom":
            if not self.base_url:
                raise ValueError("AEGIS_LLM_BASE_URL must be set when AEGIS_LLM_PROVIDER=custom.")
            base_url = self.base_url
        elif self.provider in _PROVIDER_ENDPOINTS:
            default_base, needs_key = _PROVIDER_ENDPOINTS[self.provider]
            base_url = self.base_url or default_base
            if needs_key and not _has_real_secret(self.api_key):
                raise ValueError(f"AEGIS_LLM_API_KEY must be set for provider '{self.provider}'.")
        else:
            raise ValueError(
                f"Unknown AEGIS_LLM_PROVIDER='{self.provider}'. "
                "Valid values: openai, gemini, grok, ollama, claude, custom"
            )

        return _call_openai_compatible(
            prompt,
            base_url=base_url,
            api_key=self.api_key,
            model=self.model,
            timeout=timeout_seconds,
        )

    @staticmethod
    def is_configured() -> bool:
        """Return True if the minimum required LLM settings are available."""

        return UniversalLLMAdapter.configuration_issue() is None

    @staticmethod
    def configuration_issue() -> str | None:
        """Return a human-readable LLM configuration issue, or None if usable."""

        values = load_llm_env()
        provider = (values.get("AEGIS_LLM_PROVIDER") or "").lower()
        api_key = values.get("AEGIS_LLM_API_KEY") or ""
        base_url = values.get("AEGIS_LLM_BASE_URL") or ""
        has_real_key = _has_real_secret(api_key)

        if not provider and not has_real_key:
            return (
                "no LLM provider/API key is configured. Run `aegisai configure llm`, "
                "or set AEGIS_LLM_PROVIDER and AEGIS_LLM_API_KEY."
            )

        if provider == "ollama":
            return None

        if provider == "custom":
            if not base_url:
                return "AEGIS_LLM_BASE_URL is required when AEGIS_LLM_PROVIDER=custom."
            return None

        provider = provider or "openai"
        if provider not in {"openai", "gemini", "grok", "claude"}:
            return (
                f"unknown AEGIS_LLM_PROVIDER='{provider}'. Valid values: "
                "openai, gemini, grok, ollama, claude, custom."
            )

        if not has_real_key:
            return (
                f"AEGIS_LLM_API_KEY is not configured for provider '{provider}'. "
                "Run `aegisai configure llm` to save it securely in your user config."
            )

        return None
