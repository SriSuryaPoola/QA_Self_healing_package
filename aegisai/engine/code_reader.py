"""Code reader — extracts intent context from the user's Python script.

Given a failing locator string, this module finds the surrounding code in the
script file and extracts:
  - What element the code was looking for (intent)
  - What action was going to be performed (send_keys, click, etc.)
  - The original By strategy and locator value
  - Nearby line context for the LLM prompt
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# Patterns to detect Selenium action that follows a find
_ACTION_PATTERNS = [
    (re.compile(r"\.send_keys\("), "send_keys"),
    (re.compile(r"\.click\("),     "click"),
    (re.compile(r"\.clear\("),     "clear"),
    (re.compile(r"\.submit\("),    "submit"),
    (re.compile(r"\.get_attribute\("), "get_attribute"),
    (re.compile(r"\.text"),        "read_text"),
    (re.compile(r"\.is_displayed\("), "is_displayed"),
]

_BY_PATTERN = re.compile(
    r"By\.(XPATH|CSS_SELECTOR|ID|NAME|CLASS_NAME|TAG_NAME|LINK_TEXT|PARTIAL_LINK_TEXT)",
    re.IGNORECASE,
)

_LOCATOR_VALUE_PATTERN = re.compile(r'["\']([^"\']+)["\']')


@dataclass
class CodeContext:
    """Structured context extracted from the user's script around a failing locator."""
    script_path: str
    failing_locator: str           # e.g. "XPATH=//input[@type='email']"
    by_strategy: str = "XPATH"
    locator_value: str = ""        # the raw locator string
    intended_action: str = "find"  # what the code was going to do
    variable_name: str = ""        # e.g. "email_input"
    surrounding_lines: list[str] = field(default_factory=list)
    start_line: int = 0

    def to_prompt_fragment(self) -> str:
        """Return a human-readable description for the LLM prompt."""
        lines_text = "\n".join(
            f"  {self.start_line + i}: {line}"
            for i, line in enumerate(self.surrounding_lines)
        )
        return (
            f"The Selenium script at '{self.script_path}' failed while trying to find:\n"
            f"  Strategy : {self.by_strategy}\n"
            f"  Locator  : {self.locator_value}\n"
            f"  Action   : {self.intended_action} (on variable '{self.variable_name}')\n\n"
            f"Surrounding code context:\n{lines_text}\n"
        )


def extract_context(script_path: str | Path, failing_locator: str) -> CodeContext | None:
    """
    Find the failing locator in the script and extract structured intent context.

    Returns None if the script file can't be read or the locator isn't found.
    """
    path = Path(script_path)
    if not path.exists():
        return None

    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = source.splitlines()

    # Strip the "XPATH=" / "CSS_SELECTOR=" prefix if present
    raw_locator = failing_locator
    by_strategy = "XPATH"
    if "=" in failing_locator:
        parts = failing_locator.split("=", 1)
        by_strategy = parts[0].strip().upper()
        raw_locator = parts[1].strip()

    # Find the line(s) containing this locator
    target_line_idx: int | None = None
    for i, line in enumerate(lines):
        if raw_locator in line:
            target_line_idx = i
            break

    if target_line_idx is None:
        # Fallback: return minimal context without line match
        return CodeContext(
            script_path=str(path),
            failing_locator=failing_locator,
            by_strategy=by_strategy,
            locator_value=raw_locator,
        )

    # Grab ±5 lines of context
    start = max(0, target_line_idx - 4)
    end   = min(len(lines), target_line_idx + 6)
    surrounding = lines[start:end]

    # Detect the variable name being assigned (e.g.  email_input = mywait.until(...))
    variable_name = ""
    for line in surrounding:
        m = re.match(r"\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=", line)
        if m:
            variable_name = m.group(1)

    # Detect intended action by scanning lines AFTER the find
    intended_action = "find"
    for line in lines[target_line_idx:target_line_idx + 10]:
        for pattern, action_name in _ACTION_PATTERNS:
            if pattern.search(line):
                intended_action = action_name
                break
        if intended_action != "find":
            break

    return CodeContext(
        script_path=str(path),
        failing_locator=failing_locator,
        by_strategy=by_strategy,
        locator_value=raw_locator,
        intended_action=intended_action,
        variable_name=variable_name,
        surrounding_lines=surrounding,
        start_line=start + 1,  # 1-indexed for display
    )
