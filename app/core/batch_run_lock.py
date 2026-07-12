"""Cross-process single-runner lock for Phase18 batch execution.

The operating-system byte-range lock is the authority.  PID/hostname data is
diagnostic only: it is never used to decide that another runner is dead.  A
process crash releases the OS lock but intentionally leaves the owner record
behind; the next operator must request explicit recovery, which first acquires
the OS lock non-blockingly (proof that no live holder remains) and persists a
recovery receipt before any batch/job work can begin.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _OwnerSnapshot:
    parsed: dict[str, object] | None
    sha256: str
    byte_count: int
    parse_error: str | None

    def safe_evidence(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "byte_count": self.byte_count,
            "parse_error": self.parse_error,
            "raw_content_recorded": False,
        }


def _read_owner_snapshot(path: Path) -> _OwnerSnapshot | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BatchRunnerLockRecoveryRequired(
            f"Phase18 runner owner bytes cannot be read ({path}): {exc}; recovery refused. "
            "Do not delete the record or infer liveness from a PID."
        ) from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        value = json.loads(raw.decode("utf-8"))
    except UnicodeError:
        return _OwnerSnapshot(
            parsed=None,
            sha256=digest,
            byte_count=len(raw),
            parse_error="UnicodeDecodeError: owner bytes are not valid UTF-8",
        )
    except json.JSONDecodeError:
        return _OwnerSnapshot(
            parsed=None,
            sha256=digest,
            byte_count=len(raw),
            parse_error="JSONDecodeError: owner bytes are not valid JSON",
        )
    if not isinstance(value, dict):
        return _OwnerSnapshot(
            parsed=None,
            sha256=digest,
            byte_count=len(raw),
            parse_error=f"TypeError: top-level JSON is {type(value).__name__}, not object",
        )
    return _OwnerSnapshot(
        parsed=value,
        sha256=digest,
        byte_count=len(raw),
        parse_error=None,
    )


def _read_owner(path: Path) -> dict[str, object] | None:
    snapshot = _read_owner_snapshot(path)
    if snapshot is None:
        return None
    if snapshot.parsed is None:
        raise BatchRunnerLockRecoveryRequired(
            f"Phase18 runner owner record is malformed ({path}; {snapshot.parse_error}; "
            f"sha256={snapshot.sha256}, bytes={snapshot.byte_count}). Explicit recovery is "
            "required; raw content is not echoed and PID-based cleanup is forbidden."
        )
    return snapshot.parsed


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


@dataclass(frozen=True)
class _ProcessInfo:
    pid: int
    ppid: int
    name: str
    command_line: str | None


def _windows_process_snapshot() -> list[_ProcessInfo]:
    command = (
        "$ErrorActionPreference='Stop'; "
        "$OutputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=15,
        )
        payload = json.loads(completed.stdout or "[]")
    except (OSError, UnicodeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise BatchRunnerLockRecoveryRequired(
            f"cannot verify Phase18/CODE V process quiescence on Windows: {exc}; "
            "stale-lock recovery refused"
        ) from exc
    rows = payload if isinstance(payload, list) else [payload]
    snapshot: list[_ProcessInfo] = []
    try:
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("process snapshot row is not an object")
            name_value = row.get("Name")
            if not isinstance(name_value, str) or not name_value:
                raise ValueError("process snapshot row has no executable name")
            command_line_value = row.get("CommandLine")
            if command_line_value is not None and not isinstance(command_line_value, str):
                raise ValueError("process snapshot command line is neither text nor null")
            snapshot.append(
                _ProcessInfo(
                    pid=int(row["ProcessId"]),
                    ppid=int(row["ParentProcessId"]),
                    name=name_value,
                    command_line=command_line_value,
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise BatchRunnerLockRecoveryRequired(
            f"Windows process snapshot is incomplete or malformed: {exc}; "
            "stale-lock recovery refused"
        ) from exc
    return snapshot


def _read_posix_process(process_dir: Path) -> _ProcessInfo | None:
    """Read one `/proc/<pid>` entry.

    ENOENT/ESRCH means the process exited between enumeration and read and is
    the only skippable case.  Permission, encoding, and all other errors make
    a zero-runner claim unprovable, so recovery fails closed.
    """
    import errno

    try:
        status = (process_dir / "status").read_text(encoding="utf-8")
        name = (process_dir / "comm").read_text(encoding="utf-8").strip()
        raw_cmdline = (process_dir / "cmdline").read_bytes()
        command_line = raw_cmdline.replace(b"\0", b" ").decode("utf-8")
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ESRCH}:
            return None
        raise BatchRunnerLockRecoveryRequired(
            f"cannot inspect {process_dir} for stale-lock recovery: {exc}; recovery refused"
        ) from exc
    except UnicodeError as exc:
        raise BatchRunnerLockRecoveryRequired(
            f"cannot decode {process_dir} process metadata for stale-lock recovery: {exc}; "
            "recovery refused"
        ) from exc

    ppid_line = next((line for line in status.splitlines() if line.startswith("PPid:")), None)
    if ppid_line is None:
        raise BatchRunnerLockRecoveryRequired(
            f"cannot determine parent PID for {process_dir}; stale-lock recovery refused"
        )
    try:
        ppid = int(ppid_line.partition(":")[2].strip())
    except ValueError as exc:
        raise BatchRunnerLockRecoveryRequired(
            f"invalid parent PID in {process_dir}/status; stale-lock recovery refused"
        ) from exc
    return _ProcessInfo(
        pid=int(process_dir.name),
        ppid=ppid,
        name=name,
        command_line=command_line,
    )


def _process_snapshot() -> list[_ProcessInfo]:
    """Return a process tree snapshot without importing psutil.

    Recovery is deliberately stricter than ordinary acquisition.  If process
    inspection itself is unavailable, callers cannot prove quiescence and the
    recovery path fails closed.
    """
    if os.name == "nt":
        return _windows_process_snapshot()

    proc = Path("/proc")
    if not proc.is_dir():
        raise BatchRunnerLockRecoveryRequired(
            "cannot verify Phase18/CODE V process quiescence: /proc is unavailable; "
            "stale-lock recovery refused"
        )
    snapshot: list[_ProcessInfo] = []
    try:
        process_dirs = [path for path in proc.iterdir() if path.name.isdigit()]
    except OSError as exc:
        raise BatchRunnerLockRecoveryRequired(
            f"cannot enumerate /proc for stale-lock recovery: {exc}"
        ) from exc
    for process_dir in process_dirs:
        process = _read_posix_process(process_dir)
        if process is not None:
            snapshot.append(process)
    return snapshot


def _runner_carrier(name: str) -> bool:
    normalized = name.casefold()
    return normalized in {"uv", "uv.exe", "py", "py.exe"} or normalized.startswith("python")


def _ancestor_pids(snapshot: list[_ProcessInfo], pid: int) -> set[int]:
    by_pid = {process.pid: process for process in snapshot}
    ancestors: set[int] = set()
    cursor = pid
    while cursor in by_pid:
        parent = by_pid[cursor].ppid
        if parent <= 0 or parent in ancestors:
            break
        ancestors.add(parent)
        cursor = parent
    return ancestors


def _active_phase18_processes() -> list[dict[str, object]]:
    active: list[dict[str, object]] = []
    current_pid = os.getpid()
    snapshot = _process_snapshot()
    own_process_tree = _ancestor_pids(snapshot, current_pid) | {current_pid}
    for process in snapshot:
        normalized_name = process.name.casefold()
        is_codev = normalized_name in {"codev", "codev.exe", "codevm", "codevm.exe"}
        if is_codev:
            active.append({"pid": process.pid, "name": process.name, "kind": "codev"})
            continue
        if not _runner_carrier(process.name) or process.pid in own_process_tree:
            continue
        if not process.command_line:
            raise BatchRunnerLockRecoveryRequired(
                "cannot prove Phase18 runner quiescence because command line is unavailable for "
                f"possible runner carrier {process.name}[{process.pid}]; recovery refused"
            )
        is_runner = "p18_night_batch.py" in process.command_line.casefold()
        if is_runner:
            active.append(
                {
                    "pid": process.pid,
                    "name": process.name,
                    "kind": "phase18-runner",
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
            stale_snapshot = _read_owner_snapshot(owner_path)
            stale_owner = stale_snapshot.parsed if stale_snapshot is not None else None
            if stale_snapshot is not None and not recover_stale:
                raise BatchRunnerLockRecoveryRequired(
                    "Phase18 OS lock is free but a prior owner record remains, indicating an "
                    f"unclean exit ({_owner_hint(owner_path)}). Re-run with explicit stale-lock "
                    "recovery only after verifying the prior run is no longer active; recovery "
                    "will prove this again by acquiring the OS lock and write a receipt."
                )
            if stale_snapshot is None and recover_stale:
                raise BatchRunnerLockRecoveryNotNeeded(
                    "--recover-stale-lock was requested, but no stale owner record exists; "
                    "run normally so recovery cannot become a habitual lock bypass."
                )

            owner = _new_owner(details)
            if stale_snapshot is not None:
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
                    "stale_owner_bytes": stale_snapshot.safe_evidence(),
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
