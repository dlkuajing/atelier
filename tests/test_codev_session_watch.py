"""The continuous 红线① watch must fire, and must be provably able to fire.

No `skipif` anywhere in this file, on purpose. A watchdog whose test disarms itself
when the thing it guards is absent is a watchdog that stays silent on the one run
that needed it -- this repo has already paid for that lesson once, when five
assertions rode a `skipif(not BACKFILL.is_file())` and CI stayed green for three
days over missing data. The session source is injected instead, so these run
anywhere, including on a machine with no CODE V.
"""

from __future__ import annotations

import pytest

from scripts import codev_session_watch as watch


def _run(monkeypatch, capsys, sequence, argv):
    """Drive the watch over a scripted sequence of session counts."""

    calls = iter(sequence)

    def fake_sessions():
        try:
            n = next(calls)
        except StopIteration:
            n = 0
        return [{"pid": 1000 + i, "ppid": 4, "name": "codev"} for i in range(n)]

    monkeypatch.setattr(watch, "codev_sessions", fake_sessions)
    monkeypatch.setattr(watch.time, "sleep", lambda _s: None)
    code = watch.main(argv)
    return code, capsys.readouterr().out


def test_second_instance_trips_the_red_line(monkeypatch, capsys):
    """One session is the batch's own; two is the P18 contamination mechanism."""

    code, out = _run(
        monkeypatch, capsys, [1, 1, 2, 1], ["--samples", "4", "--interval", "0", "--max", "1"]
    )
    assert code == 2
    assert "ALERT" in out
    assert "CONTAMINATED" in out


def test_quiet_run_is_clean_and_says_so(monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, [0, 0, 0], ["--samples", "3", "--interval", "0", "--max", "0"])
    assert code == 0
    assert "ALERT" not in out
    assert "verdict=clean" in out


def test_contamination_survives_a_recovery(monkeypatch, capsys):
    """The endpoint check is exactly what this exists to replace.

    A second instance that appears and exits mid-batch leaves both the pre-run and
    the `finally` count at 1. The verdict must still be CONTAMINATED, and a CLEAR
    line must not be mistaken for absolution.
    """

    code, out = _run(
        monkeypatch, capsys, [1, 2, 1, 1], ["--samples", "4", "--interval", "0", "--max", "1"]
    )
    assert code == 2
    assert "ALERT" in out
    assert "CLEAR" in out
    assert "verdict=CONTAMINATED" in out


def test_heartbeat_means_silence_is_never_ambiguous(monkeypatch, capsys):
    """A watch that prints nothing while healthy cannot be distinguished from a dead one."""

    _code, out = _run(
        monkeypatch, capsys, [0] * 5, ["--samples", "5", "--interval", "0", "--max", "0", "--heartbeat", "1"]
    )
    assert out.count("OK ") >= 5


def test_alert_is_emitted_once_per_episode_not_per_sample(monkeypatch, capsys):
    """Otherwise a long contamination floods the monitor and gets rate-limited away."""

    _code, out = _run(
        monkeypatch, capsys, [2, 2, 2, 1], ["--samples", "4", "--interval", "0", "--max", "1"]
    )
    assert out.count("ALERT") == 1


def test_session_ruler_is_shared_with_the_runner():
    """Two rulers for one quantity is this project's most expensive recurring defect."""

    from scripts import p2_crosssource_trial

    assert watch.codev_sessions is p2_crosssource_trial.codev_sessions


@pytest.mark.parametrize("count,limit,expected_trip", [(0, 0, False), (1, 1, False), (2, 1, True), (1, 0, True)])
def test_trip_boundary(monkeypatch, capsys, count, limit, expected_trip):
    code, _out = _run(
        monkeypatch, capsys, [count], ["--samples", "1", "--interval", "0", "--max", str(limit)]
    )
    assert (code == 2) is expected_trip
