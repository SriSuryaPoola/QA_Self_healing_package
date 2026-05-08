"""Selenium Page Object Model example."""

import unittest

from selenium.webdriver.common.by import By

from aegisai.unittest_integration import AegisTestMixin


class LoginPage:
    def __init__(self, driver):
        self.driver = driver

    def enter_username(self, username: str) -> None:
        self.driver.find_element(By.XPATH, "//input[@id='email-field']").send_keys(username)


class LoginTest(AegisTestMixin, unittest.TestCase):
    def test_login(self) -> None:
        driver = self.driver
        self.activate_aegis_for(driver, script_path=__file__)
        LoginPage(driver).enter_username("tomsmith")
