from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

_CODEV_EXECUTABLE_NAMES = frozenset(
    {"codev", "codev.exe", "cvcommand", "cvcommand.exe", "codevm.exe", "cvgui.exe"}
)


class RealCodeVTestLaunchBlocked(RuntimeError):
    """Raised before an offline test can create a real CODE V process."""


def _command_executable_name(command: Any) -> str:
    if isinstance(command, Sequence) and not isinstance(command, (str, bytes, bytearray)):
        if not command:
            return ""
        token = os.fspath(command[0])
    else:
        token = os.fspath(command)
        if isinstance(token, bytes):
            token = os.fsdecode(token)
        match = re.match(r'^\s*(?:"([^"]+)"|(\S+))', token)
        if match is None:
            return ""
        token = match.group(1) or match.group(2)
    if isinstance(token, bytes):
        token = os.fsdecode(token)
    return PureWindowsPath(str(token).strip('"')).name.lower()


def _guard_offline_codev_command(command: Any) -> None:
    executable_name = _command_executable_name(command)
    if executable_name in _CODEV_EXECUTABLE_NAMES:
        raise RealCodeVTestLaunchBlocked(
            f"offline test attempted to launch real CODE V executable: {executable_name}"
        )


@pytest.fixture(autouse=True)
def _isolate_offline_codev_process_lock(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep offline tests outside both the real CODE V process and lock boundaries."""

    if request.node.get_closest_marker("real_machine") is not None:
        return
    real_popen = subprocess.Popen

    def guarded_popen(command: Any, *args: Any, **kwargs: Any):
        _guard_offline_codev_command(command)
        return real_popen(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded_popen)
    from app.core.engines import codev_batch

    monkeypatch.setattr(
        codev_batch,
        "_DEFAULT_CODEV_LOCK_ROOT",
        tmp_path / "codev-execution-lock",
    )
