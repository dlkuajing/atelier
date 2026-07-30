"""The routing gate and the P2 judgement must measure the same thing.

The defect these lock down is not a wrong number, it is a wrong *convention*: a
threshold measured one way and applied to values measured another. The repo produced
three instances of it in a single day (2026-07-30) -- this gate comparing a stored
Optiland half-field spot **radius** against a bound sized for CODE V's full-field
**diameter** (188x apart at the worst case), the P4 recheck comparing a radius to a
diameter, and `zmx_writer` transposing VDY/VCY. None of them fails loudly; each one
reads as a plausible number until someone recomputes it by hand.

So the convention is asserted, not documented: one `QUANTITY` literal, carried by
both committed artifacts, checked at load, and pinned here against the census
operand the judgement itself reads.

Evidence: `.planning/evidence/stored-routing-quality-diverges-2026-07-30.md`.
"""

from __future__ import annotations

import json

import pytest

from app.core.case_library import (
    _SEED_ROUTING_RMS_PERCENTILE,
    _candidate_scenarios,
    _seed_routing_max_rms_um,
    load_case_library,
    rank_seeds,
)
from app.core.corpus_quality import (
    INSTRUMENT,
    QUANTITY,
    case_rms_spot_um,
    load_distribution,
    load_per_case,
    per_case_population,
    rms_at_percentile,
)
from app.core.lens_system import Scenario
from app.core.optical_sample import OpticalSampleData

#: The case that made the divergence undeniable: CODE V reads 447.60 um over every
#: declared field, the stored per-case JSON reads 2.38 um (diameter) from half the
#: field, and a 100 um gate therefore admitted it as one of the corpus's best lenses.
DECISIVE_CASE = "US-12436366-B2-e10"
DECISIVE_CODEV_UM = 447.598


def _cases_for(scenario: Scenario) -> list[OpticalSampleData]:
    allowed = _candidate_scenarios(scenario)
    return [
        c for c in load_case_library() if c.metadata is not None and c.metadata.scenario in allowed
    ]


def test_gate_and_judgement_name_the_same_quantity() -> None:
    """Both artifacts must spell out the same measured quantity and instrument.

    `INSTRUMENT` is the P2 judgement's own operand: the per-field `SPOTDATA` call
    behind `@rmssum`. Pinning it here is what makes "same quantity" a machine check
    rather than a claim in a docstring.
    """

    per_case = load_per_case()
    distribution = load_distribution()

    assert per_case["quantity"] == distribution["quantity"] == QUANTITY
    assert "diameter, not a radius" in QUANTITY
    assert per_case["provenance"]["instrument"] == distribution["provenance"]["instrument"]
    assert per_case["provenance"]["instrument"] == INSTRUMENT
    assert "@rmssum" in INSTRUMENT


def test_per_case_readings_come_from_the_same_population_as_the_distribution() -> None:
    """Same census, same screen, same units -- so every reading is in the distribution.

    This is the assertion that survives a careless rebuild. Repopulate the per-case
    map with radii, or with half-field values, or from a different census, and the
    values stop appearing in the reference population even though every individual
    number still looks like a plausible spot size.
    """

    readings = load_per_case()["rms_spot_um_by_case_id"]
    population = load_distribution()["sorted_rms_spot_um"]

    assert readings, "per-case artifact is empty"
    assert len(readings) == load_distribution()["n"]
    missing = [case_id for case_id, value in readings.items() if value not in population]
    assert not missing, f"readings absent from the reference population: {missing[:5]}"


def test_the_per_case_artifact_names_its_provenance() -> None:
    """A quality figure whose provenance is unstated is how the old gate went wrong."""

    population = per_case_population()
    assert population["census_run"]
    assert len(population["census_sha256"]) == 64
    assert population["caveats"]
    # Coverage is partial and must be admitted as such, not rounded up to "the corpus".
    assert population["n"] < load_per_case()["provenance"]["index_cases"]


def test_load_per_case_refuses_a_different_convention(tmp_path) -> None:
    """The guard has to be able to fail, or it is decoration."""

    payload = json.loads(json.dumps(load_per_case()))
    payload["quantity"] = "max over fields of the RMS spot radius, in um"
    tampered = tmp_path / "corpus_routing_quality.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="measures something else"):
        load_per_case(tampered)


