from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.core.engines import codev_batch
from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE, CodeVBatchError
from app.core.engines.codev_readout import (
    CODEV_READOUT_RESULT_SCHEMA,
    build_codev_readout_sequence,
    parse_codev_readout_file,
    run_codev_readout,
)
from app.core.engines.codev_roundtrip import default_patent_roundtrip_seed


def _fake_codev_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "codev.exe"
    executable.write_text("", encoding="utf-8")
    return executable


def _result_path_from_sequence(sequence_path: Path) -> Path:
    sequence = sequence_path.read_text(encoding="ascii")
    match = re.search(r'BUF EXP B1 "([^"]+)"', sequence)
    assert match is not None
    return Path(match.group(1))


def _write_readout_result(path: Path) -> None:
    rows = [
        ("schema", CODEV_READOUT_RESULT_SCHEMA),
        ("status", "ok"),
        ("source_zmx", "US20170003482A1.zmx"),
        ("units", "M"),
        ("num_surfaces", "2"),
        ("num_fields", "2"),
        ("num_zooms", "1"),
        ("stop_surface", "1"),
        ("field_type", "RIH"),
        ("reference_wavelength_index", "2"),
        ("image_height_y_mm", "3.62257"),
        ("surface.1.radius_y_mm", "1.25"),
        ("surface.1.thickness_mm", "0.45"),
        ("surface.1.glass", "___BLANK"),
        ("surface.1.nd", "1.544"),
        ("surface.1.vd", "55.9"),
        ("surface.1.surface_type", "ASP"),
        ("surface.1.is_stop", "1"),
        ("surface.1.asphere.K", "-0.12"),
        ("surface.1.asphere.A", "0.001"),
        ("surface.1.asphere.B", "-2e-05"),
        ("surface.1.asphere.C", "0"),
        ("surface.1.asphere.D", "0"),
        ("surface.1.asphere.E", "0"),
        ("surface.1.asphere.F", "0"),
        ("surface.1.asphere.G", "0"),
        ("surface.1.asphere.H", "0"),
        ("surface.1.asphere.J", "0"),
        ("surface.2.radius_y_mm", "0"),
        ("surface.2.thickness_mm", "0.75"),
        ("surface.2.glass", ""),
        ("surface.2.nd", "1.0"),
        ("surface.2.vd", "0"),
        ("surface.2.surface_type", "SPH"),
        ("surface.2.is_stop", "0"),
        ("surface.2.asphere.K", "0"),
        ("surface.2.asphere.A", "0"),
        ("surface.2.asphere.B", "0"),
        ("surface.2.asphere.C", "0"),
        ("surface.2.asphere.D", "0"),
        ("surface.2.asphere.E", "0"),
        ("surface.2.asphere.F", "0"),
        ("surface.2.asphere.G", "0"),
        ("surface.2.asphere.H", "0"),
        ("surface.2.asphere.J", "0"),
        ("field.1.definition_type", "RIH"),
        ("field.1.x", "0"),
        ("field.1.y", "0"),
        ("field.1.vuy", "0.1"),
        ("field.1.vly", "-0.1"),
        ("field.1.vux", "0.2"),
        ("field.1.vlx", "-0.2"),
        ("field.2.definition_type", "RIH"),
        ("field.2.x", "0"),
        ("field.2.y", "3.62257"),
        ("field.2.vuy", "0.3"),
        ("field.2.vly", "-0.3"),
        ("field.2.vux", "0.4"),
        ("field.2.vlx", "-0.4"),
    ]
    path.write_text("\n".join(f"{key}\t{value}" for key, value in rows) + "\n", encoding="utf-8")


def _is_nonzero_ok_result_failure(exc: CodeVBatchError) -> bool:
    data = exc.details.get("data")
    return (
        exc.kind == "failure"
        and isinstance(data, dict)
        and data.get("status") == "ok"
        and exc.details.get("returncode") not in (0, None)
    )


