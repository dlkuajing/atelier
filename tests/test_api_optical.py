"""Tests for /api/optical/* endpoints — Phase 2 wave 1 portion.

Wave 2 endpoint tests (real /raytrace returning ray paths) live in
test_optical_engine.py once Optiland is wired.
"""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


# ---------------------------------------------------------------------------
# /api/optical/suggest/{scenario}
# ---------------------------------------------------------------------------


def test_suggest_smartphone_telephoto():
    r = client.get("/api/optical/suggest/smartphone-telephoto")
    assert r.status_code == 200
    data = r.json()
    assert data["scenario"] == "smartphone-telephoto"
    assert "telephoto" in data["description"].lower()
    lo, hi = data["efl_mm_range"]
    assert 5.0 <= lo < hi <= 18.0
    f_lo, f_hi = data["f_number_range"]
    assert 1.0 <= f_lo < f_hi


def test_suggest_dslr_prime():
    r = client.get("/api/optical/suggest/dslr-prime")
    assert r.status_code == 200
    data = r.json()
    assert data["scenario"] == "dslr-prime"
    lo, hi = data["efl_mm_range"]
    assert lo >= 24.0
    assert hi >= 100.0


def test_suggest_invalid_scenario_returns_422():
    r = client.get("/api/optical/suggest/not-a-real-scenario")
    assert r.status_code == 422  # pydantic enum validation


def test_suggest_all_scenarios_respond_200():
    for scenario in [
        "smartphone-telephoto",
        "smartphone-wide",
        "smartphone-ultrawide",
        "ar-near-eye",
        "dslr-prime",
        "microscope-objective",
    ]:
        r = client.get(f"/api/optical/suggest/{scenario}")
        assert r.status_code == 200, f"failed for {scenario}: {r.text}"


# ---------------------------------------------------------------------------
# Parameter guard validation on /raytrace
# ---------------------------------------------------------------------------


def _good_request() -> dict:
    return {
        "scenario": "smartphone-telephoto",
        "focal_length_mm": 7.0,
        "f_number": 2.4,
        "field_of_view_deg": 30.0,
        "image_height_mm": 3.7,
        "n_elements": 7,
        "wavelength_nm": 550.0,
    }


def test_raytrace_valid_input_returns_full_payload():
    """Good input → 200 + paraxial summary + surfaces + ray paths."""
    r = client.post("/api/optical/raytrace", json=_good_request())
    assert r.status_code == 200, r.text
    data = r.json()
    assert "paraxial" in data and "surfaces" in data and "trace" in data
    assert abs(data["paraxial"]["effective_focal_length_mm"] - 7.0) < 0.01
    assert data["paraxial"]["n_surfaces"] == len(data["surfaces"])
    assert any(s["is_stop"] for s in data["surfaces"])
    assert any(s["is_object"] for s in data["surfaces"])
    assert any(s["is_image"] for s in data["surfaces"])
    assert len(data["trace"]["sampled_paths"]) == 3


def test_raytrace_efl_too_small_returns_400():
    """0.5mm EFL for phone tele = classic LLM hallucination → 400."""
    bad = _good_request()
    bad["focal_length_mm"] = 0.5
    r = client.post("/api/optical/raytrace", json=bad)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "parameter_guard_failed"
    assert any("EFL" in v for v in detail["violations"])


def test_raytrace_multiple_violations_aggregated():
    bad = _good_request()
    bad["focal_length_mm"] = 0.5
    bad["f_number"] = 10.0
    bad["field_of_view_deg"] = 170.0
    r = client.post("/api/optical/raytrace", json=bad)
    assert r.status_code == 400
    assert len(r.json()["detail"]["violations"]) >= 3


def test_raytrace_wrong_scenario_bounds_returns_400():
    """50mm EFL is fine for DSLR prime but huge for smartphone telephoto."""
    bad = _good_request()
    bad["focal_length_mm"] = 50.0
    r = client.post("/api/optical/raytrace", json=bad)
    assert r.status_code == 400


def test_raytrace_dslr_prime_50mm_returns_full_payload():
    """Same 50mm EFL is valid in DSLR scenario — returns real ray trace."""
    r = client.post(
        "/api/optical/raytrace",
        json={
            "scenario": "dslr-prime",
            "focal_length_mm": 50.0,
            "f_number": 1.8,
            "field_of_view_deg": 46.8,
            "image_height_mm": 21.6,
            "n_elements": 8,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert abs(data["paraxial"]["effective_focal_length_mm"] - 50.0) < 0.05
    # DSLR primes are longer than phone teles
    assert data["paraxial"]["total_track_mm"] > 20.0


# ---------------------------------------------------------------------------
# Aberration + layout-svg also enforce parameter_guards
# ---------------------------------------------------------------------------


def test_aberration_validates_parameters():
    bad = _good_request()
    bad["focal_length_mm"] = 0.5
    r = client.post("/api/optical/aberration", json=bad)
    assert r.status_code == 400


def test_aberration_valid_input_returns_mtf_payload():
    """Good input -> 200 + MTF curves + diffraction limit + spot RMS + Airy."""
    r = client.post("/api/optical/aberration", json=_good_request())
    assert r.status_code == 200, r.text
    data = r.json()
    assert "freq_lp_per_mm" in data
    assert "fields" in data and len(data["fields"]) >= 1
    assert "diff_limited" in data
    assert "cutoff_freq_lp_per_mm" in data and data["cutoff_freq_lp_per_mm"] > 0
    assert "airy_disc_diameter_um" in data and data["airy_disc_diameter_um"] > 0
    assert "rms_spot_radius_um_by_field" in data
    # MTF at DC = 1.0 for every field
    for field in data["fields"]:
        assert abs(field["sagittal"][0] - 1.0) < 0.01
        assert abs(field["tangential"][0] - 1.0) < 0.01


def test_layout_svg_validates_parameters():
    bad = _good_request()
    bad["f_number"] = 10.0
    r = client.post("/api/optical/layout-svg", json=bad)
    assert r.status_code == 400


def test_layout_svg_valid_input_returns_svg_string():
    """Good input -> 200 + non-trivial SVG content from Optiland draw()."""
    r = client.post("/api/optical/layout-svg", json=_good_request())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["format"] == "svg"
    assert data["width_px"] > 0 and data["height_px"] > 0
    svg = data["svg_content"]
    assert "<svg" in svg
    assert "</svg>" in svg
    assert len(svg) > 5000  # real layout, not empty shell
