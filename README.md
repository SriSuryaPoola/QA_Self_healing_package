# AegisAI

AegisAI is a local Python package for self-healing UI automation. It helps Selenium and Playwright test suites recover from broken locators without forcing teams to replace their framework, rewrite their test architecture, or move execution into a separate platform.

It is designed to blend into the automation code you already have:

- Keep Selenium, Playwright, pytest, unittest, behave, Robot Framework, or your existing runner.
- Choose explicit listener mode, helper mode, or opt-in auto-activation.
- Let fast deterministic layers try first.
- Use LLM healing only as an optional last resort.
- Keep sensitive data protected through local security governance.

AegisAI is not trying to become your test framework. It is a healing and governance layer that sits beside your framework.

## Why This Package Exists

Modern UI automation breaks for ordinary reasons:

- An `id` changes from `email-field` to `email`.
- A button text changes from `Submit` to `Login`.
- A React component renders later than Selenium expects.
- A DOM snapshot is stale but the live browser already has the element.
- A password locator changes, but the test data must never be leaked to an LLM.

Most self-healing approaches either retry blindly or jump straight to AI. AegisAI takes a different path: deterministic first, browser-aware second, LLM last, security always.

## What Users Get

| Benefit | What It Means |
|---|---|
| Less locator maintenance | Broken XPath/CSS selectors can be repaired during execution. |
| Framework-friendly adoption | No platform migration and no mandatory monkey patching. |
| Lower user error | Helper and auto-activation modes reduce missed `before_find(...)` calls. |
| Deterministic-first speed | L0-L4 run locally before any LLM is considered. |
| Optional LLM fallback | L5 is available only when explicitly configured. |
| Security governance | DOM context is sanitized, secrets are masked, and risky persistence is controlled. |
| Auditability | Security decisions can be logged locally for traceability. |
| CI-friendly config | Env vars still work for pipelines; local CLI config works for developers. |

## Current Capability Snapshot

| Area | Status |
|---|---|
| Selenium L0-L5 healing cascade | Available |
| Universal framework detection | Available through `from aegisai import activate_aegis` |
| Selenium runtime healing | Available |
| Selenium helper functions | Available through `heal_find`, `heal_click`, `heal_send_keys` |
| Selenium opt-in auto-activation | Available through `activate_aegis(driver, ...)` |
| Selenium safe script persistence | Available when policy allows |
| Playwright core SDK healing | Available manually via `page.content()` |
| Playwright helper functions | Available through `heal_fill`, `heal_click`, `heal_selector` |
| Playwright opt-in auto-activation | Available for sync `page.locator(...).fill()/click()` style actions |
| Playwright async helpers | Available through `aegisai.playwright_async` |
| Playwright iframe helpers | Available for explicit frame fill/click workflows |
| Playwright page hooks | Available for explicit failure/action context capture |
| Playwright full L0-L4 automatic listener | Available for common sync locator actions |
| Playwright L5 LLM fallback | Planned; use explicit SDK/LLM path for now |
| LLM provider setup CLI | Available through `aegisai configure llm` |
| Security Officer governance | Available |
| Security policy files | Available through JSON, TOML, or simple YAML |
| Dry-run / audit mode | Available through CLI and Selenium/Playwright helpers |
| Local healed-locator cache | Available and disableable |
| JSON healing reports | Available for local debugging and CI artifacts |
| Review suggestions artifact | Available as `.aegisai/HEAL_SUGGESTIONS.json` |
| pytest/unittest helpers | Available without replacing the existing runner |
| DOM drift detection | Available for pre-failure locator drift checks |
| Common QA locator anchors | Supports `data-testid`, `data-test`, `data-cy`, `data-qa`, `data-test-id`, and Angular `formControlName` |

## Healing Pipeline

AegisAI uses a layered cascade. Each layer is cheaper and safer than the next one, so the package avoids calling an LLM unless the local layers cannot solve the problem.

```text
Test Runner
  -> Framework Adapter
  -> L0 DOM Readiness
  -> L1 Locator Translation
  -> L2 Deterministic Scoring
  -> L3 Heuristic Structural Search
  -> L4 Live Browser JS Probe
  -> L5 LLM Agentic Fallback
  -> Security Officer
  -> Guardrails
  -> Retry / Optional Persistence
```

## Integration Modes

AegisAI supports universal auto-detection plus framework-specific adoption styles. This lets a team start safe and then reduce code changes as confidence grows.

