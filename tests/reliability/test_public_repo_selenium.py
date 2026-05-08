from __future__ import annotations

import os

import pytest

THE_INTERNET_BASE_URL = os.getenv("AEGISAI_THE_INTERNET_URL", "https://the-internet.herokuapp.com")


@pytest.fixture()
def driver():
    selenium = pytest.importorskip("selenium")
    assert selenium
    from selenium import webdriver

    options = webdriver.ChromeOptions()
    if os.getenv("AEGISAI_HEADLESS", "1") != "0":
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    browser = webdriver.Chrome(options=options)
    browser.set_page_load_timeout(float(os.getenv("AEGISAI_PAGE_LOAD_TIMEOUT", "30")))
    try:
        yield browser
    finally:
        browser.quit()


def _activate(driver):
    from aegisai.security import SecurityPolicy
    from aegisai.selenium import activate_aegis

    return activate_aegis(
        driver,
        backup=False,
        enable_llm=False,
        security_policy=SecurityPolicy(auto_persist_low=False),
    )


def _assert_healed(patch, expected_fragment: str | None = None):
    outcome = patch.listener.last_outcome
    assert outcome is not None, "Expected AegisAI to record a healing outcome."
    assert outcome.success, outcome.reason
    assert outcome.healed_locator
    if expected_fragment:
        assert expected_fragment in outcome.healed_locator
    return outcome


def test_selenium_heals_public_login_form_locators(driver):
    """Real public app: Sauce Labs the-internet login form.

    This validates normal Selenium auto-activation against a public repository
    app, not our local demo page.
    """

    from selenium.webdriver.common.by import By

    driver.get(f"{THE_INTERNET_BASE_URL}/login")
    patch = _activate(driver)

    username = driver.find_element(By.XPATH, "//input[@id='user-name-field']")
    username_outcome = _assert_healed(patch, "username")
    username.send_keys("tomsmith")

    password = driver.find_element(By.XPATH, "//input[@id='pass-field']")
    password_outcome = _assert_healed(patch, "password")
    password.send_keys("SuperSecretPassword!")

    button = driver.find_element(By.XPATH, "//button[@data-testid='login-submit']")
    button_outcome = _assert_healed(patch)

    assert username_outcome.layer_used in {2, 3, 4}
    assert password_outcome.layer_used in {2, 3, 4}
    assert button_outcome.layer_used in {1, 2, 3, 4}
    assert button.is_displayed()


def test_selenium_reports_iframe_shortcoming(driver):
    """Known gap: AegisAI does not yet switch iframe context automatically."""

    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.common.by import By

    driver.get(f"{THE_INTERNET_BASE_URL}/iframe")
    patch = _activate(driver)

    with pytest.raises(NoSuchElementException):
        driver.find_element(By.CSS_SELECTOR, "#tinymce")

    outcome = patch.listener.last_outcome
    assert outcome is not None
    assert not outcome.success
    assert "L0-L4 exhausted" in outcome.reason


def test_selenium_reports_shadow_dom_shortcoming(driver):
    """Known gap: L4 does not yet pierce shadow roots."""

    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.common.by import By

    driver.get(f"{THE_INTERNET_BASE_URL}/shadowdom")
    patch = _activate(driver)

    with pytest.raises(NoSuchElementException):
        driver.find_element(By.CSS_SELECTOR, "my-paragraph p")

    outcome = patch.listener.last_outcome
    assert outcome is not None
    assert not outcome.success
    assert "L0-L4 exhausted" in outcome.reason
