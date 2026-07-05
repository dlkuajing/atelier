"""Demo cache contract tests for offline-friendly analysis playback."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api import optical as optical_api
from app.api import wizard
from app.core.aberration import MTFFieldData, MTFResult
from app.core.demo_cache import (
    DemoAnalysisBundle,
    demo_cache_key,
    load_demo_cache_bundle_for_request,
    write_demo_cache_bundle,
)
from app.core.field_analysis import FieldAnalysisResult
from app.core.lens_system import LayoutSVG, RayPath, RayTraceResult, Scenario
from app.core.optical_engine import ParaxialSummary
from app.core.optical_sample import CaseMetadata, OpticalSampleData
from app.core.provenance import ProvenanceSource
from app.core.spot_diagram import SpotDiagramResult, SpotFieldData, SpotWavelengthData
from app.core.wavefront_metrics import WavefrontFieldMetric, WavefrontMetricsResult
from app.main import app


client = TestClient(app)


def _request_payload() -> dict[str, object]:
    return {
        "scenario": "smartphone-wide",
        "focal_length_mm": 2.7,
        "f_number": 2.5,
        "field_of_view_deg": 78.0,
        "image_height_mm": 2.3,
        "n_elements": 3,
        "wavelength_nm": 550.0,
        "analysis_depth": "seed_only",
    }


def _paraxial() -> ParaxialSummary:
    return ParaxialSummary(
        effective_focal_length_mm=2.71,
        f_number=2.5,
        entrance_pupil_diameter_mm=1.08,
        exit_pupil_diameter_mm=1.0,
        total_track_mm=4.44,
        n_surfaces=8,
        stop_surface_index=2,
    )


def _mtf() -> MTFResult:
    return MTFResult(
        freq_lp_per_mm=[0.0, 50.0],
        fields=[MTFFieldData(field_index=0, sagittal=[1.0, 0.62], tangential=[1.0, 0.58])],
        diff_limited=[1.0, 0.8],
        cutoff_freq_lp_per_mm=777.0,
        airy_disc_diameter_um=8.88,
        rms_spot_radius_um_by_field=[4.0],
    )


def _sample() -> OpticalSampleData:
    return OpticalSampleData(
        paraxial=_paraxial(),
        surfaces=[],
        trace=RayTraceResult(
            assembly_name="demo-seed",
            n_rays=1,
            sampled_paths=[
                RayPath(
                    ray_id="chief",
                    wavelength_nm=550.0,
                    field_angle_deg=0.0,
                    points_mm=[(0.0, 0.0), (1.0, 0.1)],
                    reaches_image=True,
                )
            ],
        ),
        mtf=_mtf(),
        layout_svg=LayoutSVG(width_px=100, height_px=50, svg_content="<svg></svg>"),
        metadata=CaseMetadata(
            case_id="3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56",
            source_zmx="3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56.ZMX",
            scenario=Scenario.SMARTPHONE_WIDE,
            n_pieces=3,
            n_imaging=3,
            n_filter=1,
            materials=["N-BK7"],
            fov_deg=78.0,
            nominal_efl_mm=2.7,
            computed_efl_mm=2.71,
            efl_error_pct=0.37,
            mtf_max_field_frac=1.0,
        ),
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
                airy_radius_x_um=1.0,
                airy_radius_y_um=1.0,
                spots_by_wavelength=[
                    SpotWavelengthData(
                        wavelength_index=0,
                        wavelength_nm=587.6,
                        x_um=[0.0],
                        y_um=[0.0],
                        intensity=[1.0],
                        rms_radius_um=0.1,
                        geometric_radius_um=0.1,
                    )
                ],
            )
        ],
    )


def _field() -> FieldAnalysisResult:
    return FieldAnalysisResult(
        field_fraction=[0.0, 1.0],
        field_coordinate=[0.0, 39.0],
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
                rms_wavefront_error_waves=0.03,
                strehl_ratio=0.96,
                valid_ray_count=12,
                zernike_type="fringe",
                zernike_coefficients_waves=[0.0],
            )
        ],
    )


def _bundle() -> DemoAnalysisBundle:
    request = optical_api.demo_cache_request(
        scenario=Scenario.SMARTPHONE_WIDE,
        focal_length_mm=2.7,
        f_number=2.5,
        field_of_view_deg=78.0,
        image_height_mm=2.3,
        n_elements=3,
        wavelength_nm=550.0,
    )
    sample = _sample()
    assert sample.metadata is not None
    return DemoAnalysisBundle(
        cache_key=demo_cache_key(request),
        generated_at_utc="2026-07-05T00:00:00+00:00",
        source_case_id=sample.metadata.case_id,
        source_zmx=sample.metadata.source_zmx,
        request=request,
        sample=sample,
        spot_diagram=_spot(),
        field_analysis=_field(),
        wavefront=_wavefront(),
    )


def test_demo_cache_round_trip_preserves_analysis_provenance(tmp_path):
    bundle = _bundle()

    path = write_demo_cache_bundle(bundle, cache_dir=tmp_path)
    loaded = load_demo_cache_bundle_for_request(bundle.request, cache_dir=tmp_path)

    assert path.is_file()
    assert loaded is not None
    assert loaded.cache_key == bundle.cache_key
    artefacts = (
        loaded.sample.paraxial,
        loaded.sample.mtf,
        loaded.spot_diagram,
        loaded.field_analysis,
        loaded.wavefront,
    )
    for artefact in artefacts:
        payload = artefact.model_dump(mode="json")
        assert payload["provenance"] in {source.value for source in ProvenanceSource}


def test_match_endpoint_cache_hit_and_fallback_return_same_payload(monkeypatch):
    bundle = _bundle()

    monkeypatch.setattr(optical_api, "load_demo_cache_bundle_for_request", lambda request: bundle)
    monkeypatch.setattr(
        optical_api,
        "match_case",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("runtime match not used")),
    )
    hit = client.post("/api/optical/match", json=_request_payload())

    monkeypatch.setattr(optical_api, "load_demo_cache_bundle_for_request", lambda request: None)
    monkeypatch.setattr(optical_api, "match_case", lambda **_kwargs: bundle.sample)
    fallback = client.post("/api/optical/match", json=_request_payload())

    assert hit.status_code == 200, hit.text
    assert fallback.status_code == 200, fallback.text
    assert hit.headers["X-Demo-Cache"] == "hit"
    assert fallback.headers["X-Demo-Cache"] == "miss"
    hit_json = hit.json()
    fallback_json = fallback.json()
    for key in ("paraxial", "trace", "mtf", "layout_svg", "metadata"):
        assert hit_json[key] == fallback_json[key]


def test_full_demo_cache_api_cache_hit_and_fallback_return_same_bundle(monkeypatch):
    bundle = _bundle()

    monkeypatch.setattr(optical_api, "load_demo_cache_bundle_for_request", lambda request: bundle)
    hit = client.post("/api/optical/demo-cache", json=_request_payload())

    monkeypatch.setattr(optical_api, "load_demo_cache_bundle_for_request", lambda request: None)
    monkeypatch.setattr(optical_api, "compute_demo_cache_bundle_for_request", lambda request: bundle)
    fallback = client.post("/api/optical/demo-cache", json=_request_payload())

    assert hit.status_code == 200, hit.text
    assert fallback.status_code == 200, fallback.text
    assert hit.headers["X-Demo-Cache"] == "hit"
    assert fallback.headers["X-Demo-Cache"] == "miss"
    assert hit.json()["sample"] == fallback.json()["sample"]
    assert hit.json()["spot_diagram"] == fallback.json()["spot_diagram"]
    assert hit.json()["field_analysis"] == fallback.json()["field_analysis"]
    assert hit.json()["wavefront"] == fallback.json()["wavefront"]


def test_result_summary_page_prefers_cached_metrics(monkeypatch):
    bundle = _bundle()
    monkeypatch.setattr("app.main.load_demo_cache_bundle_for_request", lambda request: bundle)
    summary = wizard.ExecutiveSummaryResponse(
        summary_en="Cached metric summary.",
        summary_zh="\u7f13\u5b58\u6307\u6807\u6458\u8981\u3002",
        model="test-model",
    )
    monkeypatch.setattr(
        "app.main.wizard.generate_executive_summary",
        AsyncMock(return_value=summary),
    )

    response = client.post(
        "/results/summary",
        data={
            **_request_payload(),
            "scenario_label_en": "Smartphone Wide",
            "total_track_mm": 99.0,
            "airy_disc_diameter_um": 99.0,
            "cutoff_freq_lp_per_mm": 99.0,
        },
    )

    assert response.status_code == 200, response.text
    html = response.text
    assert 'data-demo-cache="hit"' in html
    assert "4.44 mm" in html
    assert "8.88 um" in html
    assert "777 lp/mm" in html
    assert "99.00 mm" not in html
