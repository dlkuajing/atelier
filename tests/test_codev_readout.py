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
from app.core.engines.zmx_import_prep import STAGED_INPUT_DIRNAME


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
        ("aperture_type", "FNO"),
        ("f_number", "2.32"),
        ("entrance_pupil_diameter_mm", "1.56"),
        ("num_surfaces", "2"),
        ("num_fields", "2"),
        ("num_wavelengths", "2"),
        ("num_zooms", "1"),
        ("stop_surface", "1"),
        ("field_type", "RIH"),
        ("reference_wavelength_index", "2"),
        ("image_height_y_mm", "3.62257"),
        ("surface.1.radius_y_mm", "1.25"),
        ("surface.1.thickness_mm", "0.45"),
        ("surface.1.semi_diameter_mm", "1.10"),
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
        ("surface.2.semi_diameter_mm", "2.20"),
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
        ("wavelength.1.wavelength_nm", "555"),
        ("wavelength.1.weight", "1"),
        ("wavelength.2.wavelength_nm", "650"),
        ("wavelength.2.weight", "0.107"),
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
    assert "(TYP APE)" in sequence
    assert "(FNO)" in sequence
    assert "(EPD)" in sequence
    assert "(TYP FLD)" in sequence
    assert "^pi == 4*ATANF(1)" in sequence
    assert "^deg_to_rad == ^pi/180" in sequence
    assert "^efy == ABSF((EFY))" in sequence
    assert 'IF ^field_type = "ANG"' in sequence
    assert "^field_angle_y == (YAN F^f Z1)" in sequence
    assert "^field_angle_y_rad == ^field_angle_y * ^deg_to_rad" in sequence
    assert "^yh == ^efy * TANF(^field_angle_y_rad)" in sequence
    assert 'ELS IF ^field_type = "IMG"' in sequence
    assert "(YIM F^f Z1)" in sequence
    assert "(NUM W)" in sequence
    assert "(MAP S^s)" in sequence
    assert "(WL W^w)" in sequence
    assert "(WTW Z1 W^w)" in sequence
    assert "(YRI F^f Z1)" in sequence
    assert sequence.index("FOR ^f 1 ^numfld") < sequence.index('"image_height_y_mm"')
    assert sequence.index("ABSF(^yh) > ^maximh") < sequence.index('"image_height_y_mm"')
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
    assert readout.aperture_type == "FNO"
    assert readout.f_number == pytest.approx(2.32)
    assert readout.entrance_pupil_diameter_mm == pytest.approx(1.56)
    assert readout.image_height_y_mm == pytest.approx(3.62257)
    assert readout.stop_surface == 1
    assert len(readout.surfaces) == 2
    assert readout.surfaces[0].glass == "___BLANK"
    assert readout.surfaces[0].semi_diameter_mm == pytest.approx(1.10)
    assert readout.surfaces[0].nd == pytest.approx(1.544)
    assert readout.surfaces[0].vd == pytest.approx(55.9)
    assert readout.surfaces[0].vd_source == "dispersion-measured"
    assert readout.surfaces[0].surface_type == "ASP"
    assert readout.surfaces[0].is_stop is True
    assert readout.surfaces[0].asphere_coefficients["A"] == pytest.approx(0.001)
    assert readout.surfaces[0].asphere_coefficients["B"] == pytest.approx(-2e-05)
    assert readout.surfaces[0].asphere_coefficients["H"] == pytest.approx(0.0)
    assert readout.surfaces[1].glass is None
    assert len(readout.wavelengths) == 2
    assert readout.wavelengths[0].wavelength_um == pytest.approx(0.555)
    assert readout.wavelengths[1].weight == pytest.approx(0.107)
    assert len(readout.fields) == 2
    assert readout.fields[1].definition_type == "RIH"
    assert readout.fields[1].y == pytest.approx(3.62257)
    assert readout.fields[1].vuy == pytest.approx(0.3)
    assert readout.fields[1].vlx == pytest.approx(-0.4)
    assert readout.surfaces[0].describe()["vd_source"] == "dispersion-measured"


