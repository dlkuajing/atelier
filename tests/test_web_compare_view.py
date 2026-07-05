"""Web contract for the seed vs CODE V refinement comparison block."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api import wizard
from app.core.aberration import MTFFieldData, MTFResult
from app.core.demo_cache import (
    DEMO_CACHE_ANALYSIS_FINGERPRINT,
    DemoAnalysisBundle,
    demo_cache_request,
)
from app.core.field_analysis import FieldAnalysisResult
from app.core.lens_system import LayoutSVG, RayPath, RayTraceResult, Scenario
from app.core.optical_engine import ParaxialSummary, SurfaceDescriptor
from app.core.optical_sample import CaseMetadata, OpticalSampleData
from app.core.spot_diagram import SpotDiagramResult, SpotFieldData, SpotWavelengthData
from app.core.wavefront_metrics import WavefrontFieldMetric, WavefrontMetricsResult
from app.main import app


client = TestClient(app)


def _summary_form_payload() -> dict[str, object]:
    return {
        "scenario": "smartphone-wide",
        "scenario_label_en": "Smartphone Wide",
        "focal_length_mm": 3.6,
        "f_number": 1.9,
        "field_of_view_deg": 76.0,
        "image_height_mm": 3.0,
        "n_elements": 5,
        "wavelength_nm": 550.0,
        "total_track_mm": 4.2,
        "airy_disc_diameter_um": 2.6,
        "cutoff_freq_lp_per_mm": 810.0,
        "requirement": "Show a CODE V refinement comparison without a local CODE V run.",
    }


def _mtf(*, refined: bool = False) -> MTFResult:
    if refined:
        freqs = [0.0, 80.0, 160.0, 240.0]
        fields = [
            MTFFieldData(
                field_index=0,
                sagittal=[1.0, 0.82, 0.64, 0.48],
                tangential=[1.0, 0.78, 0.59, 0.43],
            )
        ]
        rms = [2.0]
    else:
        freqs = [0.0, 50.0, 100.0, 150.0]
        fields = [
            MTFFieldData(
                field_index=0,
                sagittal=[1.0, 0.70, 0.48, 0.30],
                tangential=[1.0, 0.66, 0.42, 0.26],
            )
        ]
        rms = [5.0]
    return MTFResult(
        freq_lp_per_mm=freqs,
        fields=fields,
        diff_limited=[1.0, 0.9, 0.78, 0.63],
        cutoff_freq_lp_per_mm=810.0,
        airy_disc_diameter_um=2.6,
        rms_spot_radius_um_by_field=rms,
    )


def _spot() -> SpotDiagramResult:
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
                airy_radius_x_um=1.3,
                airy_radius_y_um=1.3,
                spots_by_wavelength=[
                    SpotWavelengthData(
                        wavelength_index=0,
                        wavelength_nm=587.6,
                        x_um=[0.0],
                        y_um=[0.0],
                        intensity=[1.0],
                        rms_radius_um=0.1,
                        geometric_radius_um=0.2,
                    )
                ],
            )
        ],
    )


def _field() -> FieldAnalysisResult:
    return FieldAnalysisResult(
        field_fraction=[0.0, 1.0],
        field_coordinate=[0.0, 38.0],
        field_unit="deg",
        wavelength_nm=587.6,
        tangential_field_curvature_mm=[0.0, 0.02],
        sagittal_field_curvature_mm=[0.0, -0.01],
        distortion_pct=[0.0, 1.0],
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
                rms_wavefront_error_waves=0.05,
                strehl_ratio=0.91,
                valid_ray_count=12,
                zernike_type="fringe",
                zernike_coefficients_waves=[0.0],
            )
        ],
    )


def _sample() -> OpticalSampleData:
    return OpticalSampleData(
        paraxial=ParaxialSummary(
            effective_focal_length_mm=3.62,
            f_number=1.9,
            entrance_pupil_diameter_mm=1.9,
            exit_pupil_diameter_mm=1.7,
            total_track_mm=4.2,
            n_surfaces=10,
            stop_surface_index=3,
        ),
        surfaces=[
            SurfaceDescriptor(
                index=0,
                z_mm=0.0,
                radius_mm=12.0,
                is_stop=False,
                is_image=False,
                is_object=True,
            )
        ],
        trace=RayTraceResult(
            assembly_name="CODE V comparison fixture",
            n_rays=3,
            sampled_paths=[
                RayPath(
                    ray_id="chief",
                    wavelength_nm=550.0,
                    field_angle_deg=0.0,
                    points_mm=[(0.0, 0.0), (4.2, 0.0)],
                    reaches_image=True,
                )
            ],
        ),
        mtf=_mtf(),
        layout_svg=LayoutSVG(width_px=100, height_px=50, svg_content="<svg></svg>"),
        metadata=CaseMetadata(
            case_id="US20170003482A1",
            source_zmx="US20170003482A1.zmx",
            scenario=Scenario.SMARTPHONE_WIDE,
            n_pieces=5,
            n_imaging=5,
            n_filter=1,
            materials=["OKP4"],
            fov_deg=76.0,
            image_height_mm=3.0,
            nominal_efl_mm=3.6,
            computed_efl_mm=3.62,
            efl_error_pct=0.55,
            mtf_max_field_frac=1.0,
        ),
    )


def _run_evidence() -> dict[str, object]:
    return {
        "run_started_at_utc": "2026-07-06T00:00:00+00:00",
        "codev_executable": "D:/CODEV115/codev.exe",
        "codev_version": "11.5.27302.701",
        "returncode": 1,
        "duration_seconds": 12.3,
        "source_zmx_sha256": "a" * 64,
        "sequence_sha256": "b" * 64,
        "result_sha256": "c" * 64,
        "optimized_readout_sha256": "d" * 64,
        "optimized_zmx_sha256": "e" * 64,
    }


def _codev_artifact(*, include_run_evidence: bool = False) -> dict[str, object]:
    artifact = {
        "source_zmx": "US20170003482A1.zmx",
        "optimization_status": "aut_completed",
        "glass_policy": "glass-not-varied",
        "thickness_policy": "MNT/MNE/MXT/MNA bounded in AUT",
        "optimized_readout_path": "atelier_codev_optimized_readout.tsv",
        "optimized_zmx_filename": "optimized.zmx",
        "before": {
            "efl_y_mm": 3.62252,
            "max_lateral_color_um": 0.615114,
            "max_rms_spot_diameter_um": 10.0,
            "max_rms_wavefront_error_waves": 0.2,
            "max_distortion_pct": 2.00747,
        },
        "after": {
            "efl_y_mm": 3.62249,
            "max_lateral_color_um": 0.0502348,
            "max_rms_spot_diameter_um": 4.0,
            "max_rms_wavefront_error_waves": 0.05,
            "max_distortion_pct": 1.1004,
        },
        "efl_deviation_pct": 0.0008,
        "seed_mtf": _mtf().model_dump(mode="json"),
        "refined_mtf": _mtf(refined=True).model_dump(mode="json"),
        "cross_validation_status": "rebuilt-zmx-ingested",
        "cross_validation_provenance": "codev-cross-validated",
    }
    if include_run_evidence:
        artifact["run_evidence"] = _run_evidence()
    return artifact


def _bundle(*, include_run_evidence: bool = False) -> DemoAnalysisBundle:
    request = demo_cache_request(
        scenario=Scenario.SMARTPHONE_WIDE,
        focal_length_mm=3.6,
        f_number=1.9,
        field_of_view_deg=76.0,
        image_height_mm=3.0,
        n_elements=5,
        wavelength_nm=550.0,
    )
    return DemoAnalysisBundle(
        cache_key="smartphone-wide-codev-compare-fixture",
        analysis_fingerprint=DEMO_CACHE_ANALYSIS_FINGERPRINT,
        generated_at_utc="2026-07-06T00:00:00+00:00",
        source_case_id="US20170003482A1",
        source_zmx="US20170003482A1.zmx",
        source_zmx_sha256="0" * 64,
        request=request,
        sample=_sample(),
        spot_diagram=_spot(),
        field_analysis=_field(),
        wavefront=_wavefront(),
        codev_artifact=_codev_artifact(include_run_evidence=include_run_evidence),
    )


def _metric_provenance(html: str, metric: str) -> str:
    match = re.search(
        rf'data-compare-metric="{metric}"\s+data-provenance="([^"]+)"',
        html,
    )
    assert match is not None
    return match.group(1)


def test_result_page_renders_fixture_refinement_as_optiland_estimate(monkeypatch):
    monkeypatch.setattr("app.main.load_demo_cache_bundle_for_request", lambda _request: _bundle())
    monkeypatch.setattr(
        "app.main.wizard.generate_executive_summary",
        AsyncMock(
            return_value=wizard.ExecutiveSummaryResponse(
                summary_en="Cached CODE V comparison summary.",
                summary_zh="缓存的 CODE V 对比摘要。",
                model="test-model",
            )
        ),
    )

    response = client.post("/results/summary", data=_summary_form_payload())

    assert response.status_code == 200, response.text
    html = response.text
    assert 'data-demo-cache="hit"' in html
    assert "种子 vs CODE V 精修" in html
    assert 'data-codev-compare' in html
    assert re.search(r'data-codev-compare.*?data-available="true"', html, re.S)

    assert 'data-compare-artifact="mtf-overlay"' in html
    assert 'class="mtf-curve mtf-curve-seed"' in html
    assert 'class="mtf-curve mtf-curve-refined"' in html
    assert "MTF curve overlay" in html
    assert re.search(r'class="mtf-curve mtf-curve-refined" points="[^"]*396\.0,', html)
    assert "seed/refined frequency samples 4/4" in html

    assert 'data-compare-metric="spot-rms-shrink-pct"' in html
    assert "60.0%" in html
    assert "10.00 -&gt; 4.00 um diameter" in html
    assert 'data-compare-metric="wavefront-rms-delta"' in html
    assert "-0.150 waves" in html
    assert "0.200 -&gt; 0.050 waves" in html
    assert 'data-compare-metric="efl-cross-check"' in html
    assert "0.0008% EFL drift" in html

    for source in ("optiland-raytrace", "optiland-estimate"):
        assert f'data-provenance="{source}"' in html
    assert 'data-provenance="codev-run"' not in html
    assert 'data-validation-provenance="optiland-estimate"' in html

    for metric in (
        "spot-rms-shrink-pct",
        "wavefront-rms-delta",
        "efl-cross-check",
    ):
        assert _metric_provenance(html, metric) == "optiland-estimate"


def test_result_page_marks_codev_run_only_when_run_evidence_is_present(monkeypatch):
    monkeypatch.setattr(
        "app.main.load_demo_cache_bundle_for_request",
        lambda _request: _bundle(include_run_evidence=True),
    )
    monkeypatch.setattr(
        "app.main.wizard.generate_executive_summary",
        AsyncMock(
            return_value=wizard.ExecutiveSummaryResponse(
                summary_en="Cached CODE V comparison summary.",
                summary_zh="缓存的 CODE V 对比摘要。",
                model="test-model",
            )
        ),
    )

    response = client.post("/results/summary", data=_summary_form_payload())

    assert response.status_code == 200, response.text
    html = response.text
    assert 'data-provenance="codev-run"' in html
    assert 'data-validation-provenance="codev-cross-validated"' in html
    assert _metric_provenance(html, "spot-rms-shrink-pct") == "codev-run"
    assert _metric_provenance(html, "wavefront-rms-delta") == "codev-run"
    assert _metric_provenance(html, "efl-cross-check") == "codev-cross-validated"
