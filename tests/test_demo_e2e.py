"""Full demo narrative E2E contract test."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import main
from app.api import optical
from app.core.aberration import MTFFieldData, MTFResult
from app.core.engines import SleepEngine
from app.core.field_analysis import FieldAnalysisResult
from app.core.job_store import JobStore
from app.core.lens_system import LayoutSVG, RayPath, RayTraceResult, Scenario
from app.core.optical_engine import ParaxialSummary, SurfaceDescriptor
from app.core.optical_sample import CaseMetadata, OpticalSampleData
from app.core.spot_diagram import SpotDiagramResult, SpotFieldData, SpotWavelengthData
from app.core.wavefront_metrics import WavefrontFieldMetric, WavefrontMetricsResult
from app.main import app


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


def _summary_form_payload(*, job_id: str, requirement: str) -> dict[str, object]:
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
        "requirement": requirement,
        "job_id": job_id,
    }


def _complete_sample_payload() -> OpticalSampleData:
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
            assembly_name="Demo E2E phone wide optic",
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
                MTFFieldData(
                    field_index=0,
                    sagittal=[1.0, 0.8, 0.55],
                    tangential=[1.0, 0.78, 0.5],
                ),
                MTFFieldData(
                    field_index=1,
                    sagittal=[1.0, 0.7, 0.42],
                    tangential=[1.0, 0.66, 0.39],
                ),
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
            case_id="DEMO_E2E",
            source_zmx="DEMO_E2E.zmx",
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
def test_demo_e2e_runs_full_narrative_contract(mock_get_client, monkeypatch):
    requirement = "Design a compact wide phone camera with credible full-stack analysis."
    summary_en = "Demo E2E summary ties the confirmed phone-wide target to optical evidence."
    summary_zh = "演示端到端摘要已把手机广角目标、分析证据与深引擎任务串联起来。"

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            _mock_chat_response(
                json.dumps(
                    {
                        "scenario": "smartphone-wide",
                        "focal_length_mm": 3.8,
                        "f_number": 1.9,
                        "field_of_view_deg": 78.0,
                        "image_height_mm": 3.2,
                        "n_elements": 5,
                        "reasoning": "Phone wide request with a compact track.",
                    }
                )
            ),
            _mock_chat_response(
                json.dumps(
                    {
                        "summary_en": summary_en,
                        "summary_zh": summary_zh,
                    },
                    ensure_ascii=False,
                )
            ),
        ]
    )
    mock_get_client.return_value = mock_client

    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)
    monkeypatch.setattr(optical, "get_deep_engine", lambda: SleepEngine(delay_seconds=0.001))

    seen_match_requests: list[optical.OpticalSpecRequest] = []

    async def fake_match(req: optical.OpticalSpecRequest) -> OpticalSampleData:
        seen_match_requests.append(req)
        return _complete_sample_payload()

    monkeypatch.setattr(main.optical, "match", fake_match)

    with TestClient(app) as client:
        confirmation = client.post("/wizard/confirm", data={"requirement": requirement})
        assert confirmation.status_code == 200, confirmation.text
        confirmation_html = confirmation.text
        assert "Confirm extracted scenario" in confirmation_html
        assert 'data-scenario="smartphone-wide"' in confirmation_html
        assert requirement in confirmation_html
        assert "Phone wide request with a compact track." in confirmation_html
        assert 'data-field="focal_length_mm"' in confirmation_html
        assert "3.8 mm" in confirmation_html

        submitted = client.post(
            "/api/optical/jobs",
            json={"payload": {"case_id": "DEMO_E2E", "requirement": requirement}},
        )
        assert submitted.status_code == 202, submitted.text
        job_id = submitted.json()["job_id"]

        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            assert streamed.status_code == 200
            assert streamed.headers["content-type"].startswith("text/event-stream")
            sse_body = "".join(streamed.iter_text())

        assert "event: succeeded" in sse_body
        assert f'"job_id":"{job_id}"' in sse_body
        assert '"engine":"sleep"' in sse_body
        assert '"status":"succeeded"' in sse_body
        assert '"case_id":"DEMO_E2E"' in sse_body

        result = client.post(
            "/results/summary",
            data=_summary_form_payload(job_id=job_id, requirement=requirement),
        )

    assert result.status_code == 200, result.text
    html = result.text
    assert "Design result" in html
    assert "data-result-page" in html
    assert "data-result-summary" in html
    assert 'data-scenario="smartphone-wide"' in html

    assert 'data-narrative-section="scenario-confirmation"' in html
    assert requirement in html
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
    assert "DEMO_E2E / DEMO_E2E.zmx" in html
    for source in (
        "thin-lens-analytic",
        "optiland-raytrace",
        "optiland-wavefront",
    ):
        assert f'data-provenance="{source}"' in html

    assert "data-result-progress" in html
    assert f'data-job-id="{job_id}"' in html
    assert 'data-status="succeeded"' in html
    assert 'style="width: 100%;"' in html

    assert 'data-narrative-section="bilingual-summary"' in html
    assert 'data-summary-lang="en"' in html
    assert summary_en in html
    assert 'data-summary-lang="zh"' in html
    assert summary_zh in html

    assert len(seen_match_requests) == 1
    assert seen_match_requests[0].scenario == Scenario.SMARTPHONE_WIDE
    assert seen_match_requests[0].analysis_depth == "seed_only"
    assert seen_match_requests[0].max_total_track_mm == 4.35

    assert mock_client.chat.completions.create.await_count == 2
    extraction_messages = mock_client.chat.completions.create.call_args_list[0].kwargs["messages"]
    summary_messages = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert extraction_messages[1]["content"] == requirement
    assert "Scenario: Smartphone Wide (smartphone-wide)" in summary_messages[1]["content"]
