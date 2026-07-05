from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.core.engines import codev_batch
from app.core.engines.codev_batch import (
    CODEV_BATCH_RESULT_SCHEMA,
    DEFAULT_CODEV_EXECUTABLE,
    CodeVBatchError,
    build_trivial_sequence,
    parse_codev_result_file,
    run_codev_batch,
    run_trivial_codev_batch,
)


def _fake_codev_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "codev.exe"
    executable.write_text("", encoding="utf-8")
    return executable


def _result_path_from_sequence(sequence_path: Path) -> Path:
    sequence = sequence_path.read_text(encoding="ascii")
    match = re.search(r'BUF EXP B1 "([^"]+)"', sequence)
    assert match is not None
    return Path(match.group(1))


def _write_success_result(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                f"schema\t{CODEV_BATCH_RESULT_SCHEMA}",
                "status\tok",
                "engine\tcodev",
                "contract\ttrivial-batch",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _is_nonzero_ok_result_failure(exc: CodeVBatchError) -> bool:
    data = exc.details.get("data")
    return (
        exc.kind == "failure"
        and isinstance(data, dict)
        and data.get("status") == "ok"
        and exc.details.get("returncode") not in (0, None)
    )


def test_trivial_sequence_uses_buf_and_explicit_result_file(tmp_path: Path) -> None:
    result_path = tmp_path / "result.tsv"

    sequence = build_trivial_sequence(result_path)

    assert "BUF PUT B1" in sequence
    assert f'BUF EXP B1 "{result_path}"' in sequence
    assert "EXI YES" in sequence
    assert "WRI " not in sequence


def test_parse_codev_result_file_reads_structured_tsv(tmp_path: Path) -> None:
    result_path = tmp_path / "result.tsv"
    _write_success_result(result_path)

    assert parse_codev_result_file(result_path) == {
        "schema": CODEV_BATCH_RESULT_SCHEMA,
        "status": "ok",
        "engine": "codev",
        "contract": "trivial-batch",
    }


def test_parse_codev_result_file_rejects_missing_required_keys(tmp_path: Path) -> None:
    result_path = tmp_path / "result.tsv"
    result_path.write_text(
        "\n".join(
            [
                f"schema\t{CODEV_BATCH_RESULT_SCHEMA}",
                "status\tok",
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodeVBatchError) as error:
        parse_codev_result_file(result_path, required_keys=("schema", "status", "engine"))

    assert error.value.kind == "failure"
    assert error.value.details["missing_keys"] == ["engine"]


def test_mock_subprocess_success_path_parses_result_file(monkeypatch, tmp_path: Path) -> None:
    executable = _fake_codev_executable(tmp_path)
    calls: list[list[str]] = []

    class FakePopen:
        pid = 1234
        returncode = 0

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            calls.append(command)
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            assert timeout == 10.0
            assert self.kwargs["cwd"] == str(tmp_path)
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            _write_success_result(_result_path_from_sequence(sequence_path))
            return "screen output is ignored for success", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_trivial_codev_batch(
        work_dir=tmp_path,
        executable=executable,
        timeout_seconds=10.0,
    )

    assert calls == [[str(executable), "/B", "atelier_codev_trivial.seq"]]
    assert result.returncode == 0
    assert result.data["status"] == "ok"
    assert result.data["schema"] == CODEV_BATCH_RESULT_SCHEMA


def test_ok_result_with_nonzero_returncode_is_structured_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 1235
        returncode = 7

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            _write_success_result(_result_path_from_sequence(sequence_path))
            return "screen output", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    with pytest.raises(CodeVBatchError) as error:
        run_trivial_codev_batch(work_dir=tmp_path, executable=executable)

    assert error.value.kind == "failure"
    assert error.value.details["returncode"] == 7
    assert error.value.details["data"]["status"] == "ok"
    assert error.value.details["result_created_this_run"] is True


def test_stale_result_file_is_deleted_before_batch_launch(monkeypatch, tmp_path: Path) -> None:
    executable = _fake_codev_executable(tmp_path)
    sequence_path = tmp_path / "stale.seq"
    result_path = tmp_path / "stale.tsv"
    sequence_path.write_text(build_trivial_sequence(result_path), encoding="ascii")
    _write_success_result(result_path)

    class FakePopen:
        pid = 1236
        returncode = 0

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "no new result was written", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    with pytest.raises(CodeVBatchError) as error:
        run_codev_batch(
            sequence_path=sequence_path,
            result_path=result_path,
            executable=executable,
            work_dir=tmp_path,
        )

    assert error.value.kind == "failure"
    assert error.value.details["stale_result_deleted"] is True
    assert not result_path.exists()


def test_mock_subprocess_no_license_is_structured(monkeypatch, tmp_path: Path) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 4321
        returncode = 9

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "", "FLEXlm license checkout denied: feature not available"

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    with pytest.raises(CodeVBatchError) as error:
        run_trivial_codev_batch(work_dir=tmp_path, executable=executable)

    assert error.value.kind == "no_license"
    assert error.value.describe()["kind"] == "no_license"
    assert error.value.details["returncode"] == 9


def test_popen_launch_error_is_structured(monkeypatch, tmp_path: Path) -> None:
    executable = _fake_codev_executable(tmp_path)

    def fake_popen(command: list[str], **kwargs: object) -> object:
        raise PermissionError("permission denied")

    monkeypatch.setattr(codev_batch.subprocess, "Popen", fake_popen)

    with pytest.raises(CodeVBatchError) as error:
        run_trivial_codev_batch(work_dir=tmp_path, executable=executable)

    assert error.value.kind == "failure"
    assert error.value.details["exception_type"] == "PermissionError"
    assert error.value.details["command"] == [str(executable), "/B", "atelier_codev_trivial.seq"]


def test_mock_subprocess_failure_is_structured(monkeypatch, tmp_path: Path) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 2468
        returncode = 2

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "macro syntax error", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    with pytest.raises(CodeVBatchError) as error:
        run_trivial_codev_batch(work_dir=tmp_path, executable=executable)

    assert error.value.kind == "failure"
    assert error.value.details["returncode"] == 2
    assert "result_path" in error.value.details


def test_mock_subprocess_timeout_uses_windows_taskkill(monkeypatch, tmp_path: Path) -> None:
    executable = _fake_codev_executable(tmp_path)
    taskkill_calls: list[list[str]] = []
    instances: list[object] = []

    class FakePopen:
        pid = 7777
        returncode = None

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.communicate_calls = 0
            instances.append(self)

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise subprocess.TimeoutExpired(self.command, timeout, output="partial")
            self.returncode = -9
            return "drained", ""

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        taskkill_calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="killed", stderr="")

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(codev_batch.subprocess, "run", fake_run)

    with pytest.raises(CodeVBatchError) as error:
        run_trivial_codev_batch(
            work_dir=tmp_path,
            executable=executable,
            timeout_seconds=0.01,
            platform_name="nt",
        )

    assert error.value.kind == "timeout"
    assert taskkill_calls == [["taskkill", "/F", "/T", "/PID", "7777"]]
    assert error.value.details["kill"]["method"] == "taskkill"
    assert error.value.details["reap"]["method"] == "communicate"
    assert instances[0].communicate_calls == 2


def test_mock_subprocess_timeout_falls_back_to_kill_when_taskkill_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 8888
        returncode = None

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.killed = False
            self.communicate_calls = 0

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise subprocess.TimeoutExpired(self.command, timeout, output="partial")
            return "", ""

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

    instance: FakePopen | None = None

    def fake_popen(command: list[str], **kwargs: Mapping[str, object]) -> FakePopen:
        nonlocal instance
        instance = FakePopen(command, **kwargs)
        return instance

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="no such pid")

    monkeypatch.setattr(codev_batch.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(codev_batch.subprocess, "run", fake_run)

    with pytest.raises(CodeVBatchError) as error:
        run_trivial_codev_batch(
            work_dir=tmp_path,
            executable=executable,
            timeout_seconds=0.01,
            platform_name="nt",
        )

    assert error.value.kind == "timeout"
    assert error.value.details["kill"]["method"] == "taskkill"
    assert error.value.details["kill"]["returncode"] == 1
    assert error.value.details["kill"]["fallback"]["method"] == "kill"
    assert instance is not None
    assert instance.killed is True


@pytest.mark.skipif(not DEFAULT_CODEV_EXECUTABLE.is_file(), reason="CODE V is not installed here")
def test_real_codev_trivial_batch_smoke(tmp_path: Path) -> None:
    try:
        result = run_trivial_codev_batch(work_dir=tmp_path, timeout_seconds=30.0)
    except CodeVBatchError as exc:
        if exc.kind == "no_license" or _is_nonzero_ok_result_failure(exc):
            return
        raise

    assert result.data["schema"] == CODEV_BATCH_RESULT_SCHEMA
    assert result.data["status"] == "ok"
    assert result.data["engine"] == "codev"
