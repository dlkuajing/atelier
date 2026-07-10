"""Deep optical engine interface contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class DeepEngine(Protocol):
    """Protocol for offline/deep optical engines such as CODE V batch jobs.

    Optional attribute (deliberately not a protocol member — declaring it here
    would make `isinstance`/structural checks fail for every existing engine
    that does not carry it): `seat_lane: str` selects which `JobStore` seat
    lane the engine's jobs serialize on (`job_store.DEFAULT_SEAT_LANE` when
    absent). Engines that drive a real CODE V process must declare
    `seat_lane = job_store.CODEV_SEAT_LANE` so CODE V single-instance
    serialization holds across every submission path.
    """

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
