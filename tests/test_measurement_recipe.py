"""The recipe must define the instrument, not describe it.

P4's measured gap: the three P2 criteria reproduce in the median (0.985 / 0.918 /
1.063) but not per lens (spread 3.7x / 6.1x / 8.1x), because the number depends on
choices that live in our macro rather than in the ZMX. These tests pin the two
properties that make the recipe worth shipping: it cannot drift from the instrument
actually used, and it is sufficient -- every metric we report is defined in it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.core.engines.codev_optimize import _metric_function_block
from app.core.engines.measurement_recipe import RECIPE_SCHEMA, build_measurement_recipe


@pytest.fixture
def recipe() -> dict:
    return build_measurement_recipe(mtf_frequency_lpmm=100.0, mtf_nrd=32)


def test_recipe_ships_the_macro_source_verbatim(recipe: dict) -> None:
    """The one property that makes prose unnecessary: it *is* the instrument.

    Equality with `_metric_function_block()` also means the recipe can never drift
    from the macro the run actually executed -- there is no second copy to update.
    """

    assert recipe["metric_macro_source"] == tuple(_metric_function_block())


def test_recipe_defines_every_metric_function_the_probe_calls() -> None:
    """Sufficiency: an outsider holding the recipe must not need a sixth file.

    Derived from the probe's own generated macro rather than a hand-written list, so a
    metric added later without a recipe entry fails here instead of shipping a number
    nobody can recompute.
    """

    from scripts.p2_crosssource_trial import build_probe_sequence

    zmx = next((Path("data") / "zmx").glob("*.zmx"))
    sequence = build_probe_sequence(source_zmx=zmx, result_path=Path("r.txt"))

    called = {m.group(1) for m in re.finditer(r"(@[a-z]+)\(", sequence)}
    assert called, "probe sequence calls no metric functions -- the extraction broke"

    defined = {
        m.group(1)
        for line in build_measurement_recipe(mtf_frequency_lpmm=100.0, mtf_nrd=32)[
            "metric_macro_source"
        ]
        if (m := re.match(r"FCT (@[a-z]+)\(", line))
    }
    assert called <= defined, f"probe calls undefined-in-recipe: {sorted(called - defined)}"


def test_recipe_records_the_run_parameters_not_the_module_defaults() -> None:
    """A caller that overrides the MTF setup must not ship a recipe that contradicts it."""

    odd = build_measurement_recipe(mtf_frequency_lpmm=55.5, mtf_nrd=8)
    assert odd["metrics"]["mtf_min"]["frequency_lp_per_mm"] == 55.5
    assert odd["metrics"]["mtf_min"]["nrd"] == 8


def test_recipe_states_the_radius_versus_diameter_convention(recipe: dict) -> None:
    """This exact ambiguity produced a wrong P4 conclusion once (median 0.4925 read as
    engine disagreement when half of it was units)."""

    spot = recipe["metrics"]["rms_spot_um"]
    assert spot["quantity"] == "RMS spot diameter"
    assert "diameter" in spot["convention"]
    assert "radius" in spot["convention"]


def test_recipe_states_that_no_clipping_was_applied(recipe: dict) -> None:
    """The MAD clip is the largest per-lens discrepancy in the recheck, so silence
    about it is the one thing the recipe must not do."""

    assert recipe["post_processing"]["outlier_rejection"].startswith("none")
    assert "_robust_clip_spot_data" in recipe["post_processing"]["note"]


def test_recipe_does_not_fabricate_an_engine_build(recipe: dict) -> None:
    """Honest hole beats invented stamp: an install path is not a build number."""

    assert recipe["engine"]["build"] is None
    assert recipe["engine"]["build_unavailable_reason"]


def test_recipe_declares_the_field_and_wavelength_sets(recipe: dict) -> None:
    """These are the choices the ZMX cannot carry for a reader of a bare number."""

    assert "(NUM F)" in recipe["sampling"]["fields"]
    assert "(NUM W)" in recipe["sampling"]["wavelengths"]
    assert recipe["schema"] == RECIPE_SCHEMA


def test_the_trial_record_carries_the_recipe() -> None:
    """Source-level: the recipe is worthless if it never reaches a deliverable.

    Checked on the source rather than by running a trial because a trial costs ~46
    minutes of CODE V time, and what is being asserted is a wiring fact.
    """

    source = Path("scripts/p2_crosssource_trial.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_measurement_recipe"
    ]
    assert calls, "trial record does not build a measurement recipe"
    assert '"measurement_recipe"' in source
