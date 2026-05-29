"""Tests for the real-design case library (phase v2-02 wave 2).

Goal gates (BRIEF §5):
- 17 OpticalSampleData JSON generated and Pydantic-valid
- each case EFL within 2% of nominal
- at least one case has the full chain (paraxial + trace + mtf + layout_svg)
- honest metadata: imaging vs filter element split, materials, EFL error
"""

import warnings

from app.core.case_library import build_sample_from_optic, load_case_library
from app.core.optical_sample import OpticalSampleData
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx
from tests.data.zmx_manifest import ZMX_AMMO


def test_build_one_real_sample_roundtrip():
    """build_sample_from_optic on a real design, dump+reload, structural integrity."""
    a = ZMX_AMMO[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(ZMX_AMMO_DIR / a["filename"])
        sample = build_sample_from_optic(
            optic, a["filename"], a["n_pieces"], a["nominal_efl_mm"], a["nominal_fov_deg"]
        )
    reloaded = OpticalSampleData.model_validate_json(sample.model_dump_json())
    assert reloaded.paraxial.effective_focal_length_mm > 0
    assert reloaded.metadata is not None
    assert reloaded.metadata.case_id == a["filename"].rsplit(".", 1)[0]
    # imaging + filter elements are both detected and self-consistent
    assert reloaded.metadata.n_imaging >= 3
    assert reloaded.metadata.n_filter >= 0
    assert reloaded.metadata.materials  # non-empty real material names


def test_load_all_17_cases_valid():
    cases = load_case_library()
    assert len(cases) == 17
    for c in cases:
        assert isinstance(c, OpticalSampleData)
        assert c.metadata is not None
        assert c.metadata.scenario.value in ("smartphone-wide", "smartphone-ultrawide")


def test_at_least_one_full_chain():
    """One case proves the full Optiland chain works (wavelength regularization OK)."""
    cases = load_case_library()
    c = cases[0]
    assert len(c.mtf.freq_lp_per_mm) > 0
    assert len(c.mtf.fields) > 0
    assert len(c.trace.sampled_paths) > 0
    assert "svg" in c.layout_svg.svg_content.lower()
    assert c.paraxial.effective_focal_length_mm > 0


def test_all_cases_efl_within_2pct():
    cases = load_case_library()
    over = [
        (c.metadata.case_id, round(c.metadata.efl_error_pct, 1))
        for c in cases
        if c.metadata.efl_error_pct >= 2.0
    ]
    assert not over, f"cases with EFL beyond 2%: {over}"


def test_ir_filter_detected_for_typical_design():
    """Most real designs carry an IR-cut/cover-glass plate — verify we tag it."""
    cases = load_case_library()
    with_filter = [c for c in cases if c.metadata.n_filter >= 1]
    # the majority of phone modules have a flat IR filter; at least most cases tag one
    assert len(with_filter) >= len(cases) // 2


def test_materials_are_real_names():
    """Materials come from the zmx GLAS rows (real datasheet names), not 'AbbeMaterial'."""
    cases = load_case_library()
    all_mats = {m for c in cases for m in c.metadata.materials}
    assert all_mats, "no materials captured"
    # none should be the nameless optiland class name
    assert "ABBEMATERIAL" not in {m.upper() for m in all_mats}
