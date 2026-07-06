"""Unit tests for app.api.wizard.parse_llm_scenario_response.

The endpoint itself is a thin async wrapper over an LLM call and the parser;
testing the live LLM is out of scope (network + cost). These tests exercise
the parser against representative LLM outputs and confirm scenario bounds
clamp the proposed numerics.
"""

import asyncio
import json
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.wizard import (
    ExecutiveSummaryRequest,
    ExtractScenarioRequest,
    ExtractScenarioResponse,
    generate_executive_summary,
    _strip_markdown_fences,
    extract_scenario,
    parse_llm_scenario_response,
)
from app.core.lens_system import Scenario


def _mock_chat_response(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content=content))]
    return completion


# ---------------------------------------------------------------------------
# _strip_markdown_fences
# ---------------------------------------------------------------------------


def test_strip_passes_through_plain_json():
    raw = '{"scenario": "smartphone-telephoto"}'
    assert _strip_markdown_fences(raw) == raw


def test_strip_removes_json_code_fence():
    raw = '```json\n{"scenario": "smartphone-telephoto"}\n```'
    assert _strip_markdown_fences(raw) == '{"scenario": "smartphone-telephoto"}'


def test_strip_removes_bare_code_fence():
    raw = '```\n{"scenario": "dslr-prime"}\n```'
    assert _strip_markdown_fences(raw) == '{"scenario": "dslr-prime"}'


def test_strip_handles_whitespace_padding():
    raw = '   \n```json\n{"scenario": "ar-near-eye"}\n```\n   '
    assert _strip_markdown_fences(raw) == '{"scenario": "ar-near-eye"}'


# ---------------------------------------------------------------------------
# parse_llm_scenario_response — happy paths
# ---------------------------------------------------------------------------


def test_parse_minimal_response():
    raw = json.dumps(
        {
            "scenario": "smartphone-telephoto",
            "focal_length_mm": None,
            "f_number": None,
            "field_of_view_deg": None,
            "image_height_mm": None,
            "n_elements": None,
            "reasoning": None,
        }
    )
    r = parse_llm_scenario_response(raw)
    assert isinstance(r, ExtractScenarioResponse)
    assert r.scenario == Scenario.SMARTPHONE_TELEPHOTO
    assert r.focal_length_mm is None
    assert r.f_number is None


def test_parse_full_response_smartphone_tele():
    raw = json.dumps(
        {
            "scenario": "smartphone-telephoto",
            "focal_length_mm": 7.0,
            "f_number": 2.4,
            "field_of_view_deg": 30.0,
            "image_height_mm": 3.7,
            "n_elements": 7,
            "reasoning": "Phone telephoto camera implied by '5x zoom'.",
        }
    )
    r = parse_llm_scenario_response(raw)
    assert r.scenario == Scenario.SMARTPHONE_TELEPHOTO
    assert math.isclose(r.focal_length_mm, 7.0)
    assert math.isclose(r.f_number, 2.4)
    assert r.n_elements == 7
    assert "5x zoom" in (r.reasoning or "")


def test_parse_dslr_prime_50mm():
    raw = '{"scenario":"dslr-prime","focal_length_mm":50,"f_number":1.8,"field_of_view_deg":46.8,"image_height_mm":21.6,"n_elements":8,"reasoning":"Classic 50mm prime."}'
    r = parse_llm_scenario_response(raw)
    assert r.scenario == Scenario.DSLR_PRIME
    assert r.focal_length_mm == 50.0


# ---------------------------------------------------------------------------
# parse_llm_scenario_response — clamping
# ---------------------------------------------------------------------------


def test_parse_clamps_efl_below_min_to_min():
    """LLM hallucinated 0.5mm EFL for phone tele -> clamped to 5mm (the min)."""
    raw = json.dumps(
        {"scenario": "smartphone-telephoto", "focal_length_mm": 0.5, "n_elements": 7}
    )
    r = parse_llm_scenario_response(raw)
    assert r.focal_length_mm == 5.0


def test_parse_clamps_efl_above_max_to_max():
    """LLM proposed 50mm EFL for phone tele -> clamped to 18mm (the max)."""
    raw = json.dumps(
        {"scenario": "smartphone-telephoto", "focal_length_mm": 50.0}
    )
    r = parse_llm_scenario_response(raw)
    assert r.focal_length_mm == 18.0


