"""Playwright async quickstart."""

import asyncio

from playwright.async_api import async_playwright

from aegisai.playwright_async import activate_aegis_async


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        activate_aegis_async(page)

        await page.goto("https://the-internet.herokuapp.com/login")
        await page.locator("xpath=//input[@id='email-field']").fill("tomsmith")
        await page.locator("xpath=//input[@id='pass-field']").fill("SuperSecretPassword!")
        await page.locator("xpath=//button[@data-id='submit-btn']").click()

        await browser.close()


asyncio.run(main())
