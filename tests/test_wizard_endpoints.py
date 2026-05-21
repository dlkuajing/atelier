"""Endpoint tests for cover-image + executive-summary — LLM client mocked.

We don't hit the real relay in pytest (network, cost, rate limits). Instead
we monkey-patch app.api.wizard.get_async_client to return an AsyncMock with
the response shape the OpenAI SDK gives. The endpoint code paths under test:
prompt assembly, response parsing, error mapping (502 / 500 / 422).
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


# ---------------------------------------------------------------------------
# /api/wizard/cover-image
# ---------------------------------------------------------------------------


@patch("app.api.wizard.get_async_client")
def test_cover_image_happy_path(mock_get_client):
    """gpt-image-2 returns b64_json → endpoint relays it verbatim."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(b64_json="ZmFrZS1wbmctcGF5bG9hZA==", revised_prompt="lens module shot")
    ]
    mock_client.images.generate = AsyncMock(return_value=mock_response)
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/cover-image",
        json={
            "scenario": "smartphone-telephoto",
            "efl_mm": 7.0,
            "f_number": 2.4,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["b64_png"] == "ZmFrZS1wbmctcGF5bG9hZA=="
    assert data["scenario"] == "smartphone-telephoto"
    assert data["revised_prompt"] == "lens module shot"
    assert "gpt-image" in data["model"].lower() or data["model"] == "gpt-image-2"


@patch("app.api.wizard.get_async_client")
def test_cover_image_prompt_includes_specs_when_given(mock_get_client):
    """If the request supplies efl_mm + f_number, they appear in the prompt
    so gpt-image-2 produces aesthetically aligned output."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.data = [MagicMock(b64_json="x", revised_prompt=None)]
    mock_client.images.generate = AsyncMock(return_value=mock_response)
    mock_get_client.return_value = mock_client

    client.post(
        "/api/wizard/cover-image",
        json={
            "scenario": "dslr-prime",
            "efl_mm": 85.0,
            "f_number": 1.4,
        },
    )
    call_args = mock_client.images.generate.call_args
    prompt = call_args.kwargs.get("prompt", "")
    assert "85" in prompt or "85.0" in prompt
    assert "f/1.4" in prompt or "1.4" in prompt


@patch("app.api.wizard.get_async_client")
def test_cover_image_relay_failure_returns_502(mock_get_client):
    """Exception bubbling out of the relay call → HTTP 502 with diagnostic."""
    mock_client = AsyncMock()
    mock_client.images.generate = AsyncMock(side_effect=Exception("upstream 503"))
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/cover-image",
        json={"scenario": "smartphone-telephoto"},
    )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["error"] == "image_relay_failure"
    assert "upstream 503" in detail["message"]


@patch("app.api.wizard.get_async_client")
def test_cover_image_empty_data_returns_502(mock_get_client):
    """Relay returned with no data array → 502 (likely upstream weirdness)."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.data = []
    mock_client.images.generate = AsyncMock(return_value=mock_response)
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/cover-image",
        json={"scenario": "smartphone-telephoto"},
    )
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "image_relay_empty_response"


def test_cover_image_invalid_scenario_returns_422():
    """Pydantic Scenario enum rejects unknown id before the LLM is called."""
    r = client.post(
        "/api/wizard/cover-image",
        json={"scenario": "warp-drive-objective"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# /api/wizard/executive-summary
# ---------------------------------------------------------------------------


_FULL_EXEC_REQUEST = {
    "scenario": "smartphone-telephoto",
    "scenario_label_en": "Smartphone Telephoto",
    "focal_length_mm": 7.0,
    "f_number": 2.4,
    "field_of_view_deg": 30.0,
    "image_height_mm": 3.7,
    "n_elements": 7,
    "wavelength_nm": 550,
    "total_track_mm": 5.85,
    "airy_disc_diameter_um": 3.22,
    "cutoff_freq_lp_per_mm": 758,
}


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


@patch("app.api.wizard.get_async_client")
def test_exec_summary_happy_path(mock_get_client):
    """Claude returns bilingual JSON → endpoint splits + relays."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            '{"summary_en": "A 7mm telephoto module built on a Largan-class 7-element reference. Compact total track keeps it phone-realistic.", "summary_zh": "基于大立光 7 片式参考的 7mm 长焦镜组，总长保持在手机可塞入的尺度。"}'
        )
    )
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "telephoto" in data["summary_en"].lower()
    assert "长焦" in data["summary_zh"]


@patch("app.api.wizard.get_async_client")
def test_exec_summary_strips_markdown_fences(mock_get_client):
    """Defensive: Claude sometimes wraps JSON in ```json``` despite prompt."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            '```json\n{"summary_en": "en text", "summary_zh": "zh text"}\n```'
        )
    )
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["summary_en"] == "en text"
    assert body["summary_zh"] == "zh text"


@patch("app.api.wizard.get_async_client")
def test_exec_summary_relay_failure_returns_502(mock_get_client):
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("rate_limit"))
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "llm_relay_failure"


@patch("app.api.wizard.get_async_client")
def test_exec_summary_unparseable_json_returns_500(mock_get_client):
    """If Claude returns prose instead of JSON, surface 500 with raw payload
    so the caller can debug."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response("Sorry, I cannot help with that.")
    )
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 500
    assert r.json()["detail"]["error"] == "llm_response_unparseable"


@patch("app.api.wizard.get_async_client")
def test_exec_summary_non_object_json_returns_500(mock_get_client):
    """Edge case: Claude returned a valid JSON array, not an object."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response("[1, 2, 3]")
    )
    mock_get_client.return_value = mock_client

    r = client.post(
        "/api/wizard/executive-summary",
        json=_FULL_EXEC_REQUEST,
    )
    assert r.status_code == 500
    assert r.json()["detail"]["error"] == "llm_response_not_object"


def test_exec_summary_missing_required_field_returns_422():
    """Pydantic catches missing focal_length_mm before the LLM is called."""
    bad = dict(_FULL_EXEC_REQUEST)
    del bad["focal_length_mm"]
    r = client.post("/api/wizard/executive-summary", json=bad)
    assert r.status_code == 422


def test_exec_summary_zero_focal_length_returns_422():
    """Pydantic gt=0 constraint."""
    bad = dict(_FULL_EXEC_REQUEST)
    bad["focal_length_mm"] = 0
    r = client.post("/api/wizard/executive-summary", json=bad)
    assert r.status_code == 422
