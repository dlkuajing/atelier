"""Audit whether the current case library can satisfy a high-FOV seed intake.

Run:
  cd lumira-backend
  uv run python scripts/audit_seed_intake.py --target-fov 88 --target-efl 2.8 --target-fnum 1.9

This is intentionally lightweight: it audits the generated library evidence
that the runtime already trusts. A new ZMX candidate should first be added to
the local ammo/manifest flow and regenerated with `scripts/generate_cases.py`;
then this audit tells whether the full-field evidence gap is actually closed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.case_library import (  # noqa: E402
    build_sample_from_optic,
    build_seed_intake_audit,
    load_case_library,
)
from app.core.mtf_fields import format_mtf_field_fraction  # noqa: E402
from app.core.optical_sample import SeedAcquisitionBrief  # noqa: E402
from app.core.zmx_ingest import load_normalized_zmx  # noqa: E402

_CANDIDATE_NAME_RE = re.compile(
    r"(?P<n>\d+)P_F(?P<fnum>\d+(?:\.\d+)?)_FOV(?P<fov>\d+(?:\.\d+)?)_"
    r"EFL(?P<efl>\d+(?:\.\d+)?)_IMH(?P<imh>\d+(?:\.\d+)?)_TTL(?P<ttl>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-fov", type=float, default=88.0)
    parser.add_argument("--target-efl", type=float, default=2.8)
    parser.add_argument("--target-fnum", type=float, default=1.9)
    parser.add_argument("--min-fov", type=float, default=85.0)
    parser.add_argument("--required-field", type=float, default=1.0)
    parser.add_argument("--efl-window", type=float, default=0.30)
    parser.add_argument("--efl-lo", type=float)
    parser.add_argument("--efl-hi", type=float)
    parser.add_argument("--fnum-low-window", type=float, default=0.20)
    parser.add_argument("--fnum-high-window", type=float, default=0.25)
    parser.add_argument("--fnum-lo", type=float)
    parser.add_argument("--fnum-hi", type=float)
    parser.add_argument("--target-image-height", type=float)
    parser.add_argument("--image-height-window", type=float, default=0.35)
    parser.add_argument("--image-height-lo", type=float)
    parser.add_argument("--image-height-hi", type=float)
    parser.add_argument("--target-elements", type=int)
    parser.add_argument("--element-window", type=int, default=1)
    parser.add_argument("--element-count-lo", type=int)
    parser.add_argument("--element-count-hi", type=int)
    parser.add_argument("--max-total-track", type=float)
    parser.add_argument(
        "--candidate-zmx",
        type=Path,
        help="Optional raw ZMX candidate to preflight without adding it to the generated library.",
    )
    parser.add_argument("--candidate-n-pieces", type=int)
    parser.add_argument("--candidate-efl", type=float)
    parser.add_argument("--candidate-fov", type=float)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--fail-on-gap", action="store_true", help="Exit non-zero when unmet.")
    return parser.parse_args(argv)


def _resolve_float_window(
    *,
    target: float,
    lower_delta: float,
    upper_delta: float,
    floor: float,
    explicit_lo: float | None,
    explicit_hi: float | None,
    label: str,
) -> list[float]:
    if explicit_lo is None and explicit_hi is None:
        return [round(max(floor, target - lower_delta), 4), round(target + upper_delta, 4)]
    if explicit_lo is None or explicit_hi is None:
        raise ValueError(f"{label} requires both low and high bounds")
    if explicit_lo > explicit_hi:
        raise ValueError(f"{label} low bound must be <= high bound")
    return [round(explicit_lo, 4), round(explicit_hi, 4)]


def _resolve_optional_float_window(
    *,
    target: float | None,
    half_width: float,
    floor: float,
    explicit_lo: float | None,
    explicit_hi: float | None,
    label: str,
) -> list[float]:
    if target is None and explicit_lo is None and explicit_hi is None:
        return []
    if explicit_lo is not None and explicit_hi is not None:
        if explicit_lo > explicit_hi:
            raise ValueError(f"{label} low bound must be <= high bound")
        return [round(explicit_lo, 4), round(explicit_hi, 4)]
    if explicit_lo is not None or explicit_hi is not None:
        raise ValueError(f"{label} requires both low and high bounds")
    if target is None:
        raise ValueError(f"{label} target is required when explicit bounds are omitted")
    return [round(max(floor, target - half_width), 4), round(target + half_width, 4)]


def _resolve_optional_int_window(
    *,
    target: int | None,
    half_width: int,
    floor: int,
    ceiling: int,
    explicit_lo: int | None,
    explicit_hi: int | None,
    label: str,
) -> list[int]:
    if target is None and explicit_lo is None and explicit_hi is None:
        return []
    if explicit_lo is not None and explicit_hi is not None:
        if explicit_lo > explicit_hi:
            raise ValueError(f"{label} low bound must be <= high bound")
        return [explicit_lo, explicit_hi]
    if explicit_lo is not None or explicit_hi is not None:
        raise ValueError(f"{label} requires both low and high bounds")
    if target is None:
        raise ValueError(f"{label} target is required when explicit bounds are omitted")
    return [max(floor, target - half_width), min(ceiling, target + half_width)]


def _brief_from_args(args: argparse.Namespace) -> SeedAcquisitionBrief:
    return SeedAcquisitionBrief(
        target_regime="smartphone visible-light high-FOV main/wide camera",
        priority="required_for_full_field_claim",
        source_format="Zemax/Optiland-compatible visible-light prescription with material metadata",
        target_fov_deg=args.target_fov,
        minimum_fov_deg=args.min_fov,
        target_efl_mm=args.target_efl,
        efl_window_mm=_resolve_float_window(
            target=args.target_efl,
            lower_delta=args.efl_window,
            upper_delta=args.efl_window,
            floor=0.1,
            explicit_lo=args.efl_lo,
            explicit_hi=args.efl_hi,
            label="EFL window",
        ),
        target_f_number=args.target_fnum,
        f_number_window=_resolve_float_window(
            target=args.target_fnum,
            lower_delta=args.fnum_low_window,
            upper_delta=args.fnum_high_window,
            floor=0.8,
            explicit_lo=args.fnum_lo,
            explicit_hi=args.fnum_hi,
            label="F/# window",
        ),
        target_image_height_mm=args.target_image_height,
        image_height_window_mm=_resolve_optional_float_window(
            target=args.target_image_height,
            half_width=args.image_height_window,
            floor=0.1,
            explicit_lo=args.image_height_lo,
            explicit_hi=args.image_height_hi,
            label="image-height window",
        ),
        target_n_elements=args.target_elements,
        element_count_window=_resolve_optional_int_window(
            target=args.target_elements,
            half_width=args.element_window,
            floor=3,
            ceiling=8,
            explicit_lo=args.element_count_lo,
            explicit_hi=args.element_count_hi,
            label="element-count window",
        ),
        max_total_track_mm=args.max_total_track,
        required_mtf_field_frac=args.required_field,
        validation_requirements=[
            "visible-light wavelength set, not IR-only",
            "finite sampled ray trace through the 1.0 field",
            "MTF evaluates at 1.0 field without falling back below full field",
            "materials resolve to refractive-index data used by the backend",
            "element count and filter/cover plates can be classified from the prescription",
        ],
        rejection_filters=[
            "IR-only or monochrome near-IR prescriptions",
            "MTF max stable field below 1.0",
            "missing stop, semi-aperture, material, or wavelength metadata",
            "non-phone or non-visible-light optical scenario",
        ],
        rationale=[
            "audit command mirrors the runtime seed-intake contract",
            "full-field claim requires accepted seed evidence before promotion",
        ],
    )


def _candidate_nominals(args: argparse.Namespace, path: Path) -> tuple[int, float, float]:
    match = _CANDIDATE_NAME_RE.search(path.name)
    n_pieces = args.candidate_n_pieces
    nominal_efl = args.candidate_efl
    nominal_fov = args.candidate_fov
    if match is not None:
        n_pieces = n_pieces if n_pieces is not None else int(match.group("n"))
        nominal_efl = nominal_efl if nominal_efl is not None else float(match.group("efl"))
        nominal_fov = nominal_fov if nominal_fov is not None else float(match.group("fov"))

    missing = []
    if n_pieces is None:
        missing.append("--candidate-n-pieces")
    if nominal_efl is None:
        missing.append("--candidate-efl")
    if nominal_fov is None:
        missing.append("--candidate-fov")
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            f"{joined} required when candidate filename does not encode nP/FOV/EFL"
        )
    return n_pieces, nominal_efl, nominal_fov


def _load_candidate_samples(args: argparse.Namespace) -> list:
    if args.candidate_zmx is None:
        return []
    path = args.candidate_zmx.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"candidate ZMX not found: {path}")

    n_pieces, nominal_efl, nominal_fov = _candidate_nominals(args, path)
    optic = load_normalized_zmx(path)
    return [
        build_sample_from_optic(
            optic,
            source_zmx=path.name,
            n_pieces=n_pieces,
            nominal_efl_mm=nominal_efl,
            nominal_fov_deg=nominal_fov,
            source_path=path,
        )
    ]


def _audit(args: argparse.Namespace) -> dict:
    cases = [sample for sample in load_case_library() if sample.metadata is not None]
    cases.extend(_load_candidate_samples(args))
    audit = build_seed_intake_audit(cases=cases, brief=_brief_from_args(args))
    return audit.model_dump(mode="json")


def _print_text(report: dict) -> None:
    print(f"status: {report['status']}")
    print(f"summary: {report['summary']}")
    print(
        "target: "
        f"FOV>={report['minimum_fov_deg']:.1f} "
        f"EFL={report['efl_window_mm'][0]:.2f}-{report['efl_window_mm'][1]:.2f} "
        f"F/#={report['f_number_window'][0]:.2f}-{report['f_number_window'][1]:.2f}"
    )
    if report["image_height_window_mm"]:
        print(
            "image_height_window: "
            f"{report['image_height_window_mm'][0]:.2f}-{report['image_height_window_mm'][1]:.2f} mm"
        )
    if report["element_count_window"]:
        print(
            "element_count_window: "
            f"{report['element_count_window'][0]}-{report['element_count_window'][1]}P"
        )
    print("known_evidence:")
    for item in report["known_evidence"]:
        print(f"  - {item}")
    print("missing_evidence:")
    for item in report["missing_evidence"] or ["none"]:
        print(f"  - {item}")
    if report["nearest_candidates"]:
        print("nearest_candidates:")
    for seed in report["nearest_candidates"]:
        details = [f"field={format_mtf_field_fraction(seed['mtf_max_field_frac'])}"]
        if seed.get("highest_stable_field_frac") is not None:
            edge = f"edge={format_mtf_field_fraction(seed['highest_stable_field_frac'])}"
            if seed.get("edge_field_cliff_frac") is not None:
                edge += (
                    "/cliff="
                    f"{format_mtf_field_fraction(seed['edge_field_cliff_frac'])}"
                )
            details.append(edge)
        details.append(f"miss={'; '.join(seed['miss_reasons']) or 'none'}")
        print(
            f"  - {seed['role']}: {seed['case_id']} "
            f"FOV={seed['fov_deg']:.1f} "
            f"{'; '.join(details)}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = _audit(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_text(report)
    return 2 if args.fail_on_gap and report["status"] != "satisfied" else 0


if __name__ == "__main__":
    raise SystemExit(main())
