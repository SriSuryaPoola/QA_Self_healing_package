"""Selenium quickstart: two-line activation, existing framework unchanged."""

from selenium import webdriver
from selenium.webdriver.common.by import By

from aegisai import activate_aegis

driver = webdriver.Chrome()
activate_aegis(driver, script_path=__file__, backup=True)

driver.get("https://the-internet.herokuapp.com/login")

# This locator is intentionally stale. AegisAI can heal it at runtime.
driver.find_element(By.XPATH, "//input[@id='email-field']").send_keys("tomsmith")
driver.find_element(By.XPATH, "//input[@id='pass-field']").send_keys("SuperSecretPassword!")
driver.find_element(By.XPATH, "//button[@data-id='submit-btn']").click()

driver.quit()
