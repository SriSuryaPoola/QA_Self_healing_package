from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from aegisai import AegisAI, is_state_poisoned, on_state_poisoned, set_state_poisoned
from aegisai.engine.confidence import ConfidenceScorer, route_for_score
from aegisai.memory import load_events, merge_events, write_event
from aegisai.models import MemoryEvent
from aegisai.persistence.ast_rewrite import rewrite_static_locator
from aegisai.persistence.git_pr import should_open_pr
from aegisai.security import RiskLevel, SecurityOfficer, redact_payload
from aegisai.utils.dom_parser import parse_dom_subset


class ConfidenceTests(unittest.TestCase):
    def test_threshold_routes(self) -> None:
        self.assertEqual(route_for_score(0.91), "auto_pr")
        self.assertEqual(route_for_score(0.85), "confirm_across_runs")
        self.assertEqual(route_for_score(0.79), "block")

    def test_score_is_clamped(self) -> None:
        score = ConfidenceScorer().score(
            attribute_match=2,
            dom_proximity=1,
            historical_success=1,
        )
        self.assertEqual(score.score, 1.0)


class DomAndHealingTests(unittest.TestCase):
    def test_dom_parser_filters_sensitive_values(self) -> None:
        html = """
        <form>
          <input name="password" value="secret">
          <input name="csrf_token" value="csrf-123">
          <button data-testid="login-button" aria-label="Log in">Log in</button>
        </form>
        """
        elements = parse_dom_subset(html)
        serialized = repr(elements)
        self.assertIn("login-button", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("csrf-123", serialized)

    def test_dom_parser_keeps_common_qa_locator_attributes(self) -> None:
        html = '<input data-cy="email-input" formControlName="email">'
        element = parse_dom_subset(html)[0]

        self.assertEqual(element.attrs["data-cy"], "email-input")
        self.assertEqual(element.attrs["formcontrolname"], "email")
        self.assertEqual(element.stable_locator(), '[data-cy="email-input"]')

    def test_form_control_name_can_be_used_as_stable_locator(self) -> None:
        html = '<input formControlName="email">'
        result = AegisAI().heal_locator(
            "//input[@formControlName='email-legacy']",
            html,
            use_cache=False,
        )

        self.assertEqual(result.locator, '[formcontrolname="email"]')
        self.assertTrue(result.guardrail.allowed)

    def test_deterministic_heal_prefers_data_testid(self) -> None:
        html = '<button data-testid="login-button" aria-label="Log in">Log in</button>'
        result = AegisAI().heal_locator("#login", html, expected_role="button")
        self.assertEqual(result.locator, '[data-testid="login-button"]')
        self.assertFalse(result.llm_used)
        self.assertTrue(result.guardrail.allowed)

    def test_guardrail_blocks_role_mismatch(self) -> None:
        html = '<div data-testid="login-button">Log in</div>'
        result = AegisAI().heal_locator("#login", html, expected_role="button")
        self.assertIsNone(result.locator)
        self.assertEqual(result.guardrail.code, "role_mismatch")

    def test_guardrail_blocks_ambiguous_matches(self) -> None:
        html = """
        <button data-testid="login-primary">Log in</button>
        <button data-testid="login-secondary">Log in</button>
        """
        result = AegisAI().heal_locator("#login", html, expected_role="button")
        self.assertIsNone(result.locator)
        self.assertEqual(result.guardrail.code, "ambiguous")


class MemoryTests(unittest.TestCase):
    def test_memory_write_load_and_merge(self) -> None:
        event = MemoryEvent(
            key="login",
            old="#login",
            new='[data-testid="login-button"]',
            confidence=0.93,
            source="deterministic",
            node_id="node-a",
        )
        unique = uuid4().hex
        event = MemoryEvent(
            key=f"login-{unique}",
            old="#login",
            new='[data-testid="login-button"]',
            confidence=0.93,
            source="deterministic",
            node_id=f"node-{unique}",
        )
        output_dir = Path(".aegisai-test-memory")
        first = write_event(event, output_dir)
        second = write_event(event, output_dir)
        self.assertNotEqual(first, second)
        loaded = [item for item in load_events(output_dir) if item.get("key") == event.key]
        self.assertEqual(len(loaded), 2)
        merged = merge_events(loaded)
        self.assertEqual(len(merged), 1)


class PersistenceTests(unittest.TestCase):
    def test_static_locator_rewrite(self) -> None:
        source = 'driver.find_element(By.ID, "login")\n'
        result = rewrite_static_locator(source, "login", "login-button")
        self.assertTrue(result.changed)
        self.assertIn('"login-button"', result.source)

    def test_static_locator_rewrite_supports_playwright_locator_strings(self) -> None:
        source = 'page.locator("xpath=//button[@id=\'old-login\']").click()\n'
        result = rewrite_static_locator(source, "xpath=//button[@id='old-login']", "button[type='submit']")
        self.assertTrue(result.changed)
        self.assertIn('"button[type=\'submit\']"', result.source)

    def test_pr_decision_requires_confidence_or_confirmation(self) -> None:
        self.assertTrue(should_open_pr(0.91).eligible)
        self.assertFalse(should_open_pr(0.85, confirmations=1).eligible)
        self.assertTrue(should_open_pr(0.85, confirmations=2).eligible)
        self.assertFalse(should_open_pr(0.79, confirmations=3).eligible)

    def test_pr_body_generation_is_review_first(self) -> None:
        from aegisai.persistence.git_pr import build_pr_body

        body = build_pr_body(
            [
                {
                    "old_locator": "#old",
                    "new_locator": "#new",
                    "confidence": 0.91,
                    "source": "L2:deterministic",
                    "risk_level": "low",
                    "review_required": True,
                }
            ]
        )

        self.assertIn("Review every locator change", body)
        self.assertIn("`#new`", body)


class StateTests(unittest.TestCase):
    def test_state_poisoned_hook(self) -> None:
        set_state_poisoned(False)
        self.assertFalse(is_state_poisoned())
        result = on_state_poisoned(reset_driver=False)
        self.assertTrue(result["state_poisoned"])
        self.assertTrue(is_state_poisoned())


class InterceptorTests(unittest.TestCase):
    def test_base_interceptor_keeps_recent_failure_context(self) -> None:
        from aegisai.interceptor.base_interceptor import BaseInterceptor

        interceptor = BaseInterceptor()
        interceptor.record_action("find", locator="#missing")

        failure = interceptor.capture_failure(RuntimeError("locator not found"), locator="#missing")

        self.assertIs(interceptor.last_failure, failure)
        self.assertEqual(interceptor.failures[-1].locator, "#missing")
        self.assertEqual(interceptor.failures[-1].last_actions[-1]["locator"], "#missing")


class AutoDetectionTests(unittest.TestCase):
    class _SeleniumDriver:
        page_source = "<html></html>"

        def find_element(self, by="id", value=None):
            raise RuntimeError("missing")

        def execute_script(self, script):
            return None

    class _PlaywrightLocator:
        def count(self):
            return 0

    class _PlaywrightPage:
        def locator(self, selector, *args, **kwargs):
            return AutoDetectionTests._PlaywrightLocator()

        def content(self):
            return "<html></html>"

    def test_detect_framework_from_selenium_object(self) -> None:
        from aegisai import FrameworkKind, detect_framework

        driver = self._SeleniumDriver()
        detection = detect_framework(driver)

        self.assertEqual(detection.kind, FrameworkKind.SELENIUM)
        self.assertIs(detection.target, driver)

    def test_detect_framework_from_playwright_object(self) -> None:
        from aegisai import FrameworkKind, detect_framework

        page = self._PlaywrightPage()
        detection = detect_framework(page)

        self.assertEqual(detection.kind, FrameworkKind.PLAYWRIGHT)
        self.assertIs(detection.target, page)

    def test_universal_activate_patches_selenium_target(self) -> None:
        from aegisai import activate_aegis, deactivate_aegis

        driver = self._SeleniumDriver()
        patch = activate_aegis(driver)

        self.assertIs(getattr(driver, "_aegisai_patch"), patch)
        deactivate_aegis(driver)
        self.assertFalse(patch.active)

    def test_universal_activate_patches_playwright_target(self) -> None:
        from aegisai import activate_aegis, deactivate_aegis

        page = self._PlaywrightPage()
        patch = activate_aegis(page)

        self.assertIs(getattr(page, "_aegisai_playwright_patch"), patch)
        deactivate_aegis(page)
        self.assertFalse(patch.active)

    def test_universal_activate_detects_driver_from_caller_locals(self) -> None:
        from aegisai import activate_aegis

        def _caller():
            driver = AutoDetectionTests._SeleniumDriver()
            patch = activate_aegis()
            return driver, patch

        driver, patch = _caller()

        self.assertIs(getattr(driver, "_aegisai_patch"), patch)

    def test_script_import_detection_without_live_target_is_diagnostic(self) -> None:
        from aegisai import FrameworkKind, detect_framework

        with TemporaryDirectory() as tmp:
            script = Path(tmp) / "sample_playwright_test.py"
            script.write_text(
                "from playwright.sync_api import sync_playwright\n"
                "page.locator('#login').click()\n",
                encoding="utf-8",
            )
            detection = detect_framework(script_path=script)

        self.assertEqual(detection.kind, FrameworkKind.PLAYWRIGHT)
        self.assertIsNone(detection.target)
        self.assertEqual(detection.source, "script imports")


class RegressionTests(unittest.TestCase):
    """Regression tests for bugs fixed in v0.2.0."""

    def test_xpath_type_attribute_locator_heals(self) -> None:
        """Fix 1+2: //input[@type='email'] must score >= 0.8 and be allowed."""
        html = '<input type="email">'
        result = AegisAI().heal_locator("//input[@type='email']", html)
        self.assertIsNotNone(result.locator, "Expected a healed locator, got None")
        self.assertTrue(result.guardrail.allowed,
                        f"Guardrail blocked with: {result.guardrail.reason}")
        self.assertGreaterEqual(result.confidence, 0.8)

    def test_xpath_type_password_locator_heals_with_security_governance(self) -> None:
        """Password fields can heal at runtime, but governance controls persistence."""
        html = '<input type="password">'
        result = AegisAI().heal_locator("//input[@type='password']", html)
        self.assertEqual(result.locator, 'input[type="password"]')
        self.assertTrue(result.guardrail.allowed)

        element = parse_dom_subset(html)[0]
        decision = SecurityOfficer().review_candidate(
            old_locator="//input[@type='password']",
            new_locator=result.locator,
            element=element,
            source="test",
            confidence=result.confidence,
        )
        self.assertEqual(decision.risk_level, RiskLevel.MEDIUM)
        self.assertTrue(decision.runtime_allowed)
        self.assertFalse(decision.persistence_allowed)
        self.assertTrue(decision.review_required)

    def test_bare_input_has_stable_locator(self) -> None:
        """Fix 3: <input type='email'> with no id/name must NOT return None stable_locator."""
        from aegisai.utils.dom_parser import parse_dom_subset
        elements = parse_dom_subset('<input type="email">')
        self.assertTrue(len(elements) > 0, "DOM parser returned no elements")
        locator = elements[0].stable_locator()
        self.assertIsNotNone(locator, "stable_locator() returned None for bare input[type=email]")
        self.assertIn("email", locator)

    def test_llm_fallback_invoked_when_adapter_provided(self) -> None:
        """Fix 4: LLM fallback is called when deterministic heal is blocked."""
        import json

        class _StubAdapter:
            def complete_json(self, payload, *, timeout_seconds, temperature) -> str:
                return json.dumps({"locator": '[name="email"]', "confidence": 0.92})

        # Use a locator that can't match anything in an empty DOM
        result = AegisAI(llm_adapter=_StubAdapter()).heal_locator(
            "//div[@data-unknown='xyz']", "<div></div>"
        )
        self.assertTrue(result.llm_used, "Expected LLM fallback to be used")

    def test_noise_tokens_stripped_from_xpath(self) -> None:
        """Fix 2: XPath noise words like 'normalize', 'space' don't dilute token score."""
        from aegisai.engine.deterministic import DeterministicEngine
        tokens = DeterministicEngine._locator_tokens(
            "//button[normalize-space()='Login here']"
        )
        self.assertNotIn("normalize", tokens)
        self.assertNotIn("space", tokens)
        self.assertIn("login", tokens)
        self.assertIn("here", tokens)

    def test_locator_tokens_split_broken_id_semantics(self) -> None:
        from aegisai.engine.deterministic import DeterministicEngine

        tokens = DeterministicEngine._locator_tokens("//input[@id='pass-field']")
        self.assertEqual(tokens, {"input", "password"})

    def test_broken_id_suffix_heals_when_stable_tokens_are_preserved(self) -> None:
        result = AegisAI().heal_locator(
            "//div[@id='scene-content-container-legacy']",
            '<div id="scene-content-container"></div>',
            use_cache=False,
        )

        self.assertEqual(result.locator, "#scene-content-container")
        self.assertTrue(result.guardrail.allowed)

    def test_broken_aria_label_suffix_heals_when_label_tokens_are_preserved(self) -> None:
        result = AegisAI().heal_locator(
            "//button[@aria-label='Clear type filter legacy']",
            '<button aria-label="Clear type filter"></button>',
            use_cache=False,
        )

        self.assertEqual(result.locator, '[aria-label="Clear type filter"]')
        self.assertTrue(result.guardrail.allowed)

    def test_custom_element_tag_tokens_do_not_block_stable_label_heal(self) -> None:
        result = AegisAI().heal_locator(
            "//mat-button-toggle-group[@aria-label='Font Style legacy']",
            '<mat-button-toggle-group aria-label="Font Style"></mat-button-toggle-group>',
            use_cache=False,
        )

        self.assertEqual(result.locator, '[aria-label="Font Style"]')
        self.assertTrue(result.guardrail.allowed)

    def test_subset_boost_prefers_more_specific_locator_tokens(self) -> None:
        result = AegisAI().heal_locator(
            "//div[@id='single-select-change-counter-legacy']",
            '<div id="single-select"></div><div id="single-select-change-counter"></div>',
            use_cache=False,
        )

        self.assertEqual(result.locator, "#single-select-change-counter")
        self.assertTrue(result.guardrail.allowed)

    def test_broken_id_suffix_can_heal_to_input_type_locator(self) -> None:
        result = AegisAI().heal_locator(
            "//input[@id='password-field-legacy']",
            '<input type="password">',
            use_cache=False,
        )

        self.assertEqual(result.locator, 'input[type="password"]')
        self.assertTrue(result.guardrail.allowed)

    def test_llm_fallback_locator_must_match_filtered_dom(self) -> None:
        import json

        class _StubAdapter:
            def complete_json(self, payload, *, timeout_seconds, temperature) -> str:
                return json.dumps({"locator": '[name="email"]', "confidence": 0.92})

        result = AegisAI(llm_adapter=_StubAdapter()).heal_locator(
            "//div[@data-unknown='xyz']",
            '<input name="email" type="email">',
        )
        self.assertTrue(result.llm_used)
        self.assertEqual(result.locator, '[name="email"]')
        self.assertTrue(result.guardrail.allowed)

    def test_llm_fallback_reports_safe_error(self) -> None:
        class _BrokenAdapter:
            def complete_json(self, payload, *, timeout_seconds, temperature) -> str:
                raise RuntimeError("adapter unavailable")

        result = AegisAI(llm_adapter=_BrokenAdapter()).heal_locator(
            "//div[@data-unknown='xyz']",
            '<input name="email" type="email">',
        )
        self.assertTrue(result.llm_used)
        self.assertIsNone(result.locator)
        self.assertEqual(result.guardrail.code, "llm_error")

    def test_password_candidates_allowed_at_runtime_without_auto_persistence(self) -> None:
        from aegisai.engine.healing_orchestrator import HealingOrchestrator

        class _Element:
            tag_name = "input"
            text = ""

            def get_attribute(self, name):
                return {"tagName": "input", "type": "password", "name": "password"}.get(name)

        decision, persistence_allowed = HealingOrchestrator()._review_live_candidate(
            element=_Element(),
            locator='input[type="password"]',
            confidence=0.95,
            raw_locator="//input[@type='password']",
        )
        self.assertTrue(decision.allowed)
        self.assertFalse(persistence_allowed)

    def test_critical_token_candidates_blocked_across_layers(self) -> None:
        from aegisai.engine.healing_orchestrator import HealingOrchestrator

        class _Element:
            tag_name = "input"
            text = ""

            def get_attribute(self, name):
                return {"tagName": "input", "type": "hidden", "name": "csrf_token"}.get(name)

        decision = HealingOrchestrator()._validate_live_candidate(
            element=_Element(),
            locator='input[name="csrf_token"]',
            confidence=0.95,
            raw_locator="//input[@name='csrf_token']",
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "security_blocked")

    def test_password_candidates_generated_by_fast_layers(self) -> None:
        from aegisai.engine.js_prober import _build_strategies
        from aegisai.engine.locator_translator import translate

        translations = translate("//input[@type='password']")
        strategies = _build_strategies("//input[@type='password']")
        self.assertTrue(any(item.locator == "input[type='password']" for item in translations))
        self.assertTrue(any(item["selector"] == "input[type='password']" for item in strategies))

    def test_js_probe_supports_mail_synonym_without_l1_translation(self) -> None:
        from aegisai.engine.js_prober import _PROBE_SCRIPT, _build_strategies
        from aegisai.engine.locator_translator import translate

        locator = "//input[@data-field='mailbox-field']"
        self.assertTrue(_PROBE_SCRIPT.lstrip().startswith("return"))
        self.assertFalse(any(item.source.startswith("email") for item in translate(locator)))
        self.assertTrue(any(item["selector"] == "input[type='email']" for item in _build_strategies(locator)))

    def test_security_redactor_masks_secret_payload_values(self) -> None:
        redacted = redact_payload(
            {
                "password": "MySecret123",
                "attrs": {"value": "ActualPassword123", "placeholder": "Password"},
                "token": "csrf-123",
            }
        )
        self.assertEqual(redacted["password"], "***MASKED***")
        self.assertEqual(redacted["attrs"]["value"], "***MASKED***")
        self.assertEqual(redacted["token"], "***MASKED***")
        self.assertEqual(redacted["attrs"]["placeholder"], "Password")

    def test_orchestrator_skips_l5_when_llm_disabled(self) -> None:
        from aegisai.engine.healing_orchestrator import HealingOrchestrator
        from aegisai.utils.llm_config import CONFIG_DIR_ENV
        from unittest.mock import patch

        class _Driver:
            page_source = "<html></html>"

            def find_element(self, by, locator):
                raise RuntimeError("not found")

            def execute_script(self, script):
                return None

        with TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {CONFIG_DIR_ENV: tmp}, clear=True):
                outcome = HealingOrchestrator(enable_llm=False).orchestrate(
                    RuntimeError("missing"),
                    driver=_Driver(),
                    wait=None,
                    failing_locator="//input[@type='email']",
                )
        self.assertFalse(outcome.success)
        self.assertIn("L5 LLM fallback was not started", outcome.reason)
        self.assertIn("no LLM provider/API key is configured", outcome.reason)
        self.assertNotIn("L5:llm", outcome.layers_tried)

    def test_orchestrator_reports_missing_llm_key_when_l5_enabled(self) -> None:
        from aegisai.engine.healing_orchestrator import HealingOrchestrator
        from aegisai.utils.llm_config import CONFIG_DIR_ENV
        from unittest.mock import patch

        class _Driver:
            page_source = "<html></html>"

            def find_element(self, by, locator):
                raise RuntimeError("not found")

            def execute_script(self, script):
                return None

        with TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {CONFIG_DIR_ENV: tmp}, clear=True):
                outcome = HealingOrchestrator(enable_llm=True).orchestrate(
                    RuntimeError("missing"),
                    driver=_Driver(),
                    wait=None,
                    failing_locator="//input[@type='email']",
                )
        self.assertFalse(outcome.success)
        self.assertIn("L5:llm", outcome.layers_tried)
        self.assertIn("L5 LLM fallback is unavailable", outcome.reason)
        self.assertIn("no LLM provider/API key is configured", outcome.reason)

    def test_placeholder_llm_key_is_treated_as_missing(self) -> None:
        from aegisai.engine.universal_llm_adapter import UniversalLLMAdapter
        from aegisai.utils.llm_config import CONFIG_DIR_ENV
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            with patch.dict(
                "os.environ",
                {
                    CONFIG_DIR_ENV: tmp,
                    "AEGIS_LLM_PROVIDER": "openai",
                    "AEGIS_LLM_API_KEY": "your-api-key",
                    "AEGIS_LLM_MODEL": "gpt-4o",
                },
                clear=True,
            ):
                self.assertFalse(UniversalLLMAdapter.is_configured())
                self.assertIn(
                    "AEGIS_LLM_API_KEY is not configured",
                    UniversalLLMAdapter.configuration_issue(),
                )

    def test_configure_llm_writes_user_env_without_printing_key(self) -> None:
        from aegisai.main import main

        with TemporaryDirectory() as tmp:
            config_file = Path(tmp) / ".env"
            output = StringIO()
            with redirect_stdout(output):
                code = main(
                    [
                        "configure",
                        "llm",
                        "--enable",
                        "--provider",
                        "openai",
                        "--api-key",
                        "unit-test-secret-value",
                        "--model",
                        "gpt-4o-mini",
                        "--config-file",
                        str(config_file),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertTrue(config_file.exists())
            self.assertIn('AEGIS_LLM_ENABLED="true"', config_file.read_text(encoding="utf-8"))
            self.assertIn('AEGIS_LLM_API_KEY="unit-test-secret-value"', config_file.read_text(encoding="utf-8"))
            self.assertIn("API key: configured", output.getvalue())
            self.assertNotIn("unit-test-secret-value", output.getvalue())

    def test_universal_adapter_reads_saved_user_config(self) -> None:
        from aegisai.engine.universal_llm_adapter import UniversalLLMAdapter
        from aegisai.utils.llm_config import CONFIG_DIR_ENV, LLMSettings, write_llm_settings
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            write_llm_settings(
                LLMSettings(
                    enabled=True,
                    provider="openai",
                    api_key="unit-test-secret-value",
                    model="gpt-4o-mini",
                ),
                Path(tmp) / ".env",
            )
            with patch.dict("os.environ", {CONFIG_DIR_ENV: tmp}, clear=True):
                self.assertTrue(UniversalLLMAdapter.is_configured())
                adapter = UniversalLLMAdapter()
                self.assertEqual(adapter.provider, "openai")
                self.assertEqual(adapter.api_key, "unit-test-secret-value")
                self.assertEqual(adapter.model, "gpt-4o-mini")

    def test_listener_uses_saved_llm_enabled_preference(self) -> None:
        from aegisai.interceptor.selenium_listener import AegisSeleniumListener
        from aegisai.utils.llm_config import CONFIG_DIR_ENV, LLMSettings, write_llm_settings
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            write_llm_settings(
                LLMSettings(enabled=True, provider="ollama", model="llama3.1"),
                Path(tmp) / ".env",
            )
            with patch.dict("os.environ", {CONFIG_DIR_ENV: tmp}, clear=True):
                listener = AegisSeleniumListener()
                self.assertTrue(listener._enable_llm)

    def test_heal_find_returns_direct_element_without_healing(self) -> None:
        from aegisai.selenium import heal_find

        class _Driver:
            def find_element(self, by, value):
                return {"by": by, "value": value}

        result = heal_find(_Driver(), None, "xpath", "//input[@type='email']")
        self.assertEqual(result, {"by": "xpath", "value": "//input[@type='email']"})

    def test_heal_find_uses_listener_on_failure(self) -> None:
        from aegisai.selenium import heal_find

        class _Driver:
            def find_element(self, by, value):
                raise RuntimeError("missing")

        class _Listener:
            def __init__(self):
                self.recorded = None

            def before_find(self, by, value, driver=None):
                self.recorded = (by, value, driver)

            def autonomous_heal(self, exc, *, driver, wait=None, original_condition=None):
                return "healed-element"

        driver = _Driver()
        listener = _Listener()
        result = heal_find(driver, None, "xpath", "//missing", listener=listener)
        self.assertEqual(result, "healed-element")
        self.assertEqual(listener.recorded, ("XPATH", "//missing", driver))

    def test_activate_aegis_auto_heals_find_element_and_restores(self) -> None:
        from aegisai.selenium import activate_aegis, deactivate_aegis

        class _Driver:
            def __init__(self):
                self.original_calls = 0

            def find_element(self, by, value):
                self.original_calls += 1
                raise RuntimeError("missing")

        driver = _Driver()
        patch = activate_aegis(driver)
        patch.listener.autonomous_heal = lambda exc, *, driver, wait=None, original_condition=None: "healed"

        self.assertEqual(driver.find_element("xpath", "//missing"), "healed")
        self.assertEqual(driver.original_calls, 1)
        self.assertIs(activate_aegis(driver), patch)

        deactivate_aegis(driver)
        with self.assertRaises(RuntimeError):
            driver.find_element("xpath", "//missing")
        self.assertFalse(patch.active)

    def test_activate_aegis_does_not_recurse_during_healing(self) -> None:
        from aegisai.selenium import activate_aegis

        class _Driver:
            def __init__(self):
                self.original_calls = 0

            def find_element(self, by, value):
                self.original_calls += 1
                raise RuntimeError("missing")

        driver = _Driver()
        patch = activate_aegis(driver)

        def _heal(exc, *, driver, wait=None, original_condition=None):
            with self.assertRaises(RuntimeError):
                driver.find_element("xpath", "//still-missing")
            return "healed"

        patch.listener.autonomous_heal = _heal
        self.assertEqual(driver.find_element("xpath", "//missing"), "healed")
        self.assertEqual(driver.original_calls, 2)

    def test_playwright_activate_aegis_auto_heals_fill_and_restores(self) -> None:
        from aegisai.playwright import activate_aegis, deactivate_aegis

        class _Locator:
            def __init__(self, page, selector):
                self.page = page
                self.selector = selector

            def count(self):
                return 1 if self.selector == "#username" else 0

            def fill(self, value, **kwargs):
                if self.selector != "#username":
                    raise RuntimeError("missing")
                self.page.values[self.selector] = value

        class _Page:
            def __init__(self):
                self.values = {}

            def locator(self, selector, *args, **kwargs):
                return _Locator(self, selector)

            def content(self):
                return '<input id="username" type="text">'

            def wait_for_load_state(self, state, timeout=None):
                return None

        page = _Page()
        patch = activate_aegis(page)

        page.locator("xpath=//input[@id='user-name-field']").fill("tomsmith")

        self.assertEqual(page.values["#username"], "tomsmith")
        self.assertEqual(patch.last_outcome.layer_used, 2)
        self.assertEqual(patch.last_outcome.healed_selector, "#username")

        deactivate_aegis(page)
        with self.assertRaises(RuntimeError):
            page.locator("xpath=//input[@id='user-name-field']").fill("tomsmith")
        self.assertFalse(patch.active)

    def test_playwright_activate_aegis_auto_heals_click_with_translation(self) -> None:
        from aegisai.playwright import activate_aegis

        class _Locator:
            def __init__(self, page, selector):
                self.page = page
                self.selector = selector

            def count(self):
                return 1 if self.selector == "button[type='submit']" else 0

            def click(self, **kwargs):
                if self.selector != "button[type='submit']":
                    raise RuntimeError("missing")
                self.page.clicked = self.selector

        class _Page:
            clicked = None

            def locator(self, selector, *args, **kwargs):
                return _Locator(self, selector)

            def content(self):
                return '<button type="submit">Login</button>'

            def wait_for_load_state(self, state, timeout=None):
                return None

        page = _Page()
        patch = activate_aegis(page)

        page.locator("xpath=//button[@data-testid='login-submit']").click()

        self.assertEqual(page.clicked, "button[type='submit']")
        self.assertEqual(patch.last_outcome.layer_used, 1)
        self.assertEqual(patch.last_outcome.healed_selector, "button[type='submit']")

    def test_playwright_heal_fill_helper_uses_auto_activation(self) -> None:
        from aegisai.playwright import heal_fill

        class _Locator:
            def __init__(self, page, selector):
                self.page = page
                self.selector = selector

            def count(self):
                return 1 if self.selector == "#password" else 0

            def fill(self, value, **kwargs):
                if self.selector != "#password":
                    raise RuntimeError("missing")
                self.page.values[self.selector] = value

        class _Page:
            def __init__(self):
                self.values = {}

            def locator(self, selector, *args, **kwargs):
                return _Locator(self, selector)

            def content(self):
                return '<input id="password" type="password">'

            def wait_for_load_state(self, state, timeout=None):
                return None

        page = _Page()
        heal_fill(page, "xpath=//input[@id='pass-field']", "secret")
        self.assertEqual(page.values["#password"], "secret")

    def test_playwright_retryable_actions_include_deeper_locator_parity(self) -> None:
        from aegisai.playwright import RETRYABLE_ACTIONS

        self.assertIn("get_attribute", RETRYABLE_ACTIONS)
        self.assertIn("screenshot", RETRYABLE_ACTIONS)
        self.assertIn("tap", RETRYABLE_ACTIONS)


class ReportingCacheDryRunTests(unittest.TestCase):
    def test_healing_report_records_and_writes_json(self) -> None:
        from aegisai.reporting import HealingReport

        with TemporaryDirectory() as tmp:
            report = HealingReport()
            report.record_attempt(
                original_locator="#old",
                healed_locator="#new",
                success=True,
                source="deterministic",
                layer_label="L2:deterministic",
                confidence=0.93,
            )
            target = report.write_json(Path(tmp) / "report.json")
            payload = target.read_text(encoding="utf-8")

        self.assertIn('"success": 1', payload)
        self.assertIn('"L2:deterministic": 1', payload)

    def test_sdk_report_recording_is_opt_in(self) -> None:
        from aegisai.reporting import reset_session_report
        from aegisai.utils.config import AegisConfig, ReportConfig

        reset_session_report()
        AegisAI().heal_locator("//input[@type='email']", '<input type="email">', use_cache=False)
        self.assertEqual(len(reset_session_report().events), 0)

        app = AegisAI(config=AegisConfig(report=ReportConfig(enabled=True)))
        app.heal_locator("//input[@type='email']", '<input type="email">', use_cache=False)
        self.assertEqual(len(app.report.events), 1)

    def test_locator_cache_reuses_same_dom_fingerprint(self) -> None:
        from aegisai.utils.config import AegisConfig, CacheConfig

        with TemporaryDirectory() as tmp:
            app = AegisAI(config=AegisConfig(cache=CacheConfig(path=str(Path(tmp) / "cache.json"))))
            dom = '<input type="email">'
            first = app.heal_locator("//input[@type='email']", dom)
            second = app.heal_locator("//input[@type='email']", dom)

        self.assertEqual(first.source, "deterministic")
        self.assertEqual(second.source, "cache")
        self.assertEqual(second.locator, 'input[type="email"]')

    def test_dom_fingerprint_does_not_include_secret_values(self) -> None:
        from aegisai.cache import dom_fingerprint

        left = dom_fingerprint('<input name="password" value="secret-one">')
        right = dom_fingerprint('<input name="password" value="secret-two">')

        self.assertEqual(left, right)

    def test_cache_path_can_be_shared_through_environment(self) -> None:
        from unittest.mock import patch
        from aegisai.cache import CACHE_PATH_ENV, LocatorCache

        with TemporaryDirectory() as tmp:
            shared_path = Path(tmp) / "team-cache.json"
            with patch.dict("os.environ", {CACHE_PATH_ENV: str(shared_path)}):
                cache = LocatorCache()

        self.assertEqual(cache.path, shared_path)

    def test_dom_drift_detection_reports_added_and_removed_locators(self) -> None:
        from aegisai import detect_dom_drift

        drift = detect_dom_drift('<button id="submit">Submit</button>', '<button id="login">Login</button>')

        self.assertTrue(drift.changed)
        self.assertEqual(drift.removed_locators, ["#submit"])
        self.assertEqual(drift.added_locators, ["#login"])

    def test_dry_run_locator_reports_without_interaction(self) -> None:
        from aegisai.dry_run import audit_locator

        result = audit_locator(
            failing_locator="//input[@type='email']",
            dom='<input type="email">',
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.suggested_locator, 'input[type="email"]')

    def test_selenium_dry_run_uses_page_source_only(self) -> None:
        from aegisai.selenium import dry_run_find

        class _Driver:
            page_source = '<button data-testid="login-button">Login</button>'

            def find_element(self, by, locator):
                raise AssertionError("dry_run_find must not call find_element")

        result = dry_run_find(_Driver(), "xpath", "//button[@id='login']")
        self.assertEqual(result.suggested_locator, '[data-testid="login-button"]')

    def test_debug_artifacts_capture_redacted_dom(self) -> None:
        from aegisai import capture_debug_artifacts

        class _Driver:
            page_source = '<input name="password" value="secret"><button data-testid="login">Login</button>'

        with TemporaryDirectory() as tmp:
            paths = capture_debug_artifacts(_Driver(), directory=tmp)
            payload = Path(paths["dom"]).read_text(encoding="utf-8")

        self.assertIn("login", payload)
        self.assertNotIn("secret", payload)

    def test_playwright_dry_run_uses_page_content_only(self) -> None:
        from aegisai.playwright import dry_run_selector

        class _Page:
            def content(self):
                return '<input type="email">'

            def locator(self, selector):
                raise AssertionError("dry_run_selector must not create Playwright locators")

        result = dry_run_selector(_Page(), "xpath=//input[@type='email']")
        self.assertEqual(result.suggested_locator, 'input[type="email"]')


class PolicyAndPersistenceTests(unittest.TestCase):
    def test_security_policy_loads_toml_file(self) -> None:
        from aegisai.security import load_security_policy

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.toml"
            path.write_text(
                "[security]\n"
                "name = \"strict\"\n"
                "allow_runtime_for_high = false\n"
                "min_confidence_medium = 0.91\n",
                encoding="utf-8",
            )
            policy = load_security_policy(path)

        self.assertEqual(policy.name, "strict")
        self.assertFalse(policy.allow_runtime_for_high)
        self.assertEqual(policy.min_confidence_medium, 0.91)

    def test_security_policy_loads_simple_yaml_file(self) -> None:
        from aegisai.security import load_security_policy

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.yaml"
            path.write_text(
                "security:\n"
                "  name: yaml-policy\n"
                "  auto_persist_low: false\n",
                encoding="utf-8",
            )
            policy = load_security_policy(path)

        self.assertEqual(policy.name, "yaml-policy")
        self.assertFalse(policy.auto_persist_low)

    def test_high_risk_runtime_can_be_blocked_by_policy(self) -> None:
        from aegisai.security import SecurityPolicy

        html = '<button data-testid="delete-user">Delete user</button>'
        app = AegisAI(security_policy=SecurityPolicy(allow_runtime_for_high=False))
        result = app.heal_locator("//button[@id='delete']", html, expected_role="button")

        self.assertIsNone(result.locator)
        self.assertEqual(result.guardrail.code, "security_blocked")

    def test_security_audit_log_redacts_sensitive_values(self) -> None:
        from aegisai.models import DomElement
        from aegisai.security import SecurityOfficer, SecurityPolicy

        with TemporaryDirectory() as tmp:
            officer = SecurityOfficer(SecurityPolicy(audit_dir=tmp))
            officer.review_candidate(
                old_locator="//input[@name='password']",
                new_locator='input[type="password"]',
                element=DomElement(
                    tag="input",
                    attrs={"type": "password", "name": "password", "value": "ActualPassword123"},
                ),
                source="test",
                confidence=0.91,
            )
            files = list(Path(tmp).glob("*.json"))
            payload = files[0].read_text(encoding="utf-8")

        self.assertIn("***MASKED***", payload)
        self.assertNotIn("ActualPassword123", payload)

    def test_low_risk_success_audit_is_opt_in(self) -> None:
        from aegisai.models import DomElement
        from aegisai.security import SecurityOfficer, SecurityPolicy

        with TemporaryDirectory() as tmp:
            officer = SecurityOfficer(SecurityPolicy(audit_dir=tmp))
            officer.review_candidate(
                old_locator="#login",
                new_locator='[data-testid="login-button"]',
                element=DomElement(tag="button", attrs={"data-testid": "login-button"}, text="Login"),
                source="test",
                confidence=0.91,
            )
            self.assertEqual(list(Path(tmp).glob("*.json")), [])

            opt_in = SecurityOfficer(SecurityPolicy(audit_dir=tmp, audit_low_risk=True))
            opt_in.review_candidate(
                old_locator="#login",
                new_locator='[data-testid="login-button"]',
                element=DomElement(tag="button", attrs={"data-testid": "login-button"}, text="Login"),
                source="test",
                confidence=0.91,
            )

            self.assertEqual(len(list(Path(tmp).glob("*.json"))), 1)

    def test_security_audit_deduplicates_repeated_decisions(self) -> None:
        from aegisai.models import DomElement
        from aegisai.security import SecurityOfficer, SecurityPolicy

        with TemporaryDirectory() as tmp:
            officer = SecurityOfficer(SecurityPolicy(audit_dir=tmp))
            for _ in range(2):
                officer.review_candidate(
                    old_locator="//input[@id='pass-field']",
                    new_locator='input[type="password"]',
                    element=DomElement(tag="input", attrs={"type": "password", "name": "password"}),
                    source="test",
                    confidence=0.91,
                )

            self.assertEqual(len(list(Path(tmp).glob("*.json"))), 1)

    def test_heal_suggestions_file_contains_diff(self) -> None:
        from aegisai.persistence.suggestions import append_heal_suggestion, create_source_suggestion

        with TemporaryDirectory() as tmp:
            script = Path(tmp) / "test_login.py"
            script.write_text('driver.find_element(By.ID, "old-login")\n', encoding="utf-8")
            suggestion = create_source_suggestion(
                old_locator="old-login",
                new_locator="new-login",
                confidence=0.91,
                source_label="L2:deterministic",
                script_path=script,
                reason="review required",
            )
            target = append_heal_suggestion(suggestion, Path(tmp) / "HEAL_SUGGESTIONS.json")
            payload = target.read_text(encoding="utf-8")

        self.assertIn("new-login", payload)
        self.assertIn("--- a/test_login.py", payload)

    def test_multi_occurrence_source_patch_requires_review(self) -> None:
        source = 'page.locator("#old").click()\npage.locator("#old").fill("x")\n'
        result = rewrite_static_locator(source, "#old", "#new")

        self.assertFalse(result.changed)
        self.assertIn("Multiple static occurrences", result.reason)


class AsyncPlaywrightAndIntegrationTests(unittest.TestCase):
    def test_async_playwright_heal_fill_helper(self) -> None:
        import asyncio
        from aegisai.playwright_async import async_heal_fill

        class _Locator:
            def __init__(self, page, selector):
                self.page = page
                self.selector = selector

            async def fill(self, value, **kwargs):
                if self.selector != "#password":
                    raise RuntimeError("missing")
                self.page.values[self.selector] = value

        class _Page:
            def __init__(self):
                self.values = {}

            def locator(self, selector, *args, **kwargs):
                return _Locator(self, selector)

            async def content(self):
                return '<input id="password" type="password">'

        async def _run() -> dict[str, str]:
            page = _Page()
            await async_heal_fill(page, "xpath=//input[@id='pass-field']", "secret")
            return page.values

        self.assertEqual(asyncio.run(_run())["#password"], "secret")

    def test_universal_activate_uses_async_playwright_patch(self) -> None:
        import asyncio
        from aegisai import activate_aegis, deactivate_aegis

        class _Locator:
            async def fill(self, value, **kwargs):
                return None

        class _AsyncPage:
            def locator(self, selector, *args, **kwargs):
                return _Locator()

            async def content(self):
                return "<html></html>"

        page = _AsyncPage()
        patch = activate_aegis(page)
        self.assertIs(getattr(page, "_aegisai_async_playwright_patch"), patch)
        deactivate_aegis(page)
        self.assertFalse(patch.active)
        asyncio.run(page.content())

    def test_pytest_plugin_module_imports(self) -> None:
        import aegisai.pytest_plugin as plugin

        self.assertTrue(callable(plugin.pytest_addoption))

    def test_public_extra_modules_import(self) -> None:
        import aegisai.playwright
        import aegisai.playwright_async
        import aegisai.selenium
        import aegisai.unittest_integration

        self.assertTrue(callable(aegisai.selenium.heal_find))
        self.assertTrue(callable(aegisai.playwright.heal_fill))
        self.assertTrue(callable(aegisai.playwright_async.async_heal_fill))

    def test_unittest_mixin_restores_targets(self) -> None:
        from aegisai.unittest_integration import AegisTestMixin

        class _Driver:
            page_source = "<html></html>"

            def find_element(self, by="id", value=None):
                raise RuntimeError("missing")

            def execute_script(self, script):
                return None

        class _Case(AegisTestMixin):
            def run_case(self):
                self.driver = _Driver()
                patch = self.activate_aegis_for(self.driver)
                self.tearDown()
                return patch

        patch = _Case().run_case()
        self.assertFalse(patch.active)


class BrowserComplexityTests(unittest.TestCase):
    def test_static_fixture_dropdown_and_table_patterns_heal(self) -> None:
        html = Path("tests/fixtures/common_ui_patterns.html").read_text(encoding="utf-8")

        dropdown = AegisAI().heal_locator("//select[@id='country-field']", html, expected_role="combobox")
        table_cell = AegisAI().heal_locator("//td[@id='order-status-cell']", html)

        self.assertEqual(dropdown.locator, "#country")
        self.assertEqual(table_cell.locator, '[data-testid="order-status"]')

    def test_hidden_and_disabled_candidates_are_blocked(self) -> None:
        disabled = AegisAI().heal_locator(
            "//button[@id='disabled-login']",
            '<button data-testid="disabled-login" disabled>Login</button>',
            expected_role="button",
        )
        hidden = AegisAI().heal_locator(
            "//button[@id='hidden-login']",
            '<button data-testid="hidden-login" aria-hidden="true">Login</button>',
            expected_role="button",
        )

        self.assertIsNone(disabled.locator)
        self.assertEqual(disabled.guardrail.code, "not_interactable")
        self.assertIsNone(hidden.locator)
        self.assertEqual(hidden.guardrail.code, "not_interactable")

    def test_overlay_candidates_are_blocked(self) -> None:
        result = AegisAI().heal_locator(
            "//button[@id='login']",
            '<button data-testid="login-button" class="blocking-overlay">Login</button>',
            expected_role="button",
        )

        self.assertIsNone(result.locator)
        self.assertEqual(result.guardrail.code, "not_interactable")

    def test_stale_element_failure_is_treated_as_locator_recoverable(self) -> None:
        from aegisai.interceptor.base_interceptor import BaseInterceptor

        class StaleElementReferenceException(Exception):
            pass

        self.assertTrue(BaseInterceptor().is_locator_failure(StaleElementReferenceException("stale")))

    def test_selenium_quick_find_discovers_iframe_element(self) -> None:
        from aegisai.engine.healing_orchestrator import HealingOrchestrator

        class _Element:
            def is_displayed(self):
                return True

        class _SwitchTo:
            def __init__(self, driver):
                self.driver = driver

            def frame(self, frame):
                self.driver.in_frame = True

            def parent_frame(self):
                self.driver.in_frame = False

        class _Driver:
            def __init__(self):
                self.in_frame = False
                self.switch_to = _SwitchTo(self)

            def find_element(self, by, locator):
                if self.in_frame and locator == "#email":
                    return _Element()
                raise RuntimeError("missing")

            def find_elements(self, by, locator):
                return ["frame"] if not self.in_frame and locator == "iframe,frame" else []

        driver = _Driver()
        element = HealingOrchestrator()._quick_find(driver, "css", "#email")

        self.assertIsNotNone(element)
        self.assertTrue(driver.in_frame)

    def test_l0_handles_delayed_render_without_clicking(self) -> None:
        from aegisai.engine.healing_orchestrator import HealingOrchestrator

        class _Element:
            def is_displayed(self):
                return True

        class _Driver:
            page_source = "<html></html>"

            def __init__(self):
                self.calls = 0
                self.clicked = False

            def find_element(self, by, locator):
                self.calls += 1
                if self.calls >= 2:
                    return _Element()
                raise RuntimeError("not rendered yet")

            def execute_script(self, script):
                return None

        driver = _Driver()
        element, _ = HealingOrchestrator()._l0_dom_ready(driver, "#late")

        self.assertIsNotNone(element)
        self.assertFalse(driver.clicked)

    def test_l0_modal_closed_remains_safe_failure(self) -> None:
        from aegisai.engine.healing_orchestrator import HealingOrchestrator

        class _Driver:
            page_source = "<button id='open-login'>Open Login</button>"

            def __init__(self):
                self.clicked = False

            def find_element(self, by, locator):
                raise RuntimeError("modal closed")

            def execute_script(self, script):
                if "click" in script.lower():
                    self.clicked = True

        driver = _Driver()
        element, _ = HealingOrchestrator()._l0_dom_ready(driver, "#email")

        self.assertIsNone(element)
        self.assertFalse(driver.clicked)

    def test_smart_wait_strategy_varies_by_element_type(self) -> None:
        from aegisai.engine.healing_orchestrator import HealingOrchestrator

        self.assertLess(
            HealingOrchestrator._smart_wait_seconds("//button[@id='submit']"),
            HealingOrchestrator._smart_wait_seconds("//div[@id='profile-modal']"),
        )

    def test_l4_js_probe_contains_shadow_dom_query(self) -> None:
        from aegisai.engine.js_prober import _PROBE_SCRIPT, _build_strategies

        self.assertIn("shadowRoot", _PROBE_SCRIPT)
        self.assertIn("queryDeep", _PROBE_SCRIPT)
        self.assertTrue(any(item["label"] == "original_css_deep" for item in _build_strategies("my-widget button")))

    def test_sdk_healing_stays_under_local_performance_budget(self) -> None:
        import time

        started = time.perf_counter()
        result = AegisAI().heal_locator("//input[@type='email']", '<input type="email">', use_cache=False)
        elapsed_ms = (time.perf_counter() - started) * 1000

        self.assertEqual(result.locator, 'input[type="email"]')
        self.assertLess(elapsed_ms, 250)

    def test_sdk_reuses_parsed_dom_snapshots(self) -> None:
        app = AegisAI()
        dom = '<form><input type="email"><button>Login</button></form>'

        first = app._parse_dom(dom)
        second = app._parse_dom(dom)

        self.assertIs(first, second)
        self.assertLessEqual(len(app._parsed_dom_cache), app._parsed_dom_cache_size)

    def test_sdk_reuses_deterministic_results(self) -> None:
        app = AegisAI()
        original_heal = app.deterministic.heal
        calls = 0

        def counted_heal(request):
            nonlocal calls
            calls += 1
            return original_heal(request)

        app.deterministic.heal = counted_heal
        dom = '<input type="email">'

        first = app.heal_locator("//input[@type='email']", dom, use_cache=False)
        second = app.heal_locator("//input[@type='email']", dom, use_cache=False)

        self.assertEqual(first.locator, second.locator)
        self.assertEqual(calls, 1)
        self.assertLessEqual(len(app._deterministic_result_cache), app._deterministic_result_cache_size)

    def test_sdk_reuses_safe_runtime_results_when_report_disabled(self) -> None:
        app = AegisAI()
        original_review = app.security_officer.review_candidate
        original_parse = app._parse_dom
        calls = 0
        parse_calls = 0

        def counted_review(**kwargs):
            nonlocal calls
            calls += 1
            return original_review(**kwargs)

        def counted_parse(dom, key=None):
            nonlocal parse_calls
            parse_calls += 1
            return original_parse(dom, key)

        app.security_officer.review_candidate = counted_review
        app._parse_dom = counted_parse
        dom = '<input type="email">'

        first = app.heal_locator("//input[@type='email']", dom, use_cache=False)
        second = app.heal_locator("//input[@type='email']", dom, use_cache=False)

        self.assertEqual(first.locator, second.locator)
        self.assertEqual(calls, 1)
        self.assertEqual(parse_calls, 1)
        self.assertLessEqual(len(app._runtime_result_cache), app._runtime_result_cache_size)

    def test_long_run_repeated_healing_is_stable(self) -> None:
        from aegisai.utils.config import AegisConfig, CacheConfig

        with TemporaryDirectory() as tmp:
            app = AegisAI(config=AegisConfig(cache=CacheConfig(path=str(Path(tmp) / "cache.json"))))
            locators = [
                app.heal_locator("//input[@type='email']", '<input type="email">').locator
                for _ in range(25)
            ]

        self.assertEqual(set(locators), {'input[type="email"]'})


if __name__ == "__main__":
    unittest.main()
