"""CODE V tolerance sensitivity table contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.api import wizard
from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE, CodeVBatchError
from app.core.engines.codev_optimize import (
    CODEV_OPTIMIZE_RESULT_SCHEMA,
    build_codev_optimize_sequence,
    default_optimize_seed,
    parse_codev_optimize_file,
    run_codev_optimize,
)
from app.main import app
from tests.test_web_compare_view import _bundle, _summary_form_payload


def _optimize_rows() -> list[tuple[str, str]]:
    return [
        ("schema", CODEV_OPTIMIZE_RESULT_SCHEMA),
        ("status", "ok"),
        ("source_zmx", "US20170003482A1.zmx"),
        ("optimization_status", "aut_completed"),
        ("glass_policy", "glass-not-varied"),
        ("thickness_policy", "MNT/MNE/MXT/MNA bounded in AUT"),
        ("optimized_readout_path", "atelier_codev_optimized_readout.tsv"),
        ("optimized_zmx_filename", "optimized.zmx"),
        ("before.efl_y_mm", "3.62252"),
        ("before.max_lateral_color_um", "4.8"),
        ("before.max_rms_spot_diameter_um", "26.0"),
        ("before.max_rms_wavefront_error_waves", "0.21"),
        ("before.max_distortion_pct", "1.3"),
        ("after.efl_y_mm", "3.62260"),
        ("after.max_lateral_color_um", "3.1"),
        ("after.max_rms_spot_diameter_um", "18.0"),
        ("after.max_rms_wavefront_error_waves", "0.17"),
        ("after.max_distortion_pct", "1.1"),
        ("efl_deviation_pct", "0.0022"),
        ("tolerance.schema", "atelier-codev-tolerance-v1"),
        ("tolerance.metric", "MTF drop after CODE V perturbation replay"),
        ("tolerance.provenance", "codev-run"),
        ("tolerance.top_n", "2"),
        ("tolerance.count", "3"),
        ("tolerance.1.parameter_name", "surface.4.thickness_mm"),
        ("tolerance.1.perturbation", "+0.005 mm"),
        ("tolerance.1.mtf_drop", "0.018"),
        ("tolerance.1.nominal_mtf", "0.412"),
        ("tolerance.1.perturbed_mtf", "0.394"),
        ("tolerance.2.parameter_name", "surface.2.radius_y_mm"),
        ("tolerance.2.perturbation", "+0.031 mm"),
        ("tolerance.2.mtf_drop", "0.071"),
        ("tolerance.2.nominal_mtf", "0.412"),
        ("tolerance.2.perturbed_mtf", "0.341"),
        ("tolerance.3.parameter_name", "surface.7.radius_y_mm"),
        ("tolerance.3.perturbation", "+0.016 mm"),
        ("tolerance.3.mtf_drop", "0.044"),
        ("tolerance.3.nominal_mtf", "0.412"),
        ("tolerance.3.perturbed_mtf", "0.368"),
    ]


def _write_optimize_result(path: Path) -> None:
    path.write_text(
        "\n".join(f"{key}\t{value}" for key, value in _optimize_rows()) + "\n",
        encoding="utf-8",
    )


def test_optimize_sequence_appends_tor_sensitivity_buf_export(tmp_path: Path) -> None:
    sequence = build_codev_optimize_sequence(
        source_zmx=default_optimize_seed(),
        result_path=tmp_path / "result.tsv",
        optimized_readout_path=tmp_path / "optimized-readout.tsv",
        tolerance_top_n=3,
        tolerance_mtf_frequency_lpmm=120.0,
    )

    assert "TOR" in sequence
    assert "SNS" in sequence
    assert "WBF B2 PER" in sequence
    assert "MTF_1FLD" in sequence
    assert '"tolerance.schema"' in sequence
    assert '"tolerance.count"' in sequence
    assert '".parameter_name"' in sequence
    assert '".perturbation"' in sequence
    assert '".mtf_drop"' in sequence
    assert "BUF EXP B1" in sequence


def test_parse_codev_optimize_file_returns_top_n_tolerance_rows(tmp_path: Path) -> None:
    result_path = tmp_path / "optimize.tsv"
    _write_optimize_result(result_path)

    summary = parse_codev_optimize_file(result_path)

    assert summary.tolerance_metric == "MTF drop after CODE V perturbation replay"
    assert summary.tolerance_provenance == "codev-run"
    assert [row.parameter_name for row in summary.tolerance_sensitivity] == [
        "surface.2.radius_y_mm",
        "surface.7.radius_y_mm",
    ]
    assert [row.rank for row in summary.tolerance_sensitivity] == [1, 2]
    assert summary.tolerance_sensitivity[0].perturbation == "+0.031 mm"
    assert summary.tolerance_sensitivity[0].mtf_drop == pytest.approx(0.071)
    assert summary.describe()["tolerance_sensitivity_top_n"][0]["provenance"] == "codev-run"


def test_result_page_renders_codev_tolerance_table(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    bundle = _bundle()
    codev_artifact = dict(bundle.codev_artifact or {})
    codev_artifact["tolerance_sensitivity_top_n"] = [
        {
            "rank": 1,
            "parameter_name": "surface.2.radius_y_mm",
            "perturbation": "+0.031 mm",
            "mtf_drop": 0.071,
            "provenance": "codev-run",
        },
        {
            "rank": 2,
            "parameter_name": "surface.7.radius_y_mm",
            "perturbation": "+0.016 mm",
            "mtf_drop": 0.044,
            "provenance": "codev-run",
        },
    ]
    bundle = bundle.model_copy(update={"codev_artifact": codev_artifact}, deep=True)
    monkeypatch.setattr("app.main.load_demo_cache_bundle_for_request", lambda _request: bundle)
    monkeypatch.setattr(
        "app.main.wizard.generate_executive_summary",
        AsyncMock(
            return_value=wizard.ExecutiveSummaryResponse(
                summary_en="Cached CODE V tolerance summary.",
                summary_zh="缓存的 CODE V 公差摘要。",
                model="test-model",
            )
        ),
    )

    response = TestClient(app).post("/results/summary", data=_summary_form_payload())

    assert response.status_code == 200, response.text
    html = response.text
    assert "公差敏感度 Top-N" in html
    assert "data-codev-tolerance-table" in html
    assert 'data-provenance="codev-run"' in html
    assert "surface.2.radius_y_mm" in html
    assert "+0.031 mm" in html
    assert "0.0710" in html
    assert 'data-tolerance-rank="1"' in html


@pytest.mark.skipif(
    not DEFAULT_CODEV_EXECUTABLE.is_file()
    or os.environ.get("ATELIER_RUN_REAL_CODEV_TOLERANCE") != "1",
    reason="real CODE V tolerance smoke is opt-in and requires a local license",
)
def test_real_codev_tolerance_smoke(tmp_path: Path) -> None:
    try:
        result = run_codev_optimize(
            source_zmx=default_optimize_seed(),
            work_dir=tmp_path,
            timeout_seconds=180.0,
            max_cycles=1,
            min_cycles=1,
            tolerance_top_n=5,
        )
    except CodeVBatchError as exc:
        if exc.kind in {"no_license", "timeout"}:
            pytest.skip(f"CODE V unavailable for tolerance smoke: {exc.message}")
        raise
    except subprocess.SubprocessError as exc:
        pytest.skip(f"CODE V subprocess unavailable: {exc}")

    assert result.summary.tolerance_provenance == "codev-run"
    assert result.summary.tolerance_sensitivity
    assert result.summary.tolerance_sensitivity[0].mtf_drop >= 0.0
