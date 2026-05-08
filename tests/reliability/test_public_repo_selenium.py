from __future__ import annotations

import os
from pathlib import Path

import pytest

THE_INTERNET_BASE_URL = os.getenv("AEGISAI_THE_INTERNET_URL", "https://the-internet.herokuapp.com")
SAUCEDEMO_BASE_URL = os.getenv("AEGISAI_SAUCEDEMO_URL", "https://www.saucedemo.com")
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
def driver():
    selenium = pytest.importorskip("selenium")
    assert selenium
    from selenium import webdriver

    browser_name = os.getenv("AEGISAI_BROWSER", "chrome").lower()
    if browser_name == "edge":
        options = webdriver.EdgeOptions()
        browser_factory = webdriver.Edge
    elif browser_name == "firefox":
        options = webdriver.FirefoxOptions()
        browser_factory = webdriver.Firefox
    else:
        options = webdriver.ChromeOptions()
        browser_factory = webdriver.Chrome

    if os.getenv("AEGISAI_HEADLESS", "1") != "0":
        if browser_name == "firefox":
            options.add_argument("--headless")
        else:
            options.add_argument("--headless=new")
    if browser_name != "firefox":
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

    browser = browser_factory(options=options)
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


def test_selenium_heals_saucedemo_login_form(driver):
    """Second public app: SauceDemo login form locator drift."""

    from selenium.webdriver.common.by import By

    driver.get(SAUCEDEMO_BASE_URL)
    patch = _activate(driver)

    username = driver.find_element(By.XPATH, "//input[@id='username-field']")
    username_outcome = _assert_healed(patch, "user-name")
    username.send_keys("standard_user")

    password = driver.find_element(By.XPATH, "//input[@id='pass-field']")
    password_outcome = _assert_healed(patch, "password")
    password.send_keys("secret_sauce")

    button = driver.find_element(By.XPATH, "//button[@id='login-submit']")
    button_outcome = _assert_healed(patch, "submit")
    button.click()

    assert username_outcome.success
    assert password_outcome.success
    assert button_outcome.success
    assert "inventory" in driver.current_url


def test_selenium_heals_robotframework_webdemo_login_form(driver):
    """Local clone of robotframework/WebDemo: classic SeleniumLibrary login page."""

    from selenium.webdriver.common.by import By

    if not WEBDOMO_INDEX.exists():
        pytest.skip(f"robotframework/WebDemo clone not found at {WEBDOMO_INDEX}")

    driver.get(WEBDOMO_INDEX.as_uri())
    patch = _activate(driver)

    username = driver.find_element(By.XPATH, "//input[@id='user-name-field']")
    username_outcome = _assert_healed(patch, "username_field")
    username.send_keys("demo")

    password = driver.find_element(By.XPATH, "//input[@id='pass-field']")
    password_outcome = _assert_healed(patch, "password_field")
    password.send_keys("mode")

    button = driver.find_element(By.XPATH, "//button[@id='login-submit']")
    button_outcome = _assert_healed(patch, "submit")
    button.click()

    assert username_outcome.success
    assert password_outcome.success
    assert button_outcome.success
    assert "welcome.html" in driver.current_url


def test_selenium_heals_element_inside_iframe(driver):
    """Real public app: Selenium healing can discover simple iframe elements."""

    from selenium.webdriver.common.by import By

    driver.get(f"{THE_INTERNET_BASE_URL}/iframe")
    patch = _activate(driver)

    editor = driver.find_element(By.CSS_SELECTOR, "#tinymce")
    outcome = _assert_healed(patch, "tinymce")

    assert outcome.layer_used in {0, 4}
    assert editor.is_displayed()


def test_selenium_l4_probes_shadow_dom(driver):
    """Real public app: L4 can probe visible elements inside simple shadow roots."""

    from selenium.webdriver.common.by import By

    driver.get(f"{THE_INTERNET_BASE_URL}/shadowdom")
    patch = _activate(driver)

    paragraph = driver.find_element(By.CSS_SELECTOR, "my-paragraph p")
    outcome = _assert_healed(patch)

    assert outcome.layer_used == 4
    assert paragraph.is_displayed()
