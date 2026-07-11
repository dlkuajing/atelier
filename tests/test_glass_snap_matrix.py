from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

from app.core.engines.codev_batch import CodeVBatchResult
from app.core.engines.codev_readout import parse_codev_readout_file
from app.core.engines.glass_snap import CatalogEntry
from app.core.engines.glass_snap_matrix import (
    EXPERIMENTS,
    SNAPSHOT_SCHEMA,
    extract_snapshot_metrics,
    run_snap_matrix,
)

FIXTURE = Path(".planning/loop/p13-smoke-2026-07-11/readout5-glasscode/atelier_codev_readout.tsv")


def _candidate(tmp_path: Path, *, dotted: bool = False) -> Path:
    parent = tmp_path / (".inputs" if dotted else "inputs")
    parent.mkdir()
    path = parent / "candidate.zmx"
    path.write_text("VERS 000001\n", encoding="ascii")
    return path


def _readout_runner(**kwargs):
    source = Path(kwargs["source_zmx"])
    assert not any(part.startswith(".") for part in source.parts)
    fixture = Path(kwargs["work_dir"]) / "honest-dispersion-readout.tsv"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    text = FIXTURE.read_text(encoding="utf-8")
    for surface in (1, 4, 6, 8, 10, 12, 14, 16):
        text = text.replace(f"surface.{surface}.vd\t0", f"surface.{surface}.vd\t55.9")
    fixture.write_text(text, encoding="utf-8")
    return SimpleNamespace(readout=parse_codev_readout_file(fixture))


def _snapshot_data() -> dict[str, str]:
    data = {
        "schema": SNAPSHOT_SCHEMA,
        "status": "ok",
        "session_run_id": "fake",
        "configuration_fingerprint": "fp",
    }
    for index, stage in enumerate(
        ("before-fictitious", "after-snap-frozen", "after-snap-reopt"), 1
    ):
        data[f"{stage}.efl"] = str(index)
        data[f"{stage}.rmswfe"] = str(index / 10)
        data[f"{stage}.rmswfe_ok"] = "1"
    return data


def _batch_runner(**kwargs):
    return CodeVBatchResult(
        executable=Path("fake-codev.exe"),
        sequence_path=Path(kwargs["sequence_path"]),
        result_path=Path(kwargs["result_path"]),
        returncode=0,
        duration_seconds=0.1,
        data=_snapshot_data(),
    )


def test_matrix_full_af_execution_and_tsv_statuses(tmp_path: Path) -> None:
    output = tmp_path / "matrix"
    result = run_snap_matrix(
        [_candidate(tmp_path)],
        output_dir=output,
        run_codev=True,
        readout_runner=_readout_runner,
        batch_runner=_batch_runner,
    )
    assert len(result.rows) == len(EXPERIMENTS)
    by_code = {row["experiment"]: row for row in result.rows}
    assert by_code["D"]["status"] == "built-not-run:pending-real-machine-verification"
    assert {by_code[code]["status"] for code in "ABCEF"} == {"ok"}
    assert all(
        (output / by_code[code]["evidence_dir"] / "snapshots.json").is_file() for code in "ABCEF"
    )
    with result.matrix_path.open(encoding="utf-8", newline="") as handle:
        assert len(list(csv.DictReader(handle, delimiter="\t"))) == 6


def test_matrix_dry_run_stages_dotted_source_and_builds_sequences(tmp_path: Path) -> None:
    output = tmp_path / "matrix"
    result = run_snap_matrix(
        [_candidate(tmp_path, dotted=True)], output_dir=output, readout_runner=_readout_runner
    )
    assert {row["status"] for row in result.rows} == {"built-requires-readout"}
    assert list(output.glob("*/source.zmx"))
    assert not list(output.glob("*/readout"))


def test_matrix_identity_gate_withholds_all_cells(monkeypatch, tmp_path: Path) -> None:
    from app.core.engines import glass_snap_matrix

    monkeypatch.setattr(glass_snap_matrix, "material_claims_from_readout", lambda readout: ())
    result = run_snap_matrix(
        [_candidate(tmp_path)], output_dir=tmp_path / "matrix", run_codev=True, readout_runner=_readout_runner
    )
    assert all(row["status"].startswith("withheld:") for row in result.rows)


