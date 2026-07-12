"""Offline cross-process tests for the Phase18 single-runner lock."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import app.core.batch_run_lock as batch_run_lock_module
from app.core.batch_archive import BatchArchive
from app.core.batch_run_lock import (
    BatchRunnerLockHeldError,
    BatchRunnerLockRecoveryNotNeeded,
    BatchRunnerLockRecoveryRequired,
    batch_runner_lock,
)
from app.core.batch_runner import run_batch

REPO_ROOT = Path(__file__).resolve().parents[1]


def _wait_for(path: Path, *, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {path}")


def _subprocess_env() -> dict[str, str]:
    return {**os.environ, "PYTHONUTF8": "1"}


class _NeverEngine:
    modes_requested: tuple[()] = ()

    def run(self, target, *, artifact_dir):  # noqa: ANN001, ANN201
        raise AssertionError("the engine must not start")


def test_clean_release_removes_owner_and_recovery_flag_cannot_be_habitual(tmp_path: Path):
    root = tmp_path / "archive"
    with batch_runner_lock(root) as owner:
        assert owner["pid"] == os.getpid()
        assert (root / ".p18-runner.owner.json").is_file()

    assert not (root / ".p18-runner.owner.json").exists()
    with (
        pytest.raises(BatchRunnerLockRecoveryNotNeeded, match="no stale owner"),
        batch_runner_lock(root, recover_stale=True),
    ):
        pass


def test_recovery_quiescence_matches_codev_and_other_phase18_runner(
    monkeypatch: pytest.MonkeyPatch,
):
    process = batch_run_lock_module._ProcessInfo
    monkeypatch.setattr(
        batch_run_lock_module,
        "_process_snapshot",
        lambda: [
            process(os.getpid(), 101, "python3.12.exe", "python scripts/p18_night_batch.py"),
            process(101, 100, "uv.exe", "uv run python scripts/p18_night_batch.py"),
            process(100, 1, "pwsh.exe", "pwsh"),
            process(222, 1, "codev.exe", "codev.exe /B run.seq"),
            process(333, 1, "codevm", "codevm"),
            process(444, 1, "python3.12", "python scripts/p18_night_batch.py --resume"),
            process(445, 1, "uv.exe", "uv run scripts/p18_night_batch.py --resume"),
            process(446, 1, "py.exe", "py scripts/p18_night_batch.py --resume"),
            process(555, 1, "python.exe", "python unrelated.py"),
        ],
    )

    active = batch_run_lock_module._active_phase18_processes()

    assert {(item["pid"], item["kind"]) for item in active} == {
        (222, "codev"),
        (333, "codev"),
        (444, "phase18-runner"),
        (445, "phase18-runner"),
        (446, "phase18-runner"),
    }


@pytest.mark.parametrize("command_line", [None, ""])
def test_recovery_refuses_unreadable_possible_runner_command_line(
    monkeypatch: pytest.MonkeyPatch, command_line: str | None
):
    process = batch_run_lock_module._ProcessInfo
    monkeypatch.setattr(
        batch_run_lock_module,
        "_process_snapshot",
        lambda: [
            process(os.getpid(), 1, "python.exe", "python recovery.py"),
            process(777, 1, "python3.12", command_line),
        ],
    )

    with pytest.raises(BatchRunnerLockRecoveryRequired, match="command line is unavailable"):
        batch_run_lock_module._active_phase18_processes()


def test_posix_process_read_skips_only_exit_race(tmp_path: Path):
    assert batch_run_lock_module._read_posix_process(tmp_path / "999999") is None


def test_posix_process_read_permission_error_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import errno

    process_dir = tmp_path / "123"
    process_dir.mkdir()
    (process_dir / "status").write_text("PPid:\t1\n", encoding="utf-8")
    (process_dir / "comm").write_text("python3.12\n", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path == process_dir / "cmdline":
            raise PermissionError(errno.EACCES, "denied", str(path))
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    with pytest.raises(BatchRunnerLockRecoveryRequired, match="cannot inspect"):
        batch_run_lock_module._read_posix_process(process_dir)


def test_posix_process_read_unicode_error_fails_closed(tmp_path: Path):
    process_dir = tmp_path / "124"
    process_dir.mkdir()
    (process_dir / "status").write_text("PPid:\t1\n", encoding="utf-8")
    (process_dir / "comm").write_text("python3.12\n", encoding="utf-8")
    (process_dir / "cmdline").write_bytes(b"python\0\xff\0")

    with pytest.raises(BatchRunnerLockRecoveryRequired, match="cannot decode"):
        batch_run_lock_module._read_posix_process(process_dir)


@pytest.mark.parametrize(
    ("raw_owner", "parse_error"),
    [
        (b'{"lock_id":"secret-that-must-not-leak"', "JSONDecodeError"),
        (b'["secret-that-must-not-leak"]', "TypeError"),
    ],
)
def test_explicit_recovery_preserves_safe_evidence_for_malformed_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_owner: bytes,
    parse_error: str,
):
    root = tmp_path / "archive"
    root.mkdir()
    owner_path = root / ".p18-runner.owner.json"
    owner_path.write_bytes(raw_owner)
    monkeypatch.setattr(batch_run_lock_module, "_active_phase18_processes", lambda: [])

    with (
        pytest.raises(BatchRunnerLockRecoveryRequired, match="Explicit recovery is required"),
        batch_runner_lock(root),
    ):
        pass

    with batch_runner_lock(root, recover_stale=True):
        pass

    receipts = list((root / ".p18-runner-recoveries").glob("*.json"))
    assert len(receipts) == 1
    receipt_text = receipts[0].read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["stale_owner"] is None
    evidence = receipt["stale_owner_bytes"]
    assert evidence["sha256"] == hashlib.sha256(raw_owner).hexdigest()
    assert evidence["byte_count"] == len(raw_owner)
    assert evidence["parse_error"].startswith(parse_error)
    assert evidence["raw_content_recorded"] is False
    assert "secret-that-must-not-leak" not in receipt_text
    assert not owner_path.exists()


def test_owner_permission_error_remains_fail_closed_during_explicit_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import errno

    root = tmp_path / "archive"
    root.mkdir()
    owner_path = root / ".p18-runner.owner.json"
    owner_path.write_text('{"lock_id":"old"}', encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path == owner_path:
            raise PermissionError(errno.EACCES, "denied", str(path))
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    with (
        pytest.raises(BatchRunnerLockRecoveryRequired, match="owner bytes cannot be read"),
        batch_runner_lock(root, recover_stale=True),
    ):
        pass

    assert owner_path.is_file()
    assert not (root / ".p18-runner-recoveries").exists()


def test_live_subprocess_blocks_run_batch_before_batch_or_job_creation(tmp_path: Path):
    root = tmp_path / "archive"
    acquired = tmp_path / "acquired"
    release = tmp_path / "release"
    code = (
        "from pathlib import Path\n"
        "import time\n"
        "from app.core.batch_run_lock import batch_runner_lock\n"
        f"root=Path({str(root)!r}); acquired=Path({str(acquired)!r}); "
        f"release=Path({str(release)!r})\n"
        "with batch_runner_lock(root, details={'test':'live-holder'}):\n"
        "    acquired.write_text('held', encoding='utf-8')\n"
        "    deadline=time.monotonic()+15\n"
        "    while not release.exists() and time.monotonic() < deadline: time.sleep(0.02)\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=_subprocess_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for(acquired)
        archive = BatchArchive(root=root)
        with pytest.raises(BatchRunnerLockHeldError, match="before batch/job creation"):
            run_batch(
                engine=_NeverEngine(),
                archive=archive,
                targets=[],
                batch_id="must-not-exist",
            )
        assert not (root / "must-not-exist" / "batch.json").exists()
    finally:
        release.write_text("release", encoding="utf-8")
        stdout, stderr = holder.communicate(timeout=20)
        assert holder.returncode == 0, (stdout, stderr)


def test_crash_requires_explicit_os_lock_proven_recovery_and_writes_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "archive"
    code = (
        "import os\n"
        "from pathlib import Path\n"
        "from app.core.batch_run_lock import batch_runner_lock\n"
        f"root=Path({str(root)!r})\n"
        "with batch_runner_lock(root, details={'test':'crash-owner'}):\n"
        "    os._exit(23)\n"
    )
    crashed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert crashed.returncode == 23
    owner_path = root / ".p18-runner.owner.json"
    assert owner_path.is_file()

    archive = BatchArchive(root=root)
    with pytest.raises(BatchRunnerLockRecoveryRequired, match="explicit stale-lock recovery"):
        run_batch(
            engine=_NeverEngine(),
            archive=archive,
            targets=[],
            batch_id="recovered-batch",
        )
    assert not (root / "recovered-batch" / "batch.json").exists()

    monkeypatch.setattr(
        batch_run_lock_module,
        "_active_phase18_processes",
        lambda: [{"pid": 777, "name": "codevm.exe", "kind": "codev"}],
    )
    with pytest.raises(BatchRunnerLockRecoveryRequired, match="quiescence is not proven"):
        run_batch(
            engine=_NeverEngine(),
            archive=archive,
            targets=[],
            batch_id="recovered-batch",
            recover_stale_lock=True,
        )
    assert not (root / "recovered-batch" / "batch.json").exists()

    monkeypatch.setattr(batch_run_lock_module, "_active_phase18_processes", lambda: [])
    summary = run_batch(
        engine=_NeverEngine(),
        archive=archive,
        targets=[],
        batch_id="recovered-batch",
        recover_stale_lock=True,
    )
    assert summary.batch.status == "completed"
    receipts = list((root / ".p18-runner-recoveries").glob("*.json"))
    assert len(receipts) == 1
    receipt = receipts[0].read_text(encoding="utf-8")
    assert "PID was not used alone as a liveness decision" in receipt
    assert "crash-owner" in receipt
    assert not owner_path.exists()


def test_two_cli_resumes_are_serialized_before_duplicate_attempt(tmp_path: Path):
    """The first CLI blocks inside a Mode1-only fake engine; the second CLI
    must fail at the lock seam while job-0000 is still attempt-1."""
    root = tmp_path / "archive"
    artifacts = tmp_path / "artifacts"
    entered = tmp_path / "engine-entered"
    release = tmp_path / "engine-release"
    archive = BatchArchive(root=root)
    target = {
        "scenario": "smartphone-wide",
        "efl_mm": 4.0,
        "fnum": 2.0,
        "fov_deg": 70.0,
        "image_height_mm": 3.5,
    }
    batch = archive.create_batch(
        target_source="offline-cli-lock-test",
        targets=[target],
        engine="fake",
        batch_id="cli-race",
    )

    first_code = (
        "import time\n"
        "from pathlib import Path\n"
        "import scripts.p18_night_batch as cli\n"
        "from app.core.batch_runner import FakeEngine as InnerFakeEngine\n"
        f"entered=Path({str(entered)!r}); release=Path({str(release)!r})\n"
        "class SlowFakeEngine:\n"
        "    modes_requested=InnerFakeEngine.modes_requested\n"
        "    def __init__(self, *, n): self.inner=InnerFakeEngine(n=n)\n"
        "    def run(self, target, *, artifact_dir):\n"
        "        entered.write_text('entered', encoding='utf-8')\n"
        "        deadline=time.monotonic()+15\n"
        "        while not release.exists() and time.monotonic() < deadline: time.sleep(0.02)\n"
        "        return self.inner.run(target, artifact_dir=artifact_dir)\n"
        "cli.FakeEngine=SlowFakeEngine\n"
        f"raise SystemExit(cli.main(['--engine','fake','--resume','--batch-id',{batch.batch_id!r},"
        f"'--archive-dir',{str(root)!r}]))\n"
    )
    first = subprocess.Popen(
        [sys.executable, "-c", first_code],
        cwd=REPO_ROOT,
        env={**_subprocess_env(), "JOB_ARTIFACTS_DIR": str(artifacts)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for(entered)
        second = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "p18_night_batch.py"),
                "--engine",
                "fake",
                "--resume",
                "--batch-id",
                batch.batch_id,
                "--archive-dir",
                str(root),
            ],
            cwd=REPO_ROOT,
            env=_subprocess_env(),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert second.returncode == 2
        assert "runner lock is held" in second.stderr
        jobs_while_first_is_live = archive.list_jobs(batch.batch_id)
        assert len(jobs_while_first_is_live) == 1
        assert jobs_while_first_is_live[0].status == "running"
        assert jobs_while_first_is_live[0].attempt == 1
    finally:
        release.write_text("release", encoding="utf-8")
        stdout, stderr = first.communicate(timeout=30)
        assert first.returncode == 0, (stdout, stderr)

    final_jobs = archive.list_jobs(batch.batch_id)
    assert len(final_jobs) == 1
    assert final_jobs[0].attempt == 1
    assert final_jobs[0].status == "succeeded"
