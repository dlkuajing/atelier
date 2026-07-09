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


def test_pre_run_cleanup_deletes_stale_bare_listing_before_launch(
    monkeypatch, tmp_path: Path
) -> None:
    """启动前对称清理:同 stem 残留的裸名 .lis 会被删掉,不会被误认领为本次清单。"""
    executable = _fake_codev_executable(tmp_path)
    sequence_path = tmp_path / "probe.seq"
    result_path = tmp_path / "probe.tsv"
    sequence_path.write_text(build_trivial_sequence(result_path), encoding="ascii")

    bare_listing = sequence_path.with_suffix(".lis")
    bare_listing.write_text("STALE PREVIOUS RUN LISTING", encoding="utf-8")

    class FakePopen:
        pid = 5002
        returncode = 0

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            # 本次 run 正常收尾,不产生新的 .lis(无碰撞场景)
            _write_success_result(result_path)
            return "", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_codev_batch(
        sequence_path=sequence_path,
        result_path=result_path,
        executable=executable,
        work_dir=tmp_path,
    )

    assert not bare_listing.exists()  # 启动前已被清理
    assert result.listing_path is None  # 旧内容未被认领


def test_listing_snapshot_diff_claims_rolled_lis_after_root_collision(
    monkeypatch, tmp_path: Path
) -> None:
    """模拟 CODE V 对同 root 的清单滚动重命名（见 run_codev_batch docstring）。

    两次 run 用不同 seq 文件名（Python 视角 stem 不同，各自的 with_suffix(".lis")
    猜测互不相同），但 CODE V 内部会把结尾的 ``.<数字>`` token 当版本号剥离，
    实际把清单都写进同一份裸名 root .lis——第二次 run 前只删自己的猜测名，
    删不掉第一次残留的裸名文件；第二次 run 写入(RUN=B)会"碰撞"覆盖到同一个
    裸名文件里，快照 diff 必须认领碰撞后的内容(RUN=B)，而不是第一次的内容
    (RUN=A) 或者(由于文件名对不上)完全认领失败。
    """
    executable = _fake_codev_executable(tmp_path)
    # CODE V 剥离 ".0" / ".3" 尾缀后，两次 run 实际落到同一个裸名 root .lis
    root_lis = tmp_path / "US10281683B2_both_fixed_e0.lis"

    sequence_path_1 = tmp_path / "US10281683B2_both_fixed_e0.0.seq"
    result_path_1 = tmp_path / "result_a.tsv"
    sequence_path_1.write_text(build_trivial_sequence(result_path_1), encoding="ascii")
    assert sequence_path_1.with_suffix(".lis") != root_lis  # 猜测名与实际碰撞名不同

    run1_listing_content = "RUN=A\n"

    class FakePopenRun1:
        pid = 5003
        returncode = 0

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            root_lis.write_text(run1_listing_content, encoding="utf-8")
            _write_success_result(result_path_1)
            return "", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopenRun1)

    result_1 = run_codev_batch(
        sequence_path=sequence_path_1,
        result_path=result_path_1,
        executable=executable,
        work_dir=tmp_path,
    )

    assert result_1.listing_path == root_lis
    assert result_1.listing_path.read_text(encoding="utf-8") == run1_listing_content

    sequence_path_2 = tmp_path / "US10281683B2_both_fixed_e0.3.seq"
    result_path_2 = tmp_path / "result_b.tsv"
    sequence_path_2.write_text(build_trivial_sequence(result_path_2), encoding="ascii")
    assert sequence_path_2.with_suffix(".lis") != root_lis

    # 第二次 run 前的残留仍是第一次的 RUN=A(不同 stem 的对称清理删不到它)
    assert root_lis.read_text(encoding="utf-8") == run1_listing_content

    run2_listing_content = "RUN=B replaced with a much longer marker for size diff\n"

    class FakePopenRun2:
        pid = 5004
        returncode = 0

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            root_lis.write_text(run2_listing_content, encoding="utf-8")  # 碰撞覆盖
            _write_success_result(result_path_2)
            return "", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopenRun2)

    result_2 = run_codev_batch(
        sequence_path=sequence_path_2,
        result_path=result_path_2,
        executable=executable,
        work_dir=tmp_path,
    )

    assert result_2.listing_path == root_lis
    assert result_2.listing_path.read_text(encoding="utf-8") == run2_listing_content


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


