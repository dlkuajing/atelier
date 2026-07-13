from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_offline_codev_process_lock(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never let mocked/offline process tests mutate the production CODE V lock."""

    if request.node.get_closest_marker("real_machine") is not None:
        return
    from app.core.engines import codev_batch

    monkeypatch.setattr(
        codev_batch,
        "_DEFAULT_CODEV_LOCK_ROOT",
        tmp_path / "codev-execution-lock",
    )
