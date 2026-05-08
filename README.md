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
| Selenium runtime healing | Available |
| Selenium helper functions | Available through `heal_find`, `heal_click`, `heal_send_keys` |
| Selenium opt-in auto-activation | Available through `activate_aegis(driver, ...)` |
| Selenium safe script persistence | Available when policy allows |
| Playwright core SDK healing | Available manually via `page.content()` |
| Playwright helper functions | Available through `heal_fill`, `heal_click`, `heal_selector` |
| Playwright opt-in auto-activation | Available for sync `page.locator(...).fill()/click()` style actions |
| Playwright page hooks | Available for explicit failure/action context capture |
| Playwright full L0-L4 automatic listener | Available for common sync locator actions |
| Playwright L5 LLM fallback | Planned; use explicit SDK/LLM path for now |
| LLM provider setup CLI | Available through `aegisai configure llm` |
| Security Officer governance | Available |

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

AegisAI now supports three Selenium adoption styles. This lets a team start safe and then reduce code changes as confidence grows.

| Mode | User Code Change | Best For | Tradeoff |
|---|---|---|---|
| Explicit listener | More code per protected locator | Regulated teams, debugging, first rollout | User must remember `before_find(...)` |
| Helper functions | One clean call per locator/action | Most teams, page objects, shared utilities | Requires replacing direct calls with helper calls |
| Auto-activation | Usually two lines per driver | Large legacy suites, fast adoption, fewer user mistakes | Opt-in driver patching must be understood and reversible |

Auto-activation patches only the supplied driver instance. It does not patch Selenium globally, and it can be disabled with `deactivate_aegis(driver)` or `patch.restore()`.

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

These results were observed on the local demo suite in this repository on May 7, 2026. Browser/network time is included for Selenium demo scripts, so the package overhead is much smaller than the end-to-end script duration.

| Check | Result |
|---|---|
| Unit regression suite | 33 tests passed |
| Python compile check | Passed |
| L0 Selenium demo | Failed safely because modal was closed; no LLM call |
| L1 Selenium demo | Passed, broken button text healed |
| L2 Selenium demo | Passed, broken email/password/button locators healed |
| L3 Selenium demo | Passed, heuristic email/password/button healing |
| L4 Selenium demo | Passed, live JS probe email/password/button healing |

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

This is the lowest-change path. Add two lines after creating the driver:

```python
from selenium import webdriver

from aegisai.selenium import activate_aegis

driver = webdriver.Chrome()
activate_aegis(driver, script_path=__file__, backup=True)

# Existing Selenium code can stay mostly unchanged.
email_input = driver.find_element("xpath", "//input[@id='email-field']")
email_input.send_keys("qa@example.com")
```

If `driver.find_element(...)` fails, AegisAI records the failing locator and runs the healing cascade. If healing succeeds, the healed element is returned to the same line of user code.

You can restore raw Selenium behavior:

```python
from aegisai.selenium import activate_aegis, deactivate_aegis

patch = activate_aegis(driver, script_path=__file__)

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

from aegisai.playwright import activate_aegis

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

You can restore raw Playwright behavior:

```python
from aegisai.playwright import activate_aegis, deactivate_aegis

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

Playwright support is still intentionally honest: common sync locator actions now auto-heal through L0-L4, while Playwright L5/LLM fallback, async Playwright patching, iframe auto-switching, and Shadow DOM piercing remain future hardening areas.

## CLI Smoke Checks

Run deterministic healing against an HTML fixture:

```powershell
python -m aegisai heal --locator "#login" --dom-file examples/login.html --expected-role button
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
| `saucelabs/the-internet` | `https://the-internet.herokuapp.com` | Selenium login healing, Playwright auto-activation, Playwright manual SDK, iframe shortcoming, Shadow DOM shortcoming |

Latest verified public-suite result:

```text
6 passed
```

## Design Principles

- Deterministic before AI.
- Framework integration before framework replacement.
- Local package before platform dependency.
- Security governance before autonomous persistence.
- Fail safe over false positives.
- Explicit configuration over hidden install-time prompts.
- CI/CD compatibility by default.

## Current Status

AegisAI is an alpha package with a working Selenium L0-L5 cascade, Selenium helper functions, opt-in Selenium auto-activation, sync Playwright helper functions, opt-in sync Playwright auto-activation for common locator actions, local Security Officer governance, optional LLM configuration, deterministic SDK healing, and explicit Playwright hooks.

The most mature path today is still Selenium because it has the deepest live-browser cascade and script persistence support. Playwright is now usable for common sync `page.locator(...).fill()/click()` workflows, while Playwright L5, async Playwright, iframe auto-switching, and Shadow DOM piercing should be treated as future work.

