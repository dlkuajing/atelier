"""Null deep engine used when no external deep optimizer is available."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import NoReturn


@dataclass(frozen=True)
class NullDeepEngine:
    """Unavailable engine sentinel for CI and machines without CODE V."""

    reason: str = "code_v_executable_not_found"
    details: Mapping[str, object] = field(default_factory=dict)
    name: str = "null"

    def is_available(self) -> bool:
        return False

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "engine": "NullDeepEngine",
            "available": False,
            "reason": self.reason,
            "details": dict(self.details),
            "capabilities": [],
        }

    def submit(self, payload: Mapping[str, object]) -> NoReturn:
        raise RuntimeError(f"Deep engine unavailable: {self.reason}")
