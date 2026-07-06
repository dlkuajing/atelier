"""Web result summary contract tests."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app import main
from app.main import app


client = TestClient(app)


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


def _summary_form_payload() -> dict[str, object]:
    return {
        "scenario": "smartphone-telephoto",
        "scenario_label_en": "Smartphone Telephoto",
        "focal_length_mm": 7.0,
        "f_number": 2.4,
        "field_of_view_deg": 30.0,
        "image_height_mm": 3.7,
        "n_elements": 7,
        "wavelength_nm": 550.0,
        "total_track_mm": 5.85,
        "airy_disc_diameter_um": 3.22,
        "cutoff_freq_lp_per_mm": 758,
    }


@patch("app.api.wizard.get_async_client")
def test_result_summary_page_renders_deferred_executive_summary_shell(
    mock_get_client,
    monkeypatch,
):
    mock_get_client.side_effect = AssertionError("result page synchronously awaited LLM")
    monkeypatch.setattr(main, "_submit_executive_summary_job", lambda _payload: "summary-job-tele")

    response = client.post("/results/summary", data=_summary_form_payload())

    assert response.status_code == 200, response.text
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "Design result" in html
    assert 'data-result-summary' in html
    assert 'data-scenario="smartphone-telephoto"' in html
    assert 'data-summary-lang="en"' in html
    assert 'class="summary-panel summary-en"' in html
    assert 'lang="en"' in html
    assert "Executive Summary" in html
    assert 'data-summary-lang="zh"' in html
    assert 'class="summary-panel summary-zh"' in html
    assert 'lang="zh-Hans"' in html
    assert "\u6267\u884c\u6458\u8981" in html
    assert 'data-summary-status="pending"' in html
    assert 'data-summary-job-id="summary-job-tele"' in html
    assert "executive_summary_pending" in html
    assert mock_get_client.call_count == 0


@patch("app.api.wizard.get_async_client")
def test_executive_summary_job_generates_bilingual_summary(mock_get_client):
    summary_zh = "\u8fd9\u662f\u4e00\u6bb5\u4e2d\u6587\u6267\u884c\u6458\u8981\u3002"
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            json.dumps(
                {
                    "summary_en": (
                        "English executive summary for a compact phone telephoto result."
                    ),
                    "summary_zh": summary_zh,
                },
                ensure_ascii=False,
            )
        )
    )
    mock_get_client.return_value = mock_client

    result = asyncio.run(
        main._compute_executive_summary_job(
            {
                "job_type": "executive-summary",
                "request": _summary_form_payload(),
            }
        )
    )

    assert result["job_type"] == "executive-summary"
    assert result["summary"]["summary_zh"] == summary_zh
    assert result["summary"]["summary_en"] == (
        "English executive summary for a compact phone telephoto result."
    )
    assert mock_client.chat.completions.create.await_count == 1
    call_args = mock_client.chat.completions.create.call_args
    user_msg = call_args.kwargs["messages"][1]["content"]
    assert "Scenario: Smartphone Telephoto (smartphone-telephoto)" in user_msg
    assert "Target focal length: 7.00 mm" in user_msg
    assert "Total track length: 5.85 mm" in user_msg
    assert "Diffraction cutoff: 758 lp/mm" in user_msg


@patch("app.api.wizard.get_async_client")
def test_wizard_summary_alias_renders_same_result_page(mock_get_client, monkeypatch):
    mock_get_client.side_effect = AssertionError("wizard summary alias synchronously awaited LLM")
    monkeypatch.setattr(main, "_submit_executive_summary_job", lambda _payload: "summary-job-alias")

    response = client.post("/wizard/summary", data=_summary_form_payload())

    assert response.status_code == 200, response.text
    assert 'data-result-summary' in response.text
    assert 'data-summary-status="pending"' in response.text
    assert 'data-summary-job-id="summary-job-alias"' in response.text
    assert mock_get_client.call_count == 0
