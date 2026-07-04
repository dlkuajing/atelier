"""Provenance contracts for serialized optical analysis artefacts."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.aberration import MTFFieldData, MTFResult
from app.core.field_analysis import FieldAnalysisResult
from app.core.optical_engine import ParaxialSummary
from app.core.provenance import ProvenanceSource
from app.core.spot_diagram import SpotDiagramResult, SpotFieldData, SpotWavelengthData
from app.core.wavefront_metrics import WavefrontFieldMetric, WavefrontMetricsResult
from app.main import app


LEGAL_PROVENANCE = {source.value for source in ProvenanceSource}


def _paraxial() -> ParaxialSummary:
    return ParaxialSummary(
        effective_focal_length_mm=4.2,
        f_number=1.8,
        entrance_pupil_diameter_mm=2.3,
        exit_pupil_diameter_mm=2.0,
        total_track_mm=5.5,
        n_surfaces=8,
        stop_surface_index=3,
    )


def _mtf() -> MTFResult:
    return MTFResult(
        freq_lp_per_mm=[0.0, 50.0],
        fields=[
            MTFFieldData(
                field_index=0,
                sagittal=[1.0, 0.5],
                tangential=[1.0, 0.45],
            )
        ],
        diff_limited=[1.0, 0.7],
        cutoff_freq_lp_per_mm=900.0,
        airy_disc_diameter_um=2.7,
        rms_spot_radius_um_by_field=[4.0],
    )


def _spot_diagram() -> SpotDiagramResult:
    return SpotDiagramResult(
        coordinates="local",
        reference="chief_ray",
        distribution="hexapolar",
        num_rings=3,
        airy_reference_wavelength_nm=587.6,
        fields=[
            SpotFieldData(
                field_index=0,
                field_coordinate=(0.0, 0.0),
                field_fraction=0.0,
                airy_radius_x_um=1.5,
                airy_radius_y_um=1.5,
                spots_by_wavelength=[
                    SpotWavelengthData(
                        wavelength_index=0,
                        wavelength_nm=587.6,
                        x_um=[0.0, 0.1],
                        y_um=[0.0, -0.1],
                        intensity=[1.0, 1.0],
                        rms_radius_um=0.1,
                        geometric_radius_um=0.2,
                    )
                ],
            )
        ],
    )


def _field_analysis() -> FieldAnalysisResult:
    return FieldAnalysisResult(
        field_fraction=[0.0, 1.0],
        field_coordinate=[0.0, 20.0],
        field_unit="deg",
        wavelength_nm=587.6,
        tangential_field_curvature_mm=[0.0, 0.02],
        sagittal_field_curvature_mm=[0.0, -0.01],
        distortion_pct=[0.0, 1.2],
    )


def _wavefront() -> WavefrontMetricsResult:
    return WavefrontMetricsResult(
        wavelength_nm=587.6,
        num_rays=6,
        distribution="hexapolar",
        strategy="chief_ray",
        remove_piston=True,
        remove_tilt=True,
        fields=[
            WavefrontFieldMetric(
                field_index=0,
                field_coordinate=(0.0, 0.0),
                field_fraction=0.0,
                wavelength_nm=587.6,
                rms_wavefront_error_waves=0.02,
                strehl_ratio=0.98,
                valid_ray_count=12,
                zernike_type="fringe",
                zernike_coefficients_waves=[0.0],
            )
        ],
    )


def test_analysis_artifacts_serialize_nonempty_legal_provenance() -> None:
    artefacts = {
        "paraxial": _paraxial(),
        "mtf": _mtf(),
        "spot_diagram": _spot_diagram(),
        "field_analysis": _field_analysis(),
        "wavefront": _wavefront(),
    }

    for name, artefact in artefacts.items():
        payload = artefact.model_dump(mode="json")
        assert payload["provenance"], name
        assert payload["provenance"] in LEGAL_PROVENANCE, name


def test_provenance_enum_reserves_codev_run() -> None:
    assert ProvenanceSource.CODEV_RUN.value == "codev-run"
    assert LEGAL_PROVENANCE == {
        "optiland-raytrace",
        "optiland-wavefront",
        "thin-lens-analytic",
        "codev-run",
    }


def test_invalid_provenance_is_rejected() -> None:
    payload = _paraxial().model_dump(mode="json")
    payload["provenance"] = "untracked-source"

    with pytest.raises(ValidationError):
        ParaxialSummary.model_validate(payload)


def test_homepage_renders_provenance_badges() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    html = response.text
    assert 'class="source-badge"' in html
    for source in (
        "thin-lens-analytic",
        "optiland-raytrace",
        "optiland-wavefront",
    ):
        assert f'data-provenance="{source}"' in html

