from __future__ import annotations

import os
from pathlib import Path

import pytest

THE_INTERNET_BASE_URL = os.getenv("AEGISAI_THE_INTERNET_URL", "https://the-internet.herokuapp.com")
WEBDOMO_INDEX = Path(
    os.getenv(
        "AEGISAI_WEBDOMO_INDEX",
        Path(__file__).resolve().parents[4]
        / "public repos"
        / "repos"
        / "robotframework-webdemo"
        / "demoapp"
        / "html"
        / "index.html",
    )
)


@pytest.fixture()
def page():
    playwright_module = pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    headless = os.getenv("AEGISAI_HEADLESS", "1") != "0"
    browser_name = os.getenv("AEGISAI_BROWSER", "chromium").lower()
    with sync_playwright() as playwright:
        if browser_name == "chrome":
            browser_name = "chromium"
        browser_type = getattr(playwright, browser_name, None)
        if browser_type is None:
            pytest.skip(f"Unsupported Playwright browser: {browser_name}")
        browser = browser_type.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()

    assert playwright_module


def test_playwright_manual_sdk_heals_public_login_dom(page):
    """Current Playwright capability: explicit SDK healing from page HTML."""

    from aegisai import AegisAI

    page.goto(f"{THE_INTERNET_BASE_URL}/login")
    result = AegisAI().heal_locator("//input[@id='pass-field']", page.content())

    assert result.candidate is not None
    assert result.locator is not None
    assert "password" in result.locator

    page.locator(result.locator).fill("SuperSecretPassword!")
    assert page.locator(result.locator).input_value() == "SuperSecretPassword!"


def test_playwright_auto_activation_heals_public_login_form(page):
    """Playwright auto-activation should heal failed fill/click actions."""

    from aegisai.playwright import activate_aegis

    page.goto(f"{THE_INTERNET_BASE_URL}/login")
    patch = activate_aegis(page)

    page.locator("xpath=//input[@id='user-name-field']").fill("tomsmith", timeout=1000)
    username_outcome = patch.last_outcome
    assert username_outcome is not None
    assert username_outcome.success
    assert username_outcome.layer_used == 2
    assert username_outcome.healed_selector == "#username"

    page.locator("xpath=//input[@id='pass-field']").fill("SuperSecretPassword!", timeout=1000)
    password_outcome = patch.last_outcome
    assert password_outcome is not None
    assert password_outcome.success
    assert password_outcome.layer_used == 2
    assert password_outcome.healed_selector == "#password"

    page.locator("xpath=//button[@data-testid='login-submit']").click(timeout=1000)
    button_outcome = patch.last_outcome
    assert button_outcome is not None
    assert button_outcome.success
    assert button_outcome.layer_used == 1
    assert button_outcome.healed_selector == "button[type='submit']"
    assert "/secure" in page.url


def test_playwright_auto_activation_heals_robotframework_webdemo_login_form(page):
    """Local clone of robotframework/WebDemo through the sync Playwright adapter."""

    from aegisai.playwright import activate_aegis

    if not WEBDOMO_INDEX.exists():
        pytest.skip(f"robotframework/WebDemo clone not found at {WEBDOMO_INDEX}")

    page.goto(WEBDOMO_INDEX.as_uri())
    patch = activate_aegis(page)

    page.locator("xpath=//input[@id='user-name-field']").fill("demo", timeout=1000)
    username_outcome = patch.last_outcome
    assert username_outcome is not None
    assert username_outcome.success
    assert username_outcome.healed_selector == "#username_field"

    page.locator("xpath=//input[@id='pass-field']").fill("mode", timeout=1000)
    password_outcome = patch.last_outcome
    assert password_outcome is not None
    assert password_outcome.success
    assert password_outcome.healed_selector == "#password_field"

    page.locator("xpath=//button[@id='login-submit']").click(timeout=1000)
    button_outcome = patch.last_outcome
    assert button_outcome is not None
    assert button_outcome.success
    assert button_outcome.healed_selector == "input[type='submit']"
    assert "welcome.html" in page.url


def test_playwright_hooks_capture_failure_context_for_diagnostics(page):
    """Explicit Playwright hooks still capture action/failure context."""

    from aegisai.interceptor.playwright_listener import AegisPlaywrightHooks
    from playwright.sync_api import Error as PlaywrightError

    page.goto(f"{THE_INTERNET_BASE_URL}/login")
    hooks = AegisPlaywrightHooks()
    hooks.install(page)

    with pytest.raises(PlaywrightError):
        hooks.wrap_action(
            "fill",
            "//input[@id='user-name-field']",
            lambda: page.locator("xpath=//input[@id='user-name-field']").fill("tomsmith", timeout=1000),
        )

    assert hooks.last_failure is not None
    assert hooks.last_failure.locator == "//input[@id='user-name-field']"
    assert hooks.last_actions[-1]["action"] == "fill"
