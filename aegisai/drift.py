"""Pre-failure DOM drift detection helpers."""

from __future__ import annotations

from dataclasses import dataclass

from aegisai.cache import dom_fingerprint
from aegisai.utils.dom_parser import parse_dom_subset


@dataclass(frozen=True)
class DomDrift:
    changed: bool
    old_fingerprint: str
    new_fingerprint: str
    removed_locators: list[str]
    added_locators: list[str]


def detect_dom_drift(old_dom: str, new_dom: str) -> DomDrift:
    old_fingerprint = dom_fingerprint(old_dom)
    new_fingerprint = dom_fingerprint(new_dom)
    old_locators = {item.stable_locator() for item in parse_dom_subset(old_dom)}
    new_locators = {item.stable_locator() for item in parse_dom_subset(new_dom)}
    old_clean = {item for item in old_locators if item}
    new_clean = {item for item in new_locators if item}
    return DomDrift(
        changed=old_fingerprint != new_fingerprint,
        old_fingerprint=old_fingerprint,
        new_fingerprint=new_fingerprint,
        removed_locators=sorted(old_clean - new_clean),
        added_locators=sorted(new_clean - old_clean),
    )
