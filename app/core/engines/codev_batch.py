"""Minimal CODE V batch runner.

The batch contract is intentionally file-based: CODE V writes structured data
with ``BUF EXP`` and Python parses that result file. The runner never scrapes
the CODE V listing/log output for successful results.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.core.batch_run_lock import BatchRunnerLockOwner, batch_runner_lock
from app.core.engines.codev import probe_code_v_installation

_FALLBACK_CODEV_EXECUTABLE = Path("D:/CODEV115/codev.exe")
CODEV_BATCH_RESULT_SCHEMA = "atelier-codev-batch-v1"

CodeVBatchErrorKind = Literal["failure", "timeout", "no_license"]

_TRIVIAL_SEQUENCE_NAME = "atelier_codev_trivial.seq"
_TRIVIAL_RESULT_NAME = "atelier_codev_trivial.tsv"
_OUTPUT_TAIL_CHARS = 4000
_REAP_TIMEOUT_SECONDS = 5.0
_DEFAULT_CODEV_LOCK_ROOT = Path.home() / ".atelier" / "codev-execution-lock"
_BATCH_REQUIRED_KEYS = ("schema", "status")
_TRIVIAL_REQUIRED_KEYS = ("schema", "status", "engine", "contract")
_LICENSE_MARKERS = (
    "flexlm",
    "license",
    "license checkout",
    "licence",
    "lmgrd",
    "sentinel",
    "security key",
    "checkout",
    "feature",
)
_LICENSE_FAILURE_MARKERS = (
    "cannot",
    "can't",
    "denied",
    "error",
    "fail",
    "failed",
    "missing",
    "not found",
    "not available",
    "unable",
    "unavailable",
)


class _LazyDefaultCodeVExecutable(os.PathLike[str]):
    """Resolve the default CODE V executable only when a caller needs it."""

    def __fspath__(self) -> str:
        return str(resolve_default_codev_executable())

    def __str__(self) -> str:
        return str(resolve_default_codev_executable())

    def __repr__(self) -> str:
        return f"{type(self).__name__}({resolve_default_codev_executable()!s})"

    def is_file(self) -> bool:
        return resolve_default_codev_executable().is_file()


DEFAULT_CODEV_EXECUTABLE = _LazyDefaultCodeVExecutable()


def resolve_default_codev_executable() -> Path:
    """Resolve CODE V through the 03a installation probe, then fall back."""

    installation = probe_code_v_installation()
    if installation is not None and installation.codev_executable is not None:
        return installation.codev_executable
    return _FALLBACK_CODEV_EXECUTABLE


class CodeVBatchError(RuntimeError):
    """Structured CODE V batch failure surfaced to callers."""

    def __init__(
        self,
        kind: CodeVBatchErrorKind,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.details = dict(details or {})

    def describe(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "message": self.message,
            "details": self.details,
        }


class CodeVBatchResult:
    """Serializable facts about a completed CODE V batch run."""

    def __init__(
        self,
        *,
        executable: Path,
        sequence_path: Path,
        result_path: Path,
        returncode: int | None,
        duration_seconds: float,
        data: Mapping[str, str],
        listing_path: Path | None = None,
    ) -> None:
        self.executable = executable
        self.sequence_path = sequence_path
        self.result_path = result_path
        self.returncode = returncode
        self.duration_seconds = duration_seconds
        self.data = dict(data)
        self.listing_path = listing_path

    def describe(self) -> dict[str, object]:
        return {
            "executable": str(self.executable),
            "sequence_path": str(self.sequence_path),
            "result_path": str(self.result_path),
            "returncode": self.returncode,
            "duration_seconds": self.duration_seconds,
            "data": self.data,
            "listing_path": str(self.listing_path) if self.listing_path is not None else None,
        }


@dataclass(frozen=True)
class CodeVRawProcessCapture:
    """Exact process bytes plus the authoritative shared-lock owner."""

    process: subprocess.Popen[bytes]
    stdout_bytes: bytes
    stderr_bytes: bytes
    duration_seconds: float
    lock_owner: dict[str, object]


def run_codev_process_bytes(
    command: list[str],
    *,
    work_dir: Path,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
    platform_name: str = os.name,
    lock_root: Path | None = None,
    recover_stale_lock: bool = False,
) -> CodeVRawProcessCapture:
    """Run one CODE V process under the cross-worktree lock and retain raw bytes."""

    resolved_lock_root = (
        Path(lock_root).resolve() if lock_root is not None else _DEFAULT_CODEV_LOCK_ROOT.resolve()
    )
    details = {
        "purpose": "codev-process",
        "command": list(command),
        "work_dir": str(Path(work_dir).resolve()),
    }
    with batch_runner_lock(
        resolved_lock_root,
        recover_stale=recover_stale_lock,
        details=details,
    ) as owner:
        owner_metadata = dict(owner)
        started_at = time.monotonic()
        try:
            process = _popen_codev(
                command,
                work_dir=work_dir,
                env=env,
                platform_name=platform_name,
            )
        except OSError as exc:
            raise CodeVBatchError(
                "failure",
                "CODE V batch process could not be started",
                details={
                    "command": command,
                    "work_dir": str(work_dir),
                    "exception_type": type(exc).__name__,
                    "error": str(exc),
                    "lock_owner": owner_metadata,
                },
            ) from exc
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            if process.returncode is None:
                raise RuntimeError("communicate returned before CODE V exit was proven")
        except BaseException as exc:
            kill_details = _kill_process_tree(process, platform_name=platform_name)
            reap_details = _reap_process_after_kill(process)
            quarantine_details: dict[str, object] | None = None
            quarantine_error: Exception | None = None
            if reap_details.get("reaped") is not True:
                try:
                    quarantine_details = _write_codev_quarantine_owner(
                        resolved_lock_root,
                        owner=owner,
                        cause=exc,
                        kill=kill_details,
                        reap=reap_details,
                    )
                except Exception as metadata_exc:  # noqa: BLE001 - preserve both failure records.
                    quarantine_error = metadata_exc
                    quarantine_details = {
                        "status": "metadata-write-failed-original-owner-retained",
                        "exception_type": type(metadata_exc).__name__,
                        "error": str(metadata_exc),
                    }
            if not isinstance(exc, Exception):
                raise
            kind: CodeVBatchErrorKind = (
                "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "failure"
            )
            message = (
                "CODE V batch run exceeded its hard timeout"
                if kind == "timeout"
                else "CODE V process communication failed after startup"
            )
            error = CodeVBatchError(
                kind,
                message,
                details={
                    "command": command,
                    "pid": process.pid,
                    "timeout_seconds": timeout_seconds,
                    "exception_type": type(exc).__name__,
                    "error": str(exc),
                    "stdout_tail": _tail(_coerce_output(getattr(exc, "stdout", None))),
                    "stderr_tail": _tail(_coerce_output(getattr(exc, "stderr", None))),
                    "kill": kill_details,
                    "reap": reap_details,
                    "quarantine": quarantine_details,
                    "lock_owner": owner_metadata,
                },
            )
            raise error from (quarantine_error or exc)
        return CodeVRawProcessCapture(
            process=process,
            stdout_bytes=_coerce_bytes(stdout),
            stderr_bytes=_coerce_bytes(stderr),
            duration_seconds=time.monotonic() - started_at,
            lock_owner=owner_metadata,
        )


def _write_codev_quarantine_owner(
    lock_root: Path,
    *,
    owner: BatchRunnerLockOwner,
    cause: BaseException,
    kill: Mapping[str, object],
    reap: Mapping[str, object],
) -> dict[str, object]:
    """Leave durable stale-owner evidence when child-tree exit is unproven."""

    owner_path = lock_root / ".p18-runner.owner.json"
    # This one-way handoff must precede JSON encoding, temporary-file creation,
    # write/fsync, and replace.  Any failure after this point leaves the
    # original owner record as the durable stale gate.
    owner_snapshot = owner.handoff_to_stale_gate()
    original_lock_id = owner_snapshot.get("lock_id", "unknown")
    quarantine_lock_id = f"quarantine-{original_lock_id}"
    quarantine = {
        **owner_snapshot,
        "lock_id": quarantine_lock_id,
        "quarantine": {
            "reason": "CODE V process tree exit could not be proven before lane release",
            "exception_type": type(cause).__name__,
            "kill": dict(kill),
            "reap": dict(reap),
            "recovery": (
                "explicit stale-lock recovery is required and must independently prove "
                "all Phase18/CODE V processes are absent"
            ),
        },
    }
    temporary = owner_path.with_name(
        f"{owner_path.name}.quarantine-{os.getpid()}-{secrets.token_hex(6)}.tmp"
    )
    payload = (json.dumps(quarantine, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, owner_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "status": "quarantine-owner-written",
        "lock_id": quarantine_lock_id,
        "owner_path": str(owner_path),
    }


def run_codev_process(
    command: list[str],
    *,
    work_dir: Path,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
    platform_name: str = os.name,
    lock_root: Path | None = None,
    recover_stale_lock: bool = False,
) -> tuple[subprocess.Popen[bytes], str, str, float]:
    """Run CODE V with the shared timeout, process-tree kill, and bounded reap contract."""
    capture = run_codev_process_bytes(
        command,
        work_dir=work_dir,
        timeout_seconds=timeout_seconds,
        env=env,
        platform_name=platform_name,
        lock_root=lock_root,
        recover_stale_lock=recover_stale_lock,
    )
    return (
        capture.process,
        _coerce_output(capture.stdout_bytes),
        _coerce_output(capture.stderr_bytes),
        capture.duration_seconds,
    )


def build_trivial_sequence(result_path: Path | str) -> str:
    """Build a minimal CODE V .seq that writes structured TSV via BUF EXP."""

    result_path = Path(result_path)
    quoted_result = _quote_codev_path(result_path)
    rows = (
        ("schema", CODEV_BATCH_RESULT_SCHEMA),
        ("status", "ok"),
        ("engine", "codev"),
        ("contract", "trivial-batch"),
    )

    lines = [
        "! Generated by app.core.engines.codev_batch.",
        "OUT NO",
    ]
    for index, (key, value) in enumerate(rows, start=1):
        lines.append(f'BUF PUT B1 I{index} J1 "{key}"')
        lines.append(f'BUF PUT B1 I{index} J2 "{value}"')
    lines.extend(
        [
            f"BUF EXP B1 {quoted_result}",
            "BUF DEL B1",
            "OUT YES",
            "EXI YES",
            "",
        ]
    )
    return "\n".join(lines)


def write_trivial_sequence(sequence_path: Path | str, result_path: Path | str) -> Path:
    """Write the minimal CODE V sequence file and return its path."""

    sequence_path = Path(sequence_path)
    sequence_path.parent.mkdir(parents=True, exist_ok=True)
    sequence_path.write_text(build_trivial_sequence(Path(result_path)), encoding="ascii")
    return sequence_path


def parse_codev_result_file(
    result_path: Path | str,
    *,
    expected_schema: str = CODEV_BATCH_RESULT_SCHEMA,
    required_keys: Iterable[str] = (),
) -> dict[str, str]:
    """Parse the explicit CODE V result TSV exported by ``BUF EXP``."""

    result_path = Path(result_path)
    if not result_path.is_file():
        raise CodeVBatchError(
            "failure",
            "CODE V result file was not created",
            details={"result_path": str(result_path)},
        )

    data: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        result_path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        parts = raw_line.split("\t")
        if len(parts) < 2 or not parts[0].strip():
            raise CodeVBatchError(
                "failure",
                "CODE V result file contains a malformed row",
                details={
                    "result_path": str(result_path),
                    "line_number": line_number,
                    "line": raw_line,
                },
            )
        data[parts[0].strip()] = "\t".join(parts[1:]).strip()

    if data.get("schema") != expected_schema:
        raise CodeVBatchError(
            "failure",
            "CODE V result file has an unexpected schema",
            details={
                "result_path": str(result_path),
                "expected_schema": expected_schema,
                "actual_schema": data.get("schema"),
            },
        )
    missing_keys = tuple(key for key in required_keys if not data.get(key))
    if missing_keys:
        raise CodeVBatchError(
            "failure",
            "CODE V result file is missing required fields",
            details={
                "result_path": str(result_path),
                "missing_keys": list(missing_keys),
                "present_keys": sorted(data),
            },
        )
    return data


def run_trivial_codev_batch(
    *,
    work_dir: Path | str,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 30.0,
    env: Mapping[str, str] | None = None,
    platform_name: str = os.name,
) -> CodeVBatchResult:
    """Generate and run the minimal CODE V batch contract."""

    work_dir = Path(work_dir)
    sequence_path = work_dir / _TRIVIAL_SEQUENCE_NAME
    result_path = work_dir / _TRIVIAL_RESULT_NAME
    write_trivial_sequence(sequence_path, result_path)
    return run_codev_batch(
        sequence_path=sequence_path,
        result_path=result_path,
        executable=executable,
        work_dir=work_dir,
        timeout_seconds=timeout_seconds,
        env=env,
        platform_name=platform_name,
        required_keys=_TRIVIAL_REQUIRED_KEYS,
    )


def run_codev_batch(
    *,
    sequence_path: Path | str,
    result_path: Path | str,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    work_dir: Path | str | None = None,
    timeout_seconds: float = 30.0,
    env: Mapping[str, str] | None = None,
    platform_name: str = os.name,
    expected_schema: str = CODEV_BATCH_RESULT_SCHEMA,
    required_keys: Iterable[str] = _BATCH_REQUIRED_KEYS,
    allow_nonzero_ok_result: bool = False,
) -> CodeVBatchResult:
    """Run CODE V in batch mode and parse only the explicit result file.

    ``allow_nonzero_ok_result`` only accepts a non-zero process return code
    after the explicit result file passes schema, required-key, and status
    validation.

    命名约定警告：``sequence_path`` 的文件名 stem 不要以 ``.<数字>`` 结尾
    （例如 ``foo_e0.3.seq``）——CODE V 会把这个尾缀当成自己的清单版本号剥离，
    同 root 多次 run 时会在磁盘上撞到同一份 ``.lis`` 清单并触发滚动重命名
    （裸名 -> ``.1.lis`` -> ``.2.lis`` -> ...）。这不影响 ``BUF EXP`` 导出的
    数值结果（走绝对路径显式契约），但会让清单认领更容易撞车。数值 tag 建
    议写成不含小数点的形式（如 ``e030``）。

    更致命的一档由机制守卫兜底（非提醒）：basename 里 ``.<数字>`` 段内混有
    非数字内容（如 ``..._vig0.20_readout.tsv``）会让 CODE V 打开路径时直接
    中止整条宏——入口对 ``sequence_path``/``result_path`` 调
    ``ensure_buf_exp_safe_filename``，命中立即 ValueError。
    """

    executable = Path(executable)
    sequence_path = Path(sequence_path)
    result_path = Path(result_path)
    # 机制守卫（非命名约定提醒）：CODE V 打开这两个路径，危险文件名会让宏
    # 静默中止（BUF EXP 拿不到导出）——Python 侧提前炸，见 ensure_buf_exp_safe_filename。
    ensure_buf_exp_safe_filename(sequence_path, role="sequence_path")
    ensure_buf_exp_safe_filename(result_path, role="result_path")
    work_dir = sequence_path.parent if work_dir is None else Path(work_dir)

    if not executable.is_file():
        raise CodeVBatchError(
            "failure",
            "CODE V executable was not found",
            details={"executable": str(executable)},
        )
    if not sequence_path.is_file():
        raise CodeVBatchError(
            "failure",
            "CODE V sequence file was not found",
            details={"sequence_path": str(sequence_path)},
        )

    stale_result_deleted = _delete_stale_result(result_path)
    bare_listing_guess = sequence_path.with_suffix(".lis")
    stale_listing_deleted = _delete_stale_listing(bare_listing_guess)
    listing_snapshot_before = _snapshot_lis_files(sequence_path.parent)
    sequence_arg = (
        sequence_path.name
        if _same_directory(sequence_path.parent, work_dir)
        else str(sequence_path)
    )
    command = [str(executable), "/B", sequence_arg]
    try:
        process, stdout_text, stderr_text, duration_seconds = run_codev_process(
            command,
            work_dir=work_dir,
            timeout_seconds=timeout_seconds,
            env=env,
            platform_name=platform_name,
        )
    except CodeVBatchError as exc:
        timeout_listing_path = _claim_listing_path(listing_snapshot_before, bare_listing_guess)
        exc.details.update(
            {
                "executable": str(executable),
                "stale_result_deleted": stale_result_deleted,
                "stale_listing_deleted": stale_listing_deleted,
                "listing_tail": _read_tail(timeout_listing_path)
                if timeout_listing_path is not None
                else "",
            }
        )
        raise
    listing_path = _claim_listing_path(listing_snapshot_before, bare_listing_guess)
    listing_tail = _read_tail(listing_path) if listing_path is not None else ""

    if result_path.is_file():
        data = parse_codev_result_file(
            result_path,
            expected_schema=expected_schema,
            required_keys=required_keys,
        )
        if data.get("status") != "ok":
            raise CodeVBatchError(
                _classify_error(data.values(), stdout_text, stderr_text, listing_tail),
                "CODE V batch result reported a non-ok status",
                details={
                    "command": command,
                    "returncode": process.returncode,
                    "data": data,
                    "result_path": str(result_path),
                    "result_created_this_run": True,
                },
            )
        if process.returncode != 0 and not allow_nonzero_ok_result:
            raise CodeVBatchError(
                _classify_error(data.values(), stdout_text, stderr_text, listing_tail),
                "CODE V batch exited with a non-zero returncode despite an ok result file",
                details={
                    "command": command,
                    "returncode": process.returncode,
                    "data": data,
                    "result_path": str(result_path),
                    "result_created_this_run": True,
                    "stdout_tail": _tail(stdout_text),
                    "stderr_tail": _tail(stderr_text),
                    "listing_tail": listing_tail,
                },
            )
        return CodeVBatchResult(
            executable=executable,
            sequence_path=sequence_path,
            result_path=result_path,
            returncode=process.returncode,
            duration_seconds=duration_seconds,
            data=data,
            listing_path=listing_path,
        )

    raise CodeVBatchError(
        _classify_error((), stdout_text, stderr_text, listing_tail),
        "CODE V batch run finished without producing the result file",
        details={
            "command": command,
            "returncode": process.returncode,
            "result_path": str(result_path),
            "stale_result_deleted": stale_result_deleted,
            "stale_listing_deleted": stale_listing_deleted,
            "stdout_tail": _tail(stdout_text),
            "stderr_tail": _tail(stderr_text),
            "listing_tail": listing_tail,
        },
    )


def _delete_stale_result(result_path: Path) -> bool:
    if not result_path.exists():
        return False
    try:
        result_path.unlink()
    except OSError as exc:
        raise CodeVBatchError(
            "failure",
            "CODE V stale result file could not be removed before launch",
            details={
                "result_path": str(result_path),
                "exception_type": type(exc).__name__,
                "error": str(exc),
            },
        ) from exc
    return True


def _delete_stale_listing(listing_path: Path) -> bool:
    """尽力删除按文件名猜测的裸名 .lis（启动前对称清理）。

    清单文件仅供诊断（数值结果走 ``BUF EXP`` 显式导出，不受影响），删除失败
    不应阻断主流程——与 ``_delete_stale_result`` 不同，这里是 best-effort。
    """
    if not listing_path.exists():
        return False
    try:
        listing_path.unlink()
    except OSError:
        return False
    return True


def _snapshot_lis_files(directory: Path) -> dict[Path, tuple[int, int]]:
    """对目录下所有 ``*.lis`` 拍 (mtime_ns, size) 快照，供事后 diff 认领。"""

    snapshot: dict[Path, tuple[int, int]] = {}
    try:
        candidates = list(directory.glob("*.lis"))
    except OSError:
        return snapshot
    for candidate in candidates:
        try:
            stat_result = candidate.stat()
        except OSError:
            continue
        snapshot[candidate] = (stat_result.st_mtime_ns, stat_result.st_size)
    return snapshot


def _claim_listing_path(
    snapshot_before: Mapping[Path, tuple[int, int]],
    fallback: Path,
) -> Path | None:
    """认领本次 run 新增/变更的 .lis 清单文件（快照 diff，取代按文件名猜测）。

    CODE V 会把 seq 文件名末尾形如 ``.<数字>`` 的 token 当自己的清单版本号
    剥离（见 ``run_codev_batch`` docstring），导致同 root 多次 run 时
    ``.lis`` 在磁盘上滚动重命名（裸名 -> ``.1.lis`` -> ``.2.lis`` -> ...），
    与 Python 侧 ``sequence_path.with_suffix(".lis")`` 的按名猜测错位。这里
    改为运行前后快照 diff：谁在本次 run 期间被新建或修改，谁就是本次的清单
    （多个变更时取 mtime 最新者）；diff 为空时回退旧的按名猜测以保持兼容。

    扫描目录取 ``fallback.parent``——与运行前快照天然同目录，无需调用方另传。
    """

    snapshot_after = _snapshot_lis_files(fallback.parent)
    changed = [path for path, meta in snapshot_after.items() if snapshot_before.get(path) != meta]
    if changed:
        return max(changed, key=lambda path: snapshot_after[path][0])
    if fallback.exists():
        return fallback
    return None


def _popen_codev(
    command: list[str],
    *,
    work_dir: Path,
    env: Mapping[str, str] | None,
    platform_name: str,
):
    # 二进制读（text=False）：CODE V 偶发非 UTF-8 输出（如 cp1252 的 0xb3=³）会让
    # communicate 的 reader 线程 UnicodeDecodeError 崩溃 → stdout 管道填满 → CODE V
    # 写阻塞挂死 → 超时（观测到的真机制）。改读原始字节永不在 reader 线程 decode，
    # stdout/stderr 仅作诊断（结果走 BUF EXP 文件），由 _coerce_output 后期 errors='replace' 解码。
    popen_kwargs: dict[str, object] = {
        "cwd": str(work_dir),
        "env": dict(env) if env is not None else None,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if platform_name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(command, **popen_kwargs)


def _kill_process_tree(process, *, platform_name: str) -> dict[str, object]:
    if platform_name == "nt":
        try:
            # 二进制读（不加 text=True）：中文 Windows 上 taskkill 打印 GBK 信息（如
            # "成功: 已终止 …" 的 0xb3 字节），text=True 会让 subprocess.run 的 reader
            # 线程 UnicodeDecodeError 崩（清理 CODE V 超时进程树时观测到）。字节交给
            # _coerce_output 后期 errors='replace' 解码，永不崩。
            completed = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001 - timeout cleanup must surface diagnostics.
            return {
                "method": "taskkill",
                "pid": process.pid,
                "error": str(exc),
                "fallback": _kill_single_process(process),
            }

        details: dict[str, object] = {
            "method": "taskkill",
            "pid": process.pid,
            "returncode": completed.returncode,
            "stdout_tail": _tail(_coerce_output(completed.stdout)),
            "stderr_tail": _tail(_coerce_output(completed.stderr)),
        }
        if completed.returncode != 0:
            details["fallback"] = _kill_single_process(process)
        return details

    return _kill_single_process(process)


def _kill_single_process(process) -> dict[str, object]:
    try:
        process.kill()
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup after hard timeout.
        return {"method": "kill", "pid": process.pid, "error": str(exc)}
    return {"method": "kill", "pid": process.pid}


def _reap_process_after_kill(process) -> dict[str, object]:
    try:
        stdout, stderr = process.communicate(timeout=_REAP_TIMEOUT_SECONDS)
        return {
            "method": "communicate",
            "pid": process.pid,
            "returncode": process.returncode,
            "stdout_tail": _tail(_coerce_output(stdout)),
            "stderr_tail": _tail(_coerce_output(stderr)),
            "reaped": process.returncode is not None,
        }
    except subprocess.TimeoutExpired as exc:
        details: dict[str, object] = {
            "method": "communicate",
            "pid": process.pid,
            "timeout_seconds": _REAP_TIMEOUT_SECONDS,
            "stdout_tail": _tail(_coerce_output(exc.stdout)),
            "stderr_tail": _tail(_coerce_output(exc.stderr)),
        }
    except Exception as exc:  # noqa: BLE001 - cleanup diagnostics must not mask timeout.
        details = {
            "method": "communicate",
            "pid": process.pid,
            "exception_type": type(exc).__name__,
            "error": str(exc),
        }

    wait = getattr(process, "wait", None)
    if callable(wait):
        try:
            details["wait_returncode"] = wait(timeout=_REAP_TIMEOUT_SECONDS)
            details["reaped"] = True
        except Exception as exc:  # noqa: BLE001 - best-effort handle release.
            details["wait_error"] = str(exc)
    details.setdefault("reaped", False)
    return details


# CODE V 危险文件名机制守卫（真机实锤，隔离对照实验见 codev_optimize.
# _fmt_edge_filename_token 文档字符串）：basename 里"小数点后跟数字、且同一
# 点分段内还有非数字内容"（如 "..._vig0.20_readout.tsv" 的 ".20_readout" 段）
# 会让 CODE V 打开该路径时报 "ERROR - Unable to open file." 并中止整条宏
# （BUF EXP 导出静默拿不到）。纯数字段后直接接扩展名（"...v0.20.tsv"）、合法
# 扩展名（.tsv/.seq/.lis——点后是字母）与无小数点的 token（"_vig0200"）均安全。
# 正则语义：一个点分段以数字开头、但段内混有非数字字符 → 危险。
_BUF_EXP_HAZARD_RE = re.compile(r"\.\d[^.]*[^.\d]")


def ensure_buf_exp_safe_filename(path: Path | str, *, role: str = "path") -> None:
    """Reject basenames CODE V refuses to open — Python 侧提前 ValueError，
    不让 CODE V 到真机批跑时才静默中止宏（见 `_BUF_EXP_HAZARD_RE` 注释）。

    守卫任何 CODE V 会打开的路径——包括**将来**会被打开的。2026-07-28 真机
    单变量 A/B 推翻了本段原先的豁免建议：zmx_writer 重建的候选
    ``*_target3.797_*.zmx`` 当时确实没有消费者，但它是交付物，第三方独立复核
    与 P2 异源打平率都要把它导回 CODE V，而 ``ZEMAXOS_TO_CV`` 对这个形状报
    ``ERROR - Zemax File ...`` 并导入一个空系统。判断"会不会被 CODE V 打开"
    要按文件的用途，不是按它当前有没有调用方。
    """
    name = Path(path).name
    if _BUF_EXP_HAZARD_RE.search(name):
        raise ValueError(
            f"CODE V-unsafe {role} filename {name!r}: a '.<digits>' infix followed by "
            "non-extension content makes CODE V abort the macro with "
            "'ERROR - Unable to open file.' (use a dot-free token such as '_vig0200')"
        )


def ensure_codev_safe_input_path(path: Path | str, *, role: str = "input_path") -> None:
    """Reject paths that CODE V's Zemax import macro cannot consume safely."""

    value = str(path)
    if any(char in value for char in ('"', "\r", "\n")):
        raise ValueError(f"CODE V {role} cannot contain quotes or newlines: {value!r}")
    # PurePath semantics on the host are insufficient for Windows paths in CI,
    # so normalize both separator spellings.  Drive/UNC anchors yield empty
    # components and are deliberately ignored.
    components = value.replace("\\", "/").split("/")
    dotted = next((part for part in components if part.startswith(".") and part), None)
    if dotted is not None:
        raise ValueError(
            f"CODE V-unsafe {role} {value!r}: dot-prefixed path component {dotted!r} "
            "makes ZEMAXOS_TO_CV silently import a dummy system"
        )


