"""Deep optical engine interface contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class DeepEngine(Protocol):
    """Protocol for offline/deep optical engines such as CODE V batch jobs."""

    name: str

    def is_available(self) -> bool:
        """Return whether this engine can accept work in the current runtime."""
        ...

    def describe(self) -> dict[str, object]:
        """Return a serializable description for diagnostics and API surfaces."""
        ...

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        """Submit one deep-engine job payload and return a serializable result handle."""
        ...
