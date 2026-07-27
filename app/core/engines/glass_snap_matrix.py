"""Offline-testable execution driver for the Phase 13 A-F snap matrix."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from app.core.engines.codev_batch import (
    CodeVBatchResult,
    ensure_codev_safe_input_path,
    run_codev_batch,
)
from app.core.engines.codev_readout import CodeVReadout, CodeVReadoutResult, run_codev_readout
from app.core.engines.glass_snap import build_plastic_catalog
from app.core.engines.glass_snap_chain import (
    SnapProposal,
    build_glass_freeze_reopt_sequence,
    build_material_region_identities,
    configuration_fingerprint,
    material_claims_from_readout,
    propose_material_snaps,
)
from app.core.engines.zmx_import_prep import pad_wavm_bytes

SNAPSHOT_SCHEMA = "atelier-glass-snap-snapshots-v1"
EXPERIMENTS = (
    ("A", "fictitious baseline"),
    ("B", "catalog snap + glass frozen"),
    ("C", "B + short geometry AUT"),
    ("D", "catalog value conflict fail-closed"),
    ("E", "no-op AUT on fictitious glass"),
    ("F", "short versus converged-budget control"),
)
MATRIX_FIELDS = ("candidate_zmx", "experiment", "variable", "status", "evidence_dir", "notes")

ReadoutRunner = Callable[..., CodeVReadoutResult]
BatchRunner = Callable[..., CodeVBatchResult]


@dataclass(frozen=True)
class MatrixRunResult:
    rows: tuple[dict[str, str], ...]
    matrix_path: Path
    report_path: Path


def run_snap_matrix(
    candidates: Iterable[Path | str],
    *,
    output_dir: Path | str,
    run_codev: bool = False,
    readout_runner: ReadoutRunner = run_codev_readout,
    batch_runner: BatchRunner = run_codev_batch,
) -> MatrixRunResult:
    """Build or execute every candidate/experiment cell without judging metrics."""

    output_dir = Path(output_dir).resolve()
    ensure_codev_safe_input_path(output_dir, role="output_dir")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for index, candidate_value in enumerate(candidates):
        candidate = Path(candidate_value).resolve()
        candidate_id = _candidate_token(index, candidate)
        candidate_work = output_dir / candidate_id
        try:
            candidate_work.mkdir(parents=True, exist_ok=True)
            staged = (candidate_work / "source.zmx").resolve()
            # Normalize the WAVM table while staging: without a flush sentinel
            # CODE V imports one default wavelength and every glass loses its
            # measurable dispersion, which is exactly what this matrix probes
            # (see zmx_import_prep).
            padded_bytes, _wavm_rows_added = pad_wavm_bytes(candidate.read_bytes())
            staged.write_bytes(padded_bytes)
        except Exception as exc:  # noqa: BLE001 - preserve prior matrix rows.
            rows.extend(_failed_rows(candidate, output_dir, candidate_id, "stage", exc))
            continue
        if not run_codev:
            rows.extend(
                _pending_readout_rows(candidate, output_dir, candidate_id)
            )
            continue
        try:
            readout_result = readout_runner(source_zmx=staged, work_dir=candidate_work / "readout")
            claims = material_claims_from_readout(readout_result.readout)
            identity = build_material_region_identities(
                claims, num_zooms=readout_result.readout.num_zooms
            )
        except Exception as exc:  # noqa: BLE001 - cell records the exact failed stage.
            rows.extend(_failed_rows(candidate, output_dir, candidate_id, "readout", exc))
            continue

        proposals = propose_material_snaps(
            identity,
            build_plastic_catalog(),
            spectral_definition="C-d-F/runtime-placeholder",
            catalog_spectral_definition="C-d-F/runtime-placeholder",
            # Matrix construction only: deliberately broad and uncalibrated.
            tolerance=1.0,
        )

        for code, variable in EXPERIMENTS:
            evidence = candidate_work / code
            evidence.mkdir(parents=True, exist_ok=True)
            row = _row(candidate, code, variable, evidence, output_dir)
            _write_snap_proposals(evidence / "snap-proposals.json", proposals)
            if not identity.writable:
                row["status"] = f"withheld:{'; '.join(identity.withheld_reasons)}"
                rows.append(row)
                continue
            if code == "D":
                _build_catalog_conflict_probe(evidence, readout_result.readout)
                row["status"] = "built-not-run:pending-real-machine-verification"
                row["notes"] = "Python nd/vd recorded; CODE V GLD readback grammar is pending verification"
                rows.append(row)
                continue
            if code in {"B", "C", "F"} and any(p.disposition != "proposed" for p in proposals):
                row["status"] = "withheld:snap proposal outside uncalibrated construction tolerance"
                rows.append(row)
                continue
            sequence_path = evidence / "run.seq"
            result_path = evidence / "snapshots.tsv"
            run_id = uuid.uuid4().hex
            fingerprint = configuration_fingerprint(
                {"candidate": candidate.name, "experiment": code}
            )
            max_cycles, min_cycles = (25, 3) if code == "F" else (5, 1)
            sequence = build_glass_freeze_reopt_sequence(
                source_zmx=staged,
                result_path=result_path,
                proposals=proposals,
                session_run_id=run_id,
                configuration_fingerprint=fingerprint,
                max_cycles=max_cycles,
                min_cycles=min_cycles,
                apply_snaps=code in {"B", "C", "F"},
                run_aut=code in {"C", "E", "F"},
            )
            sequence_path.write_text(sequence, encoding="ascii", newline="\r\n")
            try:
                batch = batch_runner(
                    sequence_path=sequence_path,
                    result_path=result_path,
                    work_dir=evidence,
                    expected_schema=SNAPSHOT_SCHEMA,
                    required_keys=(
                        "schema",
                        "status",
                        "session_run_id",
                        "configuration_fingerprint",
                        *(
                            f"{stage}.{metric}"
                            for stage in (
                                "before-fictitious",
                                "after-snap-frozen",
                                "after-snap-reopt",
                            )
                            for metric in ("efl", "rmswfe", "rmswfe_ok")
                        ),
                    ),
                    allow_nonzero_ok_result=True,
                )
                _copy_listing(batch, evidence)
                snapshots = extract_snapshot_metrics(batch.data)
                (evidence / "snapshots.json").write_text(
                    json.dumps(snapshots, indent=2, sort_keys=True), encoding="utf-8"
                )
                row["status"] = "ok"
            except Exception as exc:  # noqa: BLE001 - preserve evidence and stage status.
                row["status"] = "failed:execution-or-snapshot-parse"
                row["notes"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)

    matrix_path = output_dir / "p13-snap-matrix.tsv"
    _write_matrix(matrix_path, rows)
    report_path = output_dir / "p13-snap-matrix.md"
    report_path.write_text(_report(rows), encoding="utf-8")
    return MatrixRunResult(tuple(rows), matrix_path, report_path)


def _write_snap_proposals(path: Path, proposals: tuple[SnapProposal, ...]) -> None:
    ledger = []
    for proposal in proposals:
        entry = proposal.result.entry
        ledger.append(
            {
                "region_id": proposal.region.region_id,
                "source": {
                    "glass_name": proposal.region.source_glass_name,
                    "nd": proposal.region.nd,
                    "vd": proposal.region.vd,
                },
                "proposed": None
                if entry is None
                else {
                    "catalog_id": entry.catalog_id,
                    "glass_name": entry.glass_name,
                    "nd": entry.nd,
                    "vd": entry.vd,
                },
                "distance": proposal.result.distance,
                "tolerance": proposal.result.tolerance,
                "verdict": "snapped" if proposal.disposition == "proposed" else "out-of-tolerance",
            }
        )
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")


def extract_snapshot_metrics(data: Mapping[str, str]) -> dict[str, object]:
    """Extract only exported CODE V values; missing/non-numeric facts fail closed."""

    if data.get("schema") != SNAPSHOT_SCHEMA or data.get("status") != "ok":
        raise ValueError("snapshot export schema/status is missing or invalid")
    result: dict[str, object] = {
        "schema": SNAPSHOT_SCHEMA,
        "session_run_id": _required(data, "session_run_id"),
        "configuration_fingerprint": _required(data, "configuration_fingerprint"),
        "snapshots": [],
    }
    snapshots = result["snapshots"]
    assert isinstance(snapshots, list)
    for stage in ("before-fictitious", "after-snap-frozen", "after-snap-reopt"):
        ok = float(_required(data, f"{stage}.rmswfe_ok"))
        if not math.isfinite(ok) or ok < 0.0:
            snapshots.append({"stage": stage, "status": "withheld", "reason": "RMSWE failed"})
            continue
        efl = float(_required(data, f"{stage}.efl"))
        rmswfe = float(_required(data, f"{stage}.rmswfe"))
        if not math.isfinite(efl) or not math.isfinite(rmswfe):
            snapshots.append(
                {"stage": stage, "status": "withheld", "reason": "non-finite metric"}
            )
            continue
        snapshots.append({"stage": stage, "status": "ok", "efl_mm": efl, "rms_wfe_waves": rmswfe})
    return result


def _required(data: Mapping[str, str], key: str) -> str:
    value = data.get(key)
    if value is None or not value.strip():
        raise ValueError(f"missing snapshot key: {key}")
    return value


def _safe_token(value: str) -> str:
    clean = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return f"{clean[:48]}-{hashlib.sha256(value.encode()).hexdigest()[:8]}"


def _candidate_token(index: int, candidate: Path) -> str:
    return f"{index:04d}-{_safe_token(candidate.stem)}-{hashlib.sha256(str(candidate).encode()).hexdigest()[:12]}"


def _row(candidate: Path, code: str, variable: str, evidence: Path, root: Path) -> dict[str, str]:
    return {
        "candidate_zmx": str(candidate),
        "experiment": code,
        "variable": variable,
        "status": "not-run",
        "evidence_dir": str(evidence.relative_to(root)),
        "notes": "",
    }


def _failed_rows(
    candidate: Path, root: Path, candidate_id: str, stage: str, exc: Exception
) -> list[dict[str, str]]:
    rows = []
    for code, variable in EXPERIMENTS:
        evidence = root / candidate_id / code
        evidence.mkdir(parents=True, exist_ok=True)
        row = _row(candidate, code, variable, evidence, root)
        row.update(status=f"failed:{stage}", notes=f"{type(exc).__name__}: {exc}")
        rows.append(row)
    return rows


def _pending_readout_rows(candidate: Path, root: Path, candidate_id: str) -> list[dict[str, str]]:
    rows = []
    for code, variable in EXPERIMENTS:
        evidence = root / candidate_id / code
        evidence.mkdir(parents=True, exist_ok=True)
        row = _row(candidate, code, variable, evidence, root)
        row.update(
            status="built-requires-readout",
            notes="No CODE V process was started; sequence construction requires a readout",
        )
        rows.append(row)
    return rows


def _build_catalog_conflict_probe(evidence: Path, readout: CodeVReadout) -> None:
    """Record Python facts and an explicitly unverified CODE V GLD probe skeleton."""

    facts = [
        {"surface": surface.index, "glass": surface.glass, "nd": surface.nd, "vd": surface.vd}
        for surface in readout.surfaces
        if surface.glass
    ]
    (evidence / "python-catalog-values.json").write_text(
        json.dumps(facts, indent=2, sort_keys=True), encoding="utf-8"
    )
    (evidence / "catalog-conflict-probe.seq").write_text(
        "! GLD catalog interrogation grammar pending real-machine verification\n"
        "! This artifact is built-only and MUST NOT be represented as conflict evidence.\n",
        encoding="ascii",
    )


def _copy_listing(batch: CodeVBatchResult, evidence: Path) -> None:
    if (
        batch.listing_path
        and batch.listing_path.is_file()
        and batch.listing_path.parent != evidence
    ):
        shutil.copy2(batch.listing_path, evidence / batch.listing_path.name)


def _write_matrix(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _report(rows: list[dict[str, str]]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    summary = "\n".join(f"- `{status}`: {count}" for status, count in sorted(counts.items()))
    return f"""# P13 glass snap real-machine matrix

> Thresholds and weights remain uncalibrated; this driver reports measured numbers only and makes no pass/fail verdicts pending expert ratification.

## Results

{summary or "- No rows."}
"""