def _quote_codev_path(path: Path) -> str:
    value = str(path)
    if any(char in value for char in ('"', "\r", "\n")):
        raise ValueError(f"CODE V path cannot contain quotes or newlines: {value!r}")
    return f'"{value}"'


def _same_directory(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def _classify_error(
    result_values: Iterable[object],
    stdout: str,
    stderr: str,
    listing_tail: str,
) -> CodeVBatchErrorKind:
    text = " ".join(
        [
            " ".join(str(value) for value in result_values),
            stdout,
            stderr,
            listing_tail,
        ]
    ).lower()
    has_license_marker = any(marker in text for marker in _LICENSE_MARKERS)
    has_failure_marker = any(marker in text for marker in _LICENSE_FAILURE_MARKERS)
    if has_license_marker and has_failure_marker:
        return "no_license"
    return "failure"


def _read_tail(path: Path) -> str:
    # 诊断用途 fail-open：清单文件可能被刚被杀、尚未退出的 CODE V 进程树锁住
    # （PermissionError 等 OSError）。读不到就返回空串，绝不让诊断读取把
    # timeout/failure 主异常替换成 PermissionError（保护所有调用点，尤其
    # run_codev_batch 的 timeout 分支）。
    try:
        if not path.is_file():
            return ""
        return _tail(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def _tail(value: str, limit: int = _OUTPUT_TAIL_CHARS) -> str:
    return value[-limit:] if len(value) > limit else value


def _coerce_output(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _coerce_bytes(value: object) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    return str(value).encode("utf-8")
