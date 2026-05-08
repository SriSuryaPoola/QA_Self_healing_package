"""pytest example using the built-in plugin fixture.

Run:
    pytest --aegis
"""

from selenium.webdriver.common.by import By


def test_login(driver, aegis_activate):
    aegis_activate(driver, script_path=__file__)
    driver.get("https://the-internet.herokuapp.com/login")
    driver.find_element(By.XPATH, "//input[@id='email-field']").send_keys("tomsmith")
