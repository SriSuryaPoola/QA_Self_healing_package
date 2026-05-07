"""IDE suggestion payload helper."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdeSuggestion:
    file_path: str
    old_locator: str
    new_locator: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "file_path": self.file_path,
            "old_locator": self.old_locator,
            "new_locator": self.new_locator,
            "reason": self.reason,
        }
