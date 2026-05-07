"""Layer 4 — Live Browser JavaScript Prober.

Executes JavaScript directly in the browser to probe for elements using
multiple strategies simultaneously. Zero token cost, ~50ms latency.

The browser's own query engine is used — avoids DOM serialisation limits and
catches dynamically rendered elements that the page_source snapshot misses.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# JS probing script — runs entirely in the browser, returns the first match
_PROBE_SCRIPT = """
return (function(strategies) {
    function isVisible(el) {
        if (!el) {
            return false;
        }
        var style = window.getComputedStyle(el);
        var rect = el.getBoundingClientRect();
        return style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               style.opacity !== '0' &&
               rect.width > 0 &&
               rect.height > 0;
    }
    for (var i = 0; i < strategies.length; i++) {
        var s = strategies[i];
        try {
            var el = null;
            if (s.type === 'css') {
                el = document.querySelector(s.selector);
            } else if (s.type === 'xpath') {
                var r = document.evaluate(s.selector, document, null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                el = r.singleNodeValue;
            } else if (s.type === 'text') {
                var all = document.querySelectorAll(s.tag || '*');
                for (var j = 0; j < all.length; j++) {
                    if (all[j].textContent.trim().toLowerCase()
                            .includes(s.selector.toLowerCase())) {
                        el = all[j];
                        break;
                    }
                }
            }
            if (isVisible(el)) {
                // Element is visible
                return {
                    found: true,
                    strategy_index: i,
                    strategy_label: s.label,
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    name: el.getAttribute('name') || '',
                    type: el.getAttribute('type') || '',
                    'aria-label': el.getAttribute('aria-label') || '',
                    'data-testid': el.getAttribute('data-testid') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    text: (el.textContent || '').trim().substring(0, 60)
                };
            }
        } catch(e) {}
    }
    return { found: false };
})(arguments[0]);
"""


@dataclass
class JsProbeResult:
    found: bool
    css_locator: str | None = None   # best CSS selector to use with Selenium
    strategy_label: str = ""
    element_info: dict = None

    def __post_init__(self):
        if self.element_info is None:
            self.element_info = {}


def _build_strategies(failing_locator: str) -> list[dict]:
    """Build the browser-side strategy list based on the failing locator."""
    import re
    raw = failing_locator.split("=", 1)[-1] if "=" in failing_locator else failing_locator
    strategies = []
    raw_lower = raw.lower()
    if any(marker in raw_lower for marker in ("token", "csrf", "session", "cookie", "authorization")):
        return strategies

    # Direct translations
    m = re.match(r"//(\w+)\[@([\w-]+)=['\"]([^'\"]+)['\"]\]", raw)
    if m:
        tag, attr, val = m.group(1), m.group(2), m.group(3)
        strategies += [
            {"type": "css",   "selector": f"{tag}[{attr}='{val}']",  "label": "direct_css"},
            {"type": "css",   "selector": f"[{attr}='{val}']",       "label": "no_tag_css"},
            {"type": "css",   "selector": f"{tag}[{attr}*='{val}']", "label": "contains_css"},
            {"type": "xpath", "selector": raw,                        "label": "original_xpath"},
        ]

    m2 = re.match(r"//(\w+)\[normalize-space\(\)=['\"]([^'\"]+)['\"]\]", raw)
    if m2:
        tag, text = m2.group(1), m2.group(2)
        strategies += [
            {"type": "text",  "selector": text, "tag": tag, "label": "text_match"},
            {"type": "xpath", "selector": f"//{tag}[contains(text(),'{text}')]", "label": "contains_text"},
            {"type": "xpath", "selector": f"//{tag}[text()='{text}']",           "label": "exact_text"},
        ]

    # Semantic role probes
    if "email" in raw_lower or "mail" in raw_lower:
        strategies += [
            {"type": "css", "selector": "input[type='email']",            "label": "email_type"},
            {"type": "css", "selector": "input[name='email']",            "label": "email_name"},
            {"type": "css", "selector": "input[autocomplete='email']",    "label": "email_autocomplete"},
            {"type": "css", "selector": "input[placeholder*='Email']",    "label": "email_placeholder"},
        ]
    if "password" in raw_lower:
        strategies += [
            {"type": "css", "selector": "input[type='password']", "label": "password_type"},
            {"type": "css", "selector": "input[name='password']", "label": "password_name"},
            {"type": "css", "selector": "input[autocomplete='current-password']", "label": "password_autocomplete"},
        ]
    if any(k in raw_lower for k in ["login", "sign", "submit", "auth", "authenticate"]):
        strategies += [
            {"type": "text",  "selector": "Login",  "tag": "button", "label": "login_text"},
            {"type": "text",  "selector": "Sign in","tag": "button", "label": "signin_text"},
            {"type": "text",  "selector": "Authenticate","tag": "button", "label": "auth_text"},
            {"type": "css",   "selector": "button[type='submit']",        "label": "submit_button"},
        ]

    return strategies


def _element_info_to_css(info: dict) -> str | None:
    """Convert element info dict (from JS) to the most stable CSS selector."""
    if info.get("data-testid"):
        return f'[data-testid="{info["data-testid"]}"]'
    if info.get("id"):
        return f'#{info["id"]}'
    if info.get("name"):
        return f'[name="{info["name"]}"]'
    if info.get("aria-label"):
        return f'[aria-label="{info["aria-label"]}"]'
    tag  = info.get("tag", "")
    typ  = info.get("type", "")
    ph   = info.get("placeholder", "")
    if tag and typ:
        return f'{tag}[type="{typ}"]'
    if tag and ph:
        return f'{tag}[placeholder*="{ph[:20]}"]'
    if tag:
        return tag
    return None


def probe(failing_locator: str, driver: Any) -> JsProbeResult:
    """Execute multi-strategy JavaScript probing in the live browser."""
    strategies = _build_strategies(failing_locator)
    if not strategies:
        return JsProbeResult(found=False)
    try:
        raw_result = driver.execute_script(_PROBE_SCRIPT, strategies)
        if not raw_result or not raw_result.get("found"):
            return JsProbeResult(found=False)

        css = _element_info_to_css(raw_result)
        return JsProbeResult(
            found=True,
            css_locator=css,
            strategy_label=raw_result.get("strategy_label", ""),
            element_info=raw_result,
        )
    except Exception as exc:
        logger.debug("[aegisai][js_prober] JS probe error: %s", exc)
        return JsProbeResult(found=False)
