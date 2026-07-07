"""Smoke-check generated case-library OpticalSampleData payloads.

The smoke gate reads the generated case JSON files that the result page trusts,
validates the full optical_sample payload shape, and reports crashes plus
non-finite key metrics. It intentionally does not rebuild the whole library
from ZMX; generation belongs to scripts/generate_cases.py.

Run:
  uv run python scripts/smoke_case_library.py
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / ".planning" / "loop" / "case-smoke-report.md"

sys.path.insert(0, str(ROOT))

from app.core.case_library import CASES_DIR, _case_image_height_mm  # noqa: E402
from app.core.optical_sample import OpticalSampleData  # noqa: E402


@dataclass(frozen=True)
class SmokeIssue:
    """One finite-value or payload-shape issue found in a case."""

    case_id: str
    field: str
    value: str
    reason: str


@dataclass(frozen=True)
class CaseSmokeResult:
    """Smoke status for one case file or sample."""

    case_id: str
    crash: str | None = None
    issues: tuple[SmokeIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return self.crash is None and not self.issues


@dataclass(frozen=True)
class SmokeReport:
    """Aggregate case-library smoke result."""

    total: int
    results: tuple[CaseSmokeResult, ...]

    @property
    def crashes(self) -> tuple[CaseSmokeResult, ...]:
        return tuple(result for result in self.results if result.crash is not None)

    @property
    def issues(self) -> tuple[SmokeIssue, ...]:
        return tuple(issue for result in self.results for issue in result.issues)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.ok)

    @property
    def ok(self) -> bool:
        return not self.crashes and not self.issues and self.total == len(self.results)


def _case_id_for(sample: OpticalSampleData, fallback: str) -> str:
    if sample.metadata is not None and sample.metadata.case_id:
        return sample.metadata.case_id
    return fallback


def _display_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return repr(value)


def _finite_positive(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0.0


def _finite_number(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _add_positive_issue(
    issues: list[SmokeIssue],
    *,
    case_id: str,
    field: str,
    value: object,
) -> None:
    if not _finite_positive(value):
        issues.append(
            SmokeIssue(
                case_id=case_id,
                field=field,
                value=_display_value(value),
                reason="expected finite positive value",
            )
        )


def _add_finite_issue(
    issues: list[SmokeIssue],
    *,
    case_id: str,
    field: str,
    value: object,
) -> None:
    if not _finite_number(value):
        issues.append(
            SmokeIssue(
                case_id=case_id,
                field=field,
                value=_display_value(value),
                reason="expected finite non-NaN value",
            )
        )


def _add_non_empty_issue(
    issues: list[SmokeIssue],
    *,
    case_id: str,
    field: str,
    value: Sequence[object] | str,
    reason: str,
) -> None:
    if not value:
        issues.append(
            SmokeIssue(
                case_id=case_id,
                field=field,
                value=_display_value(value),
                reason=reason,
            )
        )


def smoke_case_sample(
    sample: OpticalSampleData,
    *,
    case_id: str | None = None,
) -> CaseSmokeResult:
    """Validate one loaded OpticalSampleData payload."""

    resolved_case_id = case_id or _case_id_for(sample, "unknown")
    issues: list[SmokeIssue] = []

    if sample.metadata is None:
        issues.append(
            SmokeIssue(
                case_id=resolved_case_id,
                field="metadata",
                value="None",
                reason="metadata is required for case-library samples",
            )
        )

    _add_positive_issue(
        issues,
        case_id=resolved_case_id,
        field="paraxial.effective_focal_length_mm",
        value=sample.paraxial.effective_focal_length_mm,
    )
    _add_positive_issue(
        issues,
        case_id=resolved_case_id,
        field="image_height_mm",
        value=_case_image_height_mm(sample),
    )

    _add_non_empty_issue(
        issues,
        case_id=resolved_case_id,
        field="trace.sampled_paths",
        value=sample.trace.sampled_paths,
        reason="ray-trace payload must include sampled paths",
    )
    _add_positive_issue(
        issues,
        case_id=resolved_case_id,
        field="trace.n_rays",
        value=sample.trace.n_rays,
    )
    for path_index, path in enumerate(sample.trace.sampled_paths):
        _add_finite_issue(
            issues,
            case_id=resolved_case_id,
            field=f"trace.sampled_paths[{path_index}].field_angle_deg",
            value=path.field_angle_deg,
        )
        _add_finite_issue(
            issues,
            case_id=resolved_case_id,
            field=f"trace.sampled_paths[{path_index}].wavelength_nm",
            value=path.wavelength_nm,
        )
        _add_non_empty_issue(
            issues,
            case_id=resolved_case_id,
            field=f"trace.sampled_paths[{path_index}].points_mm",
            value=path.points_mm,
            reason="sampled ray path must include points",
        )
        for point_index, point in enumerate(path.points_mm):
            for axis_index, value in enumerate(point):
                _add_finite_issue(
                    issues,
                    case_id=resolved_case_id,
                    field=(
                        f"trace.sampled_paths[{path_index}]"
                        f".points_mm[{point_index}][{axis_index}]"
                    ),
                    value=value,
                )

    _add_non_empty_issue(
        issues,
        case_id=resolved_case_id,
        field="mtf.freq_lp_per_mm",
        value=sample.mtf.freq_lp_per_mm,
        reason="MTF payload must include frequency axis",
    )
    _add_non_empty_issue(
        issues,
        case_id=resolved_case_id,
        field="mtf.fields",
        value=sample.mtf.fields,
        reason="MTF payload must include field curves",
    )
    _add_non_empty_issue(
        issues,
        case_id=resolved_case_id,
        field="mtf.rms_spot_radius_um_by_field",
        value=sample.mtf.rms_spot_radius_um_by_field,
        reason="MTF payload must include RMS spot values",
    )
    _add_positive_issue(
        issues,
        case_id=resolved_case_id,
        field="mtf.cutoff_freq_lp_per_mm",
        value=sample.mtf.cutoff_freq_lp_per_mm,
    )
    _add_positive_issue(
        issues,
        case_id=resolved_case_id,
        field="mtf.airy_disc_diameter_um",
        value=sample.mtf.airy_disc_diameter_um,
    )
    for index, value in enumerate(sample.mtf.freq_lp_per_mm):
        _add_finite_issue(
            issues,
            case_id=resolved_case_id,
            field=f"mtf.freq_lp_per_mm[{index}]",
            value=value,
        )
    for index, value in enumerate(sample.mtf.diff_limited):
        _add_finite_issue(
            issues,
            case_id=resolved_case_id,
            field=f"mtf.diff_limited[{index}]",
            value=value,
        )
    for index, value in enumerate(sample.mtf.rms_spot_radius_um_by_field):
        _add_finite_issue(
            issues,
            case_id=resolved_case_id,
            field=f"mtf.rms_spot_radius_um_by_field[{index}]",
            value=value,
        )
    for field_index, field in enumerate(sample.mtf.fields):
        _add_non_empty_issue(
            issues,
            case_id=resolved_case_id,
            field=f"mtf.fields[{field_index}].sagittal",
            value=field.sagittal,
            reason="MTF sagittal curve must not be empty",
        )
        _add_non_empty_issue(
            issues,
            case_id=resolved_case_id,
            field=f"mtf.fields[{field_index}].tangential",
            value=field.tangential,
            reason="MTF tangential curve must not be empty",
        )
        for index, value in enumerate(field.sagittal):
            _add_finite_issue(
                issues,
                case_id=resolved_case_id,
                field=f"mtf.fields[{field_index}].sagittal[{index}]",
                value=value,
            )
        for index, value in enumerate(field.tangential):
            _add_finite_issue(
                issues,
                case_id=resolved_case_id,
                field=f"mtf.fields[{field_index}].tangential[{index}]",
                value=value,
            )

    _add_non_empty_issue(
        issues,
        case_id=resolved_case_id,
        field="layout_svg.svg_content",
        value=sample.layout_svg.svg_content,
        reason="SVG payload must not be empty",
    )
    if "<svg" not in sample.layout_svg.svg_content.lower():
        issues.append(
            SmokeIssue(
                case_id=resolved_case_id,
                field="layout_svg.svg_content",
                value=sample.layout_svg.svg_content[:40],
                reason="SVG payload must contain an <svg> element",
            )
        )
    _add_positive_issue(
        issues,
        case_id=resolved_case_id,
        field="layout_svg.width_px",
        value=sample.layout_svg.width_px,
    )
    _add_positive_issue(
        issues,
        case_id=resolved_case_id,
        field="layout_svg.height_px",
        value=sample.layout_svg.height_px,
    )

    _add_non_empty_issue(
        issues,
        case_id=resolved_case_id,
        field="surfaces",
        value=sample.surfaces,
        reason="prescription surface table must not be empty",
    )
    for index, surface in enumerate(sample.surfaces):
        _add_finite_issue(
            issues,
            case_id=resolved_case_id,
            field=f"surfaces[{index}].z_mm",
            value=surface.z_mm,
        )
        _add_finite_issue(
            issues,
            case_id=resolved_case_id,
            field=f"surfaces[{index}].radius_mm",
            value=surface.radius_mm,
        )

    return CaseSmokeResult(case_id=resolved_case_id, issues=tuple(issues))


def smoke_case_file(path: Path) -> CaseSmokeResult:
    """Load and smoke-check one case JSON file."""

    try:
        sample = OpticalSampleData.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as per-case smoke evidence.
        return CaseSmokeResult(
            case_id=path.stem,
            crash=f"{type(exc).__name__}: {exc}",
        )
    return smoke_case_sample(sample, case_id=_case_id_for(sample, path.stem))


def case_json_paths(case_dir: Path = CASES_DIR) -> tuple[Path, ...]:
    """Return generated case JSON paths, excluding index.json."""

    return tuple(
        path
        for path in sorted(case_dir.glob("*.json"))
        if path.name != "index.json"
    )


def smoke_case_paths(paths: Iterable[Path]) -> SmokeReport:
    """Smoke-check the supplied case files."""

    path_tuple = tuple(paths)
    results = tuple(smoke_case_file(path) for path in path_tuple)
    return SmokeReport(total=len(path_tuple), results=results)


def render_markdown_report(report: SmokeReport) -> str:
    """Render the smoke report expected by loop acceptance."""

    lines = [
        "# Case Library Smoke Report",
        "",
        "Generated by `scripts/smoke_case_library.py`.",
        "",
        f"- Total cases: {report.total}",
        f"- Passed cases: {report.passed}",
        f"- Crashes: {len(report.crashes)}",
        f"- NaN/non-finite issues: {len(report.issues)}",
        "",
        "## Checked Payload",
        "",
        "- Ray trace sampled paths",
        "- MTF frequency axis, field curves, and RMS spot values",
        "- Layout SVG",
        "- Prescription surface table",
        "- EFL, IMH, and RMS spot finite/non-NaN guards",
        "",
        "## Crash List",
        "",
    ]
    if report.crashes:
        for result in report.crashes:
            lines.append(f"- `{result.case_id}`: {result.crash}")
    else:
        lines.append("None.")

    lines.extend(["", "## NaN List", ""])
    if report.issues:
        for issue in report.issues:
            lines.append(
                f"- `{issue.case_id}` `{issue.field}` = `{issue.value}`: {issue.reason}"
            )
    else:
        lines.append("None.")

    return "\n".join(lines) + "\n"


def write_report(report: SmokeReport, path: Path = REPORT_PATH) -> Path:
    """Write a Markdown smoke report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(report), encoding="utf-8")
    return path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=CASES_DIR,
        help="Directory containing generated case JSON files.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPORT_PATH,
        help="Markdown report path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = smoke_case_paths(case_json_paths(args.case_dir))
    report_path = write_report(report, args.report)
    print(
        f"case smoke: total={report.total} passed={report.passed} "
        f"crashes={len(report.crashes)} issues={len(report.issues)} "
        f"report={report_path}",
        flush=True,
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