def test_real_smoke_fixture_does_not_decode_mangled_glass_name_as_vd() -> None:
    fixture = Path(".planning/loop/p13-smoke-2026-07-11/readout5-glasscode/atelier_codev_readout.tsv")
    readout = parse_codev_readout_file(fixture)
    surface = next(s for s in readout.surfaces if s.glass == "546000.401540")
    assert surface.nd == pytest.approx(1.546)
    assert surface.vd is None
    assert surface.vd_source is None


def test_model_glass_name_does_not_supply_missing_vd(tmp_path: Path) -> None:
    result_path = tmp_path / "readout.tsv"
    _write_readout_result(result_path)
    text = result_path.read_text(encoding="utf-8")
    text = text.replace("surface.1.glass\t___BLANK", "surface.1.glass\t546000.401540")
    text = text.replace("surface.1.nd\t1.544", "surface.1.nd\t1.544")
    text = text.replace("surface.1.vd\t55.9", "surface.1.vd\t0")
    result_path.write_text(text, encoding="utf-8")
    surface = parse_codev_readout_file(result_path).surfaces[0]
    assert surface.vd is None
    assert surface.vd_source is None


def test_malformed_short_model_glass_fraction_is_not_decoded(tmp_path: Path) -> None:
    result_path = tmp_path / "readout.tsv"
    _write_readout_result(result_path)
    text = result_path.read_text(encoding="utf-8")
    text = text.replace("surface.1.glass\t___BLANK", "surface.1.glass\t544000.40")
    text = text.replace("surface.1.vd\t55.9", "surface.1.vd\t0")
    result_path.write_text(text, encoding="utf-8")
    surface = parse_codev_readout_file(result_path).surfaces[0]
    assert surface.vd is None
    assert surface.vd_source is None


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
        returncode = 1

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
    assert result.batch.returncode == 1
    assert result.readout.num_surfaces == 2
    assert result.readout.surfaces[0].surface_type == "ASP"
    assert result.readout.fields[1].y == pytest.approx(3.62257)


def test_run_codev_readout_stages_dotted_source_and_reports_it(monkeypatch, tmp_path: Path) -> None:
    executable = _fake_codev_executable(tmp_path)
    dotted = tmp_path / ".inputs"
    dotted.mkdir()
    source = dotted / "lens.zmx"
    source.write_text("VERS 000001\n", encoding="ascii")

    class FakePopen:
        pid = 4330
        returncode = 0

        def __init__(self, command, **kwargs):
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout=None):
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            sequence = sequence_path.read_text(encoding="ascii")
            assert ".inputs" not in sequence
            _write_readout_result(_result_path_from_sequence(sequence_path))
            return "", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)
    result = run_codev_readout(source_zmx=source, work_dir=tmp_path / "work", executable=executable)
    # Staging is now unconditional (every import needs its WAVM flush sentinel,
    # see zmx_import_prep), so the dotted-path escape hatch it also provides
    # lands in the shared staging sub-directory rather than work_dir itself.
    assert (
        result.describe()["staged_zmx"]
        == str((tmp_path / "work" / STAGED_INPUT_DIRNAME / "lens.zmx").resolve())
    )


def test_run_codev_readout_rejects_dotted_work_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="work_dir"):
        run_codev_readout(source_zmx=default_patent_roundtrip_seed(), work_dir=tmp_path / ".work")


def test_codev_readout_rejects_returncode_outside_empirical_ok_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 4322
        returncode = 2

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            _write_readout_result(_result_path_from_sequence(sequence_path))
            return "screen output", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    with pytest.raises(CodeVBatchError) as error:
        run_codev_readout(
            source_zmx=default_patent_roundtrip_seed(),
            work_dir=tmp_path,
            executable=executable,
        )

    assert error.value.kind == "failure"
    assert error.value.details["returncode"] == 2
    assert error.value.details["allowed_returncodes"] == [0, 1]
    assert error.value.details["data"]["status"] == "ok"


