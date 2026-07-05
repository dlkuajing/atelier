"""Demo launcher subprocess smoke tests."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEALTH_TIMEOUT_SECONDS = 120.0
HOME_MARKERS = (
    "<title>Atelier Optical Design Agent</title>",
    'class="requirement-form"',
    "Natural language requirement",
    "Analysis provenance",
)


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _launcher_command() -> list[str]:
    if os.name == "nt":
        return ["cmd.exe", "/c", str(ROOT / "scripts" / "start_demo.bat")]
    return ["sh", str(ROOT / "scripts" / "start_demo.sh")]


def _fetch(path: str, port: int) -> tuple[int, str, str]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"User-Agent": "atelier-demo-launch-test"},
    )
    with urllib.request.urlopen(request, timeout=2.0) as response:
        body = response.read().decode("utf-8")
        return response.status, response.headers.get("content-type", ""), body


def _tail_log(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-4000:]


def _wait_for_health(process: subprocess.Popen[object], port: int, log_path: Path) -> None:
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                f"Demo launcher exited before /health became ready.\n{_tail_log(log_path)}"
            )

        try:
            status, _content_type, body = _fetch("/health", port)
        except Exception as exc:  # noqa: BLE001 - retry transient startup failures.
            last_error = exc
            time.sleep(0.25)
            continue

        if status == 200 and '"status":"ok"' in body.replace(" ", ""):
            return

        time.sleep(0.25)

    raise AssertionError(
        f"Timed out waiting for /health on port {port}: {last_error}\n{_tail_log(log_path)}"
    )


def _stop_process_tree(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def test_windows_launcher_is_ascii_crlf_and_anchors_to_script_dir():
    launcher = ROOT / "scripts" / "start_demo.bat"
    content = launcher.read_bytes()

    assert b"\r\n" in content
    assert b"\n" not in content.replace(b"\r\n", b"")
    content.decode("ascii")
    assert b'cd /d "%~dp0"' in content


def test_start_demo_launcher_serves_health_and_homepage(tmp_path):
    port = _unused_port()
    env = os.environ.copy()
    env["HOST"] = "127.0.0.1"
    env["PORT"] = str(port)
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    log_path = tmp_path / "demo-launch.log"

    with log_path.open("w", encoding="utf-8") as log_file:
        popen_kwargs: dict[str, object] = {
            "cwd": str(ROOT),
            "env": env,
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "text": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(_launcher_command(), **popen_kwargs)
        try:
            _wait_for_health(process, port, log_path)

            status, content_type, html = _fetch("/", port)
            assert status == 200
            assert "text/html" in content_type
            for marker in HOME_MARKERS:
                assert marker in html
        finally:
            _stop_process_tree(process)

    assert process.poll() is not None
