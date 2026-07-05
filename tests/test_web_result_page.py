"""Integrated web result page contract tests."""

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import main
from app.core.aberration import MTFFieldData, MTFResult
from app.core.field_analysis import FieldAnalysisResult
from app.core.job_store import JobNotFoundError, JobRecord, JobStatus
from app.core.lens_system import LayoutSVG, RayPath, RayTraceResult, Scenario
from app.core.optical_engine import ParaxialSummary, SurfaceDescriptor
from app.core.optical_sample import CaseMetadata, OpticalSampleData
from app.core.spot_diagram import SpotDiagramResult, SpotFieldData, SpotWavelengthData
from app.core.wavefront_metrics import WavefrontFieldMetric, WavefrontMetricsResult
from app.main import app


client = TestClient(app)


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


def _stub_summary_generation(
    mock_get_client,
    *,
    summary_en: str = "Integrated result narrative with optical evidence.",
    summary_zh: str = "\u7ed3\u679c\u9875\u5df2\u4e32\u8d77\u5b8c\u6574\u53d9\u4e8b\u3002",
) -> str:
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            json.dumps(
                {
                    "summary_en": summary_en,
                    "summary_zh": summary_zh,
                },
                ensure_ascii=False,
            )
        )
    )
    mock_get_client.return_value = mock_client
    return summary_zh


def _summary_form_payload() -> dict[str, object]:
    return {
        "scenario": "smartphone-wide",
        "scenario_label_en": "Smartphone Wide",
        "focal_length_mm": 3.8,
        "f_number": 1.9,
        "field_of_view_deg": 78.0,
        "image_height_mm": 3.2,
        "n_elements": 5,
        "wavelength_nm": 550.0,
        "total_track_mm": 4.35,
        "airy_disc_diameter_um": 2.55,
        "cutoff_freq_lp_per_mm": 820,
        "requirement": "Design a compact wide phone camera with credible analysis.",
        "job_id": "job-ui-04a",
    }


def _job_record(
    *,
    job_id: str = "job-ui-04a",
    status: JobStatus = JobStatus.SUCCEEDED,
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        engine="sleep",
        status=status,
        payload={"case_id": "demo"},
        result={"case_id": "demo"} if status is JobStatus.SUCCEEDED else None,
    )


def _install_job_store(monkeypatch, record: JobRecord) -> None:
    class StaticJobStore:
        def get(self, job_id: str) -> JobRecord:
            if job_id != record.job_id:
                raise JobNotFoundError(job_id)
            return record

    monkeypatch.setattr(main.optical, "job_store", StaticJobStore())


def _sample_payload() -> OpticalSampleData:
    return OpticalSampleData(
        paraxial=ParaxialSummary(
            effective_focal_length_mm=3.82,
            f_number=1.91,
            entrance_pupil_diameter_mm=2.0,
            exit_pupil_diameter_mm=1.8,
            total_track_mm=4.31,
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
            ),
            SurfaceDescriptor(
                index=1,
                z_mm=1.2,
                radius_mm=-8.0,
                is_stop=True,
                is_image=False,
                is_object=False,
            ),
        ],
        trace=RayTraceResult(
            assembly_name="Demo wide phone optic",
            n_rays=3,
            sampled_paths=[
                RayPath(
                    ray_id="chief",
                    wavelength_nm=550.0,
                    field_angle_deg=0.0,
                    points_mm=[(0.0, 0.0), (4.0, 0.0)],
                    reaches_image=True,
                )
            ],
        ),
        mtf=MTFResult(
            freq_lp_per_mm=[0.0, 50.0, 100.0],
            fields=[
                MTFFieldData(field_index=0, sagittal=[1.0, 0.8, 0.55], tangential=[1.0, 0.78, 0.5]),
                MTFFieldData(field_index=1, sagittal=[1.0, 0.7, 0.42], tangential=[1.0, 0.66, 0.39]),
            ],
            diff_limited=[1.0, 0.9, 0.75],
            cutoff_freq_lp_per_mm=820.0,
            airy_disc_diameter_um=2.55,
            rms_spot_radius_um_by_field=[3.5, 4.8],
        ),
        layout_svg=LayoutSVG(
            width_px=1200,
            height_px=600,
            svg_content='<svg viewBox="0 0 10 10"><path d="M0 5 L10 5"/></svg>',
        ),
        spot_diagram=SpotDiagramResult(
            coordinates="local",
            reference="chief_ray",
            distribution="hexapolar",
            num_rings=3,
            airy_reference_wavelength_nm=550.0,
            fields=[
                SpotFieldData(
                    field_index=0,
                    field_coordinate=(0.0, 0.0),
                    field_fraction=0.0,
                    airy_radius_x_um=1.4,
                    airy_radius_y_um=1.4,
                    spots_by_wavelength=[
                        SpotWavelengthData(
                            wavelength_index=0,
                            wavelength_nm=550.0,
                            x_um=[0.0, 0.1],
                            y_um=[0.0, -0.1],
                            intensity=[1.0, 1.0],
                            rms_radius_um=0.2,
                            geometric_radius_um=0.3,
                        )
                    ],
                )
            ],
        ),
        field_analysis=FieldAnalysisResult(
            field_fraction=[0.0, 1.0],
            field_coordinate=[0.0, 39.0],
            field_unit="deg",
            wavelength_nm=550.0,
            tangential_field_curvature_mm=[0.0, 0.02],
            sagittal_field_curvature_mm=[0.0, -0.01],
            distortion_pct=[0.0, 1.1],
        ),
        wavefront=WavefrontMetricsResult(
            wavelength_nm=550.0,
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
                    wavelength_nm=550.0,
                    rms_wavefront_error_waves=0.03,
                    strehl_ratio=0.965,
                    valid_ray_count=12,
                    zernike_type="fringe",
                    zernike_coefficients_waves=[0.0, 0.01],
                )
            ],
        ),
        metadata=CaseMetadata(
            case_id="DEMO_WIDE",
            source_zmx="DEMO_WIDE.zmx",
            scenario=Scenario.SMARTPHONE_WIDE,
            n_pieces=5,
            n_imaging=5,
            n_filter=1,
            materials=["OKP4", "EP8000"],
            fov_deg=78.0,
            nominal_efl_mm=3.8,
            computed_efl_mm=3.82,
            efl_error_pct=0.53,
            mtf_max_field_frac=1.0,
        ),
    )