| Mode | User Code Change | Best For | Tradeoff |
|---|---|---|---|
| Universal auto-detection | Usually one import plus one activation call | Teams using Selenium, Playwright, or both | Still requires a live `driver` or `page` object |
| Explicit listener | More code per protected locator | Regulated teams, debugging, first rollout | User must remember `before_find(...)` |
| Helper functions | One clean call per locator/action | Most teams, page objects, shared utilities | Requires replacing direct calls with helper calls |
| Auto-activation | Usually two lines per driver | Large legacy suites, fast adoption, fewer user mistakes | Opt-in driver patching must be understood and reversible |

Auto-activation patches only the supplied Selenium driver or sync Playwright page instance. It does not patch frameworks globally, and it can be disabled with `deactivate_aegis(target)` or `patch.restore()`.

## Layer Capabilities

| Layer | Purpose | Example It Can Fix | Typical Package Overhead |
|---|---|---|---|
| L0 DOM Readiness | Wait, scroll, retry, check whether the original locator appears. | Element renders slightly late. | About 1-2 seconds |
| L1 Locator Translation | Convert locator syntax and try equivalent forms. | XPath attribute selector to CSS selector, text contains variants. | Usually under 1 second |
| L2 Deterministic Engine | Score DOM elements by tag, attributes, text, and history. | `//input[@id='email-field']` -> `input[type="email"]` | Usually under 1 second |
| L3 Heuristic Search | Use fuzzy text, labels, nearby structure, and semantic hints. | Wrong placeholder or button text. | Usually under 1 second |
| L4 JS Browser Prober | Query the live browser directly using JavaScript. | React-rendered element exists in browser but not in stale snapshot. | Usually under 1 second |
| L5 LLM Fallback | Constrained browser-aware agentic reasoning over sanitized context. | Complex redesign where local rules cannot infer the locator. | Usually 3-10 seconds |

L0 has an intentional limitation: it cannot change application state. If a login modal is closed, L0 will not click a profile button to open it. That is by design. It prevents unsafe surprise interactions.

## Benchmarks From This Build

These results were observed on the local demo suite and public-repo validation workspace on May 8, 2026. Browser/network time is included for Selenium demo scripts, so the package overhead is much smaller than the end-to-end script duration.

| Check | Result |
|---|---|
| Unit regression suite | 90 tests passed |
| Python compile check | Passed |
| Public browser reliability suite | 9 tests passed |
| L0 Selenium demo | Failed safely because modal was closed; no LLM call |
| L1 Selenium demo | Passed, broken button text healed |
| L2 Selenium demo | Passed, broken email/password/button locators healed |
| L3 Selenium demo | Passed, heuristic email/password/button healing |
| L4 Selenium demo | Passed, live JS probe email/password/button healing |
| Auto-activation L0-L5 demo | L1-L4 healed; L0 and L5 failed safely where expected |
| All-layers Boltzmann demo | Passed |

Large public repo corpus result:

| Corpus | Result |
|---|---:|
| Public repo | `angular/components` |
| HTML templates scanned | 671 |
| Generated broken locator mutations | 1,500 |
| Successful heals | 1,101 |
| Success rate | 73.4% |
| False positives | 0 |
| Average SDK heal time | 0.4545 ms |
| p95 SDK heal time | 1.3473 ms |

The Angular corpus exposed real product improvements that were added to the package:

- Stable-token drift healing for suffix/prefix changes such as `scene-content-container-legacy`.
- Support for common QA attributes beyond `data-testid`: `data-test`, `data-cy`, `data-qa`, and `data-test-id`.
- Support for Angular `formControlName` as a stable locator anchor.
- Safer ambiguity behavior: repeated equivalent elements are still blocked instead of guessed.

Approximate demo script durations observed locally:

| Demo | End-to-End Duration | Notes |
|---|---:|---|
| `Login_L0_Test.py` | About 22 seconds | Includes browser launch, page load, expected wait, safe failure |
| `Login_L1_Test.py` | About 30 seconds | Includes browser launch and website interaction |
| `Login_L2_Test.py` | About 50 seconds | Three broken locators healed |
| `Login_L3_Test.py` | About 50 seconds | Three broken locators healed |
| `Login_L4_Test.py` | About 48 seconds | Three broken locators healed |
| `Login_AutoActivation_L0_L5_Test.py` | About 22 seconds | Auto-activation run: L1-L4 healed, L0 failed safely, L5 reported missing key |

