# Real-World Reliability Findings

Last verified: May 8, 2026

## Public Repos Cloned Locally

| Repo | Local folder | Commit sampled |
|---|---|---|
| `https://github.com/saucelabs/the-internet` | `public repos/repos/the-internet` | `d638883` |
| `https://github.com/saucelabs/sample-app-web` | `public repos/repos/sample-app-web` | `89b11dc` |

The cloned repo contents are ignored by Git. They are local replicas for inspection and future local app serving.

## Real Browser Suite

Command:

```powershell
$env:AEGISAI_RUN_PUBLIC_REPO_TESTS="1"
$env:AEGISAI_HEADLESS="1"
python -m pytest tests/reliability -q -s
```

Result:

```text
5 passed in 78.06s
```

## Confirmed Capabilities

### Selenium Auto-Activation On Public App

Target: `https://the-internet.herokuapp.com/login`

| Broken locator | Healed locator | Layer | Confidence |
|---|---|---|---|
| `//input[@id='user-name-field']` | `#username` | `L2:deterministic` | `0.8333` |
| `//input[@id='pass-field']` | `#password` | `L2:deterministic` | `0.8333` |
| `//button[@data-testid='login-submit']` | `button[type='submit']` | `L1:submit button` | `0.95` |

This proves the Selenium package path is not only working on the local Boltzmann demo. It can repair broken locators on an external public app tied to a public repository.

### Playwright Manual SDK Support

Target: `https://the-internet.herokuapp.com/login`

The Playwright test uses `page.content()` with `AegisAI().heal_locator(...)`, then applies the healed locator through Playwright. This passed.

### Playwright Failure Context Capture

The Playwright hook test confirms `AegisPlaywrightHooks.wrap_action(...)` records the failed action and locator. This is useful today for reporting and diagnostics.

## Confirmed Shortcomings

### Selenium iframe Auto-Switching

Target: `https://the-internet.herokuapp.com/iframe`

Current result: AegisAI correctly fails safe when asked to find `#tinymce` from the top document.

Reason: the target element is inside an iframe. The current L0-L4 cascade does not automatically detect and switch iframe context.

Needed improvement: add iframe discovery and context switching before L5.

### Selenium Shadow DOM Piercing

Target: `https://the-internet.herokuapp.com/shadowdom`

Current result: AegisAI correctly fails safe when asked to find `my-paragraph p`.

Reason: the target `p` exists inside an open shadow root. The current L4 JS probe does not pierce shadow roots.

Needed improvement: extend L4 to recursively inspect open shadow roots.

### Playwright Auto-Healing Parity

Current result: Playwright manual SDK healing works, and hooks capture failures, but Playwright actions are not auto-healed like Selenium `activate_aegis(driver)`.

Needed improvement: add `activate_aegis_playwright(page)` or helper wrappers for `.click()`, `.fill()`, and `.is_visible()`.

## Practical Release Interpretation

AegisAI is stronger than a demo-only package now because it has a repeatable real-browser public-app suite. The honest status is:

- Selenium auto-healing is usable for normal DOM locators.
- Security and fail-safe behavior are preserved for unsupported structures.
- iframe, Shadow DOM, and Playwright auto-healing are the next meaningful reliability gaps.

