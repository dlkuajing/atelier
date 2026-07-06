"""Full demo narrative E2E contract test."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api import optical
from app.core.job_store import JobStore
from app.main import app


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


class _ResultSummaryFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_result_summary_form = False
        self.action: str | None = None
        self.method: str | None = None
        self.fields: dict[str, str] = {}
        self.button_types: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: value or "" for name, value in attrs}
        if tag == "form" and attr.get("data-confirmation-form") == "result-summary":
            self.in_result_summary_form = True
            self.action = attr.get("action")
            self.method = attr.get("method")
            return

        if not self.in_result_summary_form:
            return

        if tag == "input" and attr.get("type") == "hidden":
            self.fields[attr["name"]] = attr.get("value", "")
        if tag == "button":
            self.button_types.append(attr.get("type", "submit"))

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self.in_result_summary_form:
            self.in_result_summary_form = False


def _result_summary_form(html: str) -> _ResultSummaryFormParser:
    parser = _ResultSummaryFormParser()
    parser.feed(html)
    assert parser.action == "/jobs"
    assert parser.method == "post"
    assert "submit" in parser.button_types
    return parser


def _analysis_card_html(html: str, artifact: str) -> str:
    match = re.search(
        rf'<section\b(?=[^>]*data-analysis-artifact="{re.escape(artifact)}")[^>]*>.*?</section>',
        html,
        re.S,
    )
    assert match is not None, artifact
    return match.group(0)


def _assert_analysis_card(
    html: str,
    *,
    artifact: str,
    available: str,
    provenance: str,
    snippets: tuple[str, ...],
) -> None:
    card = _analysis_card_html(html, artifact)
    assert f'data-available="{available}"' in card
    assert f'data-provenance="{provenance}"' in card
    for snippet in snippets:
        assert snippet in card


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
        form = _result_summary_form(confirmation_html)
        form_fields = form.fields
        assert {
            "scenario",
            "scenario_label_en",
            "focal_length_mm",
            "f_number",
            "field_of_view_deg",
            "image_height_mm",
            "n_elements",
            "wavelength_nm",
            "total_track_mm",
            "airy_disc_diameter_um",
            "cutoff_freq_lp_per_mm",
            "requirement",
            "job_id",
        }.issubset(form_fields)
        assert form_fields["scenario"] == "smartphone-wide"
        assert form_fields["scenario_label_en"] == "Smartphone Wide"
        assert form_fields["requirement"] == requirement
        assert float(form_fields["focal_length_mm"]) == 3.8
        assert float(form_fields["f_number"]) == 1.9
        assert float(form_fields["field_of_view_deg"]) == 78.0
        assert float(form_fields["image_height_mm"]) == 3.2
        assert int(form_fields["n_elements"]) == 5
        assert float(form_fields["total_track_mm"]) > 0.0
        assert float(form_fields["airy_disc_diameter_um"]) > 0.0
        assert float(form_fields["cutoff_freq_lp_per_mm"]) > 0.0

        submitted = client.post(form.action, data=form_fields, follow_redirects=False)
        assert submitted.status_code == 303, submitted.text
        location = submitted.headers["location"]
        assert location.startswith("/jobs/")
        job_id = location.rsplit("/", 1)[1]

        progress = client.get(location)
        assert progress.status_code == 200, progress.text
        assert f'data-job-id="{job_id}"' in progress.text
        assert f'data-result-url="/results/{job_id}"' in progress.text
        assert "window.location.assign" in progress.text

        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            assert streamed.status_code == 200
            assert streamed.headers["content-type"].startswith("text/event-stream")
            sse_body = "".join(streamed.iter_text())

        assert "event: succeeded" in sse_body
        assert f'"job_id":"{job_id}"' in sse_body
        assert '"engine":"result-summary"' in sse_body
        assert '"status":"succeeded"' in sse_body
        assert '"scenario":"smartphone-wide"' in sse_body

        result = client.get(f"/results/{job_id}")
        assert result.status_code == 200, result.text
        summary_job_match = re.search(r'data-summary-job-id="([^"]+)"', result.text)
        assert summary_job_match is not None
        summary_job_id = summary_job_match.group(1)

        with client.stream("GET", f"/api/optical/jobs/{summary_job_id}/events") as streamed:
            assert streamed.status_code == 200
            assert streamed.headers["content-type"].startswith("text/event-stream")
            summary_sse_body = "".join(streamed.iter_text())

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
    _assert_analysis_card(
        html,
        artifact="layout-svg",
        available="true",
        provenance="optiland-raytrace",
        snippets=("<svg", "Ray path layout"),
    )
    _assert_analysis_card(
        html,
        artifact="mtf",
        available="true",
        provenance="optiland-raytrace",
        snippets=("4 fields, 256 samples.", "Diffraction cutoff 830 lp/mm."),
    )
    _assert_analysis_card(
        html,
        artifact="spot-diagram",
        available="true",
        provenance="optiland-raytrace",
        snippets=("2 fields x 1 wavelengths.", "hexapolar distribution"),
    )
    _assert_analysis_card(
        html,
        artifact="field-analysis",
        available="true",
        provenance="optiland-raytrace",
        snippets=("32 points, deg field axis.", "f-tan distortion model."),
    )
    _assert_analysis_card(
        html,
        artifact="wavefront",
        available="true",
        provenance="optiland-wavefront",
        snippets=("1 fields at 587.6 nm.", "Minimum Strehl 0.000."),
    )
    assert "<svg" in html
    assert (
        "5P_F2.0_FOV78.8_EFL3.8_IMH3.2_TTL4.30 / "
        "5P_F2.0_FOV78.8_EFL3.8_IMH3.2_TTL4.30.zmx"
    ) in html
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
    assert 'data-summary-lang="zh"' in html
    assert 'data-summary-status="pending"' in html
    assert f'data-summary-job-id="{summary_job_id}"' in html
    assert "executive_summary_pending" in html
    summary_event = re.search(r"event: succeeded\ndata: (.+)", summary_sse_body)
    assert summary_event is not None
    summary_payload = json.loads(summary_event.group(1))
    assert summary_payload["result"]["summary"]["summary_en"] == summary_en
    assert summary_payload["result"]["summary"]["summary_zh"] == summary_zh

    assert mock_client.chat.completions.create.await_count == 2
    extraction_messages = mock_client.chat.completions.create.call_args_list[0].kwargs["messages"]
    summary_messages = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert extraction_messages[1]["content"] == requirement
    assert "Scenario: Smartphone Wide (smartphone-wide)" in summary_messages[1]["content"]
    assert "Total track length: 4.30 mm" in summary_messages[1]["content"]