def test_the_gate_threshold_is_a_corpus_rank_not_an_invented_number() -> None:
    """The bound must be traceable to a line in the committed distribution.

    The old 100.0 was sized to block the two broken ingest seeds, not against what a
    seed has to compete with; that is why a 447 um lens cleared it comfortably.
    """

    threshold = _seed_routing_max_rms_um()
    assert threshold == rms_at_percentile(_SEED_ROUTING_RMS_PERCENTILE)
    assert threshold == load_distribution()["percentiles"]["p50"]
    assert threshold < 100.0


def test_the_decisive_case_is_now_rejected_and_used_to_be_admitted() -> None:
    """Pin the actual regression, in both conventions."""

    codev = case_rms_spot_um(DECISIVE_CASE)
    assert codev == pytest.approx(DECISIVE_CODEV_UM)
    assert codev > _seed_routing_max_rms_um()

    case = next(c for c in load_case_library() if c.metadata.case_id == DECISIVE_CASE)
    stored_radius = max(c for c in case.mtf.rms_spot_radius_um_by_field if c == c)
    # What the gate used to compare: a radius, from part of the field, under the old
    # 100 um bound by two orders of magnitude while CODE V reads 447.60.
    assert stored_radius < 100.0
    assert case.metadata.mtf_max_field_frac < 1.0
    assert codev / (2.0 * stored_radius) > 100.0


def test_a_seed_with_no_full_field_reading_loses_to_one_that_has_it() -> None:
    """Fail closed: unmeasured is not "good enough", it is the worst thing in the pool.

    The clone is identical to a qualifying case on every axis `rank_seeds` scores, so
    the only thing that can separate them is the quality gate -- and the clone's case
    id carries no reading, which is exactly the state of the 224 corpus cases CODE V
    could not trace over their full field.
    """

    qualifying = next(
        c
        for c in _cases_for(Scenario.SMARTPHONE_WIDE)
        if (case_rms_spot_um(c.metadata.case_id) or float("inf")) <= _seed_routing_max_rms_um()
    )
    unmeasured = qualifying.model_copy(deep=True)
    unmeasured.metadata.case_id = f"{qualifying.metadata.case_id}__no_codev_reading"
    assert case_rms_spot_um(unmeasured.metadata.case_id) is None

    result = rank_seeds(
        [unmeasured, qualifying],
        efl_mm=qualifying.metadata.computed_efl_mm,
        fov_deg=qualifying.metadata.fov_deg,
        fnum=qualifying.paraxial.f_number,
    )
    assert result.best.metadata.case_id == qualifying.metadata.case_id


def test_rejected_seeds_are_ordered_by_measured_quality() -> None:
    """Two rejects are not interchangeable -- the worse-measured one must rank below.

    With a flat penalty the quality axis says nothing once every nearby seed is a
    reject, so the argmin falls to whichever reject matches parameters best. Measured
    on cross-brand pools that handed a slot to a seed CODE V reads at 17358 um where
    the previous gate had picked a 443 um one.
    """

    pool = _cases_for(Scenario.SMARTPHONE_WIDE)
    rejects = sorted(
        (
            (case_rms_spot_um(c.metadata.case_id), c)
            for c in pool
            if (case_rms_spot_um(c.metadata.case_id) or 0.0) > _seed_routing_max_rms_um()
        ),
        key=lambda pair: pair[0],
    )
    assert len(rejects) >= 2, "corpus no longer has two rejected seeds to compare"
    better_rms, better = rejects[0]
    worse_rms, worse = rejects[-1]
    assert worse_rms > better_rms

    # Score both against the worse seed's own spec, so it holds the exact parameter
    # match and only the quality axis can stop it from winning.
    result = rank_seeds(
        [better, worse],
        efl_mm=worse.metadata.computed_efl_mm,
        fov_deg=worse.metadata.fov_deg,
        fnum=worse.paraxial.f_number,
    )
    ranked = {rc.case_id: rc.distance_parts["quality"] for rc in result.ranked}
    assert ranked[better.metadata.case_id] < ranked[worse.metadata.case_id]
