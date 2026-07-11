"""Offline-authored P13 CODE V import mystery bisect batch."""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.engines.codev_batch import (  # noqa: E402
    CodeVBatchError,
    resolve_default_codev_executable,
    run_codev_process,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data/zmx/US20170003482A1.zmx"
CANDIDATE = (
    ROOT
    / ".planning/loop/candidates-2026-07-09/US20170003482A1/asphere"
    / "US20170003482A1_target3.797_optimized.zmx"
)
COMMANDS = ("import", "readout", "fct", "lcl", "sav", "wrl")
SOURCES = (
    "seed",
    "candidate",
    "hybrid-header",
    "hybrid-surfaces",
    "hybrid-wavelength",
    "hybrid-name",
)


@dataclass(frozen=True)
class Cell:
    index: int
    source: str
    command: str

    @property
    def cell_id(self) -> str:
        return f"{self.index:02d}-{self.source}-{self.command}"


@dataclass(frozen=True)
class Verdict:
    kind: str
    detail: str = ""

    def display(self) -> str:
        return f"{self.kind} ({self.detail})" if self.detail else self.kind


@dataclass(frozen=True)
class Result:
    cell: Cell
    verdict: Verdict
    returncode: int | None
    duration_seconds: float
    sequence_path: Path
    listing_path: Path


Runner = Callable[..., tuple[object, str, str, float]]


def _blocks(text: str) -> tuple[list[str], list[list[str]]]:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("SURF ")]
    header = lines[: starts[0]]
    blocks = [
        lines[start:end] for start, end in zip(starts, starts[1:] + [len(lines)], strict=True)
    ]
    return header, blocks


def build_sources(seed_text: str, candidate_text: str) -> dict[str, str]:
    """Build deterministic, single-feature candidate-toward-seed hybrids."""
    seed_header, seed_surfaces = _blocks(seed_text)
    cand_header, cand_surfaces = _blocks(candidate_text)

    header = "\n".join(seed_header + [line for block in cand_surfaces for line in block]) + "\n"
    split = len(cand_surfaces) // 2
    surface_blocks = seed_surfaces[:split] + cand_surfaces[split:]
    surfaces = "\n".join(cand_header + [line for block in surface_blocks for line in block]) + "\n"

    seed_wav = [line for line in seed_header if line.startswith(("WAVM ", "PWAV "))]
    wavelength_header = [line for line in cand_header if not line.startswith(("WAVM ", "PWAV "))]
    insert_at = (
        next(i for i, line in enumerate(wavelength_header) if line.startswith("SURF "))
        if any(line.startswith("SURF ") for line in wavelength_header)
        else len(wavelength_header)
    )
    wavelength_header[insert_at:insert_at] = seed_wav
    wavelength = (
        "\n".join(wavelength_header + [line for block in cand_surfaces for line in block]) + "\n"
    )

    seed_name = next(line for line in seed_header if line.startswith("NAME "))
    name = re.sub(r"(?m)^NAME .*$", seed_name, candidate_text, count=1)
    return {
        "seed": seed_text,
        "candidate": candidate_text,
        "hybrid-header": header,
        "hybrid-surfaces": surfaces,
        "hybrid-wavelength": wavelength,
        "hybrid-name": name,
    }


def build_grid() -> list[Cell]:
    """Return 28 cells: anchors plus paired single-variable discriminators."""
    pairs = [(source, "import") for source in SOURCES]
    pairs += [(source, command) for command in COMMANDS[1:] for source in ("seed", "candidate")]
    pairs += [(source, command) for source in SOURCES[2:] for command in ("fct", "sav", "readout")]
    return [Cell(i, source, command) for i, (source, command) in enumerate(pairs)]


def build_sequence(command: str, source_name: str = "inputzmx") -> str:
    prefix: list[str] = ["! P13 mystery bisect; generated offline.", "OUT NO"]
    if command == "fct":
        prefix += ["FCT @p13ok", "  @p13ok == 1", "END FCT @p13ok"]
    elif command == "lcl":
        prefix += ["LCL NUM ^p13row", "^p13row == 1"]
    lines = prefix + [f'IN CV_MACRO:ZEMAXOS_TO_CV "{source_name}"']
    if command == "readout":
        lines += [
            'BUF PUT B1 I1 J1 "probe"',
            'BUF PUT B1 I1 J2 "ok"',
            'BUF EXP B1 "probeout"',
            "BUF DEL B1",
        ]
    elif command == "sav":
        # CODE V Lens System Setup Reference Manual 11.5, pp. 87-89: command-line
        # SAV is the unconditional form used in .SEQ files; repeat saves version the
        # previous file. Each cell is fresh, so this relative target cannot pre-exist.
        lines += ["SAV probe_lens"]
    elif command == "wrl":
        lines += ["WRL probe_lens"]
    lines += ["OUT YES", "EXI YES", ""]
    return "\r\n".join(lines)


