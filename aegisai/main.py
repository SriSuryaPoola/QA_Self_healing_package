"""Command line entrypoint for early SDK smoke checks."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from .sdk import AegisAI
from .state import is_state_poisoned
from .utils.llm_config import (
    DEFAULT_MODELS,
    LLMSettings,
    VALID_PROVIDERS,
    redacted_status,
    settings_from_env,
    write_llm_settings,
)


def _heal(args: argparse.Namespace) -> int:
    dom = Path(args.dom_file).read_text(encoding="utf-8")
    result = AegisAI().heal_locator(
        args.locator,
        dom,
        expected_role=args.expected_role,
    )
    payload = {
        "locator": result.locator,
        "confidence": result.confidence,
        "source": result.source,
        "llm_used": result.llm_used,
        "guardrail": {
            "allowed": result.guardrail.allowed if result.guardrail else False,
            "code": result.guardrail.code if result.guardrail else "missing",
            "reason": result.guardrail.reason if result.guardrail else "No guardrail result",
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.locator else 1


def _state(_: argparse.Namespace) -> int:
    print(json.dumps({"state_poisoned": is_state_poisoned()}))
    return 0


def _configure_llm(args: argparse.Namespace) -> int:
    config_file = Path(args.config_file).expanduser() if args.config_file else None

    if args.status:
        print(json.dumps(redacted_status(config_file), indent=2, sort_keys=True))
        return 0

    if args.enable and args.disable:
        raise SystemExit("--enable and --disable cannot be used together.")

    current = settings_from_env(config_file)
    enabled = _resolve_enabled(args, current.enabled)

    if not enabled:
        provider = args.provider or current.provider
        settings = LLMSettings(
            enabled=False,
            provider=provider,
            api_key="",
            model=args.model or current.model or DEFAULT_MODELS.get(provider, "gpt-4o"),
            base_url=args.base_url or current.base_url,
        )
        target = write_llm_settings(settings, config_file)
        print(f"AegisAI LLM fallback disabled. Config file: {target}")
        return 0

    provider = (args.provider or _prompt_provider(current.provider)).lower()
    if provider not in VALID_PROVIDERS:
        raise SystemExit(f"Unsupported provider '{provider}'. Valid providers: {', '.join(sorted(VALID_PROVIDERS))}")

    model = args.model or _prompt_text("Model", current.model or DEFAULT_MODELS.get(provider, "gpt-4o"))
    base_url = args.base_url or current.base_url
    if provider == "custom" and not base_url:
        base_url = _prompt_text("Custom base URL", current.base_url)

    api_key = args.api_key or ""
    if provider not in {"ollama", "custom"} and not api_key:
        api_key = getpass.getpass("API key (input hidden): ").strip()

    settings = LLMSettings(
        enabled=True,
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
    target = write_llm_settings(settings, config_file)
    status = redacted_status(target)
    print("AegisAI LLM configuration saved.")
    print(f"Config file: {target}")
    print(f"LLM fallback: {status['enabled']}")
    print(f"Provider: {status['provider']}")
    print(f"Model: {status['model']}")
    print(f"API key: {status['api_key']}")
    print("Next: use AegisSeleniumListener() normally; L5 will be available after L0-L4 fail.")
    return 0


def _resolve_enabled(args: argparse.Namespace, current: bool) -> bool:
    if args.enable:
        return True
    if args.disable:
        return False
    answer = _prompt_text(
        "Enable L5 LLM fallback? [y/N]",
        "y" if current else "n",
    )
    return answer.strip().lower() in {"y", "yes", "true", "1", "on"}


def _prompt_provider(default: str) -> str:
    prompt = f"Provider ({'/'.join(sorted(VALID_PROVIDERS))})"
    return _prompt_text(prompt, default or "openai")


def _prompt_text(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aegisai")
    subcommands = parser.add_subparsers(dest="command", required=True)

    heal = subcommands.add_parser("heal", help="Run deterministic heal against an HTML file.")
    heal.add_argument("--locator", required=True, help="Failing locator, for example '#login'.")
    heal.add_argument("--dom-file", required=True, help="Path to a local HTML fixture.")
    heal.add_argument("--expected-role", default=None, help="Expected semantic role, for example 'button'.")
    heal.set_defaults(func=_heal)

    state = subcommands.add_parser("state", help="Print current state-poisoning flag.")
    state.set_defaults(func=_state)

    configure = subcommands.add_parser("configure", help="Configure local AegisAI settings.")
    configure_subcommands = configure.add_subparsers(dest="configure_target", required=True)
    llm = configure_subcommands.add_parser("llm", help="Configure optional L5 LLM fallback.")
    llm.add_argument("--enable", action="store_true", help="Enable L5 LLM fallback without prompting.")
    llm.add_argument("--disable", action="store_true", help="Disable L5 LLM fallback without prompting.")
    llm.add_argument("--provider", choices=sorted(VALID_PROVIDERS), help="LLM provider.")
    llm.add_argument("--api-key", default="", help="API key. Omit to enter it securely.")
    llm.add_argument("--model", default="", help="Model name.")
    llm.add_argument("--base-url", default="", help="Custom OpenAI-compatible base URL.")
    llm.add_argument("--config-file", default="", help="Override config file path, mainly for tests/CI.")
    llm.add_argument("--status", action="store_true", help="Show redacted LLM config status.")
    llm.set_defaults(func=_configure_llm)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
