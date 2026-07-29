"""Tests for the real-design case library (phase v2-02 wave 2).

Goal gates (BRIEF §5):
- 17 OpticalSampleData JSON generated and Pydantic-valid
- each case EFL within 2% of nominal
- at least one case has the full chain (paraxial + trace + mtf + layout_svg)
- honest metadata: imaging vs filter element split, materials, EFL error
"""

import warnings

from app.core.case_library import (
    _classify_scenario,
    build_sample_from_optic,
    load_case_library,
)
from app.core.lens_system import Scenario
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


def test_load_all_cases_valid():
    cases = load_case_library()
    # 17 GGG + 22 curated patent + 128 DATA-06 + 186 DATA-09d1 + 83 DATA-10a/b
    # seeds + 6 Phase 12 NEWMAX seeds.
    assert len(cases) == 442
    for c in cases:
        assert isinstance(c, OpticalSampleData)
        assert c.metadata is not None
        assert c.metadata.scenario.value in (
            "smartphone-telephoto",
            "smartphone-wide",
            "smartphone-ultrawide",
        )


def test_telephoto_tier_is_populated_after_reclassification():
    """The FOV+EFL taxonomy re-labels genuine long-focus seeds as telephoto,
    so the routable telephoto pool is no longer empty (was the 404 root cause)."""
    cases = load_case_library()
    telephoto = [
        c
        for c in cases
        if c.metadata is not None
        and c.metadata.scenario is Scenario.SMARTPHONE_TELEPHOTO
    ]
    # 115 in the 343-library baseline + 4 genuine long-focus DATA-06i seeds
    # (US-12443014-B2 e1-e4) from the 353 intake + 15 DATA-10b Sunny/Ability
    # long-focus seeds from the 436 intake + 5 Phase 12 NEWMAX telephoto seeds
    # = 139, **minus 29** re-anchored out on 2026-07-29: those seeds stored a
    # half field angle in a field documented as full FOV, so a 72-degree lens
    # read as 36 and slipped under the 45-degree telephoto ceiling. The ceiling
    # is unchanged; the numbers it compares are now one unit throughout
    # (see .planning/evidence/fov-unit-mix-2026-07-29.md).
    assert len(telephoto) == 110
    # Every telephoto seed must satisfy the guard-aligned classifier contract.
    for c in telephoto:
        assert c.metadata.computed_efl_mm >= 5.0
        assert c.metadata.fov_deg <= 45.0


def test_at_least_one_full_chain():
    """One case proves the full Optiland chain works (wavelength regularization OK)."""
    cases = load_case_library()
    c = cases[0]
    assert len(c.mtf.freq_lp_per_mm) > 0
    assert len(c.mtf.fields) > 0
    assert len(c.trace.sampled_paths) > 0
    assert "svg" in c.layout_svg.svg_content.lower()
    assert c.paraxial.effective_focal_length_mm > 0


def test_classify_scenario_tiers():
    """Multi-tier (FOV+EFL) classification: EFL is the telephoto discriminator so
    a short-EFL narrow-field seed stays wide, not tele."""
    T = Scenario.SMARTPHONE_TELEPHOTO
    W = Scenario.SMARTPHONE_WIDE
    U = Scenario.SMARTPHONE_ULTRAWIDE
    cases = [
        # (fov_deg, efl_mm, expected)
        (20.0, 12.0, T),   # long EFL, narrow field → telephoto
        (45.0, 5.0, T),    # inclusive boundary (fov<=45 and efl>=5)
        (8.7, 22.7, T),    # deep tele below the 15deg request floor (US-...578-e1)
        (35.1, 3.93, W),   # telephoto FOV but wide EFL (US-11933948-e8) → wide
        (78.0, 3.0, W),    # main wide
        (30.0, 4.99, W),   # just below the 5mm EFL floor → wide
        (45.1, 8.0, W),    # just above the 45deg tele ceiling, sub-85 → wide
        (90.0, 2.8, U),    # ultrawide
        (85.0, 3.5, U),    # ultrawide FOV floor
    ]
    for fov, efl, expected in cases:
        assert _classify_scenario(fov, efl) is expected, (fov, efl, expected)


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
