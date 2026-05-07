"""Conservative static locator rewrite helper.

The TDD calls for libcst to preserve formatting. This first slice provides a
safe, dependency-light rewrite contract and refuses broad or dynamic rewrites.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class RewriteResult:
    changed: bool
    source: str
    reason: str
    requires_review: bool = True


def rewrite_static_locator(source: str, old_locator: str, new_locator: str) -> RewriteResult:
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return RewriteResult(False, source, f"Source is not valid Python: {exc}.")

    single = f"'{old_locator}'"
    double = f'"{old_locator}"'
    occurrences = source.count(single) + source.count(double)
    if occurrences == 0:
        return RewriteResult(False, source, "Old locator was not found as a static string literal.")
    if occurrences > 1:
        return RewriteResult(False, source, "Multiple static occurrences require IDE or manual review.")

    if single in source:
        rewritten = source.replace(single, f"'{new_locator}'", 1)
    else:
        rewritten = source.replace(double, f'"{new_locator}"', 1)
    return RewriteResult(True, rewritten, "Static locator string was rewritten.", requires_review=True)