@pytest.mark.real_machine
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
        raise
    except subprocess.SubprocessError as exc:
        pytest.skip(f"CODE V subprocess unavailable: {exc}")

    assert result.readout.source_zmx == default_patent_roundtrip_seed().name
    assert result.readout.image_height_y_mm == pytest.approx(3.685, rel=0.03)
    assert result.readout.aperture_type in {"FNO", "EPD"}
    assert result.readout.f_number is not None
    assert result.readout.wavelengths
    assert result.readout.surfaces
    assert all(surface.semi_diameter_mm is not None for surface in result.readout.surfaces)
    assert any(surface.asphere_coefficients for surface in result.readout.surfaces)


# ---------------------------------------------------------------------------
# Aspheric coefficient export precision (2026-07-28)
# ---------------------------------------------------------------------------


def _surface_data(**overrides: str) -> dict[str, str]:
    data = {
        "surface.1.radius_y_mm": "10.0",
        "surface.1.thickness_mm": "1.0",
        "surface.1.semi_diameter_mm": "1.0",
        "surface.1.surface_type": "ASP",
        "surface.1.is_stop": "0",
    }
    data.update(overrides)
    return data


def test_scaled_row_is_preferred_over_the_truncated_one() -> None:
    """The unscaled row is what BUF EXP mangles; the scaled twin carries the truth.

    Real vector: CODE V exported "0.000001" for a coefficient whose true value
    is 1.23456789e-06 (a 19% error), while the same value times 1e12 exported
    as 1.234568e+06.
    """
    from app.core.engines.codev_readout import _parse_surface

    surface = _parse_surface(
        _surface_data(
            **{
                "surface.1.asphere.A": "0.000001",
                "surface.1.asphere_scaled.A": "1.234568e+06",
            }
        ),
        1,
        stop_surface=1,
    )
    assert surface.asphere_coefficients["A"] == pytest.approx(1.234568e-06, rel=1e-9)


def test_legacy_files_without_the_scaled_row_still_parse() -> None:
    """Degraded is not absent -- refusing to read old artefacts would buy nothing."""
    from app.core.engines.codev_readout import _parse_surface

    surface = _parse_surface(
        _surface_data(**{"surface.1.asphere.A": "0.000001"}), 1, stop_surface=1
    )
    assert surface.asphere_coefficients["A"] == pytest.approx(1e-06)


def test_both_emitters_write_the_scaled_row(tmp_path: Path) -> None:
    """codev_readout and codev_optimize feed the same parser; they must agree."""
    from app.core.engines.codev_optimize import _optimized_readout_block
    from app.core.engines.codev_readout import build_codev_readout_sequence

    zmx = tmp_path / "seed.zmx"
    zmx.write_text("", encoding="ascii")
    readout_seq = build_codev_readout_sequence(source_zmx=zmx, result_path=tmp_path / "o.tsv")
    optimize_seq = "\n".join(_optimized_readout_block(source_name="seed.zmx"))
    for sequence in (readout_seq, optimize_seq):
        assert ".asphere_scaled." in sequence
        assert "*1000000000000" in sequence


def test_scale_round_trips_every_plausible_coefficient_magnitude() -> None:
    """1e-3..1e-9 is where aspheric high-order terms live."""
    from app.core.engines.codev_readout import ASPHERE_EXPORT_SCALE, _parse_surface

    for true_value in (0.13053, 1.42e-2, 5.9426e-05, 3.61e-06, 9.6683e-08, 1.147e-24):
        # What CODE V would export for the scaled value: 7 significant figures.
        exported = f"{true_value * ASPHERE_EXPORT_SCALE:.6e}"
        surface = _parse_surface(
            _surface_data(**{"surface.1.asphere_scaled.A": exported}), 1, stop_surface=1
        )
        assert surface.asphere_coefficients["A"] == pytest.approx(true_value, rel=1e-6)
