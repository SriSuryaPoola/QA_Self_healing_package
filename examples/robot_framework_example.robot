*** Settings ***
Documentation     Robot Framework teams can activate AegisAI from a Python library keyword.
Library           SeleniumLibrary

*** Test Cases ***
Existing Robot Suite
    Open Browser    https://the-internet.herokuapp.com/login    chrome
    # Add a tiny Python keyword that calls aegisai.activate_aegis(driver)
    # against SeleniumLibrary's current WebDriver instance.
    Input Text      xpath=//input[@id='email-field']    tomsmith
    Close Browser
