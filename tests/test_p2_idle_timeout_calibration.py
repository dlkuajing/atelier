"""The P2 idle watchdog must stay calibrated, and must fail toward completing.

`IDLE_TIMEOUT_SECONDS` spent its first life at 60.0s with a comment that stated
the watchdog's *purpose* and no measurement of the quantity it bounds. That is
the same mistake CI caught on the `/api/optical/match` diagnostic probes the same
day: a bound reused or guessed rather than measured fires on healthy work, and a
watchdog firing on healthy work produces `unmeasurable` -- indistinguishable from
a real failure, and it biases the North Star's main indicator.

These tests pin the two ends the calibration establishes. They are cheap and
offline; the measurement itself lives in
`.planning/evidence/idle-watchdog-calibration-2026-07-30.md`.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import scripts.p2_crosssource_trial as p2

_MIN_MARGIN_OVER_HEALTHY_GAP = 10.0
"""Margin rule inherited from the probe-deadline calibration (2026-07-30).

The *rule* carries over between watchdogs; the base it multiplies never does --
it has to be measured for each quantity. Here the base is
`MEASURED_HEALTHY_MAX_GAP_SECONDS`.
"""


def test_the_bound_clears_the_measured_healthy_gap_by_a_wide_margin() -> None:
    assert p2.IDLE_TIMEOUT_SECONDS >= (
        _MIN_MARGIN_OVER_HEALTHY_GAP * p2.MEASURED_HEALTHY_MAX_GAP_SECONDS
    ), (
        "the idle bound must be a wide multiple of the worst gap measured on a "
        "healthy rung; re-run scripts/codev_idle_gap_bench.py before lowering it"
    )


def test_the_bound_clears_the_longest_complete_healthy_rung() -> None:
    """A run's wall time is the ceiling on its largest possible gap.

    Holding the bound above it keeps the watchdog safe even for a seed/config
    whose gap profile was never sampled -- including the (measured false, but
    unfalsifiable for unsampled cases) possibility of output buffered to exit.
    """

    assert p2.IDLE_TIMEOUT_SECONDS > p2.MEASURED_LONGEST_HEALTHY_RUNG_SECONDS


def test_the_bound_stays_under_the_hard_timeout_or_it_does_not_exist() -> None:
    """At or above the hard timeout the watchdog can never fire.

    That failure is silent: every rung would die of the hard timeout instead and
    nothing would report that the idle watchdog had stopped existing. Lowering
    `--timeout` below the idle bound trips this too, which is the point.
    """

    hard_timeout_default = inspect.signature(p2.run_trial).parameters["timeout_seconds"].default
    assert hard_timeout_default > p2.IDLE_TIMEOUT_SECONDS


def test_the_constant_carries_its_measurement_not_just_its_purpose() -> None:
    """The comment must cite the evidence, not restate what a watchdog is for.

    This is the check that would have failed against the original 60.0s.
    """

    source = Path(p2.__file__).read_text(encoding="utf-8")
    lines = source.splitlines()
    assignment = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("IDLE_TIMEOUT_SECONDS")
    )
    comment: list[str] = []
    cursor = assignment - 1
    while cursor >= 0 and lines[cursor].startswith("#"):
        comment.append(lines[cursor])
        cursor -= 1
    block = "\n".join(reversed(comment))

    assert "idle-watchdog-calibration-2026-07-30" in block, (
        "the bound's comment must point at the evidence that produced it"
    )
    assert "codev_idle_gap_bench" in block, (
        "the bound's comment must name the bench that can reproduce the measurement"
    )
    for measured in (
        str(p2.MEASURED_HEALTHY_MAX_GAP_SECONDS),
        str(p2.MEASURED_LONGEST_HEALTHY_RUNG_SECONDS),
    ):
        assert measured in block, f"the comment must record the measured {measured}s"


def test_the_watchdog_is_runtime_configurable() -> None:
    """Re-calibrating must not require editing code (project rule: runtime config first)."""

    tree = ast.parse(Path(p2.__file__).read_text(encoding="utf-8"))
    flags = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert "--idle-timeout" in flags
    assert inspect.signature(p2.run_trial).parameters["idle_timeout_seconds"].default == (
        p2.IDLE_TIMEOUT_SECONDS
    )