def test_mock_subprocess_timeout_taskkill_gbk_output_does_not_crash(
    monkeypatch, tmp_path: Path
) -> None:
    """中文 Windows：taskkill 输出 GBK 字节，二进制读 + errors='replace' 不崩。"""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 9999
        returncode = None

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.communicate_calls = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise subprocess.TimeoutExpired(self.command, timeout, output=b"partial")
            self.returncode = -9
            return b"drained", b""

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert "text" not in kwargs and "encoding" not in kwargs  # 二进制读
        # 模拟中文 Windows taskkill 成功信息（GBK），含非 UTF-8 字节 0xb3
        return subprocess.CompletedProcess(
            command, 0, stdout="成功: 已终止 PID 9999".encode("gbk"), stderr=b""
        )

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(codev_batch.subprocess, "run", fake_run)

    with pytest.raises(CodeVBatchError) as error:
        run_trivial_codev_batch(
            work_dir=tmp_path, executable=executable,
            timeout_seconds=0.01, platform_name="nt",
        )

    assert error.value.kind == "timeout"
    assert error.value.details["kill"]["method"] == "taskkill"
    assert error.value.details["kill"]["returncode"] == 0
    # 未崩，tail 是 str（GBK 字节被 errors='replace' 安全解码）
    assert isinstance(error.value.details["kill"]["stdout_tail"], str)


def test_mock_subprocess_timeout_listing_read_oserror_still_raises_timeout(
    monkeypatch, tmp_path: Path
) -> None:
    """timeout 分支的 .lis 诊断读取遇 OSError（如刚被杀、尚未退出的 CODE V 进程
    树仍锁着清单 → PermissionError）必须 fail-open 返回空串：主异常仍是
    CodeVBatchError('timeout')，绝不被诊断读取的 PermissionError 替换。"""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 6666
        returncode = None

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs
            self.communicate_calls = 0

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                # 模拟 CODE V 在超时前写出了清单文件（随后进程被杀，文件被锁）
                (Path(self.kwargs["cwd"]) / "atelier_codev_trivial.lis").write_text(
                    "partial listing", encoding="utf-8"
                )
                raise subprocess.TimeoutExpired(self.command, timeout, output="partial")
            self.returncode = -9
            return "drained", ""

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="killed", stderr="")

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(codev_batch.subprocess, "run", fake_run)

    real_read_text = Path.read_text

    def locked_lis_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix == ".lis":
            raise PermissionError(f"file is locked by another process: {self}")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", locked_lis_read_text)

    with pytest.raises(CodeVBatchError) as error:
        run_trivial_codev_batch(
            work_dir=tmp_path,
            executable=executable,
            timeout_seconds=0.01,
            platform_name="nt",
        )

    assert error.value.kind == "timeout"  # 主异常未被 PermissionError 替换
    assert error.value.details["listing_tail"] == ""  # 诊断读取 fail-open 为空串


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


# ---------------------------------------------------------------------------
# BUF EXP 危险文件名机制守卫（真机实锤模式：basename 里 ".<数字>" 段内混有
# 非数字内容 → CODE V "ERROR - Unable to open file." 中止整条宏）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dangerous",
    [
        "atelier_vig0.20_readout.tsv",  # 真机灾难原型：.20 后还有 _readout
        "a_target3.797_optimized_readout.tsv",  # EFL 小数 token 混进 CODE V 路径
        "foo.2a.tsv",  # 数字后混字母的杂交段
    ],
)
def test_ensure_buf_exp_safe_filename_rejects_dangerous(dangerous: str) -> None:
    with pytest.raises(ValueError, match="Unable to open file"):
        codev_batch.ensure_buf_exp_safe_filename(dangerous)


@pytest.mark.parametrize(
    "legal",
    [
        "atelier_codev_target_A.tsv",  # 普通扩展名（点后是字母）
        "atelier_codev_target_A_vig0200.seq",  # 无小数点 token（修复后的正规形态）
        "atelier_codev_target_A_vig0200_optimized_readout.tsv",
        "v0.20.tsv",  # 隔离实验证实：小数点后到扩展名之间只剩纯数字 → CODE V 不报错
        "atelier_codev_trivial.lis",
    ],
)
def test_ensure_buf_exp_safe_filename_accepts_legal(legal: str) -> None:
    codev_batch.ensure_buf_exp_safe_filename(legal)  # 不应抛


def test_run_codev_batch_rejects_dangerous_sequence_and_result_names(tmp_path: Path) -> None:
    """守卫在 run_codev_batch 入口最前（先于 executable/seq 存在性检查）：
    危险文件名立即 ValueError，绝不发起 CODE V 进程让宏静默中止。"""
    safe_seq = tmp_path / "ok.seq"
    safe_res = tmp_path / "ok.tsv"
    with pytest.raises(ValueError, match="sequence_path"):
        run_codev_batch(
            sequence_path=tmp_path / "bad_vig0.20_x.seq", result_path=safe_res,
            executable=tmp_path / "missing_codev.exe",
        )
    with pytest.raises(ValueError, match="result_path"):
        run_codev_batch(
            sequence_path=safe_seq, result_path=tmp_path / "bad_vig0.20_readout.tsv",
            executable=tmp_path / "missing_codev.exe",
        )


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