@pytest.mark.asyncio
@patch("app.api.wizard.get_async_client")
async def test_extract_scenario_preserves_explicit_in_bounds_numbers(mock_get_client):
    """Mocked LLM mutates explicit specs; endpoint post-check restores them."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            json.dumps(
                {
                    "scenario": "smartphone-telephoto",
                    "focal_length_mm": 12.0,
                    "f_number": 3.5,
                    "field_of_view_deg": 44.0,
                    "image_height_mm": 7.5,
                    "n_elements": 7,
                    "reasoning": "Phone telephoto request.",
                }
            )
        )
    )
    mock_get_client.return_value = mock_client

    response = await extract_scenario(
        ExtractScenarioRequest(
            user_input=(
                "Phone telephoto: EFL 7.0 mm, f/2.4, FOV 30 deg, "
                "image height 3.7 mm."
            )
        )
    )

    assert response.scenario == Scenario.SMARTPHONE_TELEPHOTO
    assert response.focal_length_mm == 7.0
    assert response.f_number == 2.4
    assert response.field_of_view_deg == 30.0
    assert response.image_height_mm == 3.7
    assert response.n_elements == 7

    messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
    assert "explicitly supplied" in messages[0]["content"]


@pytest.mark.asyncio
@patch("app.api.wizard.get_async_client")
async def test_extract_scenario_does_not_override_range_expressions(mock_get_client):
    """Range-like values are not single explicit targets, so the LLM selection stays."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            json.dumps(
                {
                    "scenario": "smartphone-wide",
                    "focal_length_mm": 3.0,
                    "f_number": 2.1,
                    "field_of_view_deg": 87.5,
                    "image_height_mm": 3.0,
                    "n_elements": 6,
                    "reasoning": "Phone wide request with ranged constraints.",
                }
            )
        )
    )
    mock_get_client.return_value = mock_client

    response = await extract_scenario(
        ExtractScenarioRequest(
            user_input=(
                "Phone wide: EFL 3.2 mm, FOV 80-90 deg, "
                "f/1.8-2.4, image height 3~5 mm."
            )
        )
    )

    assert response.scenario == Scenario.SMARTPHONE_WIDE
    assert response.focal_length_mm == 3.2
    assert response.f_number == 2.1
    assert response.field_of_view_deg == 87.5
    assert response.image_height_mm == 3.0


def test_parse_clamps_f_number():
    raw = json.dumps(
        {"scenario": "smartphone-telephoto", "f_number": 0.5}
    )
    r = parse_llm_scenario_response(raw)
    assert r.f_number == 1.8  # min for smartphone-tele


def test_parse_clamps_n_elements_below_min():
    raw = json.dumps(
        {"scenario": "smartphone-telephoto", "n_elements": 2}
    )
    r = parse_llm_scenario_response(raw)
    assert r.n_elements == 5  # min for smartphone-tele


def test_parse_clamps_n_elements_above_max():
    raw = json.dumps(
        {"scenario": "smartphone-telephoto", "n_elements": 50}
    )
    r = parse_llm_scenario_response(raw)
    assert r.n_elements == 9  # max for smartphone-tele


# ---------------------------------------------------------------------------
# parse_llm_scenario_response — error paths
# ---------------------------------------------------------------------------


def test_parse_invalid_json_raises():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_llm_scenario_response("this is not json {{{ ")


def test_parse_array_at_top_level_raises():
    with pytest.raises(ValueError, match="not a JSON object"):
        parse_llm_scenario_response('["not", "an", "object"]')


def test_parse_unknown_scenario_raises():
    raw = json.dumps({"scenario": "warp-drive-objective"})
    with pytest.raises(ValueError, match="unknown scenario"):
        parse_llm_scenario_response(raw)


def test_parse_missing_scenario_raises():
    raw = json.dumps({"focal_length_mm": 7.0})
    with pytest.raises(ValueError, match="missing 'scenario'"):
        parse_llm_scenario_response(raw)


def test_parse_invalid_n_elements_returns_null():
    """Non-integer n_elements coerces to None rather than crashing."""
    raw = json.dumps({"scenario": "smartphone-telephoto", "n_elements": "seven"})
    r = parse_llm_scenario_response(raw)
    assert r.n_elements is None


def test_parse_with_markdown_fences():
    """Defensive — LLM may wrap JSON despite the system prompt."""
    raw = '```json\n{"scenario": "ar-near-eye", "focal_length_mm": 18.0}\n```'
    r = parse_llm_scenario_response(raw)
    assert r.scenario == Scenario.AR_NEAR_EYE
    assert r.focal_length_mm == 18.0


@pytest.mark.asyncio
@patch("app.api.wizard.get_async_client")
async def test_generate_executive_summary_times_out_to_deterministic_fallback(
    mock_get_client,
    monkeypatch,
):
    async def slow_create(**_kwargs):
        await asyncio.sleep(1.0)
        return _mock_chat_response('{"summary_en":"late","summary_zh":"late"}')

    mock_client = MagicMock()
    mock_client.chat.completions.create = slow_create
    mock_get_client.return_value = mock_client
    monkeypatch.setattr("app.api.wizard._EXEC_SUMMARY_LLM_TIMEOUT_SECONDS", 0.01)

    response = await generate_executive_summary(
        ExecutiveSummaryRequest(
            scenario=Scenario.SMARTPHONE_WIDE,
            scenario_label_en="Smartphone Wide",
            focal_length_mm=3.2,
            f_number=2.0,
            field_of_view_deg=82.0,
            image_height_mm=3.0,
            n_elements=6,
            wavelength_nm=550.0,
            total_track_mm=4.5,
            airy_disc_diameter_um=2.7,
            cutoff_freq_lp_per_mm=900.0,
        )
    )

    assert response.fallback_reason == "llm_timeout_after_0.01s"
    assert response.model.startswith("deterministic-fallback:")
    assert "not a production-ready prescription" in response.summary_en
