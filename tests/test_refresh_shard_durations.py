"""The durations harvester must not make the shard balance worse than the stale file.

Context: the committed `tests/ci-shard-durations.json` was measured locally before the
`fov_deg` re-anchor, and CI-measured values disagree badly — one test recorded at 149.1s
actually takes 640.8s, and several recorded at 0.1s take 28-40s. That is the whole
shard-imbalance story. These tests pin the two properties that make refreshing safe.
"""

from __future__ import annotations

import json

from scripts.refresh_shard_durations import merge, parse_durations

_LOG = """
2026-07-30T01:40:00Z ============================= slowest 25 durations ==============================
2026-07-30T01:40:00Z 640.83s call     tests/test_acceptance_task_export.py::test_slow_one
2026-07-30T01:40:00Z 87.94s call     tests/test_acceptance_task_export.py::test_writes_artifacts
2026-07-30T01:40:00Z 12.10s setup    tests/test_optical_match.py::test_setup_heavy
2026-07-30T01:40:00Z 3.20s teardown tests/test_optical_match.py::test_teardown_heavy
2026-07-30T01:40:00Z 0.50s call     tests/test_aberration.py::test_quick
"""


def test_only_call_durations_are_taken() -> None:
    """setup and teardown are attributed separately; adding them would double-count the
    fixtures a parametrised test shares."""

    measured = parse_durations(_LOG)
    assert set(measured) == {
        "tests/test_acceptance_task_export.py::test_slow_one",
        "tests/test_acceptance_task_export.py::test_writes_artifacts",
        "tests/test_aberration.py::test_quick",
    }
    assert measured["tests/test_acceptance_task_export.py::test_slow_one"] == 640.83


def test_a_repeated_node_id_keeps_the_slowest_reading() -> None:
    """A log can hold a retry. Taking the last occurrence would let a warm, fast repeat
    overwrite the cold measurement the partition has to plan for."""

    doubled = _LOG + "\n2026-07-30T01:41:00Z 4.00s call     tests/test_acceptance_task_export.py::test_slow_one\n"
    assert parse_durations(doubled)["tests/test_acceptance_task_export.py::test_slow_one"] == 640.83


def test_a_parametrised_node_id_survives_parsing() -> None:
    log = "1.50s call     tests/test_optical_match.py::test_thing[match_request0]\n"
    assert parse_durations(log) == {
        "tests/test_optical_match.py::test_thing[match_request0]": 1.5
    }


def test_merge_never_drops_an_entry_ci_did_not_report() -> None:
    """`--durations=25` reports only the slowest per shard, so absence means "not
    measured this time", never "now fast". Dropping those would reset hundreds of tests
    to DEFAULT_WEIGHT and make the balance worse than the stale file it replaced."""

    existing = {"a": 10.0, "b": 20.0, "c": 30.0}
    merged, report = merge(existing, {"b": 99.0})
    assert merged == {"a": 10.0, "b": 99.0, "c": 30.0}
    assert report["existing"] == 3
    assert report["merged"] == 3
    assert report["moved"] == 1
    assert report["new"] == 0


def test_merge_reports_new_entries_separately_from_moved_ones() -> None:
    merged, report = merge({"a": 10.0}, {"a": 10.2, "z": 5.0})
    assert merged["z"] == 5.0
    assert report["new"] == 1
    # 10.0 -> 10.2 is inside the 0.5s noise band and must not be reported as a move.
    assert report["moved"] == 0


def test_the_biggest_moves_are_reported_slowest_first() -> None:
    _, report = merge({}, {"slow": 100.0, "mid": 50.0, "fast": 1.0})
    assert [row["node_id"] for row in report["biggest_moves"]] == ["slow", "mid", "fast"]


def test_the_committed_durations_file_is_a_flat_node_id_to_seconds_map() -> None:
    """Guards the shape `ci_shards.load_durations` depends on."""

    from scripts.refresh_shard_durations import DURATIONS

    data = json.loads(DURATIONS.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data
    assert all(isinstance(k, str) and k.startswith("tests/") for k in data)
    assert all(isinstance(v, (int, float)) and v >= 0 for v in data.values())


def test_writing_elsewhere_still_reads_the_committed_base(tmp_path, monkeypatch, capsys) -> None:
    """The CLI-level version of the never-drop property.

    `--out` and the base used to be the same argument, so `--out /somewhere/else.json`
    read that nonexistent file as the base and produced a durations file containing only
    the 50 freshly-harvested entries -- resetting ~1500 tests to DEFAULT_WEIGHT. The
    unit test on `merge()` did not cover this because the loss happened in the wiring.
    """

    from scripts import refresh_shard_durations as mod

    base = tmp_path / "base.json"
    base.write_text(json.dumps({"tests/a.py::test_a": 12.0, "tests/b.py::test_b": 3.0}), "utf-8")
    out = tmp_path / "nested" / "out.json"

    monkeypatch.setattr(mod, "fetch_run_logs", lambda run_id: _LOG)
    assert mod.main(["--run", "1", "--base", str(base), "--out", str(out)]) == 0

    written = json.loads(out.read_text(encoding="utf-8"))
    # Both pre-existing entries survive alongside the harvested ones.
    assert written["tests/a.py::test_a"] == 12.0
    assert written["tests/b.py::test_b"] == 3.0
    assert written["tests/test_acceptance_task_export.py::test_slow_one"] == 640.83


def test_an_empty_base_is_refused_rather_than_written(tmp_path, monkeypatch) -> None:
    """Building a durations file from one harvest alone is worse than the stale file it
    would replace, so it must fail loudly instead of succeeding quietly."""

    from scripts import refresh_shard_durations as mod

    monkeypatch.setattr(mod, "fetch_run_logs", lambda run_id: _LOG)
    out = tmp_path / "out.json"
    assert mod.main(["--run", "1", "--base", str(tmp_path / "absent.json"), "--out", str(out)]) == 1
    assert not out.exists()
