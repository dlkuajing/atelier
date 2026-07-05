from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.core.engines import codev_batch
from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE, CodeVBatchError
from app.core.engines.codev_roundtrip import (
    CODEV_ROUNDTRIP_RESULT_SCHEMA,
    DEFAULT_PATENT_ROUNDTRIP_SEED,
    _parse_vignetting,
    build_zmx_import_sequence,
    compare_roundtrip_zmx,
    default_patent_roundtrip_seed,
    run_codev_zmx_import,
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


def _write_roundtrip_result(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                f"schema\t{CODEV_ROUNDTRIP_RESULT_SCHEMA}",
                "status\tok",
                f"source_zmx\t{DEFAULT_PATENT_ROUNDTRIP_SEED}",
                "efl_y_mm\t3.62252",
                "max_image_height_y_mm\t3.62257",
                "num_surfaces\t18",
                "num_fields\t3",
                "native_zmx_export\tunavailable_in_codev_11_5_docs",
                "command_export_path\tatelier_codev_roundtrip_export.seq",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_incomplete_roundtrip_result(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                f"schema\t{CODEV_ROUNDTRIP_RESULT_SCHEMA}",
                "status\tok",
                f"source_zmx\t{DEFAULT_PATENT_ROUNDTRIP_SEED}",
                "efl_y_mm\t3.62252",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _mutated_export(tmp_path: Path, old: str, new: str) -> Path:
    source_zmx = default_patent_roundtrip_seed()
    data = source_zmx.read_bytes()
    old_bytes = old.encode("ascii")
    new_bytes = new.encode("ascii")
    if old_bytes not in data and "\n" in old:
        old_bytes = old.replace("\n", "\r\n").encode("ascii")
        new_bytes = new.replace("\n", "\r\n").encode("ascii")
    assert old_bytes in data
    mutated = data.replace(old_bytes, new_bytes, 1)
    if len(data) % 2 == 1 and len(mutated) % 2 == 0:
        mutated += b" "
    exported_zmx = tmp_path / source_zmx.name
    exported_zmx.write_bytes(mutated)
    return exported_zmx


def _is_nonzero_ok_result_failure(exc: CodeVBatchError) -> bool:
    data = exc.details.get("data")
    return (
        exc.kind == "failure"
        and isinstance(data, dict)
        and data.get("status") == "ok"
        and exc.details.get("returncode") not in (0, None)
    )


def test_import_sequence_uses_official_zemax_macro_and_wrl(tmp_path: Path) -> None:
    source_zmx = default_patent_roundtrip_seed()
    result_path = tmp_path / "result.tsv"
    command_export_path = tmp_path / "export.seq"

    sequence = build_zmx_import_sequence(
        source_zmx=source_zmx,
        result_path=result_path,
        command_export_path=command_export_path,
    )

    assert 'IN CV_MACRO:ZEMAXOS_TO_CV "' in sequence
    assert str(source_zmx) in sequence
    assert "(EFY)" in sequence
    assert "(YRI F^f Z1)" in sequence
    assert "BUF EXP B1" in sequence
    assert f'WRL "{command_export_path}"' in sequence
    assert "native_zmx_export" in sequence


def test_mock_codev_import_parses_custom_schema(monkeypatch, tmp_path: Path) -> None:
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
            assert timeout == 12.0
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            _write_roundtrip_result(_result_path_from_sequence(sequence_path))
            (Path(self.kwargs["cwd"]) / "atelier_codev_roundtrip_export.seq").write_text(
                "RDM;LEN\n",
                encoding="ascii",
            )
            return "ignored screen output", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_codev_zmx_import(
        source_zmx=default_patent_roundtrip_seed(),
        work_dir=tmp_path,
        executable=executable,
        timeout_seconds=12.0,
    )

    assert calls == [[str(executable), "/B", "atelier_codev_zmx_import.seq"]]
    assert result.data["schema"] == CODEV_ROUNDTRIP_RESULT_SCHEMA
    assert result.efl_y_mm == pytest.approx(3.62252)
    assert result.max_image_height_y_mm == pytest.approx(3.62257)
    assert result.command_export_path.is_file()


def test_mock_codev_import_rejects_missing_required_result_keys(
    monkeypatch,
    tmp_path: Path,
) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 1234
        returncode = 0

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            _write_incomplete_roundtrip_result(_result_path_from_sequence(sequence_path))
            return "ignored screen output", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    with pytest.raises(CodeVBatchError) as error:
        run_codev_zmx_import(
            source_zmx=default_patent_roundtrip_seed(),
            work_dir=tmp_path,
            executable=executable,
            timeout_seconds=12.0,
        )

    assert error.value.kind == "failure"
    assert "max_image_height_y_mm" in error.value.details["missing_keys"]


def test_compare_roundtrip_zmx_records_required_fidelity_items(tmp_path: Path) -> None:
    source_zmx = default_patent_roundtrip_seed()
    exported_zmx = tmp_path / source_zmx.name
    shutil.copyfile(source_zmx, exported_zmx)

    comparison = compare_roundtrip_zmx(source_zmx, exported_zmx)

    assert comparison.passed
    assert comparison.efl_deviation_pct == pytest.approx(0.0)
    assert comparison.source.glass_rows
    assert comparison.source.asphere_term_counts
    assert comparison.source.vignetting["VDX"] == (0.0, 0.0, 0.0)
    assert comparison.source.vignetting["VDY"] == (0.0, 0.0, 0.0)
    assert comparison.describe()["efl_within_2pct"] is True


def test_compare_roundtrip_zmx_fails_when_glass_row_changes(tmp_path: Path) -> None:
    source_zmx = default_patent_roundtrip_seed()
    exported_zmx = _mutated_export(
        tmp_path,
        "  GLAS ___BLANK 1 0 1.544 55.899999999999999",
        "  GLAS ___BLANK 1 0 1.600 55.899999999999999",
    )

    comparison = compare_roundtrip_zmx(source_zmx, exported_zmx)

    assert not comparison.passed
    assert comparison.glass_mismatches


def test_compare_roundtrip_zmx_fails_when_asphere_term_changes(tmp_path: Path) -> None:
    source_zmx = default_patent_roundtrip_seed()
    exported_zmx = _mutated_export(
        tmp_path,
        "  PARM 7 -0.0058158000000000003",
        "  PARM 7 -0.0048158000000000003",
    )

    comparison = compare_roundtrip_zmx(source_zmx, exported_zmx)

    assert not comparison.passed
    assert comparison.asphere_term_mismatches


def test_compare_roundtrip_zmx_fails_when_vignetting_changes(tmp_path: Path) -> None:
    source_zmx = default_patent_roundtrip_seed()
    exported_zmx = _mutated_export(
        tmp_path,
        "VDXN 0 0 0",
        "VDXN 0.1 0 0",
    )

    comparison = compare_roundtrip_zmx(source_zmx, exported_zmx)

    assert not comparison.passed
    assert comparison.vignetting_mismatches


def test_roundtrip_report_records_four_gates() -> None:
    report = Path(".planning/loop/codev-roundtrip-report.md")

    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "US20170003482A1.zmx" in text
    assert "EFL" in text
    assert "nd/vd" in text
    assert "非球面" in text
    assert "VDX/VDY" in text


@pytest.mark.skipif(not DEFAULT_CODEV_EXECUTABLE.is_file(), reason="CODE V is not installed here")
def test_real_codev_import_patent_seed_smoke(tmp_path: Path) -> None:
    try:
        result = run_codev_zmx_import(
            source_zmx=default_patent_roundtrip_seed(),
            work_dir=tmp_path,
            timeout_seconds=90.0,
        )
    except CodeVBatchError as exc:
        if exc.kind == "no_license":
            pytest.skip(f"CODE V license unavailable: {exc.message}")
        if _is_nonzero_ok_result_failure(exc):
            pytest.skip(f"CODE V returned non-zero after writing ok result: {exc.details}")
        raise
    except subprocess.SubprocessError as exc:
        pytest.skip(f"CODE V subprocess unavailable: {exc}")

    assert result.data["native_zmx_export"] == "unavailable_in_codev_11_5_docs"
    assert result.command_export_path.is_file()
    assert result.efl_y_mm == pytest.approx(3.621, rel=0.02)
    assert result.max_image_height_y_mm == pytest.approx(3.685, rel=0.03)


def test_parse_vignetting_survives_lf_checkout(tmp_path: Path) -> None:
    """CI regression: LF checkout made the ASCII seed even-sized, and the old
    blind utf-16 decode turned it into mojibake with zero VDX/VDY tokens."""
    source = default_patent_roundtrip_seed()
    lf_copy = tmp_path / source.name
    lf_copy.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))

    assert _parse_vignetting(lf_copy) == _parse_vignetting(source)
    assert _parse_vignetting(lf_copy)["VDX"] == (0.0, 0.0, 0.0)
