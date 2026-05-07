"""Layer 3 — Heuristic Structural Searcher.

Goes beyond attribute matching to understand DOM relationships:
  - Label association (find element linked by a <label>)
  - Sibling proximity (element near text that describes it)
  - Fuzzy text matching (similar button text)
  - Placeholder / aria-label inference
  - Role-based semantic matching
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aegisai.models import DomElement
from aegisai.utils.dom_parser import parse_dom_subset


@dataclass
class HeuristicCandidate:
    by: str
    locator: str
    confidence: float
    strategy: str


def search(failing_locator: str, page_source: str) -> list[HeuristicCandidate]:
    """Return heuristic candidates sorted by confidence."""
    results: list[HeuristicCandidate] = []
    elements = parse_dom_subset(page_source)

    # Extract semantic intent from the failing locator
    raw = failing_locator.split("=", 1)[-1] if "=" in failing_locator else failing_locator
    intent_tokens = {t.lower() for t in re.findall(r"[a-zA-Z]+", raw)
                     if t.lower() not in {"input", "button", "xpath", "by", "type", "normalize", "space"}}

    for el in elements:
        stable = el.stable_locator()
        if not stable:
            continue

        # Strategy 1: Label association — find inputs with labels matching intent
        if el.tag == "input" and el.attrs.get("type") not in {"hidden"}:
            # Check aria-label
            aria = el.attrs.get("aria-label", "").lower()
            if any(tok in aria for tok in intent_tokens):
                results.append(HeuristicCandidate(
                    by="css", locator=stable, confidence=0.85,
                    strategy=f"aria-label match: '{aria}'"
                ))
            # Check placeholder
            placeholder = el.attrs.get("placeholder", "").lower()
            if any(tok in placeholder for tok in intent_tokens):
                results.append(HeuristicCandidate(
                    by="css", locator=stable, confidence=0.80,
                    strategy=f"placeholder match: '{placeholder}'"
                ))
            # Check name attr
            name = el.attrs.get("name", "").lower()
            if any(tok in name for tok in intent_tokens):
                results.append(HeuristicCandidate(
                    by="css", locator=stable, confidence=0.82,
                    strategy=f"name attr match: '{name}'"
                ))

        # Strategy 2: Fuzzy text matching for buttons/links
        if el.tag in ("button", "a", "span", "div") and el.text:
            text_lower = el.text.lower()
            matched_tokens = sum(1 for tok in intent_tokens if tok in text_lower)
            if matched_tokens > 0 and len(intent_tokens) > 0:
                conf = min(0.90, 0.60 + 0.15 * matched_tokens)
                results.append(HeuristicCandidate(
                    by="css", locator=stable, confidence=conf,
                    strategy=f"fuzzy text match ({matched_tokens}/{len(intent_tokens)} tokens): '{el.text[:40]}'"
                ))

        # Strategy 3: Role-based matching
        if el.role:
            role_lower = el.role.lower()
            if any(tok in role_lower for tok in intent_tokens):
                results.append(HeuristicCandidate(
                    by="css", locator=stable, confidence=0.75,
                    strategy=f"role match: '{el.role}'"
                ))

        # Strategy 4: data-testid keyword match
        testid = el.attrs.get("data-testid", "").lower()
        if testid and any(tok in testid for tok in intent_tokens):
            results.append(HeuristicCandidate(
                by="css", locator=stable, confidence=0.90,
                strategy=f"data-testid match: '{testid}'"
            ))

    # Deduplicate by locator, keeping highest confidence
    seen: dict[str, HeuristicCandidate] = {}
    for c in results:
        if c.locator not in seen or c.confidence > seen[c.locator].confidence:
            seen[c.locator] = c

    return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)