In normal execution, a single failed locator that reaches only L0-L4 is usually handled in about 3-5 seconds. If L5 is enabled and needed, expect about 6-15 seconds total for that failed locator.

## Security Officer

AegisAI includes a local Security Officer layer. This is not a remote service. It runs inside the package and supervises healing decisions.

The Security Officer handles:

- Sensitive data redaction before LLM context is built.
- Risk scoring for locator changes.
- Runtime permission decisions.
- Persistence permission decisions.
- Audit-friendly local decision records.

Risk examples:

| Candidate Type | Risk | Runtime Heal | Auto Persistence |
|---|---|---|---|
| Text button rename | Low | Allowed | Allowed |
| Email field remap | Low | Allowed | Allowed |
| Password field remap | Medium | Allowed | Review required |
| Admin/delete/payment action | High | Policy controlled | Review required |
| Token/session/cookie/CSRF field | Critical | Blocked | Blocked |

Password locators can heal at runtime. Password values are not captured by the DOM parser, LLM payloads are sanitized, and persistence requires review.

Example sanitized payload concept:

```json
{
  "tag": "input",
  "attrs": {
    "type": "password",
    "name": "password"
  },
  "locator": "input[type=\"password\"]",
  "security": {
    "risk_level": "medium",
    "raw_values_included": false
  }
}
```

## L5: Optional Agentic Fallback

L5 is where AI comes into the picture, but only after L0-L4 fail.

L5 behaves like a constrained browser-aware healing agent:

- Reads nearby code intent from the failing script.
- Reads a filtered DOM candidate list.
- Uses sanitized context only.
- Requests strict JSON from the configured LLM.
- Validates the suggested locator against the DOM.
- Retries in the real browser.
- Persists only when guardrails and security policy allow it.

L5 does not receive raw cookies, session IDs, tokens, password values, or full unfiltered DOM by default.

If no key is configured, the package reports a professional reason:

```text
L0-L4 exhausted. L5 LLM fallback was not started because AEGIS_LLM_API_KEY is not configured for provider 'gemini'.
```

## Installation

Until AegisAI is published to PyPI, install it from the GitHub repository after it is pushed:

```powershell
pip install "aegisai[selenium,playwright] @ git+https://github.com/SriSuryaPoola/QA_Self_healing_package.git"
```

If you want optional L5 provider libraries too:

```powershell
pip install "aegisai[selenium,playwright,llm] @ git+https://github.com/SriSuryaPoola/QA_Self_healing_package.git"
```

Or clone the repository and install from the project root:

```powershell
git clone https://github.com/SriSuryaPoola/QA_Self_healing_package.git
cd QA_Self_healing_package
pip install ".[selenium,playwright]"
```

If you only need one browser framework:

```powershell
pip install ".[selenium]"
pip install ".[playwright]"
```

For package development, use editable mode:

```powershell
pip install -e ".[dev,llm]"
```

After AegisAI is published to PyPI, installation becomes:

```powershell
pip install "aegisai[selenium,playwright]"
```

For Playwright, install browser binaries after installing the Python dependency:

```powershell
python -m playwright install chromium
```

The `examples/` folder includes quickstarts for Selenium, Playwright sync, Playwright async, pytest, unittest/Page Object Model, Behave, Robot Framework, Security Officer policies, CI/CD usage, and notebook-style SDK exploration.

## Optional LLM Configuration

AegisAI does not ask for secrets during installation. That is intentional. Install-time prompts break CI/CD and are risky for enterprise environments.

If you plan to use L5 with hosted LLM providers, install the optional LLM dependencies.

From a cloned repository:

```powershell
pip install ".[llm]"
```

From GitHub:

```powershell
pip install "aegisai[llm] @ git+https://github.com/SriSuryaPoola/QA_Self_healing_package.git"
```

After PyPI publication:

```powershell
pip install "aegisai[llm]"
```

Configure L5 explicitly after installation:

```powershell
aegisai configure llm
```

The CLI asks:

```text
Enable L5 LLM fallback? [y/N]:
Provider:
Model:
API key (input hidden):
```

The key is stored outside the project repository in the user-level AegisAI config file. It is not printed in terminal output.

Useful commands:

```powershell
aegisai configure llm --status
aegisai configure llm --disable
aegisai configure llm --enable --provider openai --model gpt-4o-mini
```

