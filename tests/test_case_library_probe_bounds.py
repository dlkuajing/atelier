"""Deadlines on the optional diagnostic probes `match_case` runs.

Why this file exists: CI shard 2 sat at the job timeout, and the `pytest-timeout`
stack named the path -- `optical.py::match -> _match_case_for_request -> match_case
-> ... -> aberration.compute_mtf`. Nothing on it had a time bound. Optiland is known
to hang on a minority of this corpus (the trace census had to isolate every case in
its own subprocess for that reason), so this was a production defect first and a CI
symptom second: an HTTP request with no upper bound on its own duration.

The first attempt bounded the two probes that appeared in that one stack, and the
hang simply moved to a third (`protected_rms_merit_probe`, a different stack from the
same handler). That is why the guard below is derived from the import list instead of
a hand-written pair: the failure mode is a call site nobody enumerated.

The probes are *optional* -- the routing decision never reads them -- so the correct
containment is to degrade to a "not attempted" result, never to fail the request.
"""

from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

import pytest

from app.core import case_library

_SOURCE = Path(case_library.__file__).read_text(encoding="utf-8")

#: Every Optiland-backed probe `case_library` pulls in from `local_optimizer`. All of
#: them are reachable from the `/api/optical/match` handler.
_REQUEST_PATH_PROBES = tuple(
    sorted(
        alias.asname or alias.name
        for node in ast.walk(ast.parse(_SOURCE))
        if isinstance(node, ast.ImportFrom) and node.module == "app.core.local_optimizer"
        for alias in node.names
        if alias.name.startswith("protected_")
    )
)


def test_the_probe_list_covers_the_known_offenders() -> None:
    """Guards the guard: an import-derived list that silently goes empty proves nothing."""

    assert set(_REQUEST_PATH_PROBES) >= {
        "protected_edge_field_stability_scan",
        "protected_efl_refinement",
        "protected_full_field_recovery_probe",
        "protected_rms_merit_probe",  # the one the first fix missed
    }


def test_bounded_probe_gives_up_when_the_probe_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A probe that never returns must not become a request that never returns."""

    monkeypatch.setattr(case_library, "_DEFAULT_PROBE_DEADLINE_SEC", 0.3)
    released = threading.Event()

    def hangs():
        released.wait(timeout=120)  # released in the finally below, never on the deadline
        return ("should never be observed",)

    started = time.monotonic()
    try:
        result = case_library._bounded_probe(hangs)
        elapsed = time.monotonic() - started
    finally:
        released.set()

    assert result == ()
    # Generous ceiling: the point is "bounded", not "bounded tightly". Without the
    # deadline this line is never reached at all.
    assert elapsed < 15.0, f"probe was not bounded: {elapsed:.1f}s"


def test_bounded_probe_is_transparent_for_a_probe_that_finishes() -> None:
    """Negative control: the bound must not change healthy behaviour."""

    calls: list[int] = []

    def quick():
        calls.append(1)
        return ("a", "b")

    assert case_library._bounded_probe(quick) == ("a", "b")
    assert calls == [1]


def test_bounded_probe_builds_the_degraded_value_only_when_the_deadline_fires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`fallback` is a factory, not a value.

    Two reasons it must stay lazy: the structured probes' degraded values are pydantic
    models that would otherwise be constructed on every healthy request, and an eager
    factory hides a construction error that only a timeout would ever reveal.
    """

    built: list[int] = []

    def fallback():
        built.append(1)
        return "degraded"

    assert case_library._bounded_probe(lambda: "real", fallback=fallback) == "real"
    assert built == []

    monkeypatch.setattr(case_library, "_DEFAULT_PROBE_DEADLINE_SEC", 0.3)
    released = threading.Event()
    try:
        result = case_library._bounded_probe(lambda: released.wait(timeout=120), fallback=fallback)
    finally:
        released.set()
    assert result == "degraded"
    assert built == [1]


def test_bounded_probe_propagates_probe_exceptions() -> None:
    """A broken probe must still surface as a break, not as a degraded result.

    Swallowing exceptions here would make "the probe is wrong" indistinguishable from
    "the probe timed out" -- and the callers already treat degraded as normal.
    """

    def explodes():
        raise RuntimeError("probe is broken")

    with pytest.raises(RuntimeError, match="probe is broken"):
        case_library._bounded_probe(explodes)


