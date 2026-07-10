"""Generate the Phase 13 real-machine matrix manifest/report skeleton; does not run CODE V."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

EXPERIMENTS = (
    ("A", "fictitious baseline"),
    ("B", "catalog snap + glass frozen"),
    ("C", "B + short geometry AUT"),
    ("D", "catalog value conflict fail-closed"),
    ("E", "no-op AUT on fictitious glass"),
    ("F", "short versus converged-budget control"),
)


def build_rows(candidates: list[str]) -> list[dict[str, str]]:
    return [
        {
            "candidate_zmx": candidate,
            "experiment": code,
            "variable": variable,
            "status": "not-run",
            "evidence_dir": "",
            "notes": "pending orchestrator real-machine window",
        }
        for candidate in candidates
        for code, variable in EXPERIMENTS
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path, help="UTF-8 text file: one candidate ZMX per line")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    candidates = [x.strip() for x in args.candidates.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(candidates) < 3:
        parser.error("matrix requires at least three candidate ZMX paths")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_rows(candidates)
    with (args.output_dir / "p13-snap-matrix.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0], delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    report = [
        "# P13 glass snap real-machine matrix",
        "",
        "> Skeleton only. No CODE V values have been fabricated; all rows await orchestrator scheduling.",
        "",
        "## Required controls",
        "",
        "- A/B/C: prescription hash, session ID, material readback, config fingerprint, per-field × per-wavelength details.",
        "- C: variables/constraints/merit operands, MXC/MNC/IMP, termination/error trace; prove GLC stayed off.",
        "- D: Python and CODE V GLD values plus conflict label.",
        "- E/F: no-op AUT and budget controls for optical attribution.",
        "",
        "## Results",
        "",
        "Pending real-machine execution. Thresholds and AUT budgets remain uncalibrated until expert ratification.",
        "",
    ]
    (args.output_dir / "p13-snap-matrix.md").write_text("\n".join(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