Environment variables still work for CI/CD:

```text
AEGIS_LLM_ENABLED=true
AEGIS_LLM_PROVIDER=openai
AEGIS_LLM_API_KEY=...
AEGIS_LLM_MODEL=gpt-4o-mini
```

Supported providers:

| Provider | Notes |
|---|---|
| `openai` | OpenAI-compatible API |
| `gemini` | Google Gemini OpenAI-compatible endpoint |
| `grok` | xAI OpenAI-compatible endpoint |
| `claude` | Anthropic native API |
| `ollama` | Local model, no API key required |
| `custom` | Any OpenAI-compatible endpoint with `AEGIS_LLM_BASE_URL` |

## Selenium Usage

AegisAI does not require a framework rewrite. Pick the integration level that fits your team.

### Option A: Auto-Activation

This is the lowest-change path. Import the universal activator and call it after creating the driver. AegisAI detects Selenium automatically.

```python
from selenium import webdriver

from aegisai import activate_aegis

driver = webdriver.Chrome()
activate_aegis(driver, backup=True)

# Existing Selenium code can stay mostly unchanged.
email_input = driver.find_element("xpath", "//input[@id='email-field']")
email_input.send_keys("qa@example.com")
```

If `driver.find_element(...)` fails, AegisAI records the failing locator and runs the healing cascade. If healing succeeds, the healed element is returned to the same line of user code.

In simple scripts, AegisAI can also find a local variable named `driver` automatically:

```python
driver = webdriver.Chrome()
activate_aegis()
```

For page objects, fixtures, or files with multiple browser objects, pass the target explicitly.

You can restore raw Selenium behavior:

```python
from aegisai import activate_aegis, deactivate_aegis

patch = activate_aegis(driver)

# Later:
patch.restore()

# Or:
deactivate_aegis(driver)
```

Auto-activation reduces user-side code changes and lowers integration mistakes, especially in large legacy suites. Because it changes the supplied driver instance, it is intentionally opt-in and reversible.

### Option B: Helper Functions

Helper mode avoids monkey patching while still keeping test code compact.

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from aegisai.selenium import heal_find, heal_send_keys, heal_click

driver = webdriver.Chrome()
wait = WebDriverWait(driver, 10)
driver.get("https://example.com/login")

email_input = heal_find(
    driver,
    wait,
    By.XPATH,
    "//input[@id='email-field']",
    EC.presence_of_element_located,
    script_path=__file__,
)
email_input.send_keys("qa@example.com")

heal_send_keys(
    driver,
    wait,
    By.XPATH,
    "//input[@id='pass-field']",
    "secret-password",
    EC.presence_of_element_located,
    script_path=__file__,
)

heal_click(
    driver,
    wait,
    By.XPATH,
    "//button[normalize-space()='Login here']",
    EC.element_to_be_clickable,
    script_path=__file__,
)
```

This is the recommended default for most page-object models because the healing boundary is clear and there is less boilerplate than the raw listener.

### Option C: Explicit Listener

This is the safest and most transparent integration. It is useful when teams want exact control over where healing is allowed.

```python
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from aegisai.interceptor.selenium_listener import AegisSeleniumListener

driver = webdriver.Chrome()
wait = WebDriverWait(driver, 10)
listener = AegisSeleniumListener(script_path=__file__, backup=True)

driver.get("https://example.com/login")

try:
    locator = "//input[@id='email-field']"
    listener.before_find(by="XPATH", value=locator, driver=driver)
    email_input = wait.until(EC.presence_of_element_located((By.XPATH, locator)))
except Exception as exc:
    email_input = listener.autonomous_heal(
        exc,
        driver=driver,
        wait=wait,
        original_condition=EC.presence_of_element_located,
    )

email_input.send_keys("qa@example.com")
```

Explicit click example:

```python
try:
    locator = "//button[normalize-space()='Login here']"
    listener.before_find(by="XPATH", value=locator, driver=driver)
    button = wait.until(EC.element_to_be_clickable((By.XPATH, locator)))
except Exception as exc:
    button = listener.autonomous_heal(
        exc,
        driver=driver,
        wait=wait,
        original_condition=EC.element_to_be_clickable,
    )

button.click()
```

If you run `aegisai configure llm` and enable L5, all Selenium integration modes read that preference automatically. You can still override it in code:

```python
listener = AegisSeleniumListener(enable_llm=False)
listener = AegisSeleniumListener(enable_llm=True)

