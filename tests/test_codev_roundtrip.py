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
        raise
    except subprocess.SubprocessError as exc:
        pytest.skip(f"CODE V subprocess unavailable: {exc}")

    assert result.data["native_zmx_export"] == "unavailable_in_codev_11_5_docs"
    assert result.command_export_path.is_file()
    assert result.efl_y_mm == pytest.approx(3.621, rel=0.02)
    assert result.max_image_height_y_mm == pytest.approx(3.685, rel=0.03)