def classify_listing(text: str, *, timed_out: bool = False) -> Verdict:
    if timed_out:
        return Verdict("timeout")
    cascade_count = len(re.findall(r"Zero or negative value for row qualifier", text, re.I))
    if cascade_count:
        return Verdict("row-cascade", str(cascade_count))
    if re.search(
        r"(?:compile|syntax) error|ERROR.*(?:FCT|LCL)|undefined (?:variable|function)", text, re.I
    ):
        return Verdict("compile-error")
    if not re.search(r"\b(?:ERROR|CRITICAL|FATAL)\b", text, re.I):
        return Verdict("clean")
    line = next(
        line.strip() for line in text.splitlines() if re.search(r"ERROR|CRITICAL|FATAL", line, re.I)
    )
    return Verdict("other", line[:160].replace("\t", " "))


def _listing(cell_dir: Path) -> Path:
    matches = sorted(cell_dir.glob("*.lis"), key=lambda path: path.stat().st_mtime_ns)
    return matches[-1] if matches else cell_dir / "probe.lis"


def run_cell(
    cell: Cell, source_text: str, output_dir: Path, *, timeout: float, runner: Runner
) -> Result:
    cell_dir = output_dir / cell.cell_id
    cell_dir.mkdir(parents=True, exist_ok=False)
    source_path = cell_dir / "inputzmx"
    source_path.write_text(source_text, encoding="ascii", newline="\n")
    sequence_path = cell_dir / "probe.seq"
    sequence_path.write_bytes(build_sequence(cell.command).encode("ascii"))
    command = [str(resolve_default_codev_executable()), "/B", sequence_path.name]
    try:
        process, stdout, stderr, duration = runner(
            command, work_dir=cell_dir, timeout_seconds=timeout
        )
        listing_path = _listing(cell_dir)
        text = (
            listing_path.read_text(encoding="utf-8", errors="replace")
            if listing_path.exists()
            else stdout + "\n" + stderr
        )
        verdict = classify_listing(text)
        returncode = getattr(process, "returncode", None)
    except CodeVBatchError as exc:
        listing_path = _listing(cell_dir)
        text = (
            listing_path.read_text(encoding="utf-8", errors="replace")
            if listing_path.exists()
            else str(exc.details.get("listing_tail", ""))
        )
        verdict = classify_listing(text, timed_out=exc.kind == "timeout")
        returncode = None
        duration = timeout
    if not listing_path.exists():
        listing_path.write_text(text, encoding="utf-8")
    return Result(cell, verdict, returncode, duration, sequence_path, listing_path)


def write_reports(results: Sequence[Result], output_dir: Path) -> None:
    fields = [
        "cell",
        "source",
        "command_set",
        "verdict",
        "detail",
        "returncode",
        "duration_seconds",
        "seq",
        "lis",
    ]
    with (output_dir / "summary.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "cell": result.cell.cell_id,
                    "source": result.cell.source,
                    "command_set": result.cell.command,
                    "verdict": result.verdict.kind,
                    "detail": result.verdict.detail,
                    "returncode": result.returncode,
                    "duration_seconds": f"{result.duration_seconds:.3f}",
                    "seq": result.sequence_path,
                    "lis": result.listing_path,
                }
            )
    lines = [
        "# P13 mystery bisect results",
        "",
        "| cell | source | command-set | verdict | rc | seconds |",
        "|---|---|---|---|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result.cell.cell_id} | {result.cell.source} | {result.cell.command} | {result.verdict.display()} | {result.returncode if result.returncode is not None else ''} | {result.duration_seconds:.3f} |"
        )
    lines += ["", "## discriminator candidates", ""]
    lookup = {(r.cell.source, r.cell.command): r.verdict.display() for r in results}
    flips: list[str] = []
    for source in SOURCES:
        for left, right in zip(COMMANDS, COMMANDS[1:], strict=False):
            if (
                (source, left) in lookup
                and (source, right) in lookup
                and lookup[source, left] != lookup[source, right]
            ):
                flips.append(
                    f"- command-set: `{source}` `{left}` → `{right}`: {lookup[source, left]} → {lookup[source, right]}"
                )
    for command in COMMANDS:
        for source in SOURCES[1:]:
            if (
                ("seed", command) in lookup
                and (source, command) in lookup
                and lookup["seed", command] != lookup[source, command]
            ):
                flips.append(
                    f"- source: `{command}` `seed` → `{source}`: {lookup['seed', command]} → {lookup[source, command]}"
                )
    lines += flips or ["- None in the executed slice."]
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("p13-mystery-bisect-output"))
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=float, default=40.0)
    args = parser.parse_args()
    if args.start < 0 or (args.limit is not None and args.limit < 1):
        parser.error("--start must be >= 0 and --limit must be >= 1")
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    sources = build_sources(SEED.read_text(encoding="ascii"), CANDIDATE.read_text(encoding="ascii"))
    cells = build_grid()[args.start : None if args.limit is None else args.start + args.limit]
    results = [
        run_cell(cell, sources[cell.source], output, timeout=args.timeout, runner=run_codev_process)
        for cell in cells
    ]
    write_reports(results, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
