"""Behave/Cucumber-style activation hook."""

from aegisai import activate_aegis, deactivate_aegis


def before_scenario(context, scenario):
    if hasattr(context, "driver"):
        context.aegis_patch = activate_aegis(context.driver, script_path=__file__)
    elif hasattr(context, "page"):
        context.aegis_patch = activate_aegis(context.page)


def after_scenario(context, scenario):
    if hasattr(context, "driver"):
        deactivate_aegis(context.driver)
    elif hasattr(context, "page"):
        deactivate_aegis(context.page)
