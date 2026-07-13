"""Run a minimal, official-macro-anchored Stage C CODE V behavior probe.

This command records raw bytes and a post-run probe receipt.  It is exploratory
evidence only: it never constructs runner-attested Stage C evidence or an
optical/[EXPERT] verdict.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.batch_run_lock import (  # noqa: E402
    P18_GLOBAL_WINDOW_ROOT,
    batch_runner_lock,
)
from app.core.engines.codev_batch import (  # noqa: E402
    CodeVBatchError,
    resolve_default_codev_executable,
    run_codev_process_bytes,
)

ProbeArm = Literal["native", "to-img", "to-rih"]
PROBE_SCHEMA = "atelier-stagec-official-probe-v1"
OFFICIAL_MACROS = (
    Path("D:/CODEV115/macro/zemaxos_to_cv.seq"),
    Path("D:/CODEV115/macro/cvtfield.seq"),
    Path("D:/CODEV115/macro/spec/specFieldType.seq"),
    Path("D:/CODEV115/macro/spec/specFieldValue.seq"),
    Path("D:/CODEV115/macro/spec/specLateralColorRay.seq"),
    Path("D:/CODEV115/macro/refcheck.seq"),
    Path("D:/CODEV115/macro/rsiview.seq"),
)
_SAFE_RUN_ID = re.compile(r"[A-Za-z0-9_-]+")
PROBE_HEADERS = (
    "record",
    "run_id",
    "arm",
    "field_index",
    "field_type",
    "definition_x",
    "definition_y",
    "rayrsi_return_code",
    "rer",
    "bls",
    "actual_x_mm",
    "actual_y_mm",
    "direction_l",
    "direction_m",
    "direction_n",
    "vuy",
    "vly",
    "vux",
    "vlx",
    "spotdata_return_code",
    "rms_spot_diameter_um",
    "rmswe_return_value",
    "rms_wfe_waves",
    "measured_efl_mm",
)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"size_bytes": len(raw), "sha256": _sha256_bytes(raw)}


def _quote(path: Path) -> str:
    value = str(path)
    if any(char in value for char in ('"', "\r", "\n")):
        raise ValueError(f"unsafe CODE V path: {value!r}")
    return f'"{value}"'


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _field_row() -> str:
    values = (
        '"FIELD"',
        "^run_id",
        "^arm",
        "^f",
        "^field_type",
        "^definition_x",
        "^definition_y",
        "^rc",
        "^rer",
        "^bls",
        "^actual_x",
        "^actual_y",
        "^actual_l",
        "^actual_m",
        "^actual_n",
        "^vuy",
        "^vly",
        "^vux",
        "^vlx",
        "^spot_err",
        "^spot(1)*1000",
        "^wfe_ok",
        "^rwe(1,^f)",
        "^efy",
    )
    return f"  BUF PUT B1 I^row J1..24 {' '.join(values)}"


def build_probe_sequence(
    *, source_zmx: Path, metrics_path: Path, run_id: str, arm: ProbeArm
) -> str:
    """Build the smallest probe grounded in installed official macro idioms."""

    if _SAFE_RUN_ID.fullmatch(run_id) is None:
        raise ValueError("run_id must be ASCII alphanumeric/underscore/hyphen")
    conversion = {
        "native": None,
        "to-img": "IMG",
        "to-rih": "RIH",
    }[arm]
    lines = [
        "! Stage C official behavior probe; probe-only, unattested.",
        "LCL NUM ^input(4) ^spot(10) ^rwe(10,26)",
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote(source_zmx)}",
    ]
    if conversion is not None:
        lines.append(f"IN CV_MACRO:CVTFIELD {conversion}")
    lines.extend(
        [
            f'^run_id == "{run_id}"',
            f'^arm == "{arm}"',
            "^field_type == (TYP FLD)",
            "^numfld == (NUM F)",
            "^refw == (REF)",
            "^image == (FOC Z1)",
            "^efy == ABSF((EFY))",
            "^input(1) == 0",
            "^input(2) == 0",
            "^input(3) == 0",
            "^input(4) == 0",
            "^wfe_ok == RMSWE(1,0,60,^rwe,'NOM')",
            "^row == 1",
            "BUF PUT B1 I^row J1..24 " + " ".join(f'"{value}"' for value in PROBE_HEADERS),
            "^row == ^row+1",
            "OUT YES",
            f'WRI Q"STAGEC_PROBE_BEGIN {PROBE_SCHEMA} {run_id} {arm}"',
            "OUT NO",
            "FOR ^f 1 ^numfld",
            "  ^definition_x == 0",
            "  ^definition_y == 0",
            '  IF ^field_type = "ANG"',
            "    ^definition_x == (XAN F^f Z1)",
            "    ^definition_y == (YAN F^f Z1)",
            '  ELS IF ^field_type = "IMG"',
            "    ^definition_x == (XIM F^f Z1)",
            "    ^definition_y == (YIM F^f Z1)",
            '  ELS IF ^field_type = "RIH"',
            "    ^definition_x == (XRI F^f Z1)",
            "    ^definition_y == (YRI F^f Z1)",
            "  END IF",
            "  ^vuy == (VUY F^f Z1)",
            "  ^vly == (VLY F^f Z1)",
            "  ^vux == (VUX F^f Z1)",
            "  ^vlx == (VLX F^f Z1)",
            "  ^rer == 0",
            "  ^bls == 0",
            "  ^actual_x == -9.9E99",
            "  ^actual_y == -9.9E99",
            "  ^actual_l == -9.9E99",
            "  ^actual_m == -9.9E99",
            "  ^actual_n == -9.9E99",
            "  ^rc == RAYRSI(1,^refw,^f,0,^input)",
            "  IF ^rc = 0",
            "    ^rer == (RER)",
            "    IF ^rer = 0",
            "      ^bls == (BLS)",
            "      ^actual_x == (X S^image)",
            "      ^actual_y == (Y S^image)",
            "      ^actual_l == (L S^image)",
            "      ^actual_m == (M S^image)",
            "      ^actual_n == (N S^image)",
            "    END IF",
            "  END IF",
            "  ^spot_err == SPOTDATA(1,^f,1,0.01,'CEN',0,0,^spot)",
            _field_row(),
            "  BUF FMT B1 I^row J4 'd'",
            "  BUF FMT B1 I^row J6..7 '5e.17e'",
            "  BUF FMT B1 I^row J8..10 'd'",
            "  BUF FMT B1 I^row J11..19 '5e.17e'",
            "  BUF FMT B1 I^row J20 'd'",
            "  BUF FMT B1 I^row J21..24 '5e.17e'",
            "  ^row == ^row+1",
            "END FOR",
            f"BUF EXP B1 {_quote(metrics_path)}",
            "BUF DEL B1",
            "OUT YES",
            f'WRI Q"STAGEC_PROBE_END {PROBE_SCHEMA} {run_id} {arm}"',
            "EXI YES",
            "",
        ]
    )
    return "\n".join(lines)


def _probe_run_id(arm: ProbeArm) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"stagec_probe_{timestamp}_{arm.replace('-', '_')}_{uuid4().hex[:8]}"


def validate_probe_outputs(
    *, metrics_bytes: bytes, listing_bytes: bytes, run_id: str, arm: ProbeArm
) -> dict[str, object]:
    """Validate probe completeness from raw artifacts, not process return-code folklore."""

    errors: list[str] = []
    begin = f"STAGEC_PROBE_BEGIN {PROBE_SCHEMA} {run_id} {arm}".encode("ascii")
    end = f"STAGEC_PROBE_END {PROBE_SCHEMA} {run_id} {arm}".encode("ascii")
    if listing_bytes.count(begin) != 1 or listing_bytes.count(end) != 1:
        errors.append("listing must contain exactly one matching begin/end marker")
    for marker in (b"COMPILATION ERRORS", b"Sequence aborted"):
        if marker in listing_bytes:
            errors.append(f"listing contains fatal marker {marker.decode('ascii')}")
    rows: list[dict[str, str]] = []
    try:
        text = metrics_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        if tuple(reader.fieldnames or ()) != PROBE_HEADERS:
            errors.append("metrics header differs from closed probe schema")
        else:
            rows = list(reader)
    except UnicodeError as exc:
        errors.append(f"metrics are not strict UTF-8: {exc}")
    indices: list[int] = []
    for row in rows:
        if row.get("record") != "FIELD" or row.get("run_id") != run_id:
            errors.append("metrics row identity mismatch")
            continue
        if row.get("arm") != arm:
            errors.append("metrics row arm mismatch")
        try:
            indices.append(int(row["field_index"]))
        except (KeyError, ValueError):
            errors.append("metrics field_index is invalid")
    if not rows:
        errors.append("metrics contain no field rows")
    elif indices != list(range(1, len(rows) + 1)):
        errors.append("metrics field indices are not unique contiguous 1..N")
    return {
        "complete": not errors,
        "errors": errors,
        "field_count": len(rows),
        "metrics_encoding": "utf-8" if not any("UTF-8" in error for error in errors) else None,
        "process_returncode_is_not_a_completeness_gate": True,
    }


def run_probe(
    *,
    source_zmx: Path,
    run_root: Path,
    arm: ProbeArm,
    executable: Path,
    timeout_seconds: float,
    recover_stale_lock: bool = False,
    p18_window_root: Path = P18_GLOBAL_WINDOW_ROOT,
    recover_stale_window_lock: bool = False,
) -> Path:
    with batch_runner_lock(
        p18_window_root,
        recover_stale=recover_stale_window_lock,
        details={"purpose": "stagec-verified-probe"},
    ):
        return _run_probe_under_window(
            source_zmx=source_zmx,
            run_root=run_root,
            arm=arm,
            executable=executable,
            timeout_seconds=timeout_seconds,
            recover_stale_lock=recover_stale_lock,
        )


def _run_probe_under_window(
    *,
    source_zmx: Path,
    run_root: Path,
    arm: ProbeArm,
    executable: Path,
    timeout_seconds: float,
    recover_stale_lock: bool = False,
) -> Path:
    run_id = _probe_run_id(arm)
    run_dir = run_root.resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    staged_source = run_dir / "source.zmx"
    sequence_path = run_dir / "probe.seq"
    metrics_path = run_dir / "metrics.tsv"
    stdout_path = run_dir / "stdout.bin"
    stderr_path = run_dir / "stderr.bin"
    shutil.copyfile(source_zmx.resolve(), staged_source)
    sequence_path.write_text(
        build_probe_sequence(
            source_zmx=staged_source,
            metrics_path=metrics_path,
            run_id=run_id,
            arm=arm,
        ),
        encoding="ascii",
        newline="\n",
    )
    command = [str(executable.resolve()), "/B", sequence_path.name]
    capture = run_codev_process_bytes(
        command,
        work_dir=run_dir,
        timeout_seconds=timeout_seconds,
        recover_stale_lock=recover_stale_lock,
    )
    stdout_path.write_bytes(capture.stdout_bytes)
    stderr_path.write_bytes(capture.stderr_bytes)
    listing_paths = sorted(run_dir.glob("*.lis"))
    validation: dict[str, object]
    if metrics_path.is_file() and len(listing_paths) == 1:
        validation = validate_probe_outputs(
            metrics_bytes=metrics_path.read_bytes(),
            listing_bytes=listing_paths[0].read_bytes(),
            run_id=run_id,
            arm=arm,
        )
    else:
        validation = {
            "complete": False,
            "errors": ["metrics file or unique listing is missing"],
            "field_count": 0,
            "metrics_encoding": None,
            "process_returncode_is_not_a_completeness_gate": True,
        }
    artifacts = sorted(
        path
        for path in run_dir.iterdir()
        if path.is_file() and path.name != "probe-receipt.json" and ".tmp-" not in path.name
    )
    official = {}
    for path in OFFICIAL_MACROS:
        if not path.is_file():
            raise RuntimeError(f"official macro missing: {path}")
        official[str(path)] = _digest(path)
    receipt = {
        "schema_id": PROBE_SCHEMA,
        "evidence_status": "probe-only-unattested",
        "run_id": run_id,
        "arm": arm,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_original": str(source_zmx.resolve()),
        "source_original_digest": _digest(source_zmx.resolve()),
        "command": command,
        "process": {
            "returncode": capture.process.returncode,
            "duration_seconds": capture.duration_seconds,
            "lock_owner": capture.lock_owner,
        },
        "metrics_present": metrics_path.is_file(),
        "listing_count": len(listing_paths),
        "probe_validation": validation,
        "artifacts": {path.relative_to(run_dir).as_posix(): _digest(path) for path in artifacts},
        "official_macro_digests": official,
        "disclaimer": (
            "Probe bytes only; this receipt does not attest production execution, "
            "optical qualification, yield, or an [EXPERT] verdict."
        ),
    }
    receipt_path = run_dir / "probe-receipt.json"
    _atomic_json(receipt_path, receipt)
    if validation["complete"] is not True:
        raise CodeVBatchError(
            "failure",
            "Stage C behavior probe did not produce one complete raw package",
            details={
                "run_dir": str(run_dir),
                "returncode": capture.process.returncode,
                "metrics_present": metrics_path.is_file(),
                "listing_count": len(listing_paths),
                "probe_validation": validation,
                "receipt_path": str(receipt_path),
            },
        )
    return receipt_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zmx", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--arm", choices=("native", "to-img", "to-rih"), required=True)
    parser.add_argument("--executable", type=Path, default=resolve_default_codev_executable())
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--recover-stale-lock", action="store_true")
    parser.add_argument("--recover-stale-window-lock", action="store_true")
    args = parser.parse_args()
    receipt = run_probe(
        source_zmx=args.source_zmx,
        run_root=args.run_root,
        arm=args.arm,
        executable=args.executable,
        timeout_seconds=args.timeout_seconds,
        recover_stale_lock=args.recover_stale_lock,
        recover_stale_window_lock=args.recover_stale_window_lock,
    )
    print(receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
