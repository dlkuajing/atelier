"""Tests for `rank_seeds` (C1-a extraction, C1 spec 6.2) — case_library.py.

`rank_seeds` was pulled out of `match_case`'s inline ranking/candidate-
selection block as a pure move + parameterization (no numeric-logic change).
These tests lock:

1. The full, uncapped ranking (`SeedRanking.ranked`) covers every case in the
   pool, in ascending-distance order.
2. `match_case`'s top-4 `candidate_comparison` (case_id + role) is exactly
   reproducible from `rank_seeds(...).selected_candidates` given the same
   inputs -- i.e. the extraction did not change `match_case`'s behavior.
3. `nearby_alternative_N` numbering is deterministic and sequential when the
   pool has more than 4 cases and the best/cost/thin/performance picks
   collapse onto fewer than 4 distinct cases (forcing alternates to fill the
   top-4).
"""

from __future__ import annotations

from app.core.case_library import (
    _candidate_scenarios,
    load_case_library,
    match_case,
    rank_seeds,
)
from app.core.lens_system import Scenario
from app.core.optical_sample import OpticalSampleData


def _cases_for(scenario: Scenario) -> list[OpticalSampleData]:
    allowed = _candidate_scenarios(scenario)
    return [
        c for c in load_case_library() if c.metadata is not None and c.metadata.scenario in allowed
    ]


def _tied_variants(template: OpticalSampleData, count: int) -> list[OpticalSampleData]:
    """Build `count` near-duplicates of `template` that tie on every axis
    `rank_seeds` scores *except* EFL (which fans out so distance-ordering is
    unambiguous). Used to force best == cost_seed == thin_seed ==
    performance_seed deterministically, without depending on real-library
    coincidences.
    """
    variants = []
    for i in range(count):
        variant = template.model_copy(deep=True)
        assert variant.metadata is not None
        variant.metadata.case_id = f"{template.metadata.case_id}__rank_seeds_variant_{i}"
        variant.metadata.computed_efl_mm = template.metadata.computed_efl_mm + i * 0.15
        variants.append(variant)
    return variants


def test_rank_seeds_returns_full_uncapped_pool_in_distance_order():
    cases = _cases_for(Scenario.SMARTPHONE_WIDE)
    result = rank_seeds(cases, efl_mm=2.8, fov_deg=78.0, fnum=2.4)

    assert len(result.ranked) == len(cases)
    assert {rc.case_id for rc in result.ranked} == {c.metadata.case_id for c in cases}
    distances = [rc.distance for rc in result.ranked]
    assert distances == sorted(distances)
    # every entry carries a real role and its own distance_parts breakdown
    assert result.ranked[0].role == "best_match"
    assert result.ranked[0].case_id == result.best.metadata.case_id
    for rc in result.ranked:
        assert rc.distance_parts
        assert 0.0 <= rc.score <= 1.0


def test_rank_seeds_top4_matches_match_case_candidate_comparison():
    scenario = Scenario.SMARTPHONE_WIDE
    request = {
        "efl_mm": 2.8,
        "fov_deg": 78.0,
        "fnum": 2.4,
        "image_height_mm": 3.3,
        "priority": "cost",
    }

    sample = match_case(
        scenario,
        request["efl_mm"],
        request["fnum"],
        request["fov_deg"],
        image_height_mm=request["image_height_mm"],
        priority=request["priority"],
        lightweight_design_assessment=True,
    )
    assert sample is not None and sample.design_assessment is not None
    expected = [
        (c.case_id, c.role) for c in sample.design_assessment.candidate_comparison
    ]
    assert expected  # sanity: match_case actually produced comparisons

    cases = _cases_for(scenario)
    result = rank_seeds(cases, **request)
    actual = [(c.metadata.case_id, role) for c, role in result.selected_candidates]

    assert actual == expected


def test_rank_seeds_nearby_alternative_numbering_is_stable_for_large_pool():
    template = _cases_for(Scenario.SMARTPHONE_WIDE)[0]
    variants = _tied_variants(template, count=6)
    assert len(variants) > 4

    result = rank_seeds(
        variants,
        efl_mm=variants[0].metadata.computed_efl_mm,
        fov_deg=template.metadata.fov_deg,
        fnum=template.paraxial.f_number,
    )

    # best/cost/thin/performance all collapse onto variant 0 -> only one
    # "special" slot is filled, the rest of the top-4 must come from
    # nearby_alternative fill, numbered by ascending distance.
    assert result.best.metadata.case_id == variants[0].metadata.case_id
    assert result.cost_seed.metadata.case_id == variants[0].metadata.case_id
    assert result.thin_seed.metadata.case_id == variants[0].metadata.case_id
    assert result.performance_seed.metadata.case_id == variants[0].metadata.case_id

    assert len(result.selected_candidates) == 4
    roles = [role for _, role in result.selected_candidates]
    assert roles == ["best_match", "nearby_alternative_1", "nearby_alternative_2", "nearby_alternative_3"]

    case_ids = [c.metadata.case_id for c, _ in result.selected_candidates]
    assert case_ids == [
        variants[0].metadata.case_id,
        variants[1].metadata.case_id,
        variants[2].metadata.case_id,
        variants[3].metadata.case_id,
    ]

    # full uncapped ranking: only variant 0 is a special role, everyone else
    # (including variants 4/5, which never make the top-4) is unnumbered
    # "nearby_alternative".
    role_by_id = {rc.case_id: rc.role for rc in result.ranked}
    assert role_by_id[variants[0].metadata.case_id] == "best_match"
    for variant in variants[1:]:
        assert role_by_id[variant.metadata.case_id] == "nearby_alternative"