@patch("app.api.wizard.get_async_client")
def test_result_page_integrates_full_narrative_from_optical_sample(
    mock_get_client,
    monkeypatch,
):
    summary_zh = _stub_summary_generation(mock_get_client)
    _install_job_store(monkeypatch, _job_record())

    seen: dict[str, object] = {}

    async def fake_match(req):
        seen["request"] = req
        return _sample_payload()

    monkeypatch.setattr(main.optical, "match", fake_match)

    response = client.post("/results/summary", data=_summary_form_payload())

    assert response.status_code == 200, response.text
    html = response.text

    assert "Design result" in html
    assert "data-result-page" in html
    assert "data-result-summary" in html
    assert 'data-scenario="smartphone-wide"' in html

    assert 'data-narrative-section="scenario-confirmation"' in html
    assert "Design a compact wide phone camera with credible analysis." in html
    assert "Smartphone Wide" in html

    assert 'data-narrative-section="analysis-suite"' in html
    for artifact in (
        "layout-svg",
        "mtf",
        "spot-diagram",
        "field-analysis",
        "wavefront",
    ):
        assert f'data-analysis-artifact="{artifact}"' in html
    assert "<svg" in html
    assert "DEMO_WIDE / DEMO_WIDE.zmx" in html

    for source in (
        "thin-lens-analytic",
        "optiland-raytrace",
        "optiland-wavefront",
    ):
        assert f'data-provenance="{source}"' in html

    assert "data-result-progress" in html
    assert 'data-job-id="job-ui-04a"' in html
    assert 'id="job-progress-bar"' in html
    assert 'style="width: 100%;"' in html

    assert 'data-narrative-section="bilingual-summary"' in html
    assert 'data-summary-lang="en"' in html
    assert "Integrated result narrative with optical evidence." in html
    assert 'data-summary-lang="zh"' in html
    assert summary_zh in html

    req = seen["request"]
    assert req.scenario == Scenario.SMARTPHONE_WIDE
    assert req.analysis_depth == "seed_only"
    assert req.max_total_track_mm == 4.35


def test_result_page_rejects_n_elements_above_optical_spec_limit():
    payload = _summary_form_payload()
    payload["n_elements"] = 21

    response = client.post("/results/summary", data=payload)

    assert response.status_code == 422
    assert "n_elements" in response.text


@patch("app.api.wizard.get_async_client")
def test_result_page_marks_missing_spot_diagram_as_unavailable_partial(
    mock_get_client,
    monkeypatch,
):
    _stub_summary_generation(mock_get_client)
    _install_job_store(monkeypatch, _job_record())

    async def fake_match(_req):
        return _sample_payload().model_copy(update={"spot_diagram": None})

    monkeypatch.setattr(main.optical, "match", fake_match)

    response = client.post("/results/summary", data=_summary_form_payload())

    assert response.status_code == 200, response.text
    assert re.search(
        r'data-analysis-artifact="spot-diagram".*?'
        r'data-available="false".*?'
        r'data-partial="true"',
        response.text,
        re.S,
    )
    assert "MTF-linked RMS spot evidence" in response.text


@patch("app.api.wizard.get_async_client")
def test_result_page_uses_job_store_status_when_job_id_is_present(
    mock_get_client,
    monkeypatch,
):
    _stub_summary_generation(mock_get_client)
    _install_job_store(monkeypatch, _job_record(job_id="job-running", status=JobStatus.RUNNING))

    async def fake_match(_req):
        return _sample_payload()

    monkeypatch.setattr(main.optical, "match", fake_match)
    payload = _summary_form_payload()
    payload["job_id"] = "job-running"

    response = client.post("/results/summary", data=payload)

    assert response.status_code == 200, response.text
    html = response.text
    assert 'data-job-id="job-running"' in html
    assert 'data-status="running"' in html
    assert "Running" in html
    assert 'style="width: 55%;"' in html
    assert "Engine is computing the optical design package." in html
