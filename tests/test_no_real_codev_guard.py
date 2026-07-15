from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "command",
    [
        [Path("D:/CODEV115/codev.exe"), "/B", "forbidden.seq"],
        ["D:/CODEV115/cvcommand.exe", "forbidden.seq"],
        '"D:\\CODEV115\\codevm.exe" -c forbidden',
        "cvgui.exe",
    ],
)
def test_offline_test_guard_rejects_codev_before_process_creation(command: object) -> None:
    with pytest.raises(RuntimeError, match="attempted to launch real CODE V"):
        subprocess.Popen(command)  # type: ignore[arg-type]


def test_offline_test_guard_allows_patent_worker_python_processes() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "print('isolated-worker-ok')"],
        capture_output=True,
        check=True,
        text=True,
    )

    assert completed.stdout.strip() == "isolated-worker-ok"
