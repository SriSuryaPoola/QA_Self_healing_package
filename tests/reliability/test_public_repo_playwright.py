from __future__ import annotations

import os

import pytest

THE_INTERNET_BASE_URL = os.getenv("AEGISAI_THE_INTERNET_URL", "https://the-internet.herokuapp.com")


@pytest.fixture()
def page():
    playwright_module = pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    headless = os.getenv("AEGISAI_HEADLESS", "1") != "0"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
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


def test_playwright_hooks_capture_failure_but_do_not_auto_heal(page):
    """Known gap: Playwright hooks capture context but do not auto-patch locator actions yet."""

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