def test_withheld_candidate_still_writes_out_of_tolerance_proposal_ledger(
    monkeypatch, tmp_path: Path
) -> None:
    from app.core.engines import glass_snap_matrix

    monkeypatch.setattr(
        glass_snap_matrix,
        "build_plastic_catalog",
        lambda: (CatalogEntry("far-catalog", "FAR", "v1", 3.0, 1.0),),
    )
    output = tmp_path / "matrix"
    result = run_snap_matrix(
        [_candidate(tmp_path)],
        output_dir=output,
        run_codev=True,
        readout_runner=_readout_runner,
        batch_runner=_batch_runner,
    )
    row = next(row for row in result.rows if row["experiment"] == "B")
    assert row["status"] == "withheld:snap proposal outside uncalibrated construction tolerance"
    ledger = json.loads((output / row["evidence_dir"] / "snap-proposals.json").read_text())
    assert ledger
    assert {item["verdict"] for item in ledger} == {"out-of-tolerance"}
    assert all(item["tolerance"] == 1.0 for item in ledger)


def test_matrix_readout_failure_marks_all_cells(tmp_path: Path) -> None:
    def fail(**kwargs):
        raise RuntimeError("readout broke")

    result = run_snap_matrix(
        [_candidate(tmp_path)], output_dir=tmp_path / "matrix", run_codev=True, readout_runner=fail
    )
    assert {row["status"] for row in result.rows} == {"failed:readout"}
    assert all("readout broke" in row["notes"] for row in result.rows)


def test_matrix_missing_snapshot_key_fails_closed(tmp_path: Path) -> None:
    def incomplete(**kwargs):
        result = _batch_runner(**kwargs)
        result.data.pop("after-snap-reopt.efl")
        return result

    result = run_snap_matrix(
        [_candidate(tmp_path)],
        output_dir=tmp_path / "matrix",
        run_codev=True,
        readout_runner=_readout_runner,
        batch_runner=incomplete,
    )
    statuses = {row["status"] for row in result.rows if row["experiment"] != "D"}
    assert statuses == {"failed:execution-or-snapshot-parse"}


def test_same_stem_candidates_get_distinct_evidence_and_staged_bytes(tmp_path: Path) -> None:
    candidates = []
    for dirname, content in (("asphere", "ONE"), ("both", "TWO")):
        parent = tmp_path / dirname
        parent.mkdir()
        candidate = parent / "lens.zmx"
        candidate.write_text(content, encoding="ascii")
        candidates.append(candidate)
    result = run_snap_matrix(candidates, output_dir=tmp_path / "matrix")
    evidence_roots = {row["evidence_dir"].split("/")[0].split("\\")[0] for row in result.rows}
    assert len(evidence_roots) == 2
    assert {path.read_text(encoding="ascii") for path in (tmp_path / "matrix").glob("*/source.zmx")} == {"ONE", "TWO"}


def test_bad_candidate_staging_does_not_discard_prior_rows(tmp_path: Path) -> None:
    good = _candidate(tmp_path)
    result = run_snap_matrix([good, tmp_path / "missing.zmx"], output_dir=tmp_path / "matrix")
    assert len(result.rows) == 12
    assert [row["status"] for row in result.rows[:6]] == ["built-requires-readout"] * 6
    assert {row["status"] for row in result.rows[6:]} == {"failed:stage"}


def test_e_runs_aut_while_a_does_not(tmp_path: Path) -> None:
    output = tmp_path / "matrix"
    result = run_snap_matrix([_candidate(tmp_path)], output_dir=output, run_codev=True,
                             readout_runner=_readout_runner, batch_runner=_batch_runner)
    by_code = {row["experiment"]: row for row in result.rows}
    a = (output / by_code["A"]["evidence_dir"] / "run.seq").read_text(encoding="ascii")
    e = (output / by_code["E"]["evidence_dir"] / "run.seq").read_text(encoding="ascii")
    assert "\nAUT\n" not in a.replace("\r\n", "\n")
    assert "\nAUT\n" in e.replace("\r\n", "\n")


def test_snapshot_rmswe_failure_and_nonfinite_values_are_withheld() -> None:
    data = _snapshot_data()
    data["before-fictitious.rmswfe"] = "0"
    data["before-fictitious.rmswfe_ok"] = "-1"
    data["after-snap-frozen.efl"] = "nan"
    snapshots = extract_snapshot_metrics(data)["snapshots"]
    assert snapshots[0] == {"stage": "before-fictitious", "status": "withheld", "reason": "RMSWE failed"}
    assert snapshots[1]["status"] == "withheld"
    assert "efl_mm" not in snapshots[0] and "rms_wfe_waves" not in snapshots[0]


def test_snapshot_zero_rmswe_with_nonnegative_flag_is_legitimate() -> None:
    data = _snapshot_data()
    data["before-fictitious.rmswfe"] = "0"
    data["before-fictitious.rmswfe_ok"] = "0"
    snapshot = extract_snapshot_metrics(data)["snapshots"][0]
    assert snapshot == {
        "stage": "before-fictitious",
        "status": "ok",
        "efl_mm": 1.0,
        "rms_wfe_waves": 0.0,
    }