activate_aegis(driver, enable_llm=False)
activate_aegis(driver, enable_llm=True)
```

## Playwright Usage

Playwright now has the same adoption philosophy as Selenium: keep your framework, opt in locally, and let AegisAI heal failed selectors without moving execution into another platform.

### Option A: Auto-Activation

Auto-activation patches only the supplied sync Playwright `page` instance. It wraps `page.locator(...)` so failed common actions such as `.fill()`, `.click()`, `.is_visible()`, `.input_value()`, and `.text_content()` retry through the L0-L4 healing path.

```python
from playwright.sync_api import sync_playwright

from aegisai import activate_aegis

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()

    activate_aegis(page)

    page.goto("https://example.com/login")

    # Existing Playwright style can stay mostly unchanged.
    page.locator("xpath=//input[@id='email-field']").fill("qa@example.com")
    page.locator("xpath=//input[@id='pass-field']").fill("secret")
    page.locator("xpath=//button[@data-testid='login-submit']").click()

    browser.close()
```

AegisAI can also find a local variable named `page` automatically in simple scripts:

```python
page = browser.new_page()
activate_aegis()
```

You can restore raw Playwright behavior:

```python
from aegisai import activate_aegis, deactivate_aegis

patch = activate_aegis(page)

# Later:
patch.restore()

# Or:
deactivate_aegis(page)
```

### Option B: Helper Functions

Helper mode avoids patching the page object while still protecting individual actions.

```python
from playwright.sync_api import sync_playwright

from aegisai.playwright import heal_click, heal_fill

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://example.com/login")

    heal_fill(page, "xpath=//input[@id='email-field']", "qa@example.com")
    heal_fill(page, "xpath=//input[@id='pass-field']", "secret")
    heal_click(page, "xpath=//button[@data-testid='login-submit']")

    browser.close()
```

### Option C: Manual SDK

For maximum control, call the core SDK with `page.content()` and decide how to apply the healed selector yourself.

```python
from aegisai import AegisAI

app = AegisAI()
result = app.heal_locator(
    failing_locator="#email-field",
    dom=page.content(),
    expected_role="textbox",
)

if not result.locator:
    raise RuntimeError(result.guardrail.reason)

page.locator(result.locator).fill("qa@example.com")
```

You can also record Playwright failure context explicitly:

```python
from aegisai.interceptor.playwright_listener import AegisPlaywrightHooks

hooks = AegisPlaywrightHooks()
hooks.install(page)

hooks.wrap_action(
    "fill",
    "#email-field",
    lambda: page.locator("#email-field").fill("qa@example.com"),
)
```

Playwright support is still intentionally honest: common sync and async locator actions now auto-heal through local deterministic paths, while Playwright L5/LLM fallback and full automatic traversal for complex iframe/Shadow DOM cases remain future hardening areas.

### Async Playwright

Async Playwright users can use the async helper module:

```python
from aegisai.playwright_async import activate_aegis_async

activate_aegis_async(page)

await page.locator("xpath=//input[@id='email-field']").fill("qa@example.com")
await page.locator("xpath=//button[@data-id='submit-btn']").click()
```

Or use explicit helpers:

```python
from aegisai.playwright_async import async_heal_click, async_heal_fill

await async_heal_fill(page, "xpath=//input[@id='email-field']", "qa@example.com")
await async_heal_click(page, "xpath=//button[@data-id='submit-btn']")
```

### Dry Run / Audit Mode

Dry-run mode analyzes a broken locator without clicking, typing, patching source, or changing browser state.

```python
from aegisai.selenium import dry_run_find

result = dry_run_find(driver, "xpath", "//input[@id='email-field']")
print(result.to_dict())
```

For Playwright:

```python
from aegisai.playwright import dry_run_selector

