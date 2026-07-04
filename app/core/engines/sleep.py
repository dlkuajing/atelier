"""Sleep-based fake deep engine for background job wiring tests."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class SleepEngine:
    """Deterministic fake engine that sleeps briefly and echoes its payload."""

    delay_seconds: float = 0.01
    name: str = "sleep"

    def is_available(self) -> bool:
        return True

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "engine": "SleepEngine",
            "available": True,
            "capabilities": ["sleep", "echo"],
            "delay_seconds": self.delay_seconds,
        }

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        time.sleep(max(0.0, self.delay_seconds))
        if payload.get("fail"):
            message = payload.get("message", "sleep engine requested failure")
            raise RuntimeError(str(message))
        return {
            "engine": self.name,
            "status": "completed",
            "slept_seconds": self.delay_seconds,
            "payload": dict(payload),
        }
