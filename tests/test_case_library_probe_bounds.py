"""Deadlines on the optional diagnostic probes `match_case` runs.

Why this file exists: CI shard 2 sat at the 60-minute job timeout, and the
`pytest-timeout` stack named the path -- `optical.py::match ->
_match_case_for_request -> match_case -> _build_full_field_recovery_diagnostic ->
protected_full_field_recovery_probe -> ... -> aberration.compute_mtf`. Nothing on
it had a time bound. Optiland is known to hang on a minority of this corpus (the
trace census had to isolate every case in its own subprocess for that reason), so
this was a production defect first and a CI symptom second: an HTTP request with
no upper bound on its own duration.

The probes are *optional* -- the routing decision never reads them -- so the
correct containment is to degrade to "no diagnostic", never to fail the request.
"""

from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

import pytest

from app.core import case_library

_SOURCE = Path(case_library.__file__).read_text(encoding="utf-8")

#: The Optiland-backed probes reachable from the `/api/optical/match` handler.
_REQUEST_PATH_PROBES = (
    "protected_full_field_recovery_probe",
    "protected_edge_field_stability_scan",
)


def test_bounded_probe_gives_up_and_returns_empty_when_the_probe_hangs(monkeypatch):
    """A probe that never returns must not become a request that never returns."""

    monkeypatch.setattr(case_library, "FULL_FIELD_PROBE_TIMEOUT_SEC", 0.3)
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


def test_bounded_probe_is_transparent_for_a_probe_that_finishes():
    """Negative control: the bound must not change healthy behaviour."""

    seen: list[tuple] = []

    def quick(*args):
        seen.append(args)
        return ("a", "b")

    assert case_library._bounded_probe(quick, 1, "x", None) == ("a", "b")
    assert seen == [(1, "x", None)]


def test_bounded_probe_propagates_probe_exceptions():
    """A broken probe must still surface as a break, not as a silent empty result.

    Swallowing exceptions here would make "the probe is wrong" indistinguishable
    from "the probe timed out" -- and the callers already treat empty as normal.
    """

    def explodes():
        raise RuntimeError("probe is broken")

    with pytest.raises(RuntimeError, match="probe is broken"):
        case_library._bounded_probe(explodes)


def _bare_call_lines(source: str, probe_name: str) -> list[int]:
    """Line numbers where `probe_name` is *invoked*, not passed as a value.

    Passing it to `_bounded_probe` makes it a plain `Name` load, so only the
    directly-invoked form is reported.
    """

    return sorted(
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == probe_name
    )


def _function_line_span(source: str, func_name: str) -> range:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return range(node.lineno, (node.end_lineno or node.lineno) + 1)
    raise AssertionError(f"{func_name} not found")


@pytest.mark.parametrize("probe_name", _REQUEST_PATH_PROBES)
def test_every_probe_call_sits_inside_a_deadline_wrapper(probe_name):
    """Source-level guard: catches a *future* probe call that skips the bound.

    A behavioural test can only cover the call sites that exist today; the failure
    mode being guarded is someone adding another one. Two wrappers are legitimate:
    `_bounded_probe` (used by taking the probe as a value, so it produces no direct
    call at all) and the pre-existing `_edge_scan_with_timeout`, which bounds the
    same scan with thread+join because the audit path needs timeout and error told
    apart.
    """

    allowed = _function_line_span(_SOURCE, "_edge_scan_with_timeout")
    unbounded = [line for line in _bare_call_lines(_SOURCE, probe_name) if line not in allowed]
    assert not unbounded, (
        f"{probe_name} is invoked without a deadline at line(s) {unbounded}; route it "
        "through _bounded_probe so the /api/optical/match request stays bounded"
    )


@pytest.mark.parametrize("probe_name", _REQUEST_PATH_PROBES)
def test_the_source_guard_can_actually_fail(probe_name):
    """Positive control on the guard above -- an unbounded call must be detected."""

    injected = f"def f():\n    return {probe_name}(1, 2)\n"
    assert _bare_call_lines(injected, probe_name) == [2]


def test_the_deadline_reuses_the_already_calibrated_scan_timeout():
    """No new magic number: one of the bounded probes *is* the calibrated scan."""

    assert case_library.FULL_FIELD_PROBE_TIMEOUT_SEC == case_library.EDGE_SCAN_TIMEOUT_S
