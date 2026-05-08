"""Playwright sync quickstart: activate once after creating the page."""

from playwright.sync_api import sync_playwright

from aegisai import activate_aegis

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    activate_aegis(page)

    page.goto("https://the-internet.herokuapp.com/login")

    # Existing Playwright locator style stays the same.
    page.locator("xpath=//input[@id='email-field']").fill("tomsmith")
    page.locator("xpath=//input[@id='pass-field']").fill("SuperSecretPassword!")
    page.locator("xpath=//button[@data-id='submit-btn']").click()

    browser.close()