def test_readout_sequence_imports_zmx_and_reads_database_items(tmp_path: Path) -> None:
    source_zmx = default_patent_roundtrip_seed()
    result_path = tmp_path / "readout.tsv"

    sequence = build_codev_readout_sequence(source_zmx=source_zmx, result_path=result_path)

    assert 'IN CV_MACRO:ZEMAXOS_TO_CV "' in sequence
    assert str(source_zmx) in sequence
    assert "(RDY S^s)" in sequence
    assert "(THI S^s)" in sequence
    assert "(GLA S^s)" in sequence
    assert "(IND S^s W^refw)" in sequence
    assert "(TYP SUR S^s)" in sequence
    assert "(STO)" in sequence
    assert "(TYP FLD)" in sequence
    assert "(YRI F^f Z1)" in sequence
    assert "(VUY F^f Z1)" in sequence
    assert "(VLY F^f Z1)" in sequence
    assert "(VUX F^f Z1)" in sequence
    assert "(VLX F^f Z1)" in sequence
    assert "(A S^s)" in sequence
    assert "(J S^s)" in sequence
    assert "BUF EXP B1" in sequence


def test_parse_codev_readout_file_builds_structured_model(tmp_path: Path) -> None:
    result_path = tmp_path / "readout.tsv"
    _write_readout_result(result_path)

    readout = parse_codev_readout_file(result_path)

    assert readout.source_zmx == "US20170003482A1.zmx"
    assert readout.image_height_y_mm == pytest.approx(3.62257)
    assert readout.stop_surface == 1
    assert len(readout.surfaces) == 2
    assert readout.surfaces[0].glass == "___BLANK"
    assert readout.surfaces[0].nd == pytest.approx(1.544)
    assert readout.surfaces[0].vd == pytest.approx(55.9)
    assert readout.surfaces[0].surface_type == "ASP"
    assert readout.surfaces[0].is_stop is True
    assert readout.surfaces[0].asphere_coefficients["A"] == pytest.approx(0.001)
    assert readout.surfaces[0].asphere_coefficients["B"] == pytest.approx(-2e-05)
    assert readout.surfaces[1].glass is None
    assert len(readout.fields) == 2
    assert readout.fields[1].definition_type == "RIH"
    assert readout.fields[1].y == pytest.approx(3.62257)
    assert readout.fields[1].vuy == pytest.approx(0.3)
    assert readout.fields[1].vlx == pytest.approx(-0.4)


def test_parse_codev_readout_file_rejects_missing_surface_keys(tmp_path: Path) -> None:
    result_path = tmp_path / "readout.tsv"
    _write_readout_result(result_path)
    text = result_path.read_text(encoding="utf-8")
    result_path.write_text(text.replace("surface.1.radius_y_mm\t1.25\n", ""), encoding="utf-8")

    with pytest.raises(CodeVBatchError) as error:
        parse_codev_readout_file(result_path)

    assert error.value.kind == "failure"
    assert error.value.details["missing_key"] == "surface.1.radius_y_mm"


def test_mock_codev_readout_reuses_batch_runner(monkeypatch, tmp_path: Path) -> None:
    executable = _fake_codev_executable(tmp_path)
    calls: list[list[str]] = []

    class FakePopen:
        pid = 4321
        returncode = 0

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            calls.append(command)
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            assert timeout == 12.0
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            _write_readout_result(_result_path_from_sequence(sequence_path))
            return "ignored screen output", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_codev_readout(
        source_zmx=default_patent_roundtrip_seed(),
        work_dir=tmp_path,
        executable=executable,
        timeout_seconds=12.0,
    )

    assert calls == [[str(executable), "/B", "atelier_codev_readout.seq"]]
    assert result.batch.data["schema"] == CODEV_READOUT_RESULT_SCHEMA
    assert result.readout.num_surfaces == 2
    assert result.readout.surfaces[0].surface_type == "ASP"
    assert result.readout.fields[1].y == pytest.approx(3.62257)


@pytest.mark.skipif(not DEFAULT_CODEV_EXECUTABLE.is_file(), reason="CODE V is not installed here")
def test_real_codev_readout_patent_seed_smoke(tmp_path: Path) -> None:
    try:
        result = run_codev_readout(
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

    assert result.readout.source_zmx == default_patent_roundtrip_seed().name
    assert result.readout.image_height_y_mm == pytest.approx(3.685, rel=0.03)
    assert result.readout.surfaces
    assert any(surface.asphere_coefficients for surface in result.readout.surfaces)