def _unbounded_call_lines(source: str, probe_name: str) -> list[int]:
    """Line numbers where `probe_name` is invoked *outside* any `_bounded_probe(...)`.

    Lexical containment is the right test: `_bounded_probe` takes a thunk and calls it
    immediately, so the probe call sits inside the wrapper's own argument list --
    "inside the wrapper's AST subtree" and "covered by its deadline" are the same
    statement here.
    """

    tree = ast.parse(source)
    bounded: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_bounded_probe"
        ):
            bounded.update(id(inner) for inner in ast.walk(node))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == probe_name
        and id(node) not in bounded
    )


def _function_line_span(source: str, func_name: str) -> range:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return range(node.lineno, (node.end_lineno or node.lineno) + 1)
    raise AssertionError(f"{func_name} not found")


@pytest.mark.parametrize("probe_name", _REQUEST_PATH_PROBES)
def test_every_probe_call_sits_inside_a_deadline_wrapper(probe_name: str) -> None:
    """Source-level guard over the whole probe class, not the enumerated instances.

    Two wrappers are legitimate: `_bounded_probe`, and the pre-existing
    `_edge_scan_with_timeout`, which bounds the same scan with thread+join because the
    audit path needs timeout and error told apart.
    """

    allowed = _function_line_span(_SOURCE, "_edge_scan_with_timeout")
    unbounded = [line for line in _unbounded_call_lines(_SOURCE, probe_name) if line not in allowed]
    assert not unbounded, (
        f"{probe_name} is invoked without a deadline at line(s) {unbounded}; route it "
        "through _bounded_probe so the /api/optical/match request stays bounded"
    )


@pytest.mark.parametrize("probe_name", _REQUEST_PATH_PROBES)
def test_the_source_guard_can_actually_fail(probe_name: str) -> None:
    """Positive control: an unbounded call must be detected, a wrapped one must not."""

    bare = f"def f():\n    return {probe_name}(1, 2)\n"
    assert _unbounded_call_lines(bare, probe_name) == [2]
    wrapped = f"def f():\n    return _bounded_probe(lambda: {probe_name}(1, 2))\n"
    assert _unbounded_call_lines(wrapped, probe_name) == []


def test_the_edge_scan_deadline_agrees_with_its_existing_calibration() -> None:
    """The one entry that is not new: the diagnostic-path edge scan gets exactly the
    deadline `EDGE_SCAN_TIMEOUT_S` was already calibrated to, and the fresh measurement
    (n=2, max 2.3s, 10x -> 23s) independently lands on the same 30s."""

    assert (
        case_library.probe_deadline_seconds("protected_edge_field_stability_scan")
        == case_library.EDGE_SCAN_TIMEOUT_S
    )


@pytest.mark.parametrize("probe_name", _REQUEST_PATH_PROBES)
def test_every_probe_has_its_own_measured_deadline(probe_name: str) -> None:
    """One shared deadline was the actual regression: 30s, calibrated on a 5-point edge
    scan, fired on healthy runs of two probes that run whole optimisations, and three CI
    tests failed because their diagnostics went missing. So every probe must carry its
    own entry rather than inherit someone else's calibration."""

    assert probe_name in case_library._PROBE_DEADLINE_SEC


def test_an_unmeasured_probe_fails_toward_completing() -> None:
    """Asymmetric on purpose: too tight silently deletes a diagnostic, too loose only
    makes a hang slower to contain -- and the per-test timeout still names it."""

    generous = case_library.probe_deadline_seconds("some_probe_added_later")
    assert generous == max(case_library._PROBE_DEADLINE_SEC.values())
    assert generous >= max(
        case_library.probe_deadline_seconds(name) for name in _REQUEST_PATH_PROBES
    )


def test_the_slow_optimisation_probes_are_not_bounded_by_the_edge_scan_number() -> None:
    """Regression pin on the exact mistake: the merit probe measured 59.3s healthy, so
    any deadline at or below the 30s edge-scan figure fires on healthy work."""

    for probe_name in ("protected_rms_merit_probe", "protected_full_field_recovery_probe"):
        assert case_library.probe_deadline_seconds(probe_name) > case_library.EDGE_SCAN_TIMEOUT_S
