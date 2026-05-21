"""Unit tests for app.api.wizard.parse_llm_scenario_response.

The endpoint itself is a thin async wrapper over an LLM call and the parser;
testing the live LLM is out of scope (network + cost). These tests exercise
the parser against representative LLM outputs and confirm scenario bounds
clamp the proposed numerics.
"""

import json
import math

import pytest

from app.api.wizard import (
    ExtractScenarioResponse,
    _strip_markdown_fences,
    parse_llm_scenario_response,
)
from app.core.lens_system import Scenario


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
