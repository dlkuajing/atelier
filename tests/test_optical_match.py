"""Tests for /api/optical/match — real case retrieval (phase v2-03)."""

from fastapi.testclient import TestClient

from app.core.case_library import match_case
from app.core.lens_system import Scenario
from app.main import app

client = TestClient(app)


def test_match_case_nearest_wide():
    c = match_case(Scenario.SMARTPHONE_WIDE, 2.8, 2.4, 78.0)
    assert c is not None
    assert c.metadata.scenario == Scenario.SMARTPHONE_WIDE
    # nearest design to EFL 2.8 should land close to it
    assert abs(c.metadata.computed_efl_mm - 2.8) < 0.3


def test_match_case_none_for_telephoto():
    # no real telephoto data in this phase (Phase A found zero long-focus ammo)
    assert match_case(Scenario.SMARTPHONE_TELEPHOTO, 7.0, 2.4, 30.0) is None


def test_match_endpoint_returns_real_case():
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-wide",
            "focal_length_mm": 2.8,
            "f_number": 2.4,
            "field_of_view_deg": 78.0,
            "image_height_mm": 2.3,
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("paraxial", "surfaces", "trace", "mtf", "layout_svg", "metadata"):
        assert k in d
    assert d["metadata"]["source_zmx"].lower().endswith(".zmx")
    assert d["metadata"]["n_imaging"] >= 3
    assert d["metadata"]["materials"]  # real datasheet material names
    # real surfaces carry finite radii (sentinel 1e9 for planes, never inf/null)
    assert all(isinstance(s["radius_mm"], (int, float)) for s in d["surfaces"])


def test_match_endpoint_404_for_telephoto():
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-telephoto",
            "focal_length_mm": 7.0,
            "f_number": 2.4,
            "field_of_view_deg": 30.0,
            "image_height_mm": 3.7,
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "no_real_case_for_scenario"


def test_match_endpoint_400_out_of_bounds():
    # EFL 50mm is way outside the calibrated wide bounds → parameter guard 400
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-wide",
            "focal_length_mm": 50.0,
            "f_number": 2.4,
            "field_of_view_deg": 78.0,
            "image_height_mm": 2.3,
        },
    )
    assert r.status_code == 400
