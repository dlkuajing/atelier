"""Guards for the CI shard partition.

The property that matters is not balance, it is coverage: a shard split that
silently drops tests reads as a *faster green*, which is indistinguishable from
a real one. Balance only costs minutes; a coverage hole costs correctness.
"""

from __future__ import annotations

import json

import pytest

from scripts.ci_shards import DEFAULT_WEIGHT, partition, verify


def _ids(n: int) -> list[str]:
    return [f"tests/test_x.py::test_{i}" for i in range(n)]


def test_every_test_lands_in_exactly_one_shard() -> None:
    ids = _ids(200)
    buckets = partition(ids, 4, {})
    verify(ids, buckets)
    assert sum(len(b) for b in buckets) == len(ids)


def test_verify_rejects_a_missing_test() -> None:
    """The failure mode this whole file exists for."""
    ids = _ids(50)
    buckets = partition(ids, 3, {})
    buckets[0].pop()
    with pytest.raises(SystemExit, match="missing 1"):
        verify(ids, buckets)


def test_verify_rejects_an_overlap() -> None:
    """Double-running is cheaper than losing a test, but still not the contract."""
    ids = _ids(50)
    buckets = partition(ids, 3, {})
    buckets[1].append(buckets[0][0])
    with pytest.raises(SystemExit, match="overlaps"):
        verify(ids, buckets)


def test_verify_rejects_a_duplicated_collection() -> None:
    ids = _ids(10)
    dupes = [*ids, ids[0]]
    with pytest.raises(SystemExit, match="duplicate"):
        verify(dupes, partition(ids, 2, {}))


def test_an_unrecorded_test_is_still_assigned() -> None:
    """A newly added test must be run, not skipped, before durations catch up."""
    ids = _ids(20) + ["tests/test_new.py::test_brand_new"]
    buckets = partition(ids, 3, {"tests/test_x.py::test_0": 100.0})
    verify(ids, buckets)
    assert any("test_brand_new" in n for b in buckets for n in b)


def test_the_heaviest_test_does_not_share_with_the_second_heaviest() -> None:
    """LPT places the expensive ones first; that is the whole balancing act."""
    ids = _ids(4)
    durations = {ids[0]: 100.0, ids[1]: 90.0, ids[2]: 1.0, ids[3]: 1.0}
    buckets = partition(ids, 2, durations)
    heavy = next(b for b in buckets if ids[0] in b)
    assert ids[1] not in heavy


def test_partition_is_deterministic() -> None:
    """Every shard job recomputes the split independently; they must agree, or
    the union check would pass per-job while the real union has holes."""
    ids = _ids(300)
    durations = {n: (i % 7) * 0.3 for i, n in enumerate(ids)}
    assert partition(ids, 5, durations) == partition(ids, 5, durations)


def test_default_weight_is_small_enough_not_to_swamp_real_measurements() -> None:
    """Most unknowns are tests pytest omitted for running under 0.005s."""
    assert 0 < DEFAULT_WEIGHT <= 0.1


def test_committed_durations_are_parseable_and_nonempty() -> None:
    from pathlib import Path

    data = json.loads(Path("tests/ci-shard-durations.json").read_text(encoding="utf-8"))
    assert len(data) > 500
    assert all(isinstance(v, (int, float)) and v >= 0 for v in data.values())


@pytest.mark.parametrize("shards", [0, -1])
def test_a_nonsense_shard_count_is_refused(shards: int) -> None:
    with pytest.raises(ValueError, match="shards must be"):
        partition(_ids(5), shards, {})


def test_ci_passes_shard_lines_literally_to_pytest() -> None:
    r"""xargs must run with -d '\n'.

    Its default mode interprets quotes and backslashes and splits on whitespace.
    Parametrised node ids contain all three -- shard 1 alone holds 25, e.g.
    ``[D:\safe\lens.zmx]`` and ``[Abnormal AUTO Completion - Scaled down ...]``
    -- and the first sharded CI run died on exactly this
    (``pytest: error: unrecognized arguments: -55.65n4``).
    """
    from pathlib import Path

    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "xargs" in workflow
    # Raw string on purpose. Written as a normal literal this reads as a real
    # newline and would match the *broken* form -- which is exactly what
    # happened: the first version of this guard passed against a ci.yml whose
    # xargs line had a literal newline inside the quotes.
    assert r"-d '\n'" in workflow, "xargs must take each line literally"
    assert "-x" in workflow, "xargs must fail rather than silently batch"


def test_the_ci_workflow_still_parses_as_yaml() -> None:
    """The stronger guard: a real newline inside the xargs quotes breaks the
    document outright, and GitHub would only tell us after a push.
    """
    from pathlib import Path

    import yaml

    doc = yaml.safe_load(Path('.github/workflows/ci.yml').read_text(encoding='utf-8'))
    run = doc['jobs']['backend']['steps'][-1]['run']
    xargs_line = next(x for x in run.splitlines() if x.strip().startswith('xargs'))
    assert '-d ' + chr(39) + chr(92) + 'n' + chr(39) in xargs_line
