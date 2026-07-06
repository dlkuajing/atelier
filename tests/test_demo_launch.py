"""Demo launcher subprocess smoke tests."""

from __future__ import annotations

import os
import signal
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEALTH_TIMEOUT_SECONDS = 120.0
HOME_MARKERS = (
    "<title>Atelier Optical Design Agent</title>",
    'class="requirement-form"',
    "Sample ultrawide",
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


def _copy_launchers(tmp_path: Path) -> Path:
    root = tmp_path / "demo-root"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "start_demo.bat", scripts / "start_demo.bat")
    shutil.copy2(ROOT / "scripts" / "start_demo.sh", scripts / "start_demo.sh")
    return root


def _native_launcher_command(root: Path) -> list[str]:
    if os.name == "nt":
        return ["cmd.exe", "/c", str(root / "scripts" / "start_demo.bat")]
    return ["sh", str(root / "scripts" / "start_demo.sh")]


def _run_preflight(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _native_launcher_command(root),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


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
    assert b"OPENAI_API_KEY" in content


def test_start_demo_shell_launchers_check_openai_api_key():
    assert "OPENAI_API_KEY" in (ROOT / "scripts" / "start_demo.sh").read_text(
        encoding="utf-8"
    )


def test_start_demo_preflight_requires_env_file(tmp_path):
    demo_root = _copy_launchers(tmp_path)

    result = _run_preflight(demo_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "Missing .env file." in output
    assert "OPENAI_API_KEY" in output


def test_start_demo_preflight_requires_nonempty_openai_key(tmp_path):
    demo_root = _copy_launchers(tmp_path)
    (demo_root / ".env").write_text("OPENAI_API_KEY=\n", encoding="ascii")

    result = _run_preflight(demo_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "OPENAI_API_KEY is missing or empty in .env." in output


@pytest.mark.skipif(os.name != "nt", reason="start_demo.bat preflight runs on Windows")
@pytest.mark.parametrize(
    "env_text",
    [
        'OPENAI_API_KEY=""\n',
        'OPENAI_API_KEY="   "\n',
        "OPENAI_API_KEY='   '\n",
        "OPENAI_API_KEY=   \n",
    ],
)
def test_start_demo_bat_preflight_rejects_quoted_or_whitespace_openai_key(
    tmp_path,
    env_text,
):
    demo_root = _copy_launchers(tmp_path)
    (demo_root / ".env").write_text(env_text, encoding="ascii")

    result = _run_preflight(demo_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert "OPENAI_API_KEY is missing or empty in .env." in output


def test_start_demo_launcher_serves_health_and_homepage(tmp_path):
    if not (ROOT / ".env").is_file():
        pytest.skip("start_demo preflight requires a local .env file")

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
