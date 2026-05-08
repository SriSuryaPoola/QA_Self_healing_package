"""Playwright Page Object Model example."""

from aegisai import activate_aegis


class LoginPage:
    def __init__(self, page):
        self.page = page

    def enter_username(self, username: str) -> None:
        self.page.locator("xpath=//input[@id='email-field']").fill(username)


def test_login(page):
    activate_aegis(page)
    LoginPage(page).enter_username("tomsmith")