result = dry_run_selector(page, "xpath=//input[@id='email-field']")
```

### Reports, Cache, and Suggestions

AegisAI keeps package-local runtime artifacts under `.aegisai/` by default. This folder is intended for local debugging or CI artifacts and should not contain secrets.

| Artifact | Purpose |
|---|---|
| `.aegisai/cache/locator-cache.json` | Reuses successful heals for the same DOM fingerprint so repeated local heals are faster. |
| `.aegisai/audit/*.json` | Security Officer decisions with sensitive values redacted. |
| `.aegisai/HEAL_SUGGESTIONS.json` | Review-required source-fix suggestions, including optional unified diffs. |
| `.aegisai/reports/latest.json` | Optional session-level healing report for CI/debugging. |
| `.aegisai/artifacts/*` | Optional redacted DOM debug artifacts and opt-in screenshots. |

Disable cache for a single SDK call:

```python
result = app.heal_locator("#old", page.content(), use_cache=False)
```

Or disable cache for a process:

```powershell
$env:AEGISAI_CACHE_DISABLED="1"
```

Use a team-shared cache file without any platform service:

```powershell
$env:AEGISAI_CACHE_PATH=".aegisai/team-locator-cache.json"
```

Capture redacted debug artifacts for a failed case:

```python
from aegisai import capture_debug_artifacts

paths = capture_debug_artifacts(driver, include_screenshot=False)
```

Detect DOM drift before a failure happens:

```python
from aegisai import detect_dom_drift

drift = detect_dom_drift(previous_dom, current_dom)
print(drift.added_locators, drift.removed_locators)
```

### Security Policy Files

Teams can tune risk behavior without changing test code.

```toml
[security]
name = "enterprise-balanced"
allow_runtime_for_medium = true
allow_runtime_for_high = false
auto_persist_low = true
min_confidence_medium = 0.88
audit_enabled = true
```

Use the policy from code:

```python
from aegisai import AegisAI, load_security_policy

policy = load_security_policy("examples/security_policy.toml")
app = AegisAI(security_policy=policy)
```

## CLI Smoke Checks

Run deterministic healing against an HTML fixture:

```powershell
python -m aegisai heal --locator "#login" --dom-file examples/login.html --expected-role button
```

Write a JSON report while healing a fixture:

```powershell
python -m aegisai heal --locator "#login" --dom-file examples/login.html --expected-role button --report-file .aegisai/reports/latest.json
```

Run audit-only dry-run mode:

```powershell
python -m aegisai audit --locator "#login" --dom-file examples/login.html --expected-role button
```

Summarize a report:

```powershell
python -m aegisai report --input .aegisai/reports/latest.json
```

Inspect or clear the local locator cache:

```powershell
python -m aegisai cache
python -m aegisai cache --clear
```

Check state-poisoning status:

```powershell
python -m aegisai state
```

Check LLM config without exposing secrets:

```powershell
python -m aegisai configure llm --status
```

## Real-World Reliability Checks

AegisAI includes an opt-in real-world reliability suite under `tests/reliability`. These tests launch real browsers and validate the package against public QA/demo applications, so they are skipped during normal `pytest` runs unless explicitly enabled.

Run the real-world suite:

```powershell
$env:AEGISAI_RUN_PUBLIC_REPO_TESTS="1"
$env:AEGISAI_HEADLESS="1"
python -m pytest tests/reliability -q -s
```

Current public targets:

| Public repo | Runtime target | Coverage |
|---|---|---|
| `saucelabs/the-internet` | `https://the-internet.herokuapp.com` | Selenium login healing, Selenium iframe discovery, Selenium L4 Shadow DOM probing, Playwright auto-activation, Playwright manual SDK |
| SauceDemo public app | `https://www.saucedemo.com` | Selenium login-form locator drift against a second public UI |
| `robotframework/WebDemo` | Local `file:///` clone | Selenium and Playwright login-form healing against a classic SeleniumLibrary demo app |
| `angular/components` | Local HTML corpus | 1,500 generated locator mutations across 671 real Angular templates |

Latest verified public-suite result:

```text
9 passed
```

## Benchmark Methodology

The benchmark numbers in this README are intentionally practical rather than synthetic. They include real browser startup, page load, waiting, broken locator failure, healing, retry, and teardown time. For package-level speed checks, use the unit suite and the local public reliability suite together:

```powershell
python -m pytest tests/test_core.py -q
$env:AEGISAI_RUN_PUBLIC_REPO_TESTS="1"; python -m pytest tests/reliability -q
```

Run the large public HTML corpus evaluator:

```powershell
python "<sample-root>\public repos\scripts\evaluate_aegisai_on_html_corpus.py" `
  --repo "<sample-root>\public repos\repos\angular-components" `
  --package-root "." `
  --out-dir "<sample-root>\public repos\results" `
  --max-cases 1500
```

When comparing layers, remember that Selenium demo scripts intentionally include browser/network overhead. The local L0-L4 healing code itself is much faster than the full script duration.

## Architecture

```text
Existing Test Runner
  -> Selenium / Playwright Adapter
  -> Failure Detection
  -> Local Cache
  -> L0-L4 Deterministic Healing
  -> Optional L5 LLM Fallback
  -> Security Officer
  -> Guardrails
  -> Runtime Retry
  -> Report / Audit / Optional Suggestion Artifact
```

The important architectural decision is that AegisAI is a package, not a platform. Reports, cache, policies, and suggestions are local files that teams can commit, ignore, upload as CI artifacts, or replace with their own workflow.

## Known Limitations

- L5 requires explicit provider configuration and is skipped professionally when no valid key is available.
- Selenium has the deepest live-browser cascade and source persistence path today.
- Playwright supports common sync and async locator actions, but full L5 parity is still planned.
- Simple Selenium iframe discovery and L4 Shadow DOM probing are supported; complex nested frame/web-component flows still need more hardening.
- Repeated equivalent elements are intentionally blocked when AegisAI cannot choose safely. Future context-aware scoring should use nearby labels, section headings, table headers, form groups, and component ancestry to reduce these safe blocks.
- Generic `input[type="text"]` locators are weak signals in large apps because many text inputs can look equivalent.
- AegisAI fixes broken locators; it does not guess business intent when a test intentionally uses the wrong credentials or wrong expected behavior.

## FAQ

**Do I need to rewrite my framework?** No. AegisAI is designed to activate beside Selenium, Playwright, pytest, unittest, Behave, or Robot Framework.

**Will it send passwords to an LLM?** No. Password values are not captured by the DOM parser, and LLM context is sanitized by the Security Officer.

**Can I use it without LLM keys?** Yes. L0-L4 run locally without an LLM key.

**Can I stop it from changing source files?** Yes. Use helper/SDK/dry-run modes, pass `backup=True`, or use Security Officer policy controls. Medium/high-risk persistence is review-first by design.

## Troubleshooting

| Symptom | What To Check |
|---|---|
| `AegisAI could not detect Selenium or Playwright` | Call `activate_aegis(driver)` or `activate_aegis(page)` after the browser object is created. |
| L5 says no key is configured | Run `python -m aegisai configure llm --status` or disable L5 until a valid key is available. |
| A password field heals but source is not patched | This is expected. Password remaps are medium risk and require review before persistence. |
| Cache seems stale | Clear it with `python -m aegisai cache --clear` or set `AEGISAI_CACHE_DISABLED=1`. |
| A high-risk click is blocked | Review or loosen the local Security Officer policy only if the flow is safe for your environment. |
| Complex iframe/Shadow DOM case fails | Use explicit helper mode first; full automatic traversal for deeply nested cases is still a hardening area. |

## Design Principles

- Deterministic before AI.
- Framework integration before framework replacement.
- Local package before platform dependency.
- Security governance before autonomous persistence.
- Fail safe over false positives.
- Explicit configuration over hidden install-time prompts.
- CI/CD compatibility by default.

## Current Status

AegisAI is an alpha package with a working Selenium L0-L5 cascade, Selenium helper functions, opt-in Selenium auto-activation, sync and async Playwright helpers, opt-in sync/async Playwright auto-activation for common locator actions, local Security Officer governance, optional LLM configuration, deterministic SDK healing, explicit Playwright hooks, dry-run/audit mode, local cache, JSON reports, review-required source suggestions, common QA locator anchor support, and large public-repo corpus validation.

The most mature path today is still Selenium because it has the deepest live-browser cascade, simple iframe discovery, L4 Shadow DOM probing, and script persistence support. Playwright is now usable for common sync and async `page.locator(...).fill()/click()` workflows. Playwright L5 and deeply nested iframe/web-component traversal should still be treated as future hardening areas.

## Public API Stability

The intended stable imports are:

- `from aegisai import AegisAI, activate_aegis, deactivate_aegis`
- `from aegisai.selenium import heal_find, heal_click, heal_send_keys, dry_run_find`
- `from aegisai.playwright import heal_fill, heal_click, heal_selector, dry_run_selector`
- `from aegisai.playwright_async import activate_aegis_async, async_heal_fill, async_heal_click`
- `from aegisai.security import SecurityPolicy, load_security_policy`

Internal modules under `aegisai.engine`, `aegisai.guardrails`, and `aegisai.persistence` may still evolve while the package is alpha.

