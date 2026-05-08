"""Command line entrypoint for early SDK smoke checks."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from .cache import LocatorCache
from .dry_run import audit_locator
from .reporting import HealingReport, get_session_report, summarize_report
from .sdk import AegisAI
from .security import load_security_policy
from .state import is_state_poisoned
from .utils.config import AegisConfig, ReportConfig
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
    policy = load_security_policy(args.policy_file) if args.policy_file else None
    config = AegisConfig(report=ReportConfig(enabled=bool(args.report_file)))
    app = AegisAI(config=config, security_policy=policy)
    result = app.heal_locator(
        args.locator,
        dom,
        expected_role=args.expected_role,
        use_cache=not args.no_cache,
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
    if args.report_file:
        app.report.write_json(args.report_file)
    return 0 if result.locator else 1


def _audit(args: argparse.Namespace) -> int:
    dom = Path(args.dom_file).read_text(encoding="utf-8")
    policy = load_security_policy(args.policy_file) if args.policy_file else None
    result = audit_locator(
        failing_locator=args.locator,
        dom=dom,
        expected_role=args.expected_role,
        app=AegisAI(security_policy=policy),
    )
    payload = result.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if args.approval_prompt and result.suggested_locator:
        answer = input(f"Approve suggested locator {result.suggested_locator!r}? [y/N]: ").strip().lower()
        print(json.dumps({"approved": answer in {"y", "yes"}}))
    return 0 if result.suggested_locator else 1


def _report(args: argparse.Namespace) -> int:
    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        print(json.dumps(summarize_report(payload), indent=2, sort_keys=True))
        return 0
    report = get_session_report()
    if args.output:
        report.write_json(args.output)
    print(json.dumps(summarize_report(report), indent=2, sort_keys=True))
    return 0


def _cache(args: argparse.Namespace) -> int:
    cache = LocatorCache(args.path or None)
    if args.clear:
        cache.clear()
        print("AegisAI locator cache cleared.")
        return 0
    status = {
        "path": str(cache.path),
        "exists": cache.path.exists(),
        "disabled": cache.disabled,
    }
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


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
    heal.add_argument("--policy-file", default="", help="Optional JSON/TOML/YAML Security Officer policy.")
    heal.add_argument("--no-cache", action="store_true", help="Disable local healed-locator cache for this run.")
    heal.add_argument("--report-file", default="", help="Write JSON healing report to this path.")
    heal.set_defaults(func=_heal)

    audit = subcommands.add_parser("audit", aliases=["dry-run"], help="Analyze a locator without browser actions.")
    audit.add_argument("--locator", required=True, help="Failing locator, for example '#login'.")
    audit.add_argument("--dom-file", required=True, help="Path to a local HTML fixture.")
    audit.add_argument("--expected-role", default=None, help="Expected semantic role, for example 'button'.")
    audit.add_argument("--policy-file", default="", help="Optional JSON/TOML/YAML Security Officer policy.")
    audit.add_argument("--output", default="", help="Write dry-run JSON output to this path.")
    audit.add_argument("--approval-prompt", action="store_true", help="Ask for local human approval after analysis.")
    audit.set_defaults(func=_audit)

    report = subcommands.add_parser("report", help="Summarize or write a JSON healing report.")
    report.add_argument("--input", default="", help="Read an existing report JSON file.")
    report.add_argument("--output", default="", help="Write the current process report JSON.")
    report.set_defaults(func=_report)

    cache = subcommands.add_parser("cache", help="Inspect or clear the local locator cache.")
    cache.add_argument("--path", default="", help="Override cache file path.")
    cache.add_argument("--clear", action="store_true", help="Clear the cache file.")
    cache.set_defaults(func=_cache)

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
