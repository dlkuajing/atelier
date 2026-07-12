"""Cross-process single-runner lock for Phase18 batch execution.

The operating-system byte-range lock is the authority.  PID/hostname data is
diagnostic only: it is never used to decide that another runner is dead.  A
process crash releases the OS lock but intentionally leaves the owner record
behind; the next operator must request explicit recovery, which first acquires
the OS lock non-blockingly (proof that no live holder remains) and persists a
recovery receipt before any batch/job work can begin.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

_LOCK_FILE = ".p18-runner.lock"
_OWNER_FILE = ".p18-runner.owner.json"
_RECOVERY_DIR = ".p18-runner-recoveries"


class BatchRunnerLockError(RuntimeError):
    """Base class for fail-closed single-runner acquisition failures."""


class BatchRunnerLockHeldError(BatchRunnerLockError):
    """Another process currently holds the authoritative OS lock."""


class BatchRunnerLockRecoveryRequired(BatchRunnerLockError):
    """The OS lock is free, but crash metadata requires explicit recovery."""


class BatchRunnerLockRecoveryNotNeeded(BatchRunnerLockError):
    """Recovery was requested although no stale owner record exists."""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
    try:
        temporary.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_owner(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchRunnerLockRecoveryRequired(
            f"Phase18 runner owner record is unreadable ({path}): {exc}. "
            "Do not delete it or infer liveness from a PID; inspect the file, then use the "
            "explicit recovery flow once the OS lock can be acquired."
        ) from exc
    if not isinstance(value, dict):
        raise BatchRunnerLockRecoveryRequired(
            f"Phase18 runner owner record is not a JSON object: {path}. "
            "Explicit recovery is required; PID-based cleanup is forbidden."
        )
    return value


def _owner_hint(owner_path: Path) -> str:
    try:
        owner = _read_owner(owner_path)
    except BatchRunnerLockRecoveryRequired as exc:
        return str(exc)
    if owner is None:
        return f"owner metadata not yet visible at {owner_path}"
    return (
        f"owner={owner.get('lock_id', 'unknown')} pid={owner.get('pid', 'unknown')} "
        f"host={owner.get('hostname', 'unknown')} started_at={owner.get('started_at', 'unknown')}"
    )


def _try_lock(handle: BinaryIO) -> bool:
    """Acquire one byte non-blockingly; return False only for contention."""
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import errno
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _new_owner(details: Mapping[str, object] | None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "lock_id": uuid4().hex,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "started_at": _utc_now_iso(),
        "argv": list(sys.argv),
        "details": dict(details or {}),
        "liveness_note": (
            "pid/hostname are diagnostic only; the held OS file lock is the sole liveness proof"
        ),
    }


def _process_snapshot() -> list[tuple[int, str, str]]:
    """Return ``(pid, executable name, command line)`` without importing psutil.

    Recovery is deliberately stricter than ordinary acquisition.  If process
    inspection itself is unavailable, callers cannot prove quiescence and the
    recovery path fails closed.
    """
    if os.name == "nt":
        command = (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            payload = json.loads(completed.stdout or "[]")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise BatchRunnerLockRecoveryRequired(
                f"cannot verify Phase18/CODE V process quiescence on Windows: {exc}; "
                "stale-lock recovery refused"
            ) from exc
        rows = payload if isinstance(payload, list) else [payload]
        return [
            (
                int(row.get("ProcessId", -1)),
                str(row.get("Name") or ""),
                str(row.get("CommandLine") or ""),
            )
            for row in rows
            if isinstance(row, dict)
        ]

    proc = Path("/proc")
    if not proc.is_dir():
        raise BatchRunnerLockRecoveryRequired(
            "cannot verify Phase18/CODE V process quiescence: /proc is unavailable; "
            "stale-lock recovery refused"
        )
    snapshot: list[tuple[int, str, str]] = []
    try:
        process_dirs = [path for path in proc.iterdir() if path.name.isdigit()]
    except OSError as exc:
        raise BatchRunnerLockRecoveryRequired(
            f"cannot enumerate /proc for stale-lock recovery: {exc}"
        ) from exc
    for process_dir in process_dirs:
        try:
            name = (process_dir / "comm").read_text(encoding="utf-8").strip()
            raw_cmdline = (process_dir / "cmdline").read_bytes()
        except (OSError, UnicodeError):
            continue  # a process may exit between enumeration and read
        command_line = raw_cmdline.replace(b"\0", b" ").decode("utf-8", errors="replace")
        snapshot.append((int(process_dir.name), name, command_line))
    return snapshot


def _active_phase18_processes() -> list[dict[str, object]]:
    active: list[dict[str, object]] = []
    current_pid = os.getpid()
    for pid, name, command_line in _process_snapshot():
        if pid == current_pid:
            continue
        normalized_name = name.casefold()
        is_codev = normalized_name in {"codev", "codev.exe", "codevm", "codevm.exe"}
        is_runner = (
            normalized_name in {"python", "python3", "python.exe", "python3.exe", "pythonw.exe"}
            and "p18_night_batch.py" in command_line.casefold()
        )
        if is_codev or is_runner:
            active.append(
                {
                    "pid": pid,
                    "name": name,
                    "kind": "codev" if is_codev else "phase18-runner",
                }
            )
    return active


@contextmanager
def batch_runner_lock(
    archive_root: Path,
    *,
    recover_stale: bool = False,
    details: Mapping[str, object] | None = None,
) -> Iterator[dict[str, object]]:
    """Hold the archive-wide single-runner lock for the caller's full run.

    Acquisition is non-blocking and fail-closed.  ``recover_stale=True`` is
    accepted only when an owner record survived a crash *and* this call has
    already acquired the OS lock, so recovery never kills a PID or steals a
    lock from a live process.  A durable recovery receipt preserves both the
    prior and replacement owner records.
    """
    root = Path(archive_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / _LOCK_FILE
    owner_path = root / _OWNER_FILE

    # Ensure byte 0 exists before Windows' byte-range locking call.  The file
    # is permanent; replacing/removing a locked inode would invalidate the
    # cross-platform mutual-exclusion contract.
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())

        if not _try_lock(handle):
            raise BatchRunnerLockHeldError(
                "Phase18 runner lock is held; refusing before batch/job creation or engine "
                f"startup ({_owner_hint(owner_path)}). Do not kill or clear by PID."
            )

        owner: dict[str, object] | None = None
        acquired = True
        try:
            stale_owner = _read_owner(owner_path)
            if stale_owner is not None and not recover_stale:
                raise BatchRunnerLockRecoveryRequired(
                    "Phase18 OS lock is free but a prior owner record remains, indicating an "
                    f"unclean exit ({_owner_hint(owner_path)}). Re-run with explicit stale-lock "
                    "recovery only after verifying the prior run is no longer active; recovery "
                    "will prove this again by acquiring the OS lock and write a receipt."
                )
            if stale_owner is None and recover_stale:
                raise BatchRunnerLockRecoveryNotNeeded(
                    "--recover-stale-lock was requested, but no stale owner record exists; "
                    "run normally so recovery cannot become a habitual lock bypass."
                )

            owner = _new_owner(details)
            if stale_owner is not None:
                active_processes = _active_phase18_processes()
                if active_processes:
                    summary = ", ".join(
                        f"{item['kind']}:{item['name']}[{item['pid']}]"
                        for item in active_processes
                    )
                    raise BatchRunnerLockRecoveryRequired(
                        "OS runner lock is free, but Phase18/CODE V process quiescence is not "
                        f"proven ({summary}); recovery refused. Do not kill or clear by PID."
                    )
                receipt = {
                    "schema_version": 1,
                    "recovered_at": _utc_now_iso(),
                    "proof": (
                        "non-blocking OS lock acquisition succeeded; no process held the "
                        "authoritative lock, and a process snapshot found no other Phase18 "
                        "runner/codev/codevm process (PID was not used alone as a liveness decision)"
                    ),
                    "stale_owner": stale_owner,
                    "replacement_owner": owner,
                }
                receipt_name = (
                    f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid4().hex}.json"
                )
                _atomic_write_json(root / _RECOVERY_DIR / receipt_name, receipt)
            _atomic_write_json(owner_path, owner)
            yield owner
        finally:
            # Only the holder owning this lock_id may clear metadata.  If the
            # record was externally altered, leave it behind so the next run
            # fails closed into the explicit recovery path.
            if owner is not None:
                try:
                    current = _read_owner(owner_path)
                    if current is not None and current.get("lock_id") == owner["lock_id"]:
                        owner_path.unlink(missing_ok=True)
                except (OSError, BatchRunnerLockError):
                    pass
            if acquired:
                _unlock(handle)
