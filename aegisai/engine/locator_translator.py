"""Layer 1 locator translator.

This layer returns cheap, rule-based alternatives for a failing locator before
the deterministic engine or LLM are considered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TranslationCandidate:
    by: str
    locator: str
    source: str


def translate(failing_locator: str) -> list[TranslationCandidate]:
    """Return equivalent or semantically close locators to try first."""

    raw = failing_locator.split("=", 1)[-1] if "=" in failing_locator else failing_locator
    if _is_sensitive_locator(raw):
        return []

    results: list[TranslationCandidate] = []

    attr_match = re.match(r"//(\w+)\[@([\w-]+)=['\"]([^'\"]+)['\"]\]$", raw)
    if attr_match:
        tag, attr, value = attr_match.group(1), attr_match.group(2), attr_match.group(3)
        results.extend(
            [
                TranslationCandidate("css", f"{tag}[{attr}='{value}']", "xpath-css exact"),
                TranslationCandidate("css", f"{tag}[{attr}*='{value}']", "xpath-css contains"),
                TranslationCandidate("css", f"[{attr}='{value}']", "xpath-css no-tag"),
            ]
        )
        if attr == "type":
            results.append(TranslationCandidate("css", f"input[{attr}='{value}']", "input type fallback"))
        if attr in {"placeholder", "aria-label"}:
            results.append(TranslationCandidate("css", f"[{attr}*='{value}']", "partial attribute"))

    text_match = re.match(r"//(\w+)\[normalize-space\(\)=['\"]([^'\"]+)['\"]\]$", raw)
    if text_match:
        tag, text = text_match.group(1), text_match.group(2)
        results.extend(
            [
                TranslationCandidate("xpath", f"//{tag}[text()='{text}']", "normalize text"),
                TranslationCandidate("xpath", f"//{tag}[contains(text(),'{text}')]", "contains full text"),
                TranslationCandidate("xpath", f"//{tag}[contains(normalize-space(.),'{text}')]", "contains deep text"),
            ]
        )
        for word in text.split():
            if len(word) >= 3:
                results.extend(
                    [
                        TranslationCandidate("xpath", f"//{tag}[contains(text(),'{word}')]", f"contains word {word}"),
                        TranslationCandidate(
                            "xpath",
                            f"//{tag}[contains(normalize-space(.),'{word}')]",
                            f"contains deep word {word}",
                        ),
                    ]
                )
        results.append(
            TranslationCandidate(
                "xpath",
                f"//{tag}[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{text.lower()}')]",
                "case-insensitive text",
            )
        )

    id_match = re.match(r"//\*?\[@id=['\"]([^'\"]+)['\"]\]$", raw)
    if id_match:
        results.append(TranslationCandidate("css", f"#{id_match.group(1)}", "id to css"))

    class_match = re.match(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]$", raw)
    if class_match:
        tag, class_name = class_match.group(1), class_match.group(2).replace(" ", ".")
        results.append(TranslationCandidate("css", f"{tag}.{class_name}", "class to css"))

    if not raw.startswith("//") and not raw.startswith("(//"):
        results.append(TranslationCandidate("css", raw, "raw as css"))

    raw_lower = raw.lower()
    if "email" in raw_lower:
        results.extend(
            [
                TranslationCandidate("css", "input[type='email']", "email type"),
                TranslationCandidate("css", "input[name='email']", "email name"),
                TranslationCandidate("css", "input[placeholder*='email' i]", "email placeholder"),
                TranslationCandidate("css", "input[autocomplete='email']", "email autocomplete"),
                TranslationCandidate("xpath", "//input[@type='email']", "email xpath"),
            ]
        )

    if "password" in raw_lower:
        results.extend(
            [
                TranslationCandidate("css", "input[type='password']", "password type"),
                TranslationCandidate("css", "input[name='password']", "password name"),
                TranslationCandidate("css", "input[autocomplete='current-password']", "password autocomplete"),
                TranslationCandidate("xpath", "//input[@type='password']", "password xpath"),
            ]
        )

    if any(keyword in raw_lower for keyword in ("login", "sign in", "submit", "log in", "auth", "authenticate")):
        results.extend(
            [
                TranslationCandidate("xpath", "//button[contains(text(),'Login')]", "login button text"),
                TranslationCandidate("xpath", "//button[contains(text(),'Sign')]", "sign button text"),
                TranslationCandidate("xpath", "//button[contains(text(),'Authenticate')]", "auth button text"),
                TranslationCandidate("css", "button[type='submit']", "submit button"),
                TranslationCandidate("css", "input[type='submit']", "submit input"),
            ]
        )

    return results


def _is_sensitive_locator(locator: str) -> bool:
    lowered = locator.lower()
    return any(marker in lowered for marker in ("token", "csrf", "session", "cookie", "authorization"))
