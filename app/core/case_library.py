"""Real-design optical case library (phase v2-02).

Turns the normalized real zmx designs into `OpticalSampleData` via the existing
Optiland pipeline (paraxial / surfaces / trace / MTF / layout-SVG), plus honest
per-case metadata. `build_sample_from_optic` builds one design;
`load_case_library` reads the generated JSON at runtime (cached).

Two real-design quirks are handled here (verified during ingest):
- **Field type**: real zmx files define ~12 RealImageHeight fields, which make
  GeometricMTF ray-aim by iterative inverse-solve → hangs. `regularize_fields_to_angle`
  (in zmx_ingest) switches to ANGLE fields at standard MTF fractions first.
- **Full-field NaN**: some designs' 1.0-field edge rays trace to NaN, crashing
  MTF. `_mtf_with_fallback` retries with progressively smaller field sets and
  records the max field reached in metadata (honest).
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import warnings
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import numpy as np

from app.core.aberration import MTFFieldData, MTFResult, compute_mtf
from app.core.image_quality_floor import (
    IMAGE_QUALITY_FLOOR_MAX_RMS_UM as _IMAGE_QUALITY_FLOOR_MAX_RMS_UM,
)
from app.core.image_quality_floor import (
    IMAGE_QUALITY_FLOOR_MIN_MTF as _IMAGE_QUALITY_FLOOR_MIN_MTF,
)
from app.core.image_quality_floor import (
    IMAGE_QUALITY_FLOOR_WEIGHTED_MTF as _IMAGE_QUALITY_FLOOR_WEIGHTED_MTF,
)
from app.core.image_quality_floor import image_quality_floor_components
from app.core.image_quality_floor import (
    image_quality_floor_gap_score as _image_quality_floor_gap_score,
)
from app.core.layout_svg import render_layout_svg
from app.core.lens_system import LayoutSVG, Scenario
from app.core.optical_calc import airy_disk_diameter_um
from app.core.local_optimizer import (
    mtf_bands_from_snapshot,
    mtf_field_weighted_non_regressed,
    mtf_multiband_non_regressed,
    mtf_multiband_summary,
    protected_edge_field_stability_scan,
    protected_efl_refinement,
    protected_full_field_recovery_probe,
    protected_rms_merit_probe,
)
from app.core.mtf_fields import MTF_FIELD_FALLBACK_SETS, format_mtf_field_fraction
from app.core.optical_engine import (
    compute_paraxial_summary,
    extract_surface_descriptors,
    trace_optic,
)
from app.core.optical_sample import (
    AcceptanceEvidenceProbe,
    AcceptanceImprovementTask,
    CandidateComparison,
    CaseMetadata,
    DesignAssessment,
    DesignConstraintItem,
    DesignConstraintLedger,
    DesignDeliveryGate,
    DesignerReadinessDimension,
    DesignerReadinessRubric,
    DesignHandoffMetric,
    DesignHandoffPacket,
    DesignIntentConstraintItem,
    DesignIntentContract,
    DesignReadiness,
    DesignRisk,
    DesignStrategyDecision,
    DesignStrategyOption,
    DesignTraceabilityManifest,
    DesignVariableGovernanceItem,
    DraftAcceptanceCheck,
    DraftAcceptanceGate,
    DraftAcceptanceUpgradeAction,
    DraftBranchSelectionPolicy,
    DraftBranchTradeoffRow,
    DraftCandidate,
    DraftQualityDimension,
    DraftQualityRubric,
    EvidenceCloseoutItem,
    EvidenceCloseoutPlan,
    FullFieldRecoveryDiagnostic,
    FullFieldRecoveryTrial,
    LibraryCoverageDiagnostic,
    ManufacturabilityCheck,
    ManufacturabilityReview,
    ManufacturingClearanceChecklist,
    ManufacturingClearanceItem,
    ManufacturingSensitivityAudit,
    ManufacturingSensitivityFactor,
    OpticalSampleData,
    OptimizationAction,
    OptimizationMeritProbe,
    OptimizationMetricSnapshot,
    OptimizationMetricUpdate,
    OptimizationReplayGate,
    OptimizationReplayGateCheck,
    OptimizationTask,
    OptimizationTaskRun,
    OptimizationVariableChange,
    OptimizationVariableTrial,
    PrescriptionChangeSet,
    ReferenceInfluenceAudit,
    RemediationResolutionPacket,
    RemediationResolutionPath,
    RequirementCoverageItem,
    RequirementCoverageSummary,
    SeedAcquisitionBrief,
    SeedAcquisitionContract,
    SeedIntakeAudit,
    SeedIntakeCandidate,
    SeedSelectionMetricScore,
    SeedSelectionScorecard,
    SpecRepairAutoClosure,
    SpecRepairDecisionPacket,
    SpecRepairPreviewPacket,
    SpecRepairRerunContract,
    ToleranceSensitivityAudit,
    ToleranceSensitivityItem,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR, regularize_fields_to_angle
from app.core.zmx_materials import _canon

# Generated case JSON lives under the backend root: core -> app -> <root>/data.
CASES_DIR = Path(__file__).resolve().parents[1] / "data" / "optical_cases"

_PRIMARY_WL_NM = 587.6  # d-line, matches zmx_ingest wavelength regularization
# JSON-safe stand-in for an infinite (flat) radius. Pydantic serializes
# float('inf') -> null, which then fails reload; 1e9 mm reads as effectively flat.
_PLANE_RADIUS_SENTINEL = 1e9

# Real ammo maxes at ~89.5° (no true 100°+ ultrawide); 85° is the wide/ultrawide
# divide we also calibrate parameter_guards bounds to (Plan 03).
_ULTRAWIDE_FOV_MIN = 85.0

# Routing floor-violation thresholds. After the XASPHERE ingest fix the library
# is image-quality healthy (max real RMS ~40 um, min-50lp/mm MTF >= ~0.2, floor
# gap <= ~1.2); only the two genuinely-broken ingest seeds blow past these
# (RMS ~1200/4700 um, floor gap ~12/47). Routing hard-penalises seeds beyond
# these limits; everything else is decided by parameter proximity. These gate
# routing seed selection only -- the review scorecard and optimizer/replay
# gates keep the full continuous 200/250 lp/mm evidence.
_SEED_ROUTING_MAX_RMS_UM = 100.0
_SEED_ROUTING_MIN_MTF_50 = 0.08
_SEED_ROUTING_FLOOR_GAP_LIMIT = 3.0
_SEED_ROUTING_FIELD_TIEBREAK = 0.15


class ImageQualityFloorResult(NamedTuple):
    score: float
    status: str
    evidence: list[str]
    action: str | None
    blockers: list[str]


class ImageQualityRecoveryObjective(NamedTuple):
    dominant_component: str
    normalized_gap: float | None
    variables: list[str]
    evidence: list[str]
    next_action: str


def _image_quality_recovery_objective(
    metrics: OptimizationMetricSnapshot | None,
) -> ImageQualityRecoveryObjective:
    default_variables = [
        "focus position",
        "stop position",
        "air gaps",
        "asphere coefficients",
        "field weighting",
    ]
    if metrics is None:
        return ImageQualityRecoveryObjective(
            dominant_component="unavailable",
            normalized_gap=None,
            variables=default_variables,
            evidence=[
                "dominant floor gap=unavailable",
                f"targeted recovery variables={', '.join(default_variables)}",
                "recovery objective=collect MTF/RMS metrics before bounded tuning",
            ],
            next_action="collect MTF/RMS metrics before selecting a recovery variable family",
        )

    components = image_quality_floor_components(metrics)
    if not components:
        return ImageQualityRecoveryObjective(
            dominant_component="unavailable",
            normalized_gap=None,
            variables=default_variables,
            evidence=[
                "dominant floor gap=unavailable",
                f"targeted recovery variables={', '.join(default_variables)}",
                "recovery objective=collect MTF/RMS metrics before bounded tuning",
            ],
            next_action="collect MTF/RMS metrics before selecting a recovery variable family",
        )

    dominant = components[0]
    component_id = dominant.component_id
    normalized_gap = dominant.normalized_gap
    if component_id in {"mtf_200lpmm_floor_gap", "mtf_250lpmm_floor_gap"}:
        variables = [
            "asphere coefficients",
            "stop position",
            "field weighting",
            "air gaps",
            "focus position",
        ]
        action = (
            "recover high-frequency 200/250 lp/mm MTF before accepting RMS-only "
            "or aperture/element-count claims"
        )
    elif component_id.startswith("mtf_") and component_id != "mtf_field_weighted_floor_gap":
        variables = ["asphere coefficients", "stop position", "air gaps", "field weighting"]
        action = "recover minimum 50/100/150/200/250 lp/mm MTF before raw RMS gains"
    elif component_id == "mtf_field_weighted_floor_gap":
        variables = ["stop position", "air gaps", "asphere coefficients", "field weighting"]
        action = "recover field-weighted MTF before accepting local RMS-only improvements"
    elif component_id == "max_rms_floor_gap":
        variables = ["focus position", "air gaps", "radius", "stop position", "asphere coefficients"]
        action = "reduce max RMS while preserving MTF non-regression and EFL lock"
    else:
        variables = default_variables
        action = "recover the dominant MTF/RMS floor component before draft promotion"

    if math.isclose(normalized_gap, 0.0, abs_tol=1e-9):
        component_id = "none"
        action = "maintain MTF/RMS floor while continuing packaging and tolerance review"
        variables = ["focus position", "air gaps", "radius"]
    component_ladder = ", ".join(
        f"{component.component_id}:{component.normalized_gap:.3f}" for component in components
    )
    return ImageQualityRecoveryObjective(
        dominant_component=component_id,
        normalized_gap=round(normalized_gap, 3),
        variables=variables,
        evidence=[
            f"dominant floor gap={component_id} normalized={normalized_gap:.3f}",
            f"floor component gaps={component_ladder}",
            f"targeted recovery variables={', '.join(variables)}",
            f"recovery objective={action}",
        ],
        next_action=action,
    )


def _best_floor_gap_trial(
    merit_probe: OptimizationMeritProbe,
) -> OptimizationVariableTrial | None:
    floor_gap_trials = [
        trial
        for trial in merit_probe.candidate_trials
        if trial.image_quality_floor_gap_closure is not None
    ]

    def _rank(trial: OptimizationVariableTrial) -> tuple[int, int, int, int, float, float, float]:
        closure = (
            trial.image_quality_floor_gap_closure
            if trial.image_quality_floor_gap_closure is not None
            else -math.inf
        )
        promotion_score = trial.promotion_score if trial.promotion_score is not None else -math.inf
        rms_improvement = (
            trial.rms_improvement_um if trial.rms_improvement_um is not None else -math.inf
        )
        gate_clean = (
            trial.verification_status == "passed"
            and trial.mtf_field_non_regressed is True
            and trial.mtf_band_non_regressed is True
            and trial.mtf_field_weighted_non_regressed is True
            and trial.efl_locked is True
            and trial.rms_improvement_um is not None
            and trial.rms_improvement_um >= 0.0
        )
        status_rank = {
            "accepted": 3,
            "improved": 2,
            "rejected": 1,
            "failed": 0,
            "skipped": 0,
        }.get(trial.status, 0)
        return (
            1 if trial.status == "accepted" else 0,
            1 if gate_clean else 0,
            status_rank,
            1 if closure > 0.0 else 0,
            closure,
            promotion_score,
            rms_improvement,
        )

    return max(
        floor_gap_trials,
        key=_rank,
        default=None,
    )


def _evaluate_image_quality_floor(
    metrics: OptimizationMetricSnapshot | None,
) -> ImageQualityFloorResult:
    """First-pass review floor for draft promotion, not a production spec."""

    if metrics is None:
        action = "attach recommended-branch MTF/RMS metrics before draft promotion"
        return ImageQualityFloorResult(
            score=0.45,
            status="warning",
            evidence=["image quality floor missing recommended-branch metrics"],
            action=action,
            blockers=[],
        )
    min_mtf = metrics.mtf_multiband_min_score
    weighted_mtf = metrics.mtf_field_weighted_score
    max_rms = metrics.max_rms_spot_radius_um
    evidence = [
        (
            f"image quality floor: minMTF={min_mtf:.3f}"
            if min_mtf is not None
            else "image quality floor: minMTF=missing"
        ),
        (
            f"field-weighted MTF={weighted_mtf:.3f}"
            if weighted_mtf is not None
            else "field-weighted MTF=missing"
        ),
        f"max RMS={max_rms:.1f}um" if max_rms is not None else "max RMS=missing",
        (
            "review floor: 50/100/150/200/250 lp/mm min MTF>=0.08; "
            "field-weighted MTF>=0.15; max RMS<=100um"
        ),
    ]
    blockers: list[str] = []
    if min_mtf is None or min_mtf < _IMAGE_QUALITY_FLOOR_MIN_MTF:
        blockers.append("multiband MTF minimum below review floor")
    if weighted_mtf is None or weighted_mtf < _IMAGE_QUALITY_FLOOR_WEIGHTED_MTF:
        blockers.append("field-weighted MTF below review floor")
    if max_rms is None or max_rms > _IMAGE_QUALITY_FLOOR_MAX_RMS_UM:
        blockers.append("max RMS spot radius above review floor")
    if blockers:
        action = (
            "hold draft_ready until the recommended branch clears the "
            "first-pass MTF/RMS review floor"
        )
        return ImageQualityFloorResult(
            score=0.25,
            status="blocker",
            evidence=[*evidence, *blockers],
            action=action,
            blockers=blockers,
        )
    return ImageQualityFloorResult(
        score=1.0,
        status="pass",
        evidence=evidence,
        action=None,
        blockers=[],
    )


def _safe(value) -> float:
    """numpy-array-shaped scalar -> python float (optiland 0.6 / numpy 2.x)."""
    arr = np.asarray(value).flatten()
    return float(arr[0]) if arr.size else 0.0


def _classify_scenario(fov_deg: float) -> Scenario:
    if fov_deg >= _ULTRAWIDE_FOV_MIN:
        return Scenario.SMARTPHONE_ULTRAWIDE
    return Scenario.SMARTPHONE_WIDE


def _classify_surfaces(optic) -> tuple[int, int]:
    """Count imaging elements vs flat filter/cover-glass plates.

    An optical element is a surface whose *post* material is a real (non-air)
    medium — that's the front face of a lens or plate. If that face is curved
    (finite radius) it's an imaging element; if flat (radius inf) it's a filter /
    cover glass (the IR-cut plate, BRIEF 3.1). Object (0) and image (last) are
    skipped.
    """
    surfaces = optic.surface_group.surfaces
    n = len(surfaces)
    n_imaging = 0
    n_filter = 0
    for i, s in enumerate(surfaces):
        if i == 0 or i == n - 1:
            continue
        mat = getattr(s, "material_post", None)
        if mat is None or type(mat).__name__ == "IdealMaterial":
            continue  # air gap
        try:
            r = abs(_safe(s.geometry.radius))
        except Exception:
            r = float("inf")
        if (not np.isfinite(r)) or r > 1e4:
            n_filter += 1
        else:
            n_imaging += 1
    return n_imaging, n_filter


def _materials_from_zmx(filename: str, source_path: str | Path | None = None) -> list[str]:
    """Distinct real material names from a zmx's GLAS rows (canonical, deduped).

    Read from the source file (not the loaded optic) because the loader resolves
    materials to nameless AbbeMaterial objects. Canonicalization strips the
    factory `_NN` suffix so ZEONEX-K26R_14 -> ZEONEX-K26R.
    """
    path = Path(source_path) if source_path is not None else ZMX_AMMO_DIR / filename
    text = ""
    for enc in ("utf-16", "utf-16-le", "utf-8-sig", "latin-1"):
        try:
            text = path.read_text(encoding=enc)
            break
        except (UnicodeError, OSError):
            continue
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("GLAS"):
            continue
        tok = s.split()
        if len(tok) > 1 and tok[1] not in ("___BLANK", "0", "MIRROR"):
            canon = _canon(tok[1])
            if canon and canon not in seen:
                seen.add(canon)
                names.append(canon)
    return names


def _mtf_has_nan(mtf) -> bool:
    """True if any MTF value is NaN/None (full-field edge rays failed to trace).

    GeometricMTF can *return* (not raise) with NaN rms/curve entries when the
    outermost field's edge rays TIR or miss a surface; those can't serialize and
    aren't physically meaningful, so we treat them as a failed field set.
    """
    for v in mtf.rms_spot_radius_um_by_field:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return True
    for f in mtf.fields:
        for v in (*f.sagittal, *f.tangential):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return True
    return False


def _mtf_with_fallback(optic, fov_deg: float) -> tuple[object, float]:
    """Compute MTF, shrinking the field set until no value is NaN.

    Returns (MTFResult, max_field_fraction_reached). A <1.0 fraction is honest:
    the design's full-field edge rays couldn't be traced cleanly. Raises only if
    even the smallest field set yields NaN (we never ship NaN).
    """
    half = fov_deg / 2.0
    last_err: Exception | None = None
    for fracs in MTF_FIELD_FALLBACK_SETS:
        optic.set_field_type("angle")
        optic.fields.fields.clear()
        for frac in fracs:
            optic.add_field(y=half * frac)
        with contextlib.suppress(Exception):
            optic.ray_tracer.set_aiming("robust", max_iter=20)
        try:
            result = compute_mtf(optic, wavelength_nm=_PRIMARY_WL_NM)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
        if not _mtf_has_nan(result):
            return result, fracs[-1]
        last_err = RuntimeError(f"MTF returned NaN at field set {fracs}")
    raise RuntimeError(f"MTF unusable for all field sets: {last_err}")


def _conservative_zero_mtf(optic, field_count: int) -> MTFResult:
    freqs = [0.0, 50.0, 100.0, 150.0, 200.0, 250.0]
    try:
        f_number = float(optic.paraxial.FNO())
    except Exception:
        f_number = 2.0
    return MTFResult(
        freq_lp_per_mm=freqs,
        fields=[
            MTFFieldData(
                field_index=field_index,
                sagittal=[0.0 for _ in freqs],
                tangential=[0.0 for _ in freqs],
            )
            for field_index in range(max(1, field_count))
        ],
        diff_limited=[1.0 for _ in freqs],
        cutoff_freq_lp_per_mm=1000.0 / max(airy_disk_diameter_um(_PRIMARY_WL_NM, f_number), 1e-9),
        airy_disc_diameter_um=airy_disk_diameter_um(_PRIMARY_WL_NM, f_number),
        rms_spot_radius_um_by_field=[0.0 for _ in range(max(1, field_count))],
    )


def _lightweight_mtf(optic, fov_deg: float) -> tuple[MTFResult, float]:
    """Bounded DATA-06 MTF evidence: axis + 0.5 field with low ray density."""

    half = fov_deg / 2.0
    fracs = (0.0, 0.5)
    optic.set_field_type("angle")
    optic.fields.fields.clear()
    for frac in fracs:
        optic.add_field(y=half * frac)
    with contextlib.suppress(Exception):
        optic.ray_tracer.set_aiming("robust", max_iter=10)
    try:
        result = compute_mtf(optic, wavelength_nm=_PRIMARY_WL_NM, num_rays=8)
    except Exception:
        return _conservative_zero_mtf(optic, field_count=len(fracs)), 0.0
    if _mtf_has_nan(result):
        return _conservative_zero_mtf(optic, field_count=len(fracs)), 0.0
    return result, fracs[-1]


def _fast_layout_svg_from_surfaces(surfaces) -> LayoutSVG:
    width = 1200
    height = 600
    finite = [
        surface
        for surface in surfaces
        if math.isfinite(surface.z_mm) and abs(surface.z_mm) < 1e8 and not surface.is_object
    ]
    if not finite:
        return LayoutSVG(width_px=width, height_px=height, svg_content="<svg></svg>")

    min_z = min(surface.z_mm for surface in finite)
    max_z = max(surface.z_mm for surface in finite)
    z_span = max(max_z - min_z, 1e-6)

    def _x(z_mm: float) -> float:
        return 60.0 + (z_mm - min_z) / z_span * (width - 120.0)

    def _y(aperture_frac: float) -> float:
        return height / 2.0 - aperture_frac * (height * 0.42)

    def _aperture_frac(surface) -> float:
        return 0.55 if surface.is_stop else 1.0

    lines = [
        (
            f'<line x1="{_x(surface.z_mm):.3f}" y1="{_y(_aperture_frac(surface)):.3f}" '
            f'x2="{_x(surface.z_mm):.3f}" y2="{_y(-_aperture_frac(surface)):.3f}" '
            'stroke="#2f4f4f" stroke-width="2" />'
        )
        for surface in finite
    ]
    axis = (
        f'<line x1="40" y1="{height / 2:.3f}" x2="{width - 40}" y2="{height / 2:.3f}" '
        'stroke="#9ca3af" stroke-width="1" />'
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">{axis}{"".join(lines)}</svg>'
    )
    return LayoutSVG(width_px=width, height_px=height, svg_content=svg)


def build_sample_from_optic(
    optic,
    source_zmx: str,
    n_pieces: int,
    nominal_efl_mm: float,
    nominal_fov_deg: float,
    *,
    source_path: str | Path | None = None,
    lightweight_artifacts: bool = False,
) -> OpticalSampleData:
    """Build one OpticalSampleData from a normalized real optic + manifest nominals."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # ANGLE fields (full set) so trace / SVG aim fast; MTF may shrink it later.
        regularize_fields_to_angle(optic, nominal_fov_deg)
        paraxial = compute_paraxial_summary(optic)
        surfaces = extract_surface_descriptors(optic)
        # Flat filter/cover-glass faces have radius inf, which Pydantic serializes
        # to null (breaking reload). Replace with a JSON-safe flat sentinel.
        for sd in surfaces:
            if not math.isfinite(sd.radius_mm):
                sd.radius_mm = _PLANE_RADIUS_SENTINEL
        trace = trace_optic(optic, assembly_name=source_zmx, wavelength_nm=_PRIMARY_WL_NM)
        if lightweight_artifacts:
            layout = _fast_layout_svg_from_surfaces(surfaces)
            mtf, mtf_frac = _lightweight_mtf(optic, nominal_fov_deg)
        else:
            layout = render_layout_svg(optic)  # full fields (before any MTF shrink)
            mtf, mtf_frac = _mtf_with_fallback(optic, nominal_fov_deg)
        n_imaging, n_filter = _classify_surfaces(optic)

    materials = _materials_from_zmx(source_zmx, source_path=source_path)
    computed_efl = paraxial.effective_focal_length_mm
    efl_error_pct = abs(computed_efl - nominal_efl_mm) / nominal_efl_mm * 100.0

    metadata = CaseMetadata(
        case_id=source_zmx.rsplit(".", 1)[0],
        source_zmx=source_zmx,
        scenario=_classify_scenario(nominal_fov_deg),
        n_pieces=n_pieces,
        n_imaging=n_imaging,
        n_filter=n_filter,
        materials=materials,
        fov_deg=nominal_fov_deg,
        nominal_efl_mm=nominal_efl_mm,
        computed_efl_mm=computed_efl,
        efl_error_pct=efl_error_pct,
        mtf_max_field_frac=mtf_frac,
    )
    return OpticalSampleData(
        paraxial=paraxial,
        surfaces=surfaces,
        trace=trace,
        mtf=mtf,
        layout_svg=layout,
        metadata=metadata,
    )


@lru_cache(maxsize=1)
def load_case_library() -> list[OpticalSampleData]:
    """Load all generated case JSON (cached). Excludes index.json."""
    if not CASES_DIR.exists():
        return []
    cases: list[OpticalSampleData] = []
    for fp in sorted(CASES_DIR.glob("*.json")):
        if fp.name == "index.json":
            continue
        cases.append(OpticalSampleData.model_validate_json(fp.read_text()))
    return cases


_PHONE_SHORT_FOCUS = {Scenario.SMARTPHONE_WIDE, Scenario.SMARTPHONE_ULTRAWIDE}
_IMH_RE = re.compile(r"_IMH(?P<imh>\d+(?:\.\d+)?)")


def _case_image_height_mm(case: OpticalSampleData) -> float:
    """Recover nominal image height from metadata/index, with case-id fallback.

    v2-02 wrote image height to index.json but not to each generated case JSON.
    Avoid rewriting large payloads here; when metadata lacks an explicit value,
    use the compact index manifest before falling back to legacy `_IMH` tokens.
    """
    if case.metadata is None:
        return 0.0
    metadata_image_height = _positive_finite_float(
        getattr(case.metadata, "image_height_mm", None)
    )
    if metadata_image_height is not None:
        return metadata_image_height

    indexed_image_heights = _case_index_image_height_mm_by_id()
    source_zmx = getattr(case.metadata, "source_zmx", None)
    for key in (
        case.metadata.case_id,
        source_zmx,
        Path(source_zmx).stem if isinstance(source_zmx, str) and source_zmx else None,
    ):
        if isinstance(key, str) and key in indexed_image_heights:
            return indexed_image_heights[key]

    match = _IMH_RE.search(case.metadata.case_id)
    return float(match.group("imh")) if match else 0.0


@lru_cache(maxsize=1)
def _case_index_image_height_mm_by_id() -> dict[str, float]:
    """Load image heights from the compact case index without hydrating payloads."""

    index_path = CASES_DIR / "index.json"
    if not index_path.is_file():
        return {}
    try:
        records = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(records, list):
        return {}

    values: dict[str, float] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        image_height = _positive_finite_float(record.get("image_height_mm"))
        if image_height is None:
            continue
        case_id = record.get("case_id")
        source_zmx = record.get("source_zmx")
        keys = [case_id, source_zmx]
        if isinstance(source_zmx, str) and source_zmx:
            keys.append(Path(source_zmx).stem)
        for key in keys:
            if isinstance(key, str) and key:
                values[key] = image_height
    return values


@lru_cache(maxsize=1)
def _case_index_payload_edge_seed_ids() -> set[str]:
    """DATA-06 post-c waves keep payload-bounded MTF; do not rescan every audit."""

    index_path = CASES_DIR / "index.json"
    if not index_path.is_file():
        return set()
    try:
        records = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return set()
    if not isinstance(records, list):
        return set()

    values: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        batch = str(record.get("intake_batch", ""))
        if not batch.startswith("DATA-06") or batch == "DATA-06c":
            continue
        case_id = record.get("case_id")
        source_zmx = record.get("source_zmx")
        keys = [case_id, source_zmx]
        if isinstance(source_zmx, str) and source_zmx:
            keys.append(Path(source_zmx).stem)
        for key in keys:
            if isinstance(key, str) and key:
                values.add(key)
    return values


def _positive_finite_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number) and number > 0.0:
        return number
    return None


class _MassProxy(NamedTuple):
    estimated_mass_g: float
    envelope_diameter_mm: float
    envelope_volume_cm3: float
    density_g_cm3: float
    fill_factor: float


class _CandidateReviewProxy(NamedTuple):
    tolerance_risk_score: float
    tolerance_risk_level: str
    tolerance_status: str
    process_yield_score: float
    process_yield_level: str
    process_status: str
    mass_proxy_g: float
    notes: tuple[str, ...]


class _CandidateProxyBranchResolution(NamedTuple):
    status: str
    selected_case_id: str
    candidate_case_id: str
    summary: str
    evidence: tuple[str, ...]
    blockers: tuple[str, ...]


class _FovAlternativeBranchResolution(NamedTuple):
    status: str
    selected_case_id: str
    candidate_case_id: str
    summary: str
    evidence: tuple[str, ...]
    blockers: tuple[str, ...]


class _PerformanceApertureTradeoffResolution(NamedTuple):
    status: str
    selected_case_id: str
    rejected_case_id: str
    selected_floor_gap: float | None
    rejected_floor_gap: float | None
    accepted_tradeoff_ids: tuple[str, ...]
    summary: str
    rationale: tuple[str, ...]
    evidence: tuple[str, ...]
    promotion_requirements: tuple[str, ...]
    forbidden_claims: tuple[str, ...]


class _FovSpecConsistency(NamedTuple):
    status: str
    first_order_fov_deg: float
    delta_fov_deg: float
    implied_efl_mm: float
    implied_image_height_mm: float
    summary: str
    evidence: tuple[str, ...]
    next_action: str


class _FovSpecRepairReplay(NamedTuple):
    status: str
    repaired_efl_mm: float
    selected_case: OpticalSampleData
    score: float
    normalized_distance: float
    coverage_summary: RequirementCoverageSummary
    coverage: tuple[RequirementCoverageItem, ...]
    met_count: int
    tradeoff_count: int
    miss_count: int
    remaining_tradeoffs: tuple[str, ...]
    payload_policy: str
    evidence: tuple[str, ...]
    risks: tuple[str, ...]


def _material_density_proxy_g_cm3(name: str) -> float:
    """Coarse material-family density proxy for first-pass mass gating.

    This is deliberately a proxy, not a datasheet-precise mass model. The case
    JSON has material names but not molded part CAD volumes, spacers, actuator,
    sensor, barrel, or adhesive. Use broad family densities so weight budgets can
    participate in seed selection without pretending to be measured module mass.
    """

    canon = _canon(name)
    if canon.startswith(("ZEONEX", "APL")):
        return 1.02
    if canon.startswith(("OKP", "EP", "SP")):
        return 1.20
    if canon.startswith("H-ZLAF"):
        return 4.00
    if canon.startswith("H-LAK"):
        return 3.40
    if canon in {"D263T", "N-BK7", "BK7"}:
        return 2.50
    if canon == "SILICA":
        return 2.20
    return 1.35


def _mass_proxy(sample: OpticalSampleData) -> _MassProxy:
    """Estimate optical-stack mass from serialized case evidence."""

    assert sample.metadata is not None
    image_height = max(
        _case_image_height_mm(sample),
        sample.paraxial.entrance_pupil_diameter_mm * 0.5,
        0.8,
    )
    envelope_diameter = max(2.0 * image_height, sample.paraxial.entrance_pupil_diameter_mm * 1.5)
    envelope_volume_cm3 = (
        math.pi * (envelope_diameter / 2.0) ** 2 * sample.paraxial.total_track_mm / 1000.0
    )
    densities = [_material_density_proxy_g_cm3(material) for material in sample.metadata.materials]
    density = sum(densities) / len(densities) if densities else 1.35
    fill_factor = min(
        0.62,
        0.18 + 0.055 * sample.metadata.n_imaging + 0.025 * sample.metadata.n_filter,
    )
    estimated_mass = envelope_volume_cm3 * density * fill_factor
    return _MassProxy(
        estimated_mass_g=estimated_mass,
        envelope_diameter_mm=envelope_diameter,
        envelope_volume_cm3=envelope_volume_cm3,
        density_g_cm3=density,
        fill_factor=fill_factor,
    )


def _candidate_scenarios(scenario: Scenario) -> set[Scenario]:
    """Treat phone main / wide-FOV as one short-focus family for seed selection."""
    if scenario in _PHONE_SHORT_FOCUS:
        return set(_PHONE_SHORT_FOCUS)
    return {scenario}


def _norm_delta(target: float, value: float, lo: float, hi: float) -> float:
    return 0.0 if hi == lo else (target - value) / (hi - lo)


def _normalized_weights(weights: dict[str, float]) -> dict[str, float]:
    active = {k: v for k, v in weights.items() if v > 0}
    total = sum(active.values())
    return {k: v / total for k, v in active.items()} if total else {}


def _unique_strings_in_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def build_seed_intake_audit(
    cases: Sequence[OpticalSampleData],
    brief: SeedAcquisitionBrief,
) -> SeedIntakeAudit:
    """Assess whether the current library satisfies a seed-acquisition brief."""

    efl_lo, efl_hi = brief.efl_window_mm
    fnum_lo, fnum_hi = brief.f_number_window
    image_height_lo = brief.image_height_window_mm[0] if brief.image_height_window_mm else None
    image_height_hi = brief.image_height_window_mm[1] if brief.image_height_window_mm else None
    element_lo = brief.element_count_window[0] if brief.element_count_window else None
    element_hi = brief.element_count_window[1] if brief.element_count_window else None
    auditable_cases = [case for case in cases if case.metadata is not None]
    edge_stability_cache: dict[str, tuple[float | None, float | None, list[str]]] = {}
    payload_edge_seed_ids = _case_index_payload_edge_seed_ids()

    def _edge_stability(
        case: OpticalSampleData,
    ) -> tuple[float | None, float | None, list[str]]:
        assert case.metadata is not None
        cached = edge_stability_cache.get(case.metadata.case_id)
        if cached is not None:
            return cached
        if not (ZMX_AMMO_DIR / case.metadata.source_zmx).exists():
            result = (
                case.metadata.mtf_max_field_frac,
                None,
                [f"payload:{format_mtf_field_fraction(case.metadata.mtf_max_field_frac)}"],
            )
            edge_stability_cache[case.metadata.case_id] = result
            return result
        source_zmx = case.metadata.source_zmx
        payload_keys = (
            case.metadata.case_id,
            source_zmx,
            Path(source_zmx).stem if source_zmx else "",
        )
        if any(key in payload_edge_seed_ids for key in payload_keys):
            result = (
                case.metadata.mtf_max_field_frac,
                None,
                [
                    f"payload:{format_mtf_field_fraction(case.metadata.mtf_max_field_frac)}",
                    "index:intake_batch=DATA-06 payload-bounded",
                ],
            )
            edge_stability_cache[case.metadata.case_id] = result
            return result
        scan = protected_edge_field_stability_scan(
            case.metadata.source_zmx,
            case.metadata.fov_deg,
        )
        highest_stable: float | None = None
        first_cliff: float | None = None
        for point in scan:
            if point.status == "pass":
                highest_stable = point.field_frac
                continue
            first_cliff = point.field_frac
            break
        evidence = [
            f"{format_mtf_field_fraction(point.field_frac)}:{point.status}" for point in scan
        ]
        result = (highest_stable, first_cliff, evidence)
        edge_stability_cache[case.metadata.case_id] = result
        return result

    def _miss_reasons(case: OpticalSampleData) -> list[str]:
        assert case.metadata is not None
        image_height = _case_image_height_mm(case)
        reasons: list[str] = []
        if case.metadata.fov_deg < brief.minimum_fov_deg:
            reasons.append(f"FOV {case.metadata.fov_deg:.1f} < {brief.minimum_fov_deg:.1f} deg")
        if not efl_lo <= case.metadata.computed_efl_mm <= efl_hi:
            reasons.append(
                f"EFL {case.metadata.computed_efl_mm:.2f} outside {efl_lo:.2f}-{efl_hi:.2f} mm"
            )
        if not fnum_lo <= case.paraxial.f_number <= fnum_hi:
            reasons.append(f"F/# {case.paraxial.f_number:.2f} outside {fnum_lo:.2f}-{fnum_hi:.2f}")
        if (
            image_height_lo is not None
            and image_height_hi is not None
            and not image_height_lo <= image_height <= image_height_hi
        ):
            reasons.append(
                "image height "
                f"{image_height:.2f} outside {image_height_lo:.2f}-{image_height_hi:.2f} mm"
            )
        if (
            element_lo is not None
            and element_hi is not None
            and not element_lo <= case.metadata.n_pieces <= element_hi
        ):
            reasons.append(
                f"element count {case.metadata.n_pieces} outside {element_lo}-{element_hi}P"
            )
        if (
            brief.max_total_track_mm is not None
            and case.paraxial.total_track_mm > brief.max_total_track_mm
        ):
            reasons.append(
                f"TTL {case.paraxial.total_track_mm:.2f} > {brief.max_total_track_mm:.2f} mm"
            )
        if case.metadata.mtf_max_field_frac < brief.required_mtf_field_frac:
            reasons.append(
                "MTF field "
                f"{format_mtf_field_fraction(case.metadata.mtf_max_field_frac)} "
                f"< {format_mtf_field_fraction(brief.required_mtf_field_frac)}"
            )
        return reasons

    def _candidate(case: OpticalSampleData, role: str) -> SeedIntakeCandidate:
        assert case.metadata is not None
        should_scan_edge = (
            case.metadata.fov_deg >= brief.minimum_fov_deg
            or case.metadata.mtf_max_field_frac < brief.required_mtf_field_frac
        )
        highest_stable = None
        edge_cliff = None
        edge_evidence: list[str] = []
        if should_scan_edge:
            highest_stable, edge_cliff, edge_evidence = _edge_stability(case)
        return SeedIntakeCandidate(
            case_id=case.metadata.case_id,
            source_zmx=case.metadata.source_zmx,
            role=role,
            fov_deg=case.metadata.fov_deg,
            efl_mm=case.metadata.computed_efl_mm,
            f_number=case.paraxial.f_number,
            image_height_mm=_case_image_height_mm(case),
            n_pieces=case.metadata.n_pieces,
            mtf_max_field_frac=case.metadata.mtf_max_field_frac,
            highest_stable_field_frac=highest_stable,
            edge_field_cliff_frac=edge_cliff,
            edge_field_evidence=edge_evidence,
            miss_reasons=_miss_reasons(case),
        )

    full_field_cases = [
        case
        for case in auditable_cases
        if case.metadata is not None
        and case.metadata.mtf_max_field_frac >= brief.required_mtf_field_frac
    ]
    high_fov_cases = [
        case
        for case in auditable_cases
        if case.metadata is not None and case.metadata.fov_deg >= brief.minimum_fov_deg
    ]
    accepted_cases = [case for case in high_fov_cases if not _miss_reasons(case)]
    nearest_full_field = min(
        full_field_cases,
        key=lambda case: abs(case.metadata.fov_deg - brief.target_fov_deg),
        default=None,
    )
    nearest_high_fov = min(
        high_fov_cases,
        key=lambda case: abs(case.metadata.fov_deg - brief.target_fov_deg),
        default=None,
    )

    def _case_floor_gap(case: OpticalSampleData) -> float:
        assert case.metadata is not None
        bands = mtf_multiband_summary(case.mtf)
        rms_values = [v for v in case.mtf.rms_spot_radius_um_by_field if math.isfinite(v)]
        metrics = OptimizationMetricSnapshot(
            effective_focal_length_mm=case.metadata.computed_efl_mm,
            f_number=case.paraxial.f_number,
            total_track_mm=case.paraxial.total_track_mm,
            mtf_max_field_frac=case.metadata.mtf_max_field_frac,
            mtf_50lpmm_min=bands.min_50,
            mtf_50lpmm_avg=bands.avg_50,
            mtf_100lpmm_min=bands.min_100,
            mtf_100lpmm_avg=bands.avg_100,
            mtf_150lpmm_min=bands.min_150,
            mtf_150lpmm_avg=bands.avg_150,
            mtf_200lpmm_min=bands.min_200,
            mtf_200lpmm_avg=bands.avg_200,
            mtf_250lpmm_min=bands.min_250,
            mtf_250lpmm_avg=bands.avg_250,
            mtf_multiband_min_score=bands.multiband_min_score,
            mtf_field_weighted_score=bands.field_weighted_score,
            max_rms_spot_radius_um=max(rms_values) if rms_values else None,
        )
        gap = _image_quality_floor_gap_score(metrics)
        return gap if gap is not None else math.inf

    def _stable_high_fov_sort_key(case: OpticalSampleData) -> tuple[float, float, float, float]:
        assert case.metadata is not None
        highest_stable, _, _ = _edge_stability(case)
        stable_field = (
            highest_stable if highest_stable is not None else case.metadata.mtf_max_field_frac
        )
        # Deterministic tie-break when stability/field/FOV are equal (the two
        # 89.5 deg seeds tie at 0.85 stable / 0.9 cliff after the XASPHERE fix):
        # prefer the seed closest to clearing the image-quality review floor
        # (lowest floor gap = better high-frequency MTF). Higher key wins, so we
        # negate the gap. This keeps best_stable_high_fov meaningful and stable
        # rather than depending on library iteration order.
        return (
            stable_field,
            case.metadata.mtf_max_field_frac,
            -abs(case.metadata.fov_deg - brief.target_fov_deg),
            -_case_floor_gap(case),
        )

    best_stable_high_fov = max(
        high_fov_cases,
        key=_stable_high_fov_sort_key,
        default=None,
    )

    nearest_candidates: list[SeedIntakeCandidate] = []
    seen_nearest: set[str] = set()
    for role, case in [
        ("nearest_high_fov", nearest_high_fov),
        ("best_stable_high_fov", best_stable_high_fov),
        ("nearest_full_field", nearest_full_field),
    ]:
        if case is None or case.metadata is None or case.metadata.case_id in seen_nearest:
            continue
        nearest_candidates.append(_candidate(case, role))
        seen_nearest.add(case.metadata.case_id)

    known_evidence = [
        f"total visible phone seeds={len(auditable_cases)}",
        f"full-field seeds={len(full_field_cases)}",
        f"high-FOV seeds={len(high_fov_cases)}",
        f"accepted high-FOV full-field seeds={len(accepted_cases)}",
    ]
    if nearest_full_field is not None and nearest_full_field.metadata is not None:
        known_evidence.append(
            "nearest full-field seed="
            f"{nearest_full_field.metadata.case_id} "
            f"FOV={nearest_full_field.metadata.fov_deg:.1f} deg"
        )
    if nearest_high_fov is not None and nearest_high_fov.metadata is not None:
        high_fov_highest_stable, high_fov_cliff, _ = _edge_stability(nearest_high_fov)
        known_evidence.append(
            "nearest high-FOV seed="
            f"{nearest_high_fov.metadata.case_id} "
            "field="
            f"{format_mtf_field_fraction(nearest_high_fov.metadata.mtf_max_field_frac)}"
        )
        known_evidence.append(
            "nearest high-FOV edge scan="
            f"stable {format_mtf_field_fraction(high_fov_highest_stable)}, "
            f"cliff {format_mtf_field_fraction(high_fov_cliff)}"
        )
    if (
        best_stable_high_fov is not None
        and best_stable_high_fov.metadata is not None
        and (
            nearest_high_fov is None
            or nearest_high_fov.metadata is None
            or best_stable_high_fov.metadata.case_id != nearest_high_fov.metadata.case_id
        )
    ):
        stable_field, stable_cliff, _ = _edge_stability(best_stable_high_fov)
        known_evidence.append(
            "best stable high-FOV seed="
            f"{best_stable_high_fov.metadata.case_id} "
            f"stable={format_mtf_field_fraction(stable_field)} "
            f"cliff={format_mtf_field_fraction(stable_cliff)}"
        )

    missing_evidence: list[str] = []
    if not accepted_cases:
        missing_evidence = [
            f"visible-light seed with FOV >= {brief.minimum_fov_deg:.1f} deg",
            f"computed EFL in {efl_lo:.2f}-{efl_hi:.2f} mm and F/# in {fnum_lo:.2f}-{fnum_hi:.2f}",
            (
                f"image height in {image_height_lo:.2f}-{image_height_hi:.2f} mm"
                if image_height_lo is not None and image_height_hi is not None
                else "image height evidence matching the requested sensor"
            ),
            (
                f"element count {element_lo}-{element_hi}P"
                if element_lo is not None and element_hi is not None
                else "element count evidence matching the request"
            ),
            (
                f"TTL <= {brief.max_total_track_mm:.2f} mm"
                if brief.max_total_track_mm is not None
                else "TTL evidence matching the requested module envelope"
            ),
            (
                "MTF evaluates at "
                f"{format_mtf_field_fraction(brief.required_mtf_field_frac)} field without fallback"
            ),
            "finite sampled ray trace through the full field",
        ]

    command_parts = [
        "cd lumira-backend && uv run python scripts/audit_seed_intake.py",
        f"--target-fov {brief.target_fov_deg:.1f}",
        f"--target-efl {brief.target_efl_mm:.2f}",
        f"--target-fnum {brief.target_f_number:.2f}",
        f"--min-fov {brief.minimum_fov_deg:.1f}",
        f"--efl-lo {efl_lo:.2f}",
        f"--efl-hi {efl_hi:.2f}",
        f"--fnum-lo {fnum_lo:.2f}",
        f"--fnum-hi {fnum_hi:.2f}",
        f"--required-field {brief.required_mtf_field_frac:.1f}",
    ]
    if brief.target_image_height_mm is not None:
        command_parts.append(f"--target-image-height {brief.target_image_height_mm:.2f}")
    if image_height_lo is not None and image_height_hi is not None:
        command_parts.extend(
            [
                f"--image-height-lo {image_height_lo:.2f}",
                f"--image-height-hi {image_height_hi:.2f}",
            ]
        )
    if brief.target_n_elements is not None:
        command_parts.append(f"--target-elements {brief.target_n_elements}")
    if element_lo is not None and element_hi is not None:
        command_parts.extend(
            [f"--element-count-lo {element_lo}", f"--element-count-hi {element_hi}"]
        )
    if brief.max_total_track_mm is not None:
        command_parts.append(f"--max-total-track {brief.max_total_track_mm:.2f}")
    next_probe_command = " ".join([*command_parts, "--json"])
    candidate_preflight_command = " ".join(
        [*command_parts, "--candidate-zmx /path/to/candidate.zmx", "--json"]
    )

    status = "satisfied" if accepted_cases else "gap"
    summary = (
        f"{len(accepted_cases)} accepted high-FOV full-field seed(s) satisfy the intake window"
        if accepted_cases
        else "no accepted high-FOV full-field seed satisfies the intake window"
    )
    return SeedIntakeAudit(
        status=status,
        summary=summary,
        target_fov_deg=brief.target_fov_deg,
        minimum_fov_deg=brief.minimum_fov_deg,
        efl_window_mm=brief.efl_window_mm,
        f_number_window=brief.f_number_window,
        image_height_window_mm=brief.image_height_window_mm,
        element_count_window=brief.element_count_window,
        max_total_track_mm=brief.max_total_track_mm,
        required_mtf_field_frac=brief.required_mtf_field_frac,
        total_seed_count=len(auditable_cases),
        full_field_seed_count=len(full_field_cases),
        high_fov_seed_count=len(high_fov_cases),
        accepted_seed_count=len(accepted_cases),
        accepted_seed_candidates=[_candidate(case, "accepted") for case in accepted_cases[:3]],
        nearest_candidates=nearest_candidates,
        known_evidence=_unique_strings_in_order(known_evidence),
        missing_evidence=_unique_strings_in_order(missing_evidence),
        next_probe_command=next_probe_command,
        candidate_preflight_command=candidate_preflight_command,
    )


def match_case(
    scenario: Scenario,
    efl_mm: float,
    fnum: float,
    fov_deg: float,
    *,
    image_height_mm: float | None = None,
    n_elements: int | None = None,
    max_total_track_mm: float | None = None,
    max_weight_g: float | None = None,
    manufacturing_tier: str | None = None,
    priority: str | None = None,
    include_design_assessment: bool = True,
    lightweight_design_assessment: bool = False,
) -> OpticalSampleData | None:
    """Return the real case nearest to the user's full design intent.

    v2-03 only ranked (EFL / FOV / F#) inside one scenario bucket. v2-05 keeps
    the real-case seed strategy, but scores phone short-focus cases as one
    family and includes image height, element count, TTL, and coarse design
    stance. By default the returned sample carries a `design_assessment`
    explaining the match and its tradeoffs. Launch smoke paths can set
    `include_design_assessment=False` to return only the selected real seed
    payload without running the heavier optimizer/review evidence chain.

    `lightweight_design_assessment=True` still skips the protected optimizer
    and replay gates, but returns the MTF-first seed scorecard, requirement
    coverage, manufacturability proxy, and candidate comparison so production
    seed-only mode is not just a naked nearest-neighbor payload.
    """
    allowed = _candidate_scenarios(scenario)
    cases = [
        c for c in load_case_library() if c.metadata is not None and c.metadata.scenario in allowed
    ]
    if not cases:
        return None

    efls = [c.metadata.computed_efl_mm for c in cases]
    fovs = [c.metadata.fov_deg for c in cases]
    fnums = [c.paraxial.f_number for c in cases]
    imhs = [_case_image_height_mm(c) for c in cases]
    elems = [c.metadata.n_pieces for c in cases]
    ttls = [c.paraxial.total_track_mm for c in cases]
    mass_proxies = {c.metadata.case_id: _mass_proxy(c) for c in cases}
    masses = [mass_proxies[c.metadata.case_id].estimated_mass_g for c in cases]
    e_lo, e_hi = min(efls), max(efls)
    v_lo, v_hi = min(fovs), max(fovs)
    f_lo, f_hi = min(fnums), max(fnums)
    i_lo, i_hi = min(imhs), max(imhs)
    n_lo, n_hi = min(elems), max(elems)
    t_lo, t_hi = min(ttls), max(ttls)
    m_lo, m_hi = min(masses), max(masses)

    p = (priority or "balanced").lower()
    tier = (manufacturing_tier or "").lower()
    cost_like = p == "cost" or tier == "consumer"
    performance_like = p == "performance" or tier in {"premium", "research"}

    seed_floor_gap_cache: dict[str, float | None] = {}

    def _seed_floor_gap(c: OpticalSampleData) -> float | None:
        assert c.metadata is not None
        cached = seed_floor_gap_cache.get(c.metadata.case_id)
        if c.metadata.case_id in seed_floor_gap_cache:
            return cached
        bands = mtf_multiband_summary(c.mtf)
        rms_values = [value for value in c.mtf.rms_spot_radius_um_by_field if math.isfinite(value)]
        metrics = OptimizationMetricSnapshot(
            effective_focal_length_mm=c.metadata.computed_efl_mm,
            f_number=c.paraxial.f_number,
            total_track_mm=c.paraxial.total_track_mm,
            mtf_max_field_frac=c.metadata.mtf_max_field_frac,
            mtf_50lpmm_min=bands.min_50,
            mtf_50lpmm_avg=bands.avg_50,
            mtf_100lpmm_min=bands.min_100,
            mtf_100lpmm_avg=bands.avg_100,
            mtf_150lpmm_min=bands.min_150,
            mtf_150lpmm_avg=bands.avg_150,
            mtf_200lpmm_min=bands.min_200,
            mtf_200lpmm_avg=bands.avg_200,
            mtf_250lpmm_min=bands.min_250,
            mtf_250lpmm_avg=bands.avg_250,
            mtf_multiband_min_score=bands.multiband_min_score,
            mtf_field_weighted_score=bands.field_weighted_score,
            max_rms_spot_radius_um=max(rms_values) if rms_values else None,
        )
        gap = _image_quality_floor_gap_score(metrics)
        seed_floor_gap_cache[c.metadata.case_id] = gap
        return gap

    def _seed_has_floor_violation(c: OpticalSampleData) -> bool:
        """Whether a seed is a *real* image-quality floor violation.

        A violation means the mid-frequency MTF has collapsed or the spot
        geometry has blown up (unusable optics). This is distinct from the
        continuous 200/250 lp/mm floor-gap gradient: after the XASPHERE ingest
        fix the whole library is image-quality healthy, and that gradient is
        dominated by high-frequency geometric MTF which structurally favours
        slow apertures (aperture physics, not a design defect). Routing must not
        treat it as a gradient, so only genuine violations are detected here.
        The full 200/250 lp/mm evidence stays in the review scorecard and the
        optimizer promotion / replay gates (unchanged).
        """
        assert c.metadata is not None
        rms_values = [v for v in c.mtf.rms_spot_radius_um_by_field if math.isfinite(v)]
        max_rms = max(rms_values) if rms_values else None
        if max_rms is None or max_rms > _SEED_ROUTING_MAX_RMS_UM:
            return True
        if mtf_multiband_summary(c.mtf).min_50 < _SEED_ROUTING_MIN_MTF_50:
            return True
        floor_gap = _seed_floor_gap(c)
        return floor_gap is None or floor_gap > _SEED_ROUTING_FLOOR_GAP_LIMIT

    def _seed_quality_penalty(c: OpticalSampleData) -> float:
        assert c.metadata is not None
        # Threshold gate, not a gradient: a real floor violation dominates the
        # distance so a broken seed never wins over a healthy one (even an exact
        # parameter match); healthy seeds are separated by parameter proximity
        # with only a light full-field tiebreak.
        field_penalty = max(0.0, 1.0 - c.metadata.mtf_max_field_frac)
        if _seed_has_floor_violation(c):
            return 1.0
        return _SEED_ROUTING_FIELD_TIEBREAK * field_penalty

    def _seed_spec_guard_penalty(c: OpticalSampleData) -> float:
        assert c.metadata is not None
        penalty = 0.0
        fov_miss = abs(c.metadata.fov_deg - fov_deg)
        if fov_miss > 5.0:
            penalty += 0.04 + (fov_miss - 5.0) / 20.0
        if image_height_mm is not None:
            image_height_miss = abs(_case_image_height_mm(c) - image_height_mm)
            if image_height_miss > 0.35:
                penalty += 0.04 + (image_height_miss - 0.35) / 2.0
        return penalty

    if performance_like:
        quality_weight = 0.45
    elif cost_like:
        quality_weight = 0.25
    else:
        quality_weight = 0.34 if (image_height_mm is not None and image_height_mm <= 2.5) else 0.24

    weights = {
        "efl": 0.20,
        "fov": 0.46,
        "fnum": 0.05,
        "imh": 0.30 if image_height_mm is not None else 0.0,
        "nel": 0.02 if (n_elements is not None or cost_like) else 0.0,
        "ttl": 0.12 if (max_total_track_mm is not None or cost_like) else 0.0,
        "mass": 0.10 if max_weight_g is not None else 0.0,
        "quality": quality_weight,
    }
    weights = _normalized_weights(weights)

    def _distance_parts(
        c: OpticalSampleData,
        *,
        target_efl_mm: float = efl_mm,
    ) -> dict[str, float]:
        assert c.metadata is not None
        parts: dict[str, float] = {
            "efl": _norm_delta(target_efl_mm, c.metadata.computed_efl_mm, e_lo, e_hi),
            "fov": _norm_delta(fov_deg, c.metadata.fov_deg, v_lo, v_hi),
            "fnum": _norm_delta(fnum, c.paraxial.f_number, f_lo, f_hi),
        }
        if "imh" in weights and image_height_mm is not None:
            parts["imh"] = _norm_delta(image_height_mm, _case_image_height_mm(c), i_lo, i_hi)
        if "nel" in weights:
            target_n = n_elements if n_elements is not None else n_lo
            parts["nel"] = _norm_delta(float(target_n), float(c.metadata.n_pieces), n_lo, n_hi)
        if "ttl" in weights:
            # TTL is a ceiling, not a target. Designs under the limit get no
            # violation penalty; cost-like requests without an explicit ceiling
            # use the shortest real case as the implied target.
            target_t = max_total_track_mm if max_total_track_mm is not None else t_lo
            ttl_over = max(0.0, c.paraxial.total_track_mm - target_t)
            parts["ttl"] = 0.0 if t_hi == t_lo else ttl_over / (t_hi - t_lo)
        if "mass" in weights and max_weight_g is not None:
            mass_over = max(0.0, mass_proxies[c.metadata.case_id].estimated_mass_g - max_weight_g)
            mass_span = max(m_hi - m_lo, max_weight_g, 1e-6)
            parts["mass"] = mass_over / mass_span
        if "quality" in weights:
            parts["quality"] = _seed_quality_penalty(c)
        return parts

    def _distance(c: OpticalSampleData, *, target_efl_mm: float = efl_mm) -> float:
        parts = _distance_parts(c, target_efl_mm=target_efl_mm)
        weighted_distance = math.sqrt(sum(weights[k] * parts.get(k, 0.0) ** 2 for k in weights))
        return weighted_distance + _seed_spec_guard_penalty(c)

    distances: dict[str, float] = {}
    for case in cases:
        assert case.metadata is not None
        distances[case.metadata.case_id] = _distance(case)

    def _case_distance(c: OpticalSampleData) -> float:
        assert c.metadata is not None
        return distances[c.metadata.case_id]

    def _score_from_distance(value: float) -> float:
        return max(0.0, min(1.0, 1.0 / (1.0 + value)))

    ranked = sorted(cases, key=_case_distance)
    best = ranked[0]
    assert best.metadata is not None
    distance = _case_distance(best)
    score = _score_from_distance(distance)
    imh = _case_image_height_mm(best)

    cost_seed = min(
        cases,
        key=lambda c: (c.metadata.n_pieces, _case_distance(c), c.paraxial.total_track_mm),
    )
    thin_seed = min(cases, key=lambda c: (c.paraxial.total_track_mm, _case_distance(c)))
    full_field_cases = [c for c in cases if c.metadata and c.metadata.mtf_max_field_frac >= 1.0]
    performance_pool = full_field_cases or cases
    performance_seed = min(
        performance_pool,
        key=lambda c: (
            _seed_quality_penalty(c),
            abs(c.metadata.fov_deg - fov_deg),
            abs(c.metadata.computed_efl_mm - efl_mm),
            abs(c.paraxial.f_number - fnum),
            _case_distance(c),
        ),
    )

    selected_candidates: list[tuple[OpticalSampleData, str]] = []

    def _append_candidate(candidate: OpticalSampleData, role: str) -> None:
        assert candidate.metadata is not None
        case_id = candidate.metadata.case_id
        if any(
            existing.metadata and existing.metadata.case_id == case_id
            for existing, _ in selected_candidates
        ):
            return
        selected_candidates.append((candidate, role))

    _append_candidate(best, "best_match")
    if cost_like:
        _append_candidate(cost_seed, "cost_variant")
    if max_total_track_mm is not None or cost_like:
        _append_candidate(thin_seed, "thin_variant")
    if performance_like:
        _append_candidate(performance_seed, "performance_variant")
    for candidate, role in (
        (cost_seed, "cost_variant"),
        (thin_seed, "thin_variant"),
        (performance_seed, "performance_variant"),
    ):
        _append_candidate(candidate, role)
    for candidate in ranked:
        _append_candidate(candidate, "nearby_alternative")
    selected_candidates = selected_candidates[:4]
    nearby_alternative_index = 0
    disambiguated_candidates: list[tuple[OpticalSampleData, str]] = []
    for candidate, role in selected_candidates:
        if role == "nearby_alternative":
            nearby_alternative_index += 1
            role = f"nearby_alternative_{nearby_alternative_index}"
        disambiguated_candidates.append((candidate, role))
    selected_candidates = disambiguated_candidates

    warnings_out: list[str] = []
    rationale: list[str] = [
        "ranked real phone short-focus cases by EFL, F/#, FOV, image height, elements, and TTL",
        f"selected {best.metadata.case_id} as the lowest weighted-distance seed",
        "compared alternate seeds for cost, TTL, and performance tradeoffs",
        "applied a guard penalty for severe FOV or image-height mismatch",
    ]
    if best.metadata.scenario != scenario:
        rationale.append(
            f"cross-selected {best.metadata.scenario.value} because it better fits the requested FOV"
        )
    if image_height_mm is not None:
        rationale.append("image height participated in seed scoring")
    if n_elements is not None:
        rationale.append("requested element count participated in seed scoring")
    if max_total_track_mm is not None:
        rationale.append("TTL ceiling participated as a one-sided penalty")
    if priority is not None:
        rationale.append(f"design priority '{priority}' adjusted the scoring weights")
    if manufacturing_tier is not None:
        rationale.append(f"manufacturing tier '{manufacturing_tier}' adjusted the scoring weights")
    rationale.append("MTF/RMS floor evidence participated in seed scoring")

    if not include_design_assessment and not lightweight_design_assessment:
        return best.model_copy(update={"design_assessment": None}, deep=True)

    delta_efl = best.metadata.computed_efl_mm - efl_mm
    delta_fnum = best.paraxial.f_number - fnum
    delta_fov = best.metadata.fov_deg - fov_deg
    delta_imh = imh - image_height_mm if image_height_mm is not None else None
    delta_n = best.metadata.n_pieces - n_elements if n_elements is not None else None
    delta_ttl = (
        best.paraxial.total_track_mm - max_total_track_mm
        if max_total_track_mm is not None
        else None
    )

    if abs(delta_efl) > 0.25:
        warnings_out.append(f"EFL differs from target by {delta_efl:+.2f} mm")
    if abs(delta_fnum) > 0.25:
        warnings_out.append(f"F/# differs from target by {delta_fnum:+.2f}")
    if abs(delta_fov) > 5.0:
        warnings_out.append(f"FOV differs from target by {delta_fov:+.1f} deg")
    if delta_imh is not None and abs(delta_imh) > 0.35:
        warnings_out.append(f"image height differs from target by {delta_imh:+.2f} mm")
    if delta_n is not None and delta_n != 0:
        warnings_out.append(f"element count differs from target by {delta_n:+d}")
    if delta_ttl is not None and delta_ttl > 0:
        warnings_out.append(f"total track exceeds requested ceiling by {delta_ttl:+.2f} mm")
    if max_weight_g is not None:
        best_mass_proxy = mass_proxies[best.metadata.case_id]
        mass_delta = best_mass_proxy.estimated_mass_g - max_weight_g
        if mass_delta > 0:
            warnings_out.append(f"mass proxy exceeds requested budget by {mass_delta:+.3f} g")
        elif abs(mass_delta) <= max(0.01, 0.15 * max_weight_g):
            warnings_out.append(
                f"mass proxy has tight margin versus budget ({-mass_delta:.3f} g reserve)"
            )
    if best.metadata.mtf_max_field_frac < 1.0:
        warnings_out.append(
            "MTF was computed to "
            f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)} field; "
            "full-field rays were unstable"
        )

    def _finite_surface_spacings(sample: OpticalSampleData) -> list[float]:
        z_values = [
            surface.z_mm
            for surface in sample.surfaces
            if math.isfinite(surface.z_mm) and abs(surface.z_mm) < 1e8 and not surface.is_object
        ]
        return [
            after - before
            for before, after in zip(z_values, z_values[1:], strict=False)
            if after - before > 1e-4
        ]

    def _finite_surface_radii(sample: OpticalSampleData) -> list[float]:
        return [
            abs(surface.radius_mm)
            for surface in sample.surfaces
            if math.isfinite(surface.radius_mm)
            and 0.02 < abs(surface.radius_mm) < 1e8
            and not surface.is_object
            and not surface.is_image
        ]

    def _plastic_material_count(sample: OpticalSampleData) -> int:
        assert sample.metadata is not None
        plastic_prefixes = ("ZEONEX", "APL", "OKP", "EP", "SP")
        return sum(
            1
            for material in sample.metadata.materials
            if _canon(material).startswith(plastic_prefixes)
        )

    def _element_complexity_status(sample: OpticalSampleData) -> str:
        assert sample.metadata is not None
        if tier == "consumer":
            if sample.metadata.n_pieces <= 4:
                return "pass"
            if sample.metadata.n_pieces == 5:
                return "warning"
            return "blocker"
        return "pass" if sample.metadata.n_pieces <= 5 else "warning"

    def _ttl_packaging_status(sample: OpticalSampleData) -> str:
        if max_total_track_mm is None:
            return "not_applicable"
        ttl_reserve = max_total_track_mm - sample.paraxial.total_track_mm
        if ttl_reserve >= 0.20:
            return "pass"
        if ttl_reserve >= 0.0:
            return "warning"
        return "blocker"

    def _mass_budget_status(sample: OpticalSampleData) -> str:
        assert sample.metadata is not None
        if max_weight_g is None:
            return "not_applicable"
        mass_proxy = mass_proxies[sample.metadata.case_id]
        mass_reserve = max_weight_g - mass_proxy.estimated_mass_g
        if mass_reserve >= max(0.01, max_weight_g * 0.15):
            return "pass"
        if mass_reserve >= 0.0:
            return "warning"
        return "blocker"

    def _candidate_tolerance_proxy(sample: OpticalSampleData) -> tuple[float, str, str]:
        assert sample.metadata is not None
        spacings = _finite_surface_spacings(sample)
        radii = _finite_surface_radii(sample)
        min_spacing = min(spacings) if spacings else None
        min_radius = min(radii) if radii else None
        plastic_count = _plastic_material_count(sample)
        spacing_subscore = (
            0.15
            if min_spacing is None
            else (
                0.0
                if min_spacing >= 0.10
                else (0.25 if min_spacing >= 0.08 else (0.50 if min_spacing >= 0.05 else 0.70))
            )
        )
        radius_subscore = (
            0.15
            if min_radius is None
            else (
                0.0
                if min_radius >= 1.00
                else (0.10 if min_radius >= 0.75 else (0.20 if min_radius >= 0.50 else 0.50))
            )
        )
        aperture_subscore = (
            0.35
            if sample.paraxial.f_number <= 1.85
            else (0.18 if sample.paraxial.f_number <= 2.10 else 0.05)
        )
        piece_subscore = (
            0.35
            if sample.metadata.n_pieces >= 5
            else (0.15 if sample.metadata.n_pieces == 4 else 0.0)
        )
        plastic_subscore = 0.20 if plastic_count >= 3 else (0.10 if plastic_count else 0.0)
        field_subscore = 0.40 if sample.metadata.mtf_max_field_frac < 1.0 else 0.0
        tolerance_score = min(
            1.0,
            spacing_subscore * 0.35
            + radius_subscore * 0.20
            + aperture_subscore * 0.15
            + piece_subscore * 0.15
            + plastic_subscore * 0.10
            + field_subscore * 0.05,
        )
        if tolerance_score <= 0.24:
            return tolerance_score, "pass", "low"
        if tolerance_score < 0.62:
            return tolerance_score, "warning", "medium"
        return tolerance_score, "blocker", "high"

    def _candidate_process_yield_proxy(
        sample: OpticalSampleData, tolerance_status: str
    ) -> tuple[float, str, str]:
        assert sample.metadata is not None
        material_count = len(sample.metadata.materials)
        plastic_count = _plastic_material_count(sample)
        element_status = _element_complexity_status(sample)
        ttl_status = _ttl_packaging_status(sample)
        mass_status = _mass_budget_status(sample)
        process_score = 0.0
        process_score += (
            0.20
            if sample.metadata.n_pieces >= 5
            else (0.10 if sample.metadata.n_pieces == 4 else 0.0)
        )
        process_score += (
            0.02
            if material_count <= 3
            else (0.08 if material_count == 4 else (0.16 if material_count == 5 else 0.34))
        )
        process_score += 0.06 if plastic_count >= 3 else (0.03 if plastic_count else 0.0)
        if tolerance_status == "warning":
            process_score += 0.16
        elif tolerance_status == "blocker":
            process_score += 0.45
        if element_status == "warning":
            process_score += 0.12
        elif element_status == "blocker":
            process_score += 0.35
        if ttl_status == "warning":
            process_score += 0.08
        elif ttl_status == "blocker":
            process_score += 0.25
        if mass_status == "warning":
            process_score += 0.08
        elif mass_status == "blocker":
            process_score += 0.25
        if sample.metadata.mtf_max_field_frac < 1.0:
            process_score += 0.12
        if tier == "consumer" and sample.metadata.n_pieces >= 5:
            process_score += 0.12
        if performance_like and sample.paraxial.f_number <= 1.85:
            process_score += 0.06
        process_score = min(1.0, process_score)
        if process_score <= 0.25:
            return process_score, "pass", "low"
        if process_score < 0.75:
            return process_score, "warning", "medium"
        return process_score, "blocker", "high"

    review_proxy_cache: dict[str, _CandidateReviewProxy] = {}

    def _candidate_review_proxy(sample: OpticalSampleData) -> _CandidateReviewProxy:
        assert sample.metadata is not None
        case_id = sample.metadata.case_id
        cached = review_proxy_cache.get(case_id)
        if cached is not None:
            return cached
        tolerance_score, tolerance_status, tolerance_level = _candidate_tolerance_proxy(sample)
        process_score, process_status, process_level = _candidate_process_yield_proxy(
            sample, tolerance_status
        )
        mass_proxy = mass_proxies[case_id]
        notes = [
            f"tolerance {tolerance_level} score={tolerance_score:.2f}",
            f"process {process_level} score={process_score:.2f}",
            f"mass proxy={mass_proxy.estimated_mass_g:.3f} g",
        ]
        if max_weight_g is not None:
            notes.append(f"mass reserve={max_weight_g - mass_proxy.estimated_mass_g:+.3f} g")
        if sample.metadata.mtf_max_field_frac < 1.0:
            notes.append(
                f"MTF field={format_mtf_field_fraction(sample.metadata.mtf_max_field_frac)}"
            )
        proxy = _CandidateReviewProxy(
            tolerance_risk_score=tolerance_score,
            tolerance_risk_level=tolerance_level,
            tolerance_status=tolerance_status,
            process_yield_score=process_score,
            process_yield_level=process_level,
            process_status=process_status,
            mass_proxy_g=mass_proxy.estimated_mass_g,
            notes=tuple(notes[:4]),
        )
        review_proxy_cache[case_id] = proxy
        return proxy

    def _manufacturability_review() -> ManufacturabilityReview:
        checks: list[ManufacturabilityCheck] = []
        tier_label = tier or (manufacturing_tier or "unspecified")
        best_review_proxy = _candidate_review_proxy(best)

        def add_check(
            check_id: str,
            label: str,
            status: str,
            target: str,
            actual: str,
            *,
            evidence: list[str] | None = None,
            mitigation: str | None = None,
        ) -> None:
            checks.append(
                ManufacturabilityCheck(
                    check_id=check_id,
                    label=label,
                    status=status,
                    target=target,
                    actual=actual,
                    evidence=[
                        item.strip()
                        for item in dict.fromkeys(evidence or [])
                        if item and item.strip()
                    ][:4],
                    mitigation=mitigation,
                )
            )

        if tier == "consumer":
            element_status = _element_complexity_status(best)
            element_target = "consumer target <=4P preferred; 5P requires cost review"
        else:
            element_status = _element_complexity_status(best)
            element_target = "phone main/wide reference library target <=5P"
        add_check(
            "element_count_complexity",
            "Element-count complexity",
            element_status,
            element_target,
            f"{best.metadata.n_pieces}P imaging seed",
            evidence=[
                f"n_imaging={best.metadata.n_imaging}",
                f"n_filter={best.metadata.n_filter}",
            ],
            mitigation=(
                "compare the lower-piece cost branch before accepting this seed"
                if element_status != "pass"
                else None
            ),
        )

        spacings = _finite_surface_spacings(best)
        min_spacing = min(spacings) if spacings else None
        if min_spacing is None:
            spacing_status = "not_applicable"
            spacing_actual = "no finite spacing samples"
        elif min_spacing >= 0.08:
            spacing_status = "pass"
            spacing_actual = f"{min_spacing:.3f} mm"
        elif min_spacing >= 0.025:
            spacing_status = "warning"
            spacing_actual = f"{min_spacing:.3f} mm"
        else:
            spacing_status = "blocker"
            spacing_actual = f"{min_spacing:.3f} mm"
        add_check(
            "minimum_axial_spacing",
            "Minimum axial spacing",
            spacing_status,
            ">=0.08 mm preferred; >=0.025 mm hard floor for protected spacing edits",
            spacing_actual,
            evidence=["computed from finite serialized surface z positions"],
            mitigation=(
                "protect tight gaps during merit tuning and packaging review"
                if spacing_status in {"warning", "blocker"}
                else None
            ),
        )

        radii = _finite_surface_radii(best)
        min_radius = min(radii) if radii else None
        if min_radius is None:
            radius_status = "not_applicable"
            radius_actual = "no finite curved radius samples"
        elif min_radius >= 0.50:
            radius_status = "pass"
            radius_actual = f"{min_radius:.3f} mm"
        elif min_radius >= 0.30:
            radius_status = "warning"
            radius_actual = f"{min_radius:.3f} mm"
        else:
            radius_status = "blocker"
            radius_actual = f"{min_radius:.3f} mm"
        add_check(
            "minimum_curvature_radius",
            "Minimum curvature radius",
            radius_status,
            ">=0.50 mm preferred first-pass curvature radius",
            radius_actual,
            evidence=[f"finite curved surfaces={len(radii)}"],
            mitigation=(
                "keep radius variables bounded and ask for process review on tight curvature"
                if radius_status in {"warning", "blocker"}
                else None
            ),
        )

        material_count = len(best.metadata.materials)
        material_limit = 4 if tier == "consumer" else 5
        material_status = (
            "pass"
            if material_count <= material_limit
            else ("warning" if material_count <= material_limit + 1 else "blocker")
        )
        add_check(
            "material_diversity",
            "Material diversity",
            material_status,
            f"<= {material_limit} distinct material families for {tier_label} tier",
            f"{material_count}: {', '.join(best.metadata.materials[:5])}",
            evidence=["material names resolved from source ZMX GLAS rows"],
            mitigation=(
                "rationalize material families before cost/yield review"
                if material_status != "pass"
                else None
            ),
        )

        if max_total_track_mm is None:
            ttl_status = "not_applicable"
            ttl_actual = "no TTL ceiling supplied"
            ttl_target = "provide TTL ceiling for packaging reserve check"
            ttl_mitigation = "capture module envelope before production review"
        else:
            ttl_reserve = max_total_track_mm - best.paraxial.total_track_mm
            ttl_actual = f"{ttl_reserve:.2f} mm reserve"
            ttl_target = ">=0.20 mm preferred reserve; >=0.00 mm minimum"
            if ttl_reserve >= 0.20:
                ttl_status = "pass"
                ttl_mitigation = None
            elif ttl_reserve >= 0.0:
                ttl_status = "warning"
                ttl_mitigation = "protect remaining track during air-gap and tolerance cleanup"
            else:
                ttl_status = "blocker"
                ttl_mitigation = "select the thin branch or increase allowed total track"
        add_check(
            "ttl_packaging_reserve",
            "TTL packaging reserve",
            ttl_status,
            ttl_target,
            ttl_actual,
            evidence=[f"selected seed TTL={best.paraxial.total_track_mm:.2f} mm"],
            mitigation=ttl_mitigation,
        )

        plastic_count = _plastic_material_count(best)
        tolerance_score = best_review_proxy.tolerance_risk_score
        tolerance_status = best_review_proxy.tolerance_status
        tolerance_label = best_review_proxy.tolerance_risk_level
        if tolerance_status == "warning":
            tolerance_mitigation = "run first-order tolerance sensitivity before external release"
        elif tolerance_status == "blocker":
            tolerance_mitigation = (
                "select a less sensitive seed or relax packaging/performance constraints"
            )
        else:
            tolerance_mitigation = None
        add_check(
            "tolerance_risk_proxy",
            "Tolerance risk proxy",
            tolerance_status,
            "low first-pass tolerance risk preferred; medium requires review",
            f"{tolerance_label} risk score={tolerance_score:.2f}",
            evidence=[
                (
                    f"min spacing={min_spacing:.3f} mm"
                    if min_spacing is not None
                    else "min spacing unavailable"
                ),
                (
                    f"min radius={min_radius:.3f} mm"
                    if min_radius is not None
                    else "min radius unavailable"
                ),
                f"F/#={best.paraxial.f_number:.2f}, pieces={best.metadata.n_pieces}P",
                (
                    f"plastic material families={plastic_count}; "
                    f"MTF field={format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}"
                ),
            ],
            mitigation=tolerance_mitigation,
        )

        mass_status = "not_applicable"
        if max_weight_g is not None:
            mass_proxy = mass_proxies[best.metadata.case_id]
            mass_reserve = max_weight_g - mass_proxy.estimated_mass_g
            mass_actual = (
                f"{mass_proxy.estimated_mass_g:.3f} g proxy ({mass_reserve:+.3f} g reserve)"
            )
            mass_target = (
                f"<= {max_weight_g:.2f} g optical-stack proxy; "
                "measured module mass still required before release"
            )
            if mass_reserve >= max(0.01, max_weight_g * 0.15):
                mass_status = "pass"
                mass_mitigation = None
            elif mass_reserve >= 0.0:
                mass_status = "warning"
                mass_mitigation = "protect lens diameter, spacer, and barrel reserve during tuning"
            else:
                mass_status = "blocker"
                mass_mitigation = "select a lighter seed or relax the weight budget"
            add_check(
                "mass_proxy_budget",
                "Mass proxy budget",
                mass_status,
                mass_target,
                mass_actual,
                evidence=[
                    f"envelope diameter={mass_proxy.envelope_diameter_mm:.2f} mm",
                    f"envelope volume={mass_proxy.envelope_volume_cm3:.4f} cm^3",
                    f"density proxy={mass_proxy.density_g_cm3:.2f} g/cm^3",
                    f"fill factor={mass_proxy.fill_factor:.2f}",
                ],
                mitigation=mass_mitigation,
            )

        process_score = best_review_proxy.process_yield_score
        process_status = best_review_proxy.process_status
        process_label = best_review_proxy.process_yield_level
        if process_status == "warning":
            process_mitigation = "obtain supplier/process review before cost or yield claims"
        elif process_status == "blocker":
            process_mitigation = (
                "select a simpler seed or relax cost, yield, or packaging assumptions"
            )
        else:
            process_mitigation = None
        add_check(
            "process_yield_proxy",
            "Process/yield proxy",
            process_status,
            "low process/yield risk preferred; medium requires supplier review",
            f"{process_label} process risk score={process_score:.2f}",
            evidence=[
                f"pieces={best.metadata.n_pieces}P, material families={material_count}",
                f"plastic material families={plastic_count}, tier={tier_label}",
                f"tolerance proxy={tolerance_status}, TTL reserve={ttl_status}",
                (
                    f"mass budget={mass_status}; "
                    f"MTF field={format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}"
                ),
            ],
            mitigation=process_mitigation,
        )

        blockers = sum(check.status == "blocker" for check in checks)
        warnings_count = sum(check.status == "warning" for check in checks)
        score_value = max(0.0, 1.0 - blockers * 0.35 - warnings_count * 0.12)
        if blockers:
            status = "blocked"
            summary = f"{blockers} manufacturability blocker(s) require branch changes"
        elif warnings_count:
            status = "warning"
            summary = f"{warnings_count} first-pass manufacturability warning(s) need review"
        else:
            status = "pass"
            summary = "first-pass geometry and complexity checks are acceptable"
        return ManufacturabilityReview(
            status=status,
            tier=tier_label,
            score=score_value,
            summary=summary,
            checks=checks,
            limitations=[
                "tolerance risk proxy is not a Monte-Carlo tolerance or yield analysis",
                "mass proxy excludes sensor, actuator, adhesive, and detailed barrel CAD",
                "process/yield proxy is not a supplier quote, molding cost table, or yield model",
                "uses selected seed geometry only; optimizer branch must be rechecked after changes",
            ],
        )

    manufacturability_review = _manufacturability_review()

    def _candidate_review_risk_for_sample(sample: OpticalSampleData) -> float:
        review_proxy = _candidate_review_proxy(sample)
        return review_proxy.tolerance_risk_score * 0.45 + review_proxy.process_yield_score * 0.55

    def _candidate_proxy_case_opportunity() -> (
        tuple[OpticalSampleData, OpticalSampleData, float, float] | None
    ):
        if not selected_candidates:
            return None
        selected = selected_candidates[0][0]
        leader = min(
            (candidate for candidate, _role in selected_candidates),
            key=lambda candidate: (
                _candidate_review_risk_for_sample(candidate),
                _case_distance(candidate),
            ),
        )
        assert selected.metadata is not None
        assert leader.metadata is not None
        selected_risk = _candidate_review_risk_for_sample(selected)
        leader_risk = _candidate_review_risk_for_sample(leader)
        if (
            leader.metadata.case_id == selected.metadata.case_id
            or leader_risk + 0.03 >= selected_risk
        ):
            return None
        return selected, leader, selected_risk, leader_risk

    candidate_proxy_case_opportunity = _candidate_proxy_case_opportunity()

    def _candidate_proxy_branch_resolution() -> _CandidateProxyBranchResolution | None:
        if candidate_proxy_case_opportunity is None:
            return None

        selected, candidate, selected_risk, candidate_risk = candidate_proxy_case_opportunity
        assert selected.metadata is not None
        assert candidate.metadata is not None
        candidate_imh = _case_image_height_mm(candidate)
        blockers: list[str] = []
        evidence = [
            f"candidate {candidate.metadata.case_id} review risk {candidate_risk:.2f} "
            f"vs selected {selected.metadata.case_id} {selected_risk:.2f}",
            f"EFL delta {candidate.metadata.computed_efl_mm - efl_mm:+.2f} mm",
            f"F/# delta {candidate.paraxial.f_number - fnum:+.2f}",
            f"FOV delta {candidate.metadata.fov_deg - fov_deg:+.1f} deg",
        ]

        if abs(candidate.metadata.computed_efl_mm - efl_mm) > 0.25:
            blockers.append(
                f"EFL miss {candidate.metadata.computed_efl_mm - efl_mm:+.2f} mm exceeds 0.25 mm"
            )
        if abs(candidate.paraxial.f_number - fnum) > 0.25:
            blockers.append(f"F/# miss {candidate.paraxial.f_number - fnum:+.2f} exceeds 0.25")
        if abs(candidate.metadata.fov_deg - fov_deg) > 5.0:
            blockers.append(
                f"FOV miss {candidate.metadata.fov_deg - fov_deg:+.1f} deg exceeds 5.0 deg"
            )
        if image_height_mm is not None:
            imh_delta = candidate_imh - image_height_mm
            evidence.append(f"image-height delta {imh_delta:+.2f} mm")
            if abs(imh_delta) > 0.35:
                blockers.append(f"image-height miss {imh_delta:+.2f} mm exceeds 0.35 mm")
        if max_total_track_mm is not None:
            ttl_over = candidate.paraxial.total_track_mm - max_total_track_mm
            evidence.append(
                f"TTL margin {max_total_track_mm - candidate.paraxial.total_track_mm:+.2f} mm"
            )
            if ttl_over > 0.20:
                blockers.append(f"TTL exceeds package by {ttl_over:+.2f} mm")
        if candidate.metadata.mtf_max_field_frac < 1.0:
            blockers.append(
                "candidate does not carry full-field MTF evidence "
                f"({format_mtf_field_fraction(candidate.metadata.mtf_max_field_frac)} field)"
            )

        if not blockers:
            return None

        return _CandidateProxyBranchResolution(
            status="rejected_for_target_fit",
            selected_case_id=selected.metadata.case_id,
            candidate_case_id=candidate.metadata.case_id,
            summary=(
                "lower-risk candidate branch was compared and rejected because it misses "
                "hard optical/package targets; selected branch remains primary"
            ),
            evidence=tuple(dict.fromkeys(evidence))[:8],
            blockers=tuple(dict.fromkeys(blockers))[:6],
        )

    candidate_proxy_branch_resolution = _candidate_proxy_branch_resolution()

    def _fov_alternative_case() -> OpticalSampleData | None:
        selected_gap = abs(best.metadata.fov_deg - fov_deg)
        if selected_gap <= 2.0:
            return None
        alternatives = [
            case
            for case in cases
            if case.metadata is not None and case.metadata.case_id != best.metadata.case_id
        ]
        if not alternatives:
            return None
        candidate = min(
            alternatives,
            key=lambda case: (
                abs(case.metadata.fov_deg - fov_deg),
                (
                    abs(_case_image_height_mm(case) - image_height_mm)
                    if image_height_mm is not None
                    else 0.0
                ),
                abs(case.metadata.computed_efl_mm - efl_mm),
                abs(case.paraxial.f_number - fnum),
                _case_distance(case),
            ),
        )
        assert candidate.metadata is not None
        candidate_gap = abs(candidate.metadata.fov_deg - fov_deg)
        if candidate_gap + 1.0 >= selected_gap:
            return None
        return candidate

    fov_alternative_case = _fov_alternative_case()

    def _fov_alternative_branch_resolution() -> _FovAlternativeBranchResolution | None:
        if fov_alternative_case is None or fov_alternative_case.metadata is None:
            return None

        candidate = fov_alternative_case
        selected_fov_delta = best.metadata.fov_deg - fov_deg
        candidate_fov_delta = candidate.metadata.fov_deg - fov_deg
        candidate_efl_delta = candidate.metadata.computed_efl_mm - efl_mm
        candidate_fnum_delta = candidate.paraxial.f_number - fnum
        candidate_imh_delta = (
            _case_image_height_mm(candidate) - image_height_mm
            if image_height_mm is not None
            else None
        )
        candidate_n_delta = (
            candidate.metadata.n_pieces - n_elements if n_elements is not None else None
        )

        evidence = [
            f"selected seed {best.metadata.case_id} FOV delta {selected_fov_delta:+.1f} deg",
            f"alternative seed {candidate.metadata.case_id} FOV delta {candidate_fov_delta:+.1f} deg",
        ]
        blockers: list[str] = []

        if abs(candidate_efl_delta) > 0.25:
            blockers.append(f"alternative EFL misses target by {candidate_efl_delta:+.2f} mm")
        elif abs(candidate_efl_delta) > 0.15:
            evidence.append(f"alternative EFL remains a tradeoff at {candidate_efl_delta:+.2f} mm")

        if candidate_fnum_delta > 0.25:
            blockers.append(
                f"alternative F-number is slower than target by {candidate_fnum_delta:+.2f}"
            )
        elif candidate_fnum_delta > 0.15:
            evidence.append(
                f"alternative F-number remains a tradeoff at {candidate_fnum_delta:+.2f}"
            )
        elif candidate_fnum_delta <= 0:
            evidence.append("alternative aperture is faster than or equal to target")

        if candidate_imh_delta is not None:
            if abs(candidate_imh_delta) > 0.35:
                blockers.append(
                    f"alternative image height misses target by {candidate_imh_delta:+.2f} mm"
                )
            elif abs(candidate_imh_delta) > 0.20:
                evidence.append(
                    f"alternative image height remains a tradeoff at {candidate_imh_delta:+.2f} mm"
                )

        if candidate_n_delta is not None:
            if abs(candidate_n_delta) > 1:
                blockers.append(
                    f"alternative element count differs by {candidate_n_delta:+d} pieces"
                )
            elif candidate_n_delta != 0:
                evidence.append(
                    f"alternative element count remains a tradeoff at {candidate_n_delta:+d} pieces"
                )

        if candidate.metadata.mtf_max_field_frac < 1.0:
            blockers.append(
                "alternative MTF evidence reaches only "
                f"{format_mtf_field_fraction(candidate.metadata.mtf_max_field_frac)} field"
            )
        else:
            evidence.append("alternative has full-field MTF evidence")

        if blockers:
            return _FovAlternativeBranchResolution(
                status="rejected_for_target_fit",
                selected_case_id=best.metadata.case_id,
                candidate_case_id=candidate.metadata.case_id,
                summary=(
                    f"FOV alternative {candidate.metadata.case_id} closes the field-angle gap "
                    "but cannot replace the selected seed without target-fit regressions"
                ),
                evidence=tuple(dict.fromkeys(evidence))[:6],
                blockers=tuple(dict.fromkeys(blockers))[:6],
            )

        return _FovAlternativeBranchResolution(
            status="review_required",
            selected_case_id=best.metadata.case_id,
            candidate_case_id=candidate.metadata.case_id,
            summary=(
                f"FOV alternative {candidate.metadata.case_id} closes the field-angle gap "
                "and needs branch-level review before payload selection"
            ),
            evidence=tuple(dict.fromkeys(evidence))[:6],
            blockers=(),
        )

    fov_alternative_branch_resolution = _fov_alternative_branch_resolution()

    def _fov_target_seed_brief() -> SeedAcquisitionBrief | None:
        resolution = fov_alternative_branch_resolution
        if resolution is None or resolution.status != "rejected_for_target_fit":
            return None
        if abs(best.metadata.fov_deg - fov_deg) <= 2.0:
            return None

        target_image_height = image_height_mm or best.metadata.image_height_mm
        target_elements = n_elements or best.metadata.n_pieces
        image_height_window = (
            [
                round(max(0.1, target_image_height - 0.20), 2),
                round(target_image_height + 0.20, 2),
            ]
            if target_image_height is not None
            else []
        )
        element_count_window = (
            [
                max(3, target_elements - 1),
                min(8, target_elements + 1),
            ]
            if target_elements is not None
            else []
        )
        return SeedAcquisitionBrief(
            target_regime="smartphone visible-light main/wide FOV-closure seed",
            priority="required_for_fov_acceptance_or_explicit_waiver",
            source_format="Zemax/Optiland-compatible visible-light prescription with material metadata",
            target_fov_deg=fov_deg,
            minimum_fov_deg=max(1.0, fov_deg - 2.0),
            target_efl_mm=efl_mm,
            efl_window_mm=[round(max(0.1, efl_mm - 0.15), 2), round(efl_mm + 0.15, 2)],
            target_f_number=fnum,
            f_number_window=[round(max(0.8, fnum - 0.30), 2), round(fnum + 0.15, 2)],
            target_image_height_mm=target_image_height,
            image_height_window_mm=image_height_window,
            target_n_elements=target_elements,
            element_count_window=element_count_window,
            max_total_track_mm=max_total_track_mm,
            required_mtf_field_frac=1.0,
            validation_requirements=[
                "visible-light wavelength set, not IR-only",
                f"FOV within +/-2.0 deg of {fov_deg:.1f} deg target",
                f"EFL within {efl_mm - 0.15:.2f}-{efl_mm + 0.15:.2f} mm",
                f"F-number no slower than {fnum + 0.15:.2f}",
                "finite ray trace and MTF at 1.0 field",
            ],
            rejection_filters=[
                "FOV-only match that slows aperture beyond the F-number window",
                "element count outside the allowed branch window",
                "image-height mismatch outside the target sensor window",
                "MTF max stable field below 1.0",
                *list(resolution.blockers[:3]),
            ],
            rationale=[
                resolution.summary,
                *list(resolution.evidence[:3]),
                *list(resolution.blockers[:3]),
            ],
        )

    fov_target_seed_brief = _fov_target_seed_brief()

    def _fov_spec_consistency() -> _FovSpecConsistency | None:
        if image_height_mm is None or efl_mm <= 0 or fov_deg <= 0:
            return None

        half_angle_rad = math.radians(fov_deg / 2.0)
        half_angle_tan = math.tan(half_angle_rad)
        if half_angle_tan <= 0:
            return None

        first_order_fov = 2.0 * math.degrees(math.atan(image_height_mm / efl_mm))
        geometry_delta = fov_deg - first_order_fov
        implied_efl = image_height_mm / half_angle_tan
        implied_image_height = efl_mm * half_angle_tan
        abs_delta = abs(geometry_delta)
        if abs_delta <= 2.0:
            status = "met"
        elif abs_delta <= 5.0:
            status = "tradeoff"
        else:
            status = "miss"

        if geometry_delta > 0:
            direction = "wider"
            action = (
                "first reconcile the EFL/image-height/FOV triad: lower EFL toward "
                f"{implied_efl:.2f} mm, increase image height toward "
                f"{implied_image_height:.2f} mm, or relax the FOV target"
            )
        else:
            direction = "narrower"
            action = (
                "first reconcile the EFL/image-height/FOV triad: raise EFL toward "
                f"{implied_efl:.2f} mm, reduce image height toward "
                f"{implied_image_height:.2f} mm, or relax the FOV target"
            )

        summary = (
            f"requested FOV is {abs_delta:.1f} deg {direction} than the first-order "
            "EFL/image-height estimate"
        )
        evidence = (
            f"first-order FOV at EFL {efl_mm:.2f} mm and image height "
            f"{image_height_mm:.2f} mm is {first_order_fov:.1f} deg",
            f"{fov_deg:.1f} deg at image height {image_height_mm:.2f} mm implies "
            f"EFL {implied_efl:.2f} mm",
            f"{fov_deg:.1f} deg at EFL {efl_mm:.2f} mm implies image height "
            f"{implied_image_height:.2f} mm",
        )
        return _FovSpecConsistency(
            status=status,
            first_order_fov_deg=first_order_fov,
            delta_fov_deg=geometry_delta,
            implied_efl_mm=implied_efl,
            implied_image_height_mm=implied_image_height,
            summary=summary,
            evidence=evidence,
            next_action=action,
        )

    fov_spec_consistency = _fov_spec_consistency()

    def _fov_spec_default_repair() -> tuple[str, str, str] | None:
        if fov_spec_consistency is None or image_height_mm is None:
            return None
        if fov_spec_consistency.status == "met":
            return None

        direction = "downward" if fov_spec_consistency.delta_fov_deg > 0 else "upward"
        recommendation = (
            "default repair recommendation: preserve sensor image height "
            f"{image_height_mm:.2f} mm and FOV {fov_deg:.1f} deg; repair target "
            f"EFL {direction} to {fov_spec_consistency.implied_efl_mm:.2f} mm"
        )
        requirement = (
            "record the default repaired target EFL "
            f"{fov_spec_consistency.implied_efl_mm:.2f} mm while preserving image height "
            f"{image_height_mm:.2f} mm, or explicitly override it with image-height repair "
            "or FOV waiver"
        )
        rationale = (
            "default repair assumes sensor image height is the harder product/package "
            "constraint; override only if perspective/EFL is the locked requirement"
        )
        return recommendation, requirement, rationale

    fov_spec_default_repair = _fov_spec_default_repair()

    def _fov_alternative_next_action() -> str:
        spec_prefix = ""
        if (
            fov_spec_consistency is not None
            and fov_spec_consistency.status != "met"
            and abs(delta_fov) > 2.0
        ):
            spec_prefix = f"{fov_spec_consistency.next_action}; then "
        if fov_alternative_branch_resolution is not None:
            if fov_alternative_branch_resolution.status == "rejected_for_target_fit":
                return (
                    f"{spec_prefix}FOV alternative "
                    f"{fov_alternative_branch_resolution.candidate_case_id} "
                    "rejected for target-fit regressions; acquire or optimize a seed that "
                    "preserves requested FOV without EFL/F-number/image-height regressions, "
                    "using the fov-target-seed-needed brief, or review fov-waiver-review to "
                    "explicitly waive the selected seed's narrower-FOV tradeoff"
                )
            return (
                f"{spec_prefix}compare FOV alternative "
                f"{fov_alternative_branch_resolution.candidate_case_id} "
                "against EFL/F-number/image-height/MTF tradeoffs before accepting the narrower-FOV seed"
            )
        if fov_alternative_case is not None and fov_alternative_case.metadata is not None:
            return (
                f"{spec_prefix}compare FOV alternative {fov_alternative_case.metadata.case_id} "
                "against EFL/F-number/image-height/MTF tradeoffs before accepting the narrower-FOV seed"
            )
        if fov_deg >= 85.0:
            return f"{spec_prefix}select a relaxed-FOV fallback or acquire a closer high-FOV seed"
        return (
            f"{spec_prefix}acquire a closer-FOV seed or explicitly accept the selected "
            "seed's narrower-FOV tradeoff"
        )

    def _coverage_status(delta: float, *, met: float, tradeoff: float) -> str:
        value = abs(delta)
        if value <= met:
            return "met"
        if value <= tradeoff:
            return "tradeoff"
        return "miss"

    def _fov_spec_repair_replay() -> _FovSpecRepairReplay | None:
        if fov_spec_default_repair is None or fov_spec_consistency is None:
            return None

        repaired_efl = fov_spec_consistency.implied_efl_mm
        replay_ranked = sorted(cases, key=lambda c: _distance(c, target_efl_mm=repaired_efl))
        replay_best = replay_ranked[0]
        assert replay_best.metadata is not None

        replay_distance = _distance(replay_best, target_efl_mm=repaired_efl)
        replay_score = _score_from_distance(replay_distance)
        replay_imh = _case_image_height_mm(replay_best)
        replay_delta_efl = replay_best.metadata.computed_efl_mm - repaired_efl
        replay_delta_fov = replay_best.metadata.fov_deg - fov_deg
        replay_delta_fnum = replay_best.paraxial.f_number - fnum
        replay_delta_imh = replay_imh - image_height_mm if image_height_mm is not None else None
        replay_delta_n = (
            replay_best.metadata.n_pieces - n_elements if n_elements is not None else None
        )
        replay_delta_ttl = (
            replay_best.paraxial.total_track_mm - max_total_track_mm
            if max_total_track_mm is not None
            else None
        )

        replay_coverage: list[RequirementCoverageItem] = []

        def add_preview_item(
            requirement_id: str,
            label: str,
            status: str,
            target: str,
            actual: str,
            *,
            delta: float | None = None,
            tolerance: float | None = None,
            unit: str | None = None,
            evidence: list[str] | None = None,
            next_action: str | None = None,
        ) -> None:
            replay_coverage.append(
                RequirementCoverageItem(
                    requirement_id=requirement_id,
                    label=label,
                    status=status,
                    priority="preview",
                    target=target,
                    actual=actual,
                    delta=delta,
                    tolerance=tolerance,
                    unit=unit,
                    evidence=[
                        item.strip()
                        for item in dict.fromkeys(evidence or [])
                        if item and item.strip()
                    ][:4],
                    next_action=next_action,
                )
            )

        add_preview_item(
            "effective_focal_length",
            "Effective focal length",
            _coverage_status(replay_delta_efl, met=0.15, tradeoff=0.25),
            f"{repaired_efl:.2f}",
            f"{replay_best.metadata.computed_efl_mm:.2f}",
            delta=replay_delta_efl,
            tolerance=0.25,
            unit="mm",
            evidence=["replayed after default spec repair"],
        )
        replay_f_number_status = (
            "met"
            if replay_delta_fnum <= 0
            else _coverage_status(replay_delta_fnum, met=0.15, tradeoff=0.25)
        )
        add_preview_item(
            "f_number",
            "F-number",
            replay_f_number_status,
            f"{fnum:.2f}",
            f"{replay_best.paraxial.f_number:.2f}",
            delta=replay_delta_fnum,
            tolerance=0.25,
            evidence=["faster aperture remains accepted in preview"],
        )
        add_preview_item(
            "field_of_view",
            "Field of view",
            _coverage_status(replay_delta_fov, met=2.0, tradeoff=5.0),
            f"{fov_deg:.1f}",
            f"{replay_best.metadata.fov_deg:.1f}",
            delta=replay_delta_fov,
            tolerance=5.0,
            unit="deg",
            evidence=["FOV is still evaluated against the original requested field"],
            next_action=(
                "review FOV waiver or seed acquisition after repaired-target replay"
                if abs(replay_delta_fov) > 2.0
                else None
            ),
        )
        replay_mtf_status = (
            "met"
            if replay_best.metadata.mtf_max_field_frac >= 1.0
            else ("tradeoff" if replay_best.metadata.mtf_max_field_frac >= 0.8 else "miss")
        )
        add_preview_item(
            "mtf_field_evidence",
            "MTF field evidence",
            replay_mtf_status,
            "1.0 field",
            f"{format_mtf_field_fraction(replay_best.metadata.mtf_max_field_frac)} field",
            delta=replay_best.metadata.mtf_max_field_frac - 1.0,
            tolerance=0.0,
            evidence=["preview uses existing seed MTF evidence"],
        )
        if replay_delta_imh is not None:
            add_preview_item(
                "image_height",
                "Image height",
                _coverage_status(replay_delta_imh, met=0.20, tradeoff=0.35),
                f"{image_height_mm:.2f}",
                f"{replay_imh:.2f}",
                delta=replay_delta_imh,
                tolerance=0.35,
                unit="mm",
                evidence=["default repair preserves target sensor format"],
            )
        if replay_delta_n is not None:
            add_preview_item(
                "element_count",
                "Element count",
                "met"
                if replay_delta_n == 0
                else ("tradeoff" if abs(replay_delta_n) == 1 else "miss"),
                f"{n_elements}P",
                f"{replay_best.metadata.n_pieces}P",
                delta=float(replay_delta_n),
                tolerance=0.0,
                unit="pieces",
                evidence=["preview uses the replay-selected seed element count"],
            )
        if replay_delta_ttl is not None:
            add_preview_item(
                "total_track",
                "Total track length",
                "met"
                if replay_delta_ttl <= 0
                else ("tradeoff" if replay_delta_ttl <= 0.20 else "miss"),
                f"<= {max_total_track_mm:.2f}",
                f"{replay_best.paraxial.total_track_mm:.2f}",
                delta=replay_delta_ttl,
                tolerance=0.0,
                unit="mm",
                evidence=["preview uses the replay-selected seed TTL"],
            )

        met_count = sum(item.status == "met" for item in replay_coverage)
        tradeoff_count = sum(item.status == "tradeoff" for item in replay_coverage)
        miss_count = sum(item.status == "miss" for item in replay_coverage)
        unresolved = [
            f"{item.label}={item.status}" for item in replay_coverage if item.status != "met"
        ]
        replay_status = (
            "ready_after_repair"
            if not tradeoff_count and not miss_count
            else ("blocked_after_repair" if miss_count else "tradeoff_after_repair")
        )
        selected_label = (
            "same seed"
            if replay_best.metadata.case_id == best.metadata.case_id
            else f"reselected from {best.metadata.case_id}"
        )
        evidence = [
            (
                f"repaired-target replay uses EFL {repaired_efl:.2f} mm, "
                f"image height {image_height_mm:.2f} mm, FOV {fov_deg:.1f} deg"
            ),
            (
                f"replay {selected_label}: {replay_best.metadata.case_id}, "
                f"score {replay_score:.3f}, distance {replay_distance:.3f}"
            ),
            (
                f"replay deltas: EFL {replay_delta_efl:+.2f} mm, "
                f"FOV {replay_delta_fov:+.1f} deg, F/# {replay_delta_fnum:+.2f}"
            ),
            (
                f"replay coverage preview: {met_count} met / "
                f"{tradeoff_count} tradeoff / {miss_count} miss"
            ),
        ]
        if unresolved:
            evidence.append("remaining after repaired target: " + ", ".join(unresolved[:4]))
        risks = [
            "replay is a target-ranking preview; delivered prescription is unchanged",
        ]
        if replay_best.metadata.case_id == best.metadata.case_id and replay_delta_fov < -2.0:
            risks.append("default repair stabilizes EFL fit but leaves selected seed FOV narrow")
        if miss_count:
            risks.append("repaired-target replay still has hard misses before draft promotion")
        payload_policy = (
            "preview_only: repaired target is not applied to the delivered payload until "
            "branch selection is recorded and the full assessment is regenerated"
        )
        coverage_summary = RequirementCoverageSummary(
            status=("blocked" if miss_count else ("tradeoff" if tradeoff_count else "met")),
            met_count=met_count,
            tradeoff_count=tradeoff_count,
            miss_count=miss_count,
            unscored_count=0,
            summary=(
                f"repaired-target preview: {met_count} met, "
                f"{tradeoff_count} tradeoff, {miss_count} miss"
            ),
        )
        return _FovSpecRepairReplay(
            status=replay_status,
            repaired_efl_mm=repaired_efl,
            selected_case=replay_best,
            score=replay_score,
            normalized_distance=replay_distance,
            coverage_summary=coverage_summary,
            coverage=tuple(replay_coverage),
            met_count=met_count,
            tradeoff_count=tradeoff_count,
            miss_count=miss_count,
            remaining_tradeoffs=tuple(unresolved),
            payload_policy=payload_policy,
            evidence=tuple(evidence[:5]),
            risks=tuple(risks[:4]),
        )

    fov_spec_repair_replay = _fov_spec_repair_replay()

    spec_repair_preview = (
        SpecRepairPreviewPacket(
            source_candidate_id="fov-spec-reconciliation",
            status=fov_spec_repair_replay.status,
            repaired_target_focal_length_mm=fov_spec_repair_replay.repaired_efl_mm,
            repaired_target_image_height_mm=image_height_mm,
            target_fov_deg=fov_deg,
            selected_case_id=fov_spec_repair_replay.selected_case.metadata.case_id,
            score=fov_spec_repair_replay.score,
            normalized_distance=fov_spec_repair_replay.normalized_distance,
            coverage_summary=fov_spec_repair_replay.coverage_summary,
            coverage=list(fov_spec_repair_replay.coverage),
            remaining_tradeoffs=list(fov_spec_repair_replay.remaining_tradeoffs),
            payload_policy=fov_spec_repair_replay.payload_policy,
            evidence=list(fov_spec_repair_replay.evidence),
            risks=list(fov_spec_repair_replay.risks),
        )
        if fov_spec_repair_replay is not None
        else None
    )

    def _spec_repair_decision() -> SpecRepairDecisionPacket | None:
        if (
            fov_spec_consistency is None
            or fov_spec_default_repair is None
            or fov_spec_repair_replay is None
            or spec_repair_preview is None
        ):
            return None

        repaired_efl = fov_spec_repair_replay.repaired_efl_mm
        selected_case_id = fov_spec_repair_replay.selected_case.metadata.case_id
        if fov_spec_repair_replay.miss_count:
            status = "blocked"
        elif fov_spec_repair_replay.tradeoff_count:
            status = "recommended_with_tradeoffs"
        else:
            status = "recommended"

        alternatives = [
            (
                f"repair image height to {fov_spec_consistency.implied_image_height_mm:.2f} mm "
                f"while keeping target EFL {efl_mm:.2f} mm"
            ),
            (
                f"explicitly waive FOV to the selected seed at {best.metadata.fov_deg:.1f} deg "
                f"and keep target EFL {efl_mm:.2f} mm"
            ),
        ]
        evidence = [
            fov_spec_default_repair[0],
            *fov_spec_consistency.evidence[:3],
            *fov_spec_repair_replay.evidence[:4],
        ]
        risks = [
            fov_spec_default_repair[2],
            *fov_spec_repair_replay.risks[:3],
            "accepting the repaired EFL changes the target spec, not the delivered prescription",
        ]
        rerun_contract = SpecRepairRerunContract(
            source_decision="accept_repaired_efl_target",
            status="ready" if not fov_spec_repair_replay.miss_count else "blocked",
            target_scenario=scenario,
            target_focal_length_mm=repaired_efl,
            target_f_number=fnum,
            target_fov_deg=fov_deg,
            target_image_height_mm=image_height_mm,
            target_n_elements=n_elements,
            target_total_track_mm=max_total_track_mm,
            priority=priority,
            manufacturing_tier=manufacturing_tier,
            expected_case_id=selected_case_id,
            expected_coverage_summary=spec_repair_preview.coverage_summary,
            query_summary=(
                f"rerun match request with EFL {repaired_efl:.2f} mm, "
                f"F/# {fnum:.2f}, FOV {fov_deg:.1f} deg"
                + (
                    f", image height {image_height_mm:.2f} mm"
                    if image_height_mm is not None
                    else ""
                )
                + (f", {n_elements}P" if n_elements is not None else "")
                + f", scenario {scenario.value}"
            ),
            validation_checks=[
                (
                    f"rerun matching with target_scenario={scenario.value}, "
                    f"target_focal_length_mm={repaired_efl:.2f} "
                    "and unchanged FOV/image height"
                ),
                f"confirm selected case remains {selected_case_id} or document reselection",
                (
                    "confirm repaired-target coverage is "
                    f"{fov_spec_repair_replay.met_count} met / "
                    f"{fov_spec_repair_replay.tradeoff_count} tradeoff / "
                    f"{fov_spec_repair_replay.miss_count} miss"
                ),
                "rebuild branch selection, acceptance gate, PDF, and summary from the rerun result",
            ],
            payload_policy=(
                "not applied to current payload; use as the exact next match request "
                "after the target-spec decision is accepted"
            ),
        )
        return SpecRepairDecisionPacket(
            source_candidate_id="fov-spec-reconciliation",
            status=status,
            recommended_decision="accept_repaired_efl_target",
            locked_constraint="sensor_image_height_and_target_fov",
            repaired_parameter="target_focal_length_mm",
            original_focal_length_mm=efl_mm,
            repaired_focal_length_mm=repaired_efl,
            original_image_height_mm=image_height_mm,
            repaired_image_height_mm=image_height_mm,
            target_fov_deg=fov_deg,
            first_order_fov_deg=fov_spec_consistency.first_order_fov_deg,
            implied_image_height_mm=fov_spec_consistency.implied_image_height_mm,
            selected_case_id=selected_case_id,
            preview_status=spec_repair_preview.status,
            preview_coverage_summary=spec_repair_preview.coverage_summary,
            decision_summary=(
                f"Record repaired target EFL {repaired_efl:.2f} mm while preserving "
                f"image height {image_height_mm:.2f} mm and target FOV {fov_deg:.1f} deg; "
                f"replay selects {selected_case_id} with "
                f"{fov_spec_repair_replay.met_count} met / "
                f"{fov_spec_repair_replay.tradeoff_count} tradeoff / "
                f"{fov_spec_repair_replay.miss_count} miss."
            ),
            alternatives=alternatives,
            required_record=fov_spec_default_repair[1],
            acceptance_effect=(
                "records the target-spec decision and unblocks branch-selection review; "
                "full draft claims still require regenerating the assessment against the "
                "accepted target"
            ),
            payload_policy=spec_repair_preview.payload_policy,
            rerun_contract=rerun_contract,
            evidence=list(dict.fromkeys(item for item in evidence if item))[:8],
            risks=list(dict.fromkeys(item for item in risks if item))[:6],
        )

    spec_repair_decision = _spec_repair_decision()

    def _spec_repair_auto_closure() -> SpecRepairAutoClosure | None:
        if (
            spec_repair_decision is None
            or spec_repair_preview is None
            or fov_spec_consistency is None
            or fov_spec_repair_replay is None
            or fov_spec_repair_replay.miss_count
            or fov_spec_consistency.status != "tradeoff"
            or spec_repair_decision.repaired_focal_length_mm is None
        ):
            return None
        repair_delta = abs(
            spec_repair_decision.original_focal_length_mm
            - spec_repair_decision.repaired_focal_length_mm
        )
        repair_delta_pct = (
            repair_delta / spec_repair_decision.original_focal_length_mm * 100.0
            if spec_repair_decision.original_focal_length_mm > 0
            else 100.0
        )
        remaining = set(spec_repair_preview.remaining_tradeoffs)
        only_soft_fov_tradeoff = remaining.issubset({"Field of view=tradeoff"})
        alternative_rejected = (
            fov_alternative_branch_resolution is None
            or fov_alternative_branch_resolution.status == "rejected_for_target_fit"
        )
        if (
            repair_delta > 0.20
            or repair_delta_pct > 6.0
            or not only_soft_fov_tradeoff
            or not alternative_rejected
            or spec_repair_preview.selected_case_id != best.metadata.case_id
        ):
            return None
        accepted_tradeoff_ids = ["fov_spec_consistency"]
        if "Field of view=tradeoff" in remaining:
            accepted_tradeoff_ids.append("field_of_view")
        return SpecRepairAutoClosure(
            source_decision=spec_repair_decision.recommended_decision,
            status="auto_closed_for_review",
            repaired_target_focal_length_mm=spec_repair_decision.repaired_focal_length_mm,
            target_image_height_mm=spec_repair_decision.original_image_height_mm,
            target_fov_deg=spec_repair_decision.target_fov_deg,
            repair_delta_mm=repair_delta,
            repair_delta_pct=repair_delta_pct,
            accepted_tradeoff_ids=list(dict.fromkeys(accepted_tradeoff_ids)),
            summary=(
                "minor first-order target-spec repair is recorded as a review note; "
                "the delivered payload remains unchanged"
            ),
            rationale=[
                "default repair preserves sensor image height and requested FOV",
                (
                    f"EFL repair delta {repair_delta:.2f} mm / {repair_delta_pct:.1f}% "
                    "is within the minor auto-closure window"
                ),
                (
                    "repaired-target replay has no hard misses"
                    f" ({spec_repair_preview.coverage_summary.met_count} met / "
                    f"{spec_repair_preview.coverage_summary.tradeoff_count} tradeoff / "
                    f"{spec_repair_preview.coverage_summary.miss_count} miss)"
                ),
                "closer-FOV alternative was rejected for target-fit regressions",
            ],
            evidence=[
                spec_repair_decision.required_record,
                spec_repair_decision.decision_summary,
                *spec_repair_preview.evidence[:3],
            ],
            forbidden_claims=[
                "original target EFL, image height, and FOV claimed as simultaneously satisfied",
                "selected payload mutated to repaired EFL before rerun",
                "remaining FOV tradeoff hidden from the report",
            ],
        )

    spec_repair_auto_closure = _spec_repair_auto_closure()

    def _performance_aperture_tradeoff_resolution() -> (
        _PerformanceApertureTradeoffResolution | None
    ):
        if not performance_like or delta_fnum <= 0.25:
            return None

        selected_floor_gap = _seed_floor_gap(best)
        if selected_floor_gap is None or selected_floor_gap > 0.10:
            return None

        def _is_exact_aperture_candidate(case: OpticalSampleData) -> bool:
            assert case.metadata is not None
            if case.metadata.case_id == best.metadata.case_id:
                return False
            if case.paraxial.f_number > fnum + 0.15:
                return False
            if abs(case.metadata.computed_efl_mm - efl_mm) > 0.25:
                return False
            if abs(case.metadata.fov_deg - fov_deg) > 5.0:
                return False
            if (
                image_height_mm is not None
                and abs(_case_image_height_mm(case) - image_height_mm) > 0.35
            ):
                return False
            if n_elements is not None and case.metadata.n_pieces != n_elements:
                return False
            return (
                max_total_track_mm is None
                or case.paraxial.total_track_mm <= max_total_track_mm + 0.20
            )

        exact_aperture_candidates = [case for case in cases if _is_exact_aperture_candidate(case)]
        if not exact_aperture_candidates:
            return None

        def _target_fit_key(case: OpticalSampleData) -> tuple[float, float, float, float, float]:
            assert case.metadata is not None
            return (
                abs(case.paraxial.f_number - fnum),
                abs(case.metadata.computed_efl_mm - efl_mm),
                abs(case.metadata.fov_deg - fov_deg) / 5.0,
                (
                    abs(_case_image_height_mm(case) - image_height_mm)
                    if image_height_mm is not None
                    else 0.0
                ),
                _seed_floor_gap(case) if _seed_floor_gap(case) is not None else math.inf,
            )

        rejected_case = min(exact_aperture_candidates, key=_target_fit_key)
        rejected_floor_gap = _seed_floor_gap(rejected_case)
        if rejected_floor_gap is None or rejected_floor_gap <= selected_floor_gap + 0.75:
            return None

        accepted_tradeoff_ids = ["f_number"]
        if delta_n is not None and abs(delta_n) == 1:
            accepted_tradeoff_ids.append("element_count")
        if priority is not None:
            accepted_tradeoff_ids.append("design_priority")

        selected_field = format_mtf_field_fraction(best.metadata.mtf_max_field_frac)
        rejected_field = format_mtf_field_fraction(rejected_case.metadata.mtf_max_field_frac)
        summary = (
            "performance branch prefers the floor-clean slower-aperture seed over "
            "the exact-aperture seed; aperture and element count require explicit review"
        )
        rationale = [
            (f"selected {best.metadata.case_id} has MTF/RMS floor gap {selected_floor_gap:.3f}"),
            (
                f"exact-aperture candidate {rejected_case.metadata.case_id} has "
                f"MTF/RMS floor gap {rejected_floor_gap:.3f}"
            ),
            (
                f"selected branch is F/{best.paraxial.f_number:.2f} and "
                f"{best.metadata.n_pieces}P versus requested F/{fnum:.2f}"
                + (f" and {n_elements}P" if n_elements is not None else "")
            ),
        ]
        evidence = [
            f"selected floor gap={selected_floor_gap:.3f}; MTF field={selected_field}",
            f"rejected exact-aperture seed={rejected_case.metadata.case_id}",
            f"rejected floor gap={rejected_floor_gap:.3f}; MTF field={rejected_field}",
            f"rejected F/# delta={rejected_case.paraxial.f_number - fnum:+.2f}",
            f"selected F/# delta={delta_fnum:+.2f}",
        ]
        promotion_requirements = [
            "record an explicit F-number / element-count waiver for the floor-clean branch",
            "or ingest a floor-clean 5P/F1.8-ish visible-light seed and rerun fixed eval",
            "keep the protected full-field recovery branch replay-gated before payload mutation",
        ]
        forbidden_claims = [
            f"claiming F/{fnum:.2f} compliance from a F/{best.paraxial.f_number:.2f} seed",
            (
                f"claiming {n_elements}P compliance from a {best.metadata.n_pieces}P seed"
                if n_elements is not None
                else "claiming exact element-count compliance without checking the selected seed"
            ),
            "claiming the exact-aperture seed was preferred despite its MTF/RMS floor gap",
        ]
        return _PerformanceApertureTradeoffResolution(
            status="waiver_required",
            selected_case_id=best.metadata.case_id,
            rejected_case_id=rejected_case.metadata.case_id,
            selected_floor_gap=selected_floor_gap,
            rejected_floor_gap=rejected_floor_gap,
            accepted_tradeoff_ids=tuple(dict.fromkeys(accepted_tradeoff_ids)),
            summary=summary,
            rationale=tuple(dict.fromkeys(rationale)),
            evidence=tuple(dict.fromkeys(evidence)),
            promotion_requirements=tuple(dict.fromkeys(promotion_requirements)),
            forbidden_claims=tuple(dict.fromkeys(forbidden_claims)),
        )

    performance_aperture_tradeoff_resolution = _performance_aperture_tradeoff_resolution()

    def _requirement_coverage() -> tuple[RequirementCoverageSummary, list[RequirementCoverageItem]]:
        items: list[RequirementCoverageItem] = []

        def add(
            requirement_id: str,
            label: str,
            status: str,
            priority_level: str,
            target: str,
            actual: str,
            *,
            delta: float | None = None,
            tolerance: float | None = None,
            unit: str | None = None,
            evidence: list[str] | None = None,
            next_action: str | None = None,
        ) -> None:
            items.append(
                RequirementCoverageItem(
                    requirement_id=requirement_id,
                    label=label,
                    status=status,
                    priority=priority_level,
                    target=target,
                    actual=actual,
                    delta=delta,
                    tolerance=tolerance,
                    unit=unit,
                    evidence=[
                        item.strip()
                        for item in dict.fromkeys(evidence or [])
                        if item and item.strip()
                    ][:4],
                    next_action=next_action,
                )
            )

        add(
            "effective_focal_length",
            "Effective focal length",
            _coverage_status(delta_efl, met=0.15, tradeoff=0.25),
            "critical",
            f"{efl_mm:.2f}",
            f"{best.metadata.computed_efl_mm:.2f}",
            delta=delta_efl,
            tolerance=0.25,
            unit="mm",
            evidence=[
                f"weighted score component={weights.get('efl', 0.0):.2f}",
                f"selected seed={best.metadata.case_id}",
            ],
            next_action=(
                "apply protected EFL refinement before promoting the draft"
                if abs(delta_efl) > 0.15
                else None
            ),
        )
        f_number_status = _coverage_status(delta_fnum, met=0.15, tradeoff=0.25)
        f_number_evidence = [
            f"weighted score component={weights.get('fnum', 0.0):.2f}",
            "aperture is evaluated before local tolerance sensitivity",
        ]
        f_number_next_action = (
            "compare aperture tradeoff against tolerance and MTF sensitivity"
            if abs(delta_fnum) > 0.15
            else None
        )
        if delta_fnum <= 0:
            f_number_status = "met"
            f_number_evidence.append(
                "actual aperture is faster than or equal to target; cost/tolerance risk stays in manufacturability review"
            )
            f_number_next_action = None
        elif performance_aperture_tradeoff_resolution is not None:
            f_number_status = "tradeoff"
            f_number_evidence = [
                f_number_evidence[0],
                performance_aperture_tradeoff_resolution.summary,
                performance_aperture_tradeoff_resolution.evidence[1],
                performance_aperture_tradeoff_resolution.evidence[0],
            ]
            f_number_next_action = performance_aperture_tradeoff_resolution.promotion_requirements[
                0
            ]
        add(
            "f_number",
            "F-number",
            f_number_status,
            "critical",
            f"{fnum:.2f}",
            f"{best.paraxial.f_number:.2f}",
            delta=delta_fnum,
            tolerance=0.25,
            evidence=f_number_evidence,
            next_action=f_number_next_action,
        )
        add(
            "field_of_view",
            "Field of view",
            _coverage_status(delta_fov, met=2.0, tradeoff=5.0),
            "critical",
            f"{fov_deg:.1f}",
            f"{best.metadata.fov_deg:.1f}",
            delta=delta_fov,
            tolerance=5.0,
            unit="deg",
            evidence=[
                f"weighted score component={weights.get('fov', 0.0):.2f}",
                f"selected scenario={best.metadata.scenario.value}",
            ],
            next_action=(_fov_alternative_next_action() if abs(delta_fov) > 2.0 else None),
        )
        if (
            fov_spec_consistency is not None
            and fov_spec_consistency.status != "met"
            and abs(delta_fov) > 2.0
        ):
            add(
                "fov_spec_consistency",
                "EFL / image height / FOV consistency",
                fov_spec_consistency.status,
                "critical",
                (
                    f"{fov_deg:.1f} deg from EFL {efl_mm:.2f} mm / "
                    f"image height {image_height_mm:.2f} mm"
                ),
                f"first-order {fov_spec_consistency.first_order_fov_deg:.1f} deg",
                delta=fov_spec_consistency.delta_fov_deg,
                tolerance=2.0,
                unit="deg",
                evidence=list(fov_spec_consistency.evidence),
                next_action=fov_spec_consistency.next_action,
            )
        if image_height_mm is not None:
            assert delta_imh is not None
            add(
                "image_height",
                "Image height",
                _coverage_status(delta_imh, met=0.20, tradeoff=0.35),
                "important",
                f"{image_height_mm:.2f}",
                f"{imh:.2f}",
                delta=delta_imh,
                tolerance=0.35,
                unit="mm",
                evidence=[f"weighted score component={weights.get('imh', 0.0):.2f}"],
                next_action=(
                    "re-rank seed family around the requested sensor format"
                    if abs(delta_imh) > 0.20
                    else None
                ),
            )
        if n_elements is not None:
            assert delta_n is not None
            add(
                "element_count",
                "Element count",
                "met" if delta_n == 0 else ("tradeoff" if abs(delta_n) == 1 else "miss"),
                "important",
                f"{n_elements}P",
                f"{best.metadata.n_pieces}P",
                delta=float(delta_n),
                tolerance=0.0,
                unit="pieces",
                evidence=[f"weighted score component={weights.get('nel', 0.0):.2f}"],
                next_action=(
                    "compare cost branch before accepting the extra element count"
                    if delta_n > 0
                    else (
                        "verify whether fewer pieces can keep MTF and distortion acceptable"
                        if delta_n < 0
                        else None
                    )
                ),
            )
        if max_total_track_mm is not None:
            assert delta_ttl is not None
            ttl_status = "met" if delta_ttl <= 0 else ("tradeoff" if delta_ttl <= 0.20 else "miss")
            add(
                "total_track",
                "Total track length",
                ttl_status,
                "critical",
                f"<= {max_total_track_mm:.2f}",
                f"{best.paraxial.total_track_mm:.2f}",
                delta=delta_ttl,
                tolerance=0.0,
                unit="mm",
                evidence=[f"weighted score component={weights.get('ttl', 0.0):.2f}"],
                next_action=(
                    "prioritize the thin branch or re-balance back focal distance"
                    if delta_ttl > 0
                    else None
                ),
            )
        mtf_field = best.metadata.mtf_max_field_frac
        mtf_status = "met" if mtf_field >= 1.0 else ("tradeoff" if mtf_field >= 0.8 else "miss")
        add(
            "mtf_field_evidence",
            "MTF field evidence",
            mtf_status,
            "critical",
            "1.0 field",
            f"{format_mtf_field_fraction(mtf_field)} field",
            delta=mtf_field - 1.0,
            tolerance=0.0,
            evidence=[
                "full-field MTF is required before production-ready or edge-performance claims",
                f"seed MTF max field={format_mtf_field_fraction(mtf_field)}",
            ],
            next_action=(
                "recover full-field ray stability or use a full-field fallback seed"
                if mtf_field < 1.0
                else None
            ),
        )
        if priority is not None:
            priority_status = "met"
            priority_evidence = [f"scoring priority={p}"]
            priority_next_action: str | None = None
            if cost_like:
                cost_branch_reviewed = (
                    candidate_proxy_branch_resolution is not None
                    and candidate_proxy_branch_resolution.status == "rejected_for_target_fit"
                )
                priority_status = (
                    "met"
                    if best.metadata.case_id == cost_seed.metadata.case_id or cost_branch_reviewed
                    else "tradeoff"
                )
                priority_evidence.append(
                    f"cost branch={cost_seed.metadata.case_id}/{cost_seed.metadata.n_pieces}P"
                )
                if cost_branch_reviewed:
                    priority_evidence.extend(
                        [
                            candidate_proxy_branch_resolution.summary,
                            *candidate_proxy_branch_resolution.blockers[:2],
                        ]
                    )
                priority_next_action = (
                    "compare selected seed against the cost branch before accepting extra pieces"
                    if priority_status == "tradeoff"
                    else None
                )
            elif performance_like:
                priority_status = (
                    "met"
                    if best.metadata.case_id == performance_seed.metadata.case_id
                    and best.metadata.mtf_max_field_frac >= 1.0
                    else "tradeoff"
                )
                priority_evidence.append(
                    f"performance branch={performance_seed.metadata.case_id}/MTF "
                    f"{format_mtf_field_fraction(performance_seed.metadata.mtf_max_field_frac)} field"
                )
                priority_next_action = (
                    "compare selected seed against the performance branch and full-field MTF gate"
                    if priority_status == "tradeoff"
                    else None
                )
            add(
                "design_priority",
                "Design priority",
                priority_status,
                "important",
                p,
                f"selected {best.metadata.case_id}",
                evidence=priority_evidence,
                next_action=priority_next_action,
            )
        if manufacturing_tier is not None:
            if manufacturability_review.status == "pass":
                manufacturing_status = "met"
            elif manufacturability_review.status == "warning":
                manufacturing_status = "tradeoff"
            else:
                manufacturing_status = "miss"
            flagged_checks = [
                check
                for check in manufacturability_review.checks
                if check.status in {"warning", "blocker"}
            ]
            add(
                "manufacturing_tier",
                "Manufacturing tier",
                manufacturing_status,
                "context",
                tier or manufacturing_tier,
                f"{manufacturability_review.status} proxy score={manufacturability_review.score:.2f}",
                evidence=[
                    f"scoring tier={tier or manufacturing_tier}",
                    manufacturability_review.summary,
                    *[
                        f"{check.check_id}={check.status}: {check.actual}"
                        for check in flagged_checks[:2]
                    ],
                ],
                next_action=(
                    flagged_checks[0].mitigation
                    if flagged_checks and flagged_checks[0].mitigation is not None
                    else "run full tolerance/yield review before external release"
                ),
            )
        tolerance_check = next(
            (
                check
                for check in manufacturability_review.checks
                if check.check_id == "tolerance_risk_proxy"
            ),
            None,
        )
        if tolerance_check is not None:
            tolerance_status = (
                "met"
                if tolerance_check.status == "pass"
                else ("miss" if tolerance_check.status == "blocker" else "tradeoff")
            )
            add(
                "tolerance_risk",
                "Tolerance risk",
                tolerance_status,
                "context",
                "low first-pass risk preferred",
                tolerance_check.actual,
                evidence=[
                    *tolerance_check.evidence[:3],
                    "proxy only; full Monte-Carlo tolerance remains required before release",
                ],
                next_action=(
                    tolerance_check.mitigation
                    if tolerance_check.mitigation is not None
                    else "carry proxy result into the review package"
                ),
            )
        process_check = next(
            (
                check
                for check in manufacturability_review.checks
                if check.check_id == "process_yield_proxy"
            ),
            None,
        )
        if process_check is not None:
            process_status = (
                "met"
                if process_check.status == "pass"
                else ("miss" if process_check.status == "blocker" else "tradeoff")
            )
            add(
                "process_yield_risk",
                "Process/yield risk",
                process_status,
                "context",
                "low process/yield risk preferred",
                process_check.actual,
                evidence=[
                    *process_check.evidence[:3],
                    "proxy only; supplier process table and yield evidence remain required",
                ],
                next_action=(
                    process_check.mitigation
                    if process_check.mitigation is not None
                    else "carry process proxy result into the review package"
                ),
            )
        if max_weight_g is not None:
            mass_proxy = mass_proxies[best.metadata.case_id]
            mass_delta = mass_proxy.estimated_mass_g - max_weight_g
            if mass_delta <= 0:
                mass_status = "met"
                mass_next_action = "validate measured module mass before release"
            elif mass_proxy.estimated_mass_g <= max_weight_g * 1.25:
                mass_status = "tradeoff"
                mass_next_action = "protect mass reserve or compare lighter seed before review"
            else:
                mass_status = "miss"
                mass_next_action = "select a lighter seed or relax the weight budget"
            add(
                "mass_budget",
                "Mass budget",
                mass_status,
                "context",
                f"<= {max_weight_g:.2f}",
                f"{mass_proxy.estimated_mass_g:.3f} g optical-stack proxy",
                delta=mass_delta,
                tolerance=max_weight_g * 0.25,
                unit="g",
                evidence=[
                    f"envelope diameter={mass_proxy.envelope_diameter_mm:.2f} mm",
                    f"density proxy={mass_proxy.density_g_cm3:.2f} g/cm^3",
                    "excludes sensor/actuator/barrel CAD and measured module mass",
                ],
                next_action=mass_next_action,
            )

        met_count = sum(item.status == "met" for item in items)
        tradeoff_count = sum(item.status == "tradeoff" for item in items)
        miss_count = sum(item.status == "miss" for item in items)
        unscored_count = sum(item.status == "unscored" for item in items)
        if miss_count:
            coverage_status = "blocked"
            summary = (
                f"{miss_count} requirement(s) miss the first-pass tolerance; "
                "resolve before treating the output as a draft"
            )
        elif tradeoff_count or unscored_count:
            coverage_status = "tradeoff"
            summary = (
                f"{met_count} requirement(s) met, {tradeoff_count} tradeoff(s), "
                f"{unscored_count} unscored context item(s)"
            )
        else:
            coverage_status = "met"
            summary = "all scored first-pass requirements are covered by the selected seed"

        return (
            RequirementCoverageSummary(
                status=coverage_status,
                met_count=met_count,
                tradeoff_count=tradeoff_count,
                miss_count=miss_count,
                unscored_count=unscored_count,
                summary=summary,
            ),
            items,
        )

    requirement_coverage_summary, requirement_coverage = _requirement_coverage()

    def _seed_selection_scorecard() -> SeedSelectionScorecard:
        metric_labels = {
            "efl": "Effective focal length",
            "fov": "Field of view",
            "fnum": "F-number",
            "imh": "Image height",
            "nel": "Element count",
            "ttl": "Total track",
            "mass": "Mass budget",
            "quality": "MTF/RMS floor evidence",
        }

        def _metric_target(metric_id: str) -> str:
            if metric_id == "efl":
                return f"{efl_mm:.2f} mm"
            if metric_id == "fov":
                return f"{fov_deg:.1f} deg"
            if metric_id == "fnum":
                return f"F/{fnum:.2f}"
            if metric_id == "imh":
                return f"{image_height_mm:.2f} mm" if image_height_mm is not None else "not fixed"
            if metric_id == "nel":
                return f"{n_elements}P" if n_elements is not None else f"lowest available {n_lo}P"
            if metric_id == "ttl":
                return (
                    f"<= {max_total_track_mm:.2f} mm"
                    if max_total_track_mm is not None
                    else f"shortest available {t_lo:.2f} mm"
                )
            if metric_id == "mass":
                return f"<= {max_weight_g:.2f} g" if max_weight_g is not None else "not fixed"
            if metric_id == "quality":
                return "0-250 lp/mm MTF/RMS floor gap 0.0; prefer 1.0-field evidence"
            return "active scoring metric"

        def _metric_actual(metric_id: str, candidate: OpticalSampleData) -> str:
            assert candidate.metadata is not None
            if metric_id == "efl":
                return f"{candidate.metadata.computed_efl_mm:.2f} mm"
            if metric_id == "fov":
                return f"{candidate.metadata.fov_deg:.1f} deg"
            if metric_id == "fnum":
                return f"F/{candidate.paraxial.f_number:.2f}"
            if metric_id == "imh":
                return f"{_case_image_height_mm(candidate):.2f} mm"
            if metric_id == "nel":
                return f"{candidate.metadata.n_pieces}P"
            if metric_id == "ttl":
                return f"{candidate.paraxial.total_track_mm:.2f} mm"
            if metric_id == "mass":
                proxy = mass_proxies[candidate.metadata.case_id]
                return f"{proxy.estimated_mass_g:.3f} g proxy"
            if metric_id == "quality":
                gap = _seed_floor_gap(candidate)
                gap_label = f"{gap:.3f}" if gap is not None else "missing"
                bands = mtf_multiband_summary(candidate.mtf)
                min_250 = f"; min250 {bands.min_250:.3f}" if bands.min_250 is not None else ""
                return (
                    f"floor gap {gap_label}; "
                    f"{format_mtf_field_fraction(candidate.metadata.mtf_max_field_frac)} field"
                    f"{min_250}"
                )
            return "n/a"

        parts = _distance_parts(best)
        raw_scores: list[tuple[str, float, float, float]] = []
        for metric_id, weight in weights.items():
            normalized_miss = abs(parts.get(metric_id, 0.0))
            contribution = weight * normalized_miss**2
            raw_scores.append((metric_id, weight, normalized_miss, contribution))
        raw_scores.sort(key=lambda item: item[3], reverse=True)
        top_penalty_metric_id = raw_scores[0][0] if raw_scores and raw_scores[0][3] > 0 else None

        metric_scores: list[SeedSelectionMetricScore] = []
        for metric_id, weight, normalized_miss, contribution in raw_scores:
            if metric_id == top_penalty_metric_id and contribution > 0.01:
                metric_status = "dominant"
            elif normalized_miss > 0.15:
                metric_status = "tradeoff"
            else:
                metric_status = "aligned"
            metric_scores.append(
                SeedSelectionMetricScore(
                    metric_id=metric_id,
                    label=metric_labels.get(metric_id, metric_id),
                    weight=round(weight, 4),
                    target=_metric_target(metric_id),
                    actual=_metric_actual(metric_id, best),
                    normalized_miss=round(normalized_miss, 4),
                    contribution=round(contribution, 4),
                    status=metric_status,
                    rationale=(
                        "largest weighted penalty for the selected seed"
                        if metric_status == "dominant"
                        else (
                            "visible scored tradeoff to keep in review"
                            if metric_status == "tradeoff"
                            else "close to the normalized brief"
                        )
                    ),
                )
            )

        accepted_tradeoffs = _unique_strings_in_order(
            [
                f"{item.label}: {item.actual} vs {item.target}"
                for item in requirement_coverage
                if item.status == "tradeoff"
            ]
        )[:6]

        def _dominant_alt_miss(candidate: OpticalSampleData) -> str:
            alt_parts = _distance_parts(candidate)
            scored = [
                (metric_id, weights[metric_id] * abs(alt_parts.get(metric_id, 0.0)) ** 2)
                for metric_id in weights
            ]
            scored.sort(key=lambda item: item[1], reverse=True)
            if not scored or scored[0][1] <= 0:
                return "no dominant miss"
            return metric_labels.get(scored[0][0], scored[0][0])

        rejected_alternatives: list[str] = []
        for candidate in ranked[1:5]:
            assert candidate.metadata is not None
            alt_distance = _case_distance(candidate)
            rejected_alternatives.append(
                f"{candidate.metadata.case_id}: score {_score_from_distance(alt_distance):.3f}, "
                f"distance {alt_distance:.3f}, dominant miss {_dominant_alt_miss(candidate)}"
            )

        if top_penalty_metric_id is None:
            summary = (
                f"{best.metadata.case_id} is the closest real seed with no meaningful "
                "weighted penalty in active metrics"
            )
        else:
            summary = (
                f"{best.metadata.case_id} ranks first with "
                f"{metric_labels.get(top_penalty_metric_id, top_penalty_metric_id)} "
                "as the largest remaining penalty"
            )

        next_action = next(
            (
                item.next_action
                for item in requirement_coverage
                if item.next_action and item.status in {"tradeoff", "miss"}
            ),
            "use this scorecard to review whether the selected seed or a branch should continue",
        )

        return SeedSelectionScorecard(
            selected_case_id=best.metadata.case_id,
            selected_rank=1,
            selected_score=score,
            normalized_distance=distance,
            scoring_profile=(
                f"priority={priority or 'balanced'}; "
                f"manufacturing_tier={manufacturing_tier or 'unspecified'}; "
                f"active_metrics={','.join(weights)}"
            ),
            metric_scores=metric_scores,
            top_penalty_metric_id=top_penalty_metric_id,
            accepted_tradeoffs=accepted_tradeoffs,
            rejected_alternatives=rejected_alternatives[:4],
            summary=summary,
            next_action=next_action,
        )

    seed_selection_scorecard = _seed_selection_scorecard()

    def _candidate_strengths(c: OpticalSampleData, role: str) -> list[str]:
        assert c.metadata is not None
        review_proxy = _candidate_review_proxy(c)
        best_review_proxy = _candidate_review_proxy(best)
        strengths: list[str] = []
        if role == "best_match":
            strengths.append("lowest weighted-distance seed for the request")
        elif role == "cost_variant":
            strengths.append("lowest element-count branch in the allowed family")
        elif role == "thin_variant":
            strengths.append("shortest total-track branch in the allowed family")
        elif role == "performance_variant":
            strengths.append("best full-field MTF branch near the requested aperture")

        if abs(c.metadata.computed_efl_mm - efl_mm) <= 0.15:
            strengths.append("EFL is within 0.15 mm of target")
        if abs(c.metadata.fov_deg - fov_deg) <= 2.0:
            strengths.append("FOV is within 2 deg of target")
        if abs(c.paraxial.f_number - fnum) <= 0.15:
            strengths.append("F/# is close to target")
        if image_height_mm is not None and abs(_case_image_height_mm(c) - image_height_mm) <= 0.2:
            strengths.append("image height matches the sensor class")
        if n_elements is not None and c.metadata.n_pieces == n_elements:
            strengths.append("element count matches the request")
        if max_total_track_mm is not None and c.paraxial.total_track_mm <= max_total_track_mm:
            strengths.append("TTL stays inside the requested ceiling")
        if review_proxy.tolerance_risk_level == "low":
            strengths.append("low first-pass tolerance risk")
        if review_proxy.process_yield_level == "low":
            strengths.append("low process/yield risk proxy")
        elif review_proxy.process_yield_score < best_review_proxy.process_yield_score:
            strengths.append("lower process/yield risk than the selected seed")
        if c.metadata.mtf_max_field_frac >= 1.0:
            strengths.append("full-field MTF evaluation is available")
        return strengths[:3] or ["usable real production seed"]

    def _candidate_tradeoffs(c: OpticalSampleData) -> list[str]:
        assert c.metadata is not None
        review_proxy = _candidate_review_proxy(c)
        tradeoffs: list[str] = []
        d_efl = c.metadata.computed_efl_mm - efl_mm
        d_fnum = c.paraxial.f_number - fnum
        d_fov = c.metadata.fov_deg - fov_deg
        d_imh = _case_image_height_mm(c) - image_height_mm if image_height_mm is not None else None
        d_n = c.metadata.n_pieces - n_elements if n_elements is not None else None
        d_ttl = (
            c.paraxial.total_track_mm - max_total_track_mm
            if max_total_track_mm is not None
            else None
        )

        if abs(d_efl) > 0.25:
            tradeoffs.append(f"EFL differs by {d_efl:+.2f} mm")
        if d_fnum > 0.2:
            tradeoffs.append(f"aperture is slower by {d_fnum:+.2f} F/#")
        elif d_fnum < -0.3:
            tradeoffs.append("brighter aperture raises tolerance sensitivity")
        if abs(d_fov) > 3.0:
            tradeoffs.append(f"FOV differs by {d_fov:+.1f} deg")
        if d_imh is not None and abs(d_imh) > 0.3:
            tradeoffs.append(f"image height differs by {d_imh:+.2f} mm")
        if d_n is not None and d_n != 0:
            tradeoffs.append(f"element count differs by {d_n:+d}")
        if d_ttl is not None and d_ttl > 0:
            tradeoffs.append(f"TTL exceeds ceiling by {d_ttl:+.2f} mm")
        if c.metadata.mtf_max_field_frac < 1.0:
            tradeoffs.append(
                f"MTF only reached {format_mtf_field_fraction(c.metadata.mtf_max_field_frac)} field"
            )
        if review_proxy.tolerance_risk_level != "low":
            tradeoffs.append(
                f"{review_proxy.tolerance_risk_level} tolerance risk proxy "
                f"({review_proxy.tolerance_risk_score:.2f})"
            )
        if review_proxy.process_yield_level != "low":
            tradeoffs.append(
                f"{review_proxy.process_yield_level} process/yield risk proxy "
                f"({review_proxy.process_yield_score:.2f})"
            )
        if max_weight_g is not None:
            mass = mass_proxies[c.metadata.case_id].estimated_mass_g
            if mass > max_weight_g:
                tradeoffs.append(f"mass proxy exceeds budget by {mass - max_weight_g:+.3f} g")
            else:
                tradeoffs.append(f"mass proxy leaves {max_weight_g - mass:.3f} g reserve")
        return tradeoffs[:3] or ["no major first-order mismatch against the request"]

    def _candidate_comparison(c: OpticalSampleData, role: str) -> CandidateComparison:
        assert c.metadata is not None
        candidate_distance = _case_distance(c)
        review_proxy = _candidate_review_proxy(c)
        return CandidateComparison(
            case_id=c.metadata.case_id,
            role=role,
            score=_score_from_distance(candidate_distance),
            normalized_distance=candidate_distance,
            scenario=c.metadata.scenario,
            efl_mm=c.metadata.computed_efl_mm,
            f_number=c.paraxial.f_number,
            fov_deg=c.metadata.fov_deg,
            image_height_mm=_case_image_height_mm(c),
            total_track_mm=c.paraxial.total_track_mm,
            n_pieces=c.metadata.n_pieces,
            mtf_max_field_frac=c.metadata.mtf_max_field_frac,
            tolerance_risk_score=review_proxy.tolerance_risk_score,
            tolerance_risk_level=review_proxy.tolerance_risk_level,
            process_yield_score=review_proxy.process_yield_score,
            process_yield_level=review_proxy.process_yield_level,
            mass_proxy_g=review_proxy.mass_proxy_g,
            review_proxy_notes=list(review_proxy.notes),
            strengths=_candidate_strengths(c, role),
            tradeoffs=_candidate_tradeoffs(c),
        )

    candidate_comparison = [
        _candidate_comparison(candidate, role) for candidate, role in selected_candidates
    ]

    if lightweight_design_assessment:
        selected_floor_gap = _seed_floor_gap(best)

        def _lightweight_next_steps() -> list[str]:
            steps: list[str] = []
            if selected_floor_gap is None or selected_floor_gap > 0:
                steps.append(
                    "recover the first-pass MTF/RMS floor before treating this seed as draft-ready"
                )
            elif best.metadata.mtf_max_field_frac < 1.0:
                steps.append(
                    "close 1.0-field MTF evidence before making full-field edge-performance claims"
                )
            if requirement_coverage_summary.status != "met":
                steps.append(requirement_coverage_summary.summary)
            if abs(delta_fnum) > 0.25:
                steps.append("record the F-number tradeoff before promoting the selected seed")
            if delta_n is not None and delta_n != 0:
                steps.append("record the element-count tradeoff before promoting the selected seed")
            steps.append(
                "rerun with analysis_depth='full' for protected optimizer and replay-gate evidence"
            )
            return _unique_strings_in_order(steps)[:5]

        lightweight_rationale = _unique_strings_in_order(
            [
                *rationale,
                (
                    "seed-only lightweight assessment skipped protected optimizer and replay "
                    "gates; use analysis_depth='full' for mutation evidence"
                ),
            ]
        )
        assessment = DesignAssessment(
            matched_case_id=best.metadata.case_id,
            score=score,
            normalized_distance=distance,
            seed_selection_scorecard=seed_selection_scorecard,
            target_focal_length_mm=efl_mm,
            target_f_number=fnum,
            target_fov_deg=fov_deg,
            target_image_height_mm=image_height_mm,
            target_n_elements=n_elements,
            target_total_track_mm=max_total_track_mm,
            priority=priority,
            manufacturing_tier=manufacturing_tier,
            delta_efl_mm=delta_efl,
            delta_f_number=delta_fnum,
            delta_fov_deg=delta_fov,
            delta_image_height_mm=delta_imh,
            delta_n_elements=delta_n,
            delta_total_track_mm=delta_ttl,
            warnings=warnings_out,
            rationale=lightweight_rationale,
            candidate_comparison=candidate_comparison,
            requirement_coverage_summary=requirement_coverage_summary,
            requirement_coverage=requirement_coverage,
            manufacturability_review=manufacturability_review,
            next_steps=_lightweight_next_steps(),
            recommended_candidate_id="seed-baseline",
        )
        return best.model_copy(update={"design_assessment": assessment}, deep=True)

    before_rms_values = [
        value for value in best.mtf.rms_spot_radius_um_by_field if math.isfinite(value)
    ]
    before_mtf_bands = mtf_multiband_summary(best.mtf)
    seed_baseline_metrics = OptimizationMetricSnapshot(
        effective_focal_length_mm=best.metadata.computed_efl_mm,
        f_number=best.paraxial.f_number,
        total_track_mm=best.paraxial.total_track_mm,
        mtf_max_field_frac=best.metadata.mtf_max_field_frac,
        mtf_50lpmm_min=before_mtf_bands.min_50,
        mtf_50lpmm_avg=before_mtf_bands.avg_50,
        mtf_100lpmm_min=before_mtf_bands.min_100,
        mtf_100lpmm_avg=before_mtf_bands.avg_100,
        mtf_150lpmm_min=before_mtf_bands.min_150,
        mtf_150lpmm_avg=before_mtf_bands.avg_150,
        mtf_200lpmm_min=before_mtf_bands.min_200,
        mtf_200lpmm_avg=before_mtf_bands.avg_200,
        mtf_250lpmm_min=before_mtf_bands.min_250,
        mtf_250lpmm_avg=before_mtf_bands.avg_250,
        mtf_multiband_min_score=before_mtf_bands.multiband_min_score,
        mtf_field_weighted_score=before_mtf_bands.field_weighted_score,
        max_rms_spot_radius_um=max(before_rms_values) if before_rms_values else None,
    )
    optimization_attempt = protected_efl_refinement(
        best.metadata.source_zmx,
        best.metadata.fov_deg,
        efl_mm,
        max_total_track_mm,
        before_mtf_max_field_frac=best.metadata.mtf_max_field_frac,
        before_mtf_bands=before_mtf_bands,
        before_max_rms_spot_radius_um=max(before_rms_values) if before_rms_values else None,
    )
    rationale.append(f"ran protected local optimizer probe: {optimization_attempt.status}")
    if optimization_attempt.verification is not None:
        rationale.append(
            f"optimizer verification gate returned {optimization_attempt.verification.status}"
        )
    efl_gate_probeable = (
        optimization_attempt.verification is not None
        and optimization_attempt.verification.status in {"passed", "warning"}
        and optimization_attempt.verification.ray_trace_ok
        and optimization_attempt.verification.mtf_ok
    )
    merit_probe_radius_changes = (
        tuple(
            (change.surface_index, change.after)
            for change in optimization_attempt.variable_changes
            if change.variable == "radius"
        )
        if efl_gate_probeable
        else ()
    )
    merit_probe_before = (
        optimization_attempt.after_metrics if efl_gate_probeable else seed_baseline_metrics
    )
    merit_probe_recovery_objective = _image_quality_recovery_objective(merit_probe_before)
    merit_probe_variable_priority = (
        tuple(merit_probe_recovery_objective.variables)
        if merit_probe_recovery_objective.dominant_component != "none"
        and merit_probe_recovery_objective.normalized_gap is not None
        and merit_probe_recovery_objective.normalized_gap > 0.0
        else ()
    )
    merit_optimization_probe = protected_rms_merit_probe(
        source_zmx=best.metadata.source_zmx,
        nominal_fov_deg=best.metadata.fov_deg,
        target_efl_mm=efl_mm,
        max_total_track_mm=max_total_track_mm,
        radius_changes=merit_probe_radius_changes,
        before_effective_focal_length_mm=(
            merit_probe_before.effective_focal_length_mm if merit_probe_before else None
        ),
        before_f_number=merit_probe_before.f_number if merit_probe_before else None,
        before_total_track_mm=merit_probe_before.total_track_mm if merit_probe_before else None,
        before_mtf_max_field_frac=(
            merit_probe_before.mtf_max_field_frac if merit_probe_before else None
        ),
        before_mtf_bands=mtf_bands_from_snapshot(merit_probe_before),
        before_max_rms_spot_radius_um=(
            merit_probe_before.max_rms_spot_radius_um if merit_probe_before else None
        ),
        variable_priority=merit_probe_variable_priority,
        probe_purpose=(
            "image_quality_floor_recovery" if merit_probe_variable_priority else "rms_merit"
        ),
    )
    rationale.append(f"ran protected RMS merit probe: {merit_optimization_probe.status}")
    floor_gap_recovery_trial = (
        _best_floor_gap_trial(merit_optimization_probe)
        if merit_optimization_probe.probe_purpose == "image_quality_floor_recovery"
        else None
    )
    guarded_asphere_candidates = [
        candidate
        for candidate in merit_optimization_probe.variable_candidates
        if candidate.variable == "asphere_coefficient"
        and candidate.status == "audited_only"
        and candidate.manufacturability_status == "guarded"
    ]
    needs_asphere_guarded_audit = merit_optimization_probe.status == "warning" and bool(
        guarded_asphere_candidates
    )

    def _unique_in_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out

    def _trial_label(trial: OptimizationVariableTrial) -> str:
        label = f"{trial.variable} S{trial.surface_index}"
        if trial.coefficient_index is not None:
            label = f"{label}:c{trial.coefficient_index}"
        return label

    def _prioritize_seed_gap_evidence(values: list[str]) -> list[str]:
        unique_values = _unique_in_order(values)
        near_misses = [item for item in unique_values if item.startswith("near miss")]
        supporting_context = [item for item in unique_values if not item.startswith("near miss")]
        return [*near_misses, *supporting_context]

    def _build_full_field_recovery_diagnostic() -> FullFieldRecoveryDiagnostic | None:
        gate = optimization_attempt.verification
        gate_status = gate.status if gate is not None else "not_run"
        seed_field = best.metadata.mtf_max_field_frac
        gate_field = gate.mtf_max_field_frac if gate is not None else None
        merit_gate = merit_optimization_probe.verification
        merit_field = merit_gate.mtf_max_field_frac if merit_gate is not None else None
        needs_full_field = seed_field < 1.0 or gate_status == "warning"
        if not needs_full_field:
            return None

        branch_fields = [
            ("seed-baseline", seed_field),
            ("optimizer-proposal", gate_field),
            ("merit-probe", merit_field),
        ]
        stable_branch, current_field = max(
            ((name, value) for name, value in branch_fields if value is not None),
            key=lambda item: item[1],
            default=("seed-baseline", None),
        )
        field_gap = 1.0 - current_field if current_field is not None else None
        if field_gap is not None:
            field_gap = max(0.0, field_gap)

        trials = merit_optimization_probe.candidate_trials
        local_variable_families = _unique_in_order([trial.variable for trial in trials])
        rejected_trial_count = sum(
            1 for trial in trials if trial.status in {"rejected", "failed", "skipped"}
        )
        rms_deltas = [
            trial.rms_improvement_um
            for trial in trials
            if trial.rms_improvement_um is not None and math.isfinite(trial.rms_improvement_um)
        ]
        best_partial_rms_delta = merit_optimization_probe.rms_improvement_um
        if best_partial_rms_delta is None:
            best_partial_rms_delta = max(rms_deltas) if rms_deltas else None
        recovery_trials = list(
            protected_full_field_recovery_probe(
                best.metadata.source_zmx,
                best.metadata.fov_deg,
                max_total_track_mm,
                best.metadata.computed_efl_mm,
                best.paraxial.total_track_mm,
                seed_field,
                max(before_rms_values) if before_rms_values else None,
            )
        )
        edge_field_scan = list(
            protected_edge_field_stability_scan(
                best.metadata.source_zmx,
                best.metadata.fov_deg,
            )
        )
        highest_scanned_stable_field: float | None = None
        edge_field_cliff: float | None = None
        for point in edge_field_scan:
            if point.status == "pass":
                highest_scanned_stable_field = point.field_frac
                continue
            edge_field_cliff = point.field_frac
            break
        recovery_rank = {"recovered": 4, "improved": 3, "rejected": 2, "skipped": 1, "failed": 0}
        best_recovery_trial = max(
            recovery_trials,
            key=lambda trial: (
                recovery_rank.get(trial.status, 0),
                trial.mtf_max_field_frac if trial.mtf_max_field_frac is not None else -math.inf,
                -(
                    trial.image_quality_floor_gap_score
                    if trial.image_quality_floor_gap_score is not None
                    else math.inf
                ),
                trial.rms_delta_um if trial.rms_delta_um is not None else -math.inf,
            ),
            default=None,
        )

        verification_failed = (
            gate is None
            or gate_status in {"failed", "not_run"}
            or not (gate.ray_trace_ok and gate.mtf_ok)
        )
        failure_mode = (
            "verification_failure" if verification_failed else "partial_field_stability_gap"
        )
        if current_field is not None and current_field < 0.9:
            recommended_family = "chief-ray aiming + stop position before asphere optimization"
            next_action = (
                "recover 0.9/1.0 field ray aiming with chief-ray and stop-position "
                "variables before applying local radius/asphere changes"
            )
        elif current_field is not None and current_field < 1.0:
            recommended_family = "edge-field ray aiming + stop-position solve"
            next_action = (
                "close the remaining edge-field MTF gap, then rerun protected local "
                "merit trials under the full-field gate"
            )
        else:
            recommended_family = "verification gate cleanup"
            next_action = "make the verification gate clean before promoting the branch"
        if best_recovery_trial is not None and best_recovery_trial.status == "recovered":
            if best_recovery_trial.variable_family == "compound_field_extension":
                if (
                    best_recovery_trial.image_quality_floor_gap_score is not None
                    and best_recovery_trial.image_quality_floor_gap_score <= 0.0
                ):
                    recommended_family = "floor-clean compound field-extension replay"
                    next_action = (
                        "convert the floor-clean compound field-extension branch into "
                        "a protected recovery candidate, then review aperture and "
                        "element-count tradeoffs"
                    )
                else:
                    recommended_family = "compound field-extension replay"
                    next_action = (
                        "replay the compound field-extension branch, then keep MTF/RMS "
                        "floor recovery gated until the full quality floor clears"
                    )
            else:
                recommended_family = best_recovery_trial.variable_family
                next_action = "replay the recovered full-field branch under the MTF/RMS floor gate"

        evidence = [
            (f"stable MTF field={format_mtf_field_fraction(current_field)}; target=1.0"),
            f"stable branch={stable_branch}",
            f"optimizer gate={gate_status}",
        ]
        if field_gap is not None:
            evidence.append(f"field gap={field_gap:.2f}")
        if local_variable_families:
            evidence.append("tested local variable families=" + ", ".join(local_variable_families))
        if rejected_trial_count:
            evidence.append(f"non-promoted local trials={rejected_trial_count}")
        if best_partial_rms_delta is not None:
            evidence.append(f"best partial RMS delta={best_partial_rms_delta:+.2f}um")
        if best_recovery_trial is not None:
            evidence.append(
                f"best recovery trial={best_recovery_trial.variable_family} "
                f"S{best_recovery_trial.surface_index} {best_recovery_trial.status}"
            )
            if best_recovery_trial.rms_delta_um is not None:
                evidence.append(
                    f"best recovery RMS delta={best_recovery_trial.rms_delta_um:+.2f}um"
                )
            if best_recovery_trial.mtf_max_field_frac is not None:
                evidence.append(
                    "best recovery field="
                    f"{format_mtf_field_fraction(best_recovery_trial.mtf_max_field_frac)}"
                )
            if best_recovery_trial.image_quality_floor_gap_score is not None:
                evidence.append(
                    "best recovery floor gap="
                    f"{best_recovery_trial.image_quality_floor_gap_score:.3f}"
                )
            if best_recovery_trial.metrics is not None:
                metrics = best_recovery_trial.metrics
                if (
                    metrics.mtf_multiband_min_score is not None
                    and metrics.mtf_field_weighted_score is not None
                    and metrics.max_rms_spot_radius_um is not None
                ):
                    evidence.append(
                        "best recovery MTF/RMS="
                        f"min {metrics.mtf_multiband_min_score:.3f}; "
                        f"weighted {metrics.mtf_field_weighted_score:.3f}; "
                        f"RMS {metrics.max_rms_spot_radius_um:.2f}um"
                    )
        if edge_field_scan:
            scan_summary = ", ".join(
                f"{format_mtf_field_fraction(point.field_frac)}:{point.status}"
                for point in edge_field_scan
            )
            evidence.append(f"edge-field scan={scan_summary}")
        if highest_scanned_stable_field is not None:
            evidence.append(
                "highest scanned stable field="
                f"{format_mtf_field_fraction(highest_scanned_stable_field)}"
            )
        if edge_field_cliff is not None:
            evidence.append(
                f"edge-field cliff starts at {format_mtf_field_fraction(edge_field_cliff)}"
            )
        if any(trial.variable == "asphere_coefficient" for trial in trials):
            evidence.append("asphere coefficient trials remain audit-only until full-field passes")

        return FullFieldRecoveryDiagnostic(
            status="warning",
            failure_mode=failure_mode,
            current_field_frac=current_field,
            field_gap=field_gap,
            stable_branch=stable_branch,
            local_variable_families_tested=local_variable_families,
            rejected_trial_count=rejected_trial_count,
            best_partial_rms_delta_um=best_partial_rms_delta,
            recovery_trials=recovery_trials,
            best_recovery_trial=best_recovery_trial,
            edge_field_scan=edge_field_scan,
            highest_scanned_stable_field_frac=highest_scanned_stable_field,
            edge_field_cliff_frac=edge_field_cliff,
            recommended_variable_family=recommended_family,
            next_action=next_action,
            evidence=_unique_in_order(evidence),
        )

    full_field_recovery_diagnostic = _build_full_field_recovery_diagnostic()

    def _floor_clean_full_field_recovery_trial() -> FullFieldRecoveryTrial | None:
        trial = (
            full_field_recovery_diagnostic.best_recovery_trial
            if full_field_recovery_diagnostic is not None
            else None
        )
        if (
            trial is not None
            and trial.variable_family == "compound_field_extension"
            and trial.status == "recovered"
            and trial.mtf_max_field_frac is not None
            and trial.mtf_max_field_frac >= 1.0
            and trial.image_quality_floor_gap_score is not None
            and trial.image_quality_floor_gap_score <= 0.0
            and trial.metrics is not None
            and trial.variable_changes
        ):
            return trial
        return None

    def _edge_stability_stats(
        case: OpticalSampleData,
    ) -> tuple[float | None, float | None]:
        assert case.metadata is not None
        if (
            case.metadata.case_id == best.metadata.case_id
            and full_field_recovery_diagnostic is not None
        ):
            return (
                full_field_recovery_diagnostic.highest_scanned_stable_field_frac,
                full_field_recovery_diagnostic.edge_field_cliff_frac,
            )
        scan = protected_edge_field_stability_scan(
            case.metadata.source_zmx,
            case.metadata.fov_deg,
        )
        highest_stable: float | None = None
        first_cliff: float | None = None
        for point in scan:
            if point.status == "pass":
                highest_stable = point.field_frac
                continue
            first_cliff = point.field_frac
            break
        return highest_stable, first_cliff

    def _build_library_coverage_diagnostic() -> LibraryCoverageDiagnostic | None:
        if fov_deg < _ULTRAWIDE_FOV_MIN:
            return None
        full_field_cases = [
            c for c in cases if c.metadata is not None and c.metadata.mtf_max_field_frac >= 1.0
        ]
        high_fov_cases = [
            c for c in cases if c.metadata is not None and c.metadata.fov_deg >= _ULTRAWIDE_FOV_MIN
        ]
        high_fov_full_field_cases = [
            c for c in high_fov_cases if c.metadata and c.metadata.mtf_max_field_frac >= 1.0
        ]
        nearest_full_field = min(
            full_field_cases,
            key=lambda c: abs(c.metadata.fov_deg - fov_deg),
            default=None,
        )
        nearest_high_fov = min(
            high_fov_cases,
            key=lambda c: abs(c.metadata.fov_deg - fov_deg),
            default=None,
        )
        high_fov_full_field_available = bool(high_fov_full_field_cases)
        full_field_gap = (
            fov_deg - nearest_full_field.metadata.fov_deg
            if nearest_full_field is not None and nearest_full_field.metadata is not None
            else None
        )
        status = "covered" if high_fov_full_field_available else "gap"
        if status == "covered":
            strategy = "continue from the high-FOV full-field seed and keep local promotion gated"
        else:
            nearest_full_fov = (
                nearest_full_field.metadata.fov_deg
                if nearest_full_field is not None and nearest_full_field.metadata is not None
                else None
            )
            strategy = (
                "add or ingest a full-field high-FOV seed before claiming edge performance; "
                f"otherwise relax FOV toward {nearest_full_fov:.1f} deg or label the draft partial-field only"
                if nearest_full_fov is not None
                else "add or ingest a full-field high-FOV seed before claiming edge performance"
            )
        evidence: list[str] = [
            f"target FOV={fov_deg:.1f} deg",
            f"full-field high-FOV seeds={len(high_fov_full_field_cases)}",
            f"partial high-FOV seeds={len([c for c in high_fov_cases if c.metadata and c.metadata.mtf_max_field_frac < 1.0])}",
        ]
        if nearest_full_field is not None and nearest_full_field.metadata is not None:
            evidence.append(
                f"nearest full-field seed={nearest_full_field.metadata.case_id} "
                f"FOV={nearest_full_field.metadata.fov_deg:.1f}"
            )
        if nearest_high_fov is not None and nearest_high_fov.metadata is not None:
            evidence.append(
                f"nearest high-FOV seed={nearest_high_fov.metadata.case_id} "
                f"MTF field={format_mtf_field_fraction(nearest_high_fov.metadata.mtf_max_field_frac)}"
            )
        if full_field_gap is not None:
            evidence.append(f"full-field FOV gap={full_field_gap:+.1f} deg")
        return LibraryCoverageDiagnostic(
            status=status,
            target_fov_deg=fov_deg,
            high_fov_full_field_available=high_fov_full_field_available,
            nearest_full_field_case_id=(
                nearest_full_field.metadata.case_id
                if nearest_full_field is not None and nearest_full_field.metadata is not None
                else None
            ),
            nearest_full_field_fov_deg=(
                nearest_full_field.metadata.fov_deg
                if nearest_full_field is not None and nearest_full_field.metadata is not None
                else None
            ),
            full_field_fov_gap_deg=full_field_gap,
            nearest_high_fov_case_id=(
                nearest_high_fov.metadata.case_id
                if nearest_high_fov is not None and nearest_high_fov.metadata is not None
                else None
            ),
            nearest_high_fov_mtf_field_frac=(
                nearest_high_fov.metadata.mtf_max_field_frac
                if nearest_high_fov is not None and nearest_high_fov.metadata is not None
                else None
            ),
            recommended_strategy=strategy,
            evidence=evidence,
        )

    library_coverage_diagnostic = _build_library_coverage_diagnostic()

    def _build_design_strategy_decision() -> DesignStrategyDecision | None:
        if library_coverage_diagnostic is None or library_coverage_diagnostic.status != "gap":
            return None

        provable_fov = library_coverage_diagnostic.nearest_full_field_fov_deg
        fov_gap = library_coverage_diagnostic.full_field_fov_gap_deg
        partial_candidate_id = best.metadata.case_id
        partial_fov = best.metadata.fov_deg
        partial_field = best.metadata.mtf_max_field_frac
        current_edge_stable_field = (
            full_field_recovery_diagnostic.highest_scanned_stable_field_frac
            if full_field_recovery_diagnostic is not None
            and full_field_recovery_diagnostic.highest_scanned_stable_field_frac is not None
            else partial_field
        )
        sibling_edge_candidates: list[tuple[OpticalSampleData, float, float | None]] = []
        if current_edge_stable_field is not None:
            for case in cases:
                if (
                    case.metadata is None
                    or case.metadata.case_id == best.metadata.case_id
                    or case.metadata.mtf_max_field_frac >= 1.0
                    or case.metadata.fov_deg < _ULTRAWIDE_FOV_MIN
                    or abs(case.metadata.fov_deg - best.metadata.fov_deg) > 1.0
                    or abs(case.metadata.computed_efl_mm - best.metadata.computed_efl_mm) > 0.08
                    or abs(case.paraxial.f_number - best.paraxial.f_number) > 0.15
                    or case.metadata.n_pieces != best.metadata.n_pieces
                ):
                    continue
                stable_field, cliff_field = _edge_stability_stats(case)
                if stable_field is not None and stable_field > current_edge_stable_field + 1e-6:
                    sibling_edge_candidates.append((case, stable_field, cliff_field))
        stable_sibling_case: OpticalSampleData | None = None
        stable_sibling_field: float | None = None
        stable_sibling_cliff: float | None = None
        if sibling_edge_candidates:
            stable_sibling_case, stable_sibling_field, stable_sibling_cliff = max(
                sibling_edge_candidates,
                key=lambda item: (
                    item[1],
                    -abs(item[0].metadata.fov_deg - fov_deg),
                    -_case_distance(item[0]),
                ),
            )
        near_threshold_partial_case = min(
            (
                case
                for case in cases
                if case.metadata is not None
                and case.metadata.case_id != library_coverage_diagnostic.nearest_high_fov_case_id
                and case.metadata.fov_deg >= _ULTRAWIDE_FOV_MIN - 1.0
                and case.metadata.fov_deg < fov_deg
                and case.metadata.mtf_max_field_frac < 1.0
                and case.metadata.mtf_max_field_frac >= 0.9
            ),
            key=lambda case: abs(case.metadata.fov_deg - fov_deg),
            default=None,
        )
        selected = "add_full_field_high_fov_seed"
        rationale = [
            "current library has no high-FOV seed with full-field MTF evidence",
            f"target FOV={fov_deg:.1f} deg",
            (
                f"nearest full-field seed proves {provable_fov:.1f} deg"
                if provable_fov is not None
                else "no full-field seed is available for a nearby FOV"
            ),
            (
                "protected recovery replay still stops at "
                f"{format_mtf_field_fraction(full_field_recovery_diagnostic.current_field_frac)} field"
                if full_field_recovery_diagnostic is not None
                and full_field_recovery_diagnostic.current_field_frac is not None
                else "full-field recovery replay has not produced 1.0-field evidence"
            ),
        ]
        if (
            stable_sibling_case is not None
            and stable_sibling_case.metadata is not None
            and stable_sibling_field is not None
        ):
            rationale.append(
                "more stable high-FOV sibling exists: "
                f"{stable_sibling_case.metadata.case_id} reaches "
                f"{format_mtf_field_fraction(stable_sibling_field)} field"
            )
        if (
            near_threshold_partial_case is not None
            and near_threshold_partial_case.metadata is not None
        ):
            rationale.append(
                "near-threshold partial-field fallback exists: "
                f"{near_threshold_partial_case.metadata.case_id} at "
                f"{near_threshold_partial_case.metadata.fov_deg:.1f} deg / "
                f"{format_mtf_field_fraction(near_threshold_partial_case.metadata.mtf_max_field_frac)} field"
            )
        primary_tradeoff = (
            "add_full_field_high_fov_seed: preserves the requested FOV and enables a "
            "full-field performance claim, but depends on new reference data"
        )
        stable_sibling_tradeoff = (
            (
                "stable_partial_field_sibling_seed: keep high-FOV geometry and improve "
                "the scanned edge-field limit from "
                f"{format_mtf_field_fraction(current_edge_stable_field)} to "
                f"{format_mtf_field_fraction(stable_sibling_field)} field, but still no "
                "full-field approval"
            )
            if stable_sibling_case is not None
            and stable_sibling_case.metadata is not None
            and stable_sibling_field is not None
            and current_edge_stable_field is not None
            else None
        )
        near_threshold_tradeoff = (
            (
                "near_threshold_partial_field_seed: trade down to "
                f"{near_threshold_partial_case.metadata.fov_deg:.1f} deg and "
                f"{format_mtf_field_fraction(near_threshold_partial_case.metadata.mtf_max_field_frac)} field; "
                "useful for intermediate review but still not a full-field approval"
            )
            if near_threshold_partial_case is not None
            and near_threshold_partial_case.metadata is not None
            else None
        )
        relaxed_tradeoff = (
            f"relax_fov_to_full_field_seed: move toward {provable_fov:.1f} deg full-field "
            f"evidence and give up about {fov_gap:.1f} deg FOV"
            if provable_fov is not None and fov_gap is not None
            else "relax_fov_to_full_field_seed: use the closest full-field seed as the spec target"
        )
        partial_tradeoff = (
            f"partial_field_high_fov_draft: keep {partial_fov:.1f} deg geometry, "
            f"but label evidence as {format_mtf_field_fraction(partial_field)} field only"
            if partial_field is not None
            else f"partial_field_high_fov_draft: keep {partial_fov:.1f} deg geometry with incomplete field evidence"
        )
        primary_required_evidence = "ingest at least one >=85 deg visible-light seed with finite ray trace and MTF at 1.0 field"
        stable_sibling_required_evidence = (
            "review the more edge-stable high-FOV sibling as a partial-field trade study; "
            "keep 1.0-field claims forbidden"
            if stable_sibling_case is not None
            else None
        )
        near_threshold_required_evidence = (
            "review the near-threshold partial-field seed as an intermediate "
            "trade study while keeping full-field claims forbidden"
            if near_threshold_partial_case is not None
            else None
        )
        relaxed_required_evidence = (
            f"explicitly relax target FOV toward {provable_fov:.1f} deg and regenerate from the nearest full-field seed"
            if provable_fov is not None
            else "explicitly relax target FOV to a full-field-covered seed"
        )
        partial_required_evidence = (
            "keep the high-FOV branch marked as partial-field only in UI, PDF, and task queue"
        )
        tradeoffs = _unique_in_order(
            [
                primary_tradeoff,
                *([stable_sibling_tradeoff] if stable_sibling_tradeoff is not None else []),
                *([near_threshold_tradeoff] if near_threshold_tradeoff is not None else []),
                relaxed_tradeoff,
                partial_tradeoff,
            ]
        )
        required_evidence = _unique_in_order(
            [
                primary_required_evidence,
                *(
                    [stable_sibling_required_evidence]
                    if stable_sibling_required_evidence is not None
                    else []
                ),
                *(
                    [near_threshold_required_evidence]
                    if near_threshold_required_evidence is not None
                    else []
                ),
                relaxed_required_evidence,
                partial_required_evidence,
            ]
        )
        options = [
            DesignStrategyOption(
                option_id="add_full_field_high_fov_seed",
                label="Add or ingest a high-FOV full-field seed",
                recommendation="primary",
                candidate_id=None,
                target_fov_deg=fov_deg,
                fov_deg=fov_deg,
                mtf_max_field_frac=1.0,
                evidence_status="needs_seed",
                spec_impact="preserves requested FOV and keeps full-field performance claim possible",
                required_evidence=[primary_required_evidence],
                tradeoffs=[primary_tradeoff],
            )
        ]
        if (
            stable_sibling_case is not None
            and stable_sibling_case.metadata is not None
            and stable_sibling_field is not None
            and stable_sibling_required_evidence is not None
        ):
            options.append(
                DesignStrategyOption(
                    option_id="stable_partial_field_sibling_seed",
                    label="Review more edge-stable high-FOV sibling",
                    recommendation="fallback",
                    candidate_id=stable_sibling_case.metadata.case_id,
                    target_fov_deg=fov_deg,
                    fov_deg=stable_sibling_case.metadata.fov_deg,
                    mtf_max_field_frac=stable_sibling_field,
                    evidence_status="partial_field_only",
                    spec_impact=(
                        "preserves high-FOV geometry while improving scanned edge-field "
                        f"stability to {format_mtf_field_fraction(stable_sibling_field)} field"
                    ),
                    required_evidence=[stable_sibling_required_evidence],
                    tradeoffs=[
                        stable_sibling_tradeoff
                        or "stable sibling remains partial-field only; full-field claims stay forbidden"
                    ],
                )
            )
        if (
            near_threshold_partial_case is not None
            and near_threshold_partial_case.metadata is not None
        ):
            near_threshold_fov_gap = fov_deg - near_threshold_partial_case.metadata.fov_deg
            options.append(
                DesignStrategyOption(
                    option_id="near_threshold_partial_field_seed",
                    label="Review near-threshold partial-field seed",
                    recommendation="fallback",
                    candidate_id=near_threshold_partial_case.metadata.case_id,
                    target_fov_deg=fov_deg,
                    fov_deg=near_threshold_partial_case.metadata.fov_deg,
                    mtf_max_field_frac=near_threshold_partial_case.metadata.mtf_max_field_frac,
                    evidence_status="partial_field_only",
                    spec_impact=(
                        f"reduces FOV by about {near_threshold_fov_gap:.1f} deg but "
                        "improves partial-field stability versus the 89.5 deg seed"
                    ),
                    required_evidence=(
                        [near_threshold_required_evidence]
                        if near_threshold_required_evidence is not None
                        else []
                    ),
                    tradeoffs=[
                        (
                            "near-threshold fallback remains partial-field only; "
                            "full-field edge-performance claims stay forbidden"
                        )
                    ],
                )
            )
        if (
            library_coverage_diagnostic.nearest_full_field_case_id is not None
            and provable_fov is not None
        ):
            options.append(
                DesignStrategyOption(
                    option_id="relax_fov_to_full_field_seed",
                    label="Relax FOV to nearest full-field seed",
                    recommendation="fallback",
                    candidate_id=library_coverage_diagnostic.nearest_full_field_case_id,
                    target_fov_deg=fov_deg,
                    fov_deg=provable_fov,
                    mtf_max_field_frac=1.0,
                    evidence_status="full_field_available",
                    spec_impact=(
                        f"reduces FOV by about {fov_gap:.1f} deg to regain full-field evidence"
                        if fov_gap is not None
                        else "relaxes FOV to the closest full-field-covered seed"
                    ),
                    required_evidence=[relaxed_required_evidence],
                    tradeoffs=[relaxed_tradeoff],
                )
            )
        if partial_candidate_id is not None:
            options.append(
                DesignStrategyOption(
                    option_id="partial_field_high_fov_draft",
                    label="Keep high-FOV seed as partial-field draft",
                    recommendation="hold",
                    candidate_id=partial_candidate_id,
                    target_fov_deg=fov_deg,
                    fov_deg=partial_fov,
                    mtf_max_field_frac=partial_field,
                    evidence_status="partial_field_only",
                    spec_impact=(
                        "preserves high-FOV geometry but forbids full-field performance claims"
                    ),
                    required_evidence=[partial_required_evidence],
                    tradeoffs=[partial_tradeoff],
                )
            )
        brief_target_image_height = image_height_mm or best.metadata.image_height_mm
        brief_target_elements = n_elements or best.metadata.n_pieces
        seed_acquisition_brief = SeedAcquisitionBrief(
            target_regime="smartphone visible-light high-FOV main/wide camera",
            priority="required_for_full_field_claim",
            source_format="Zemax/Optiland-compatible visible-light prescription with material metadata",
            target_fov_deg=fov_deg,
            minimum_fov_deg=_ULTRAWIDE_FOV_MIN,
            target_efl_mm=efl_mm,
            efl_window_mm=[round(max(0.1, efl_mm - 0.30), 2), round(efl_mm + 0.30, 2)],
            target_f_number=fnum,
            f_number_window=[round(max(0.8, fnum - 0.20), 2), round(fnum + 0.25, 2)],
            target_image_height_mm=brief_target_image_height,
            image_height_window_mm=[
                round(max(0.1, brief_target_image_height - 0.35), 2),
                round(brief_target_image_height + 0.35, 2),
            ],
            target_n_elements=brief_target_elements,
            element_count_window=[
                max(3, brief_target_elements - 1),
                min(8, brief_target_elements + 1),
            ],
            max_total_track_mm=max_total_track_mm,
            required_mtf_field_frac=1.0,
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
                "current high-FOV seeds are partial-field only",
                (
                    f"nearest full-field seed is {fov_gap:.1f} deg below target"
                    if fov_gap is not None
                    else "no nearby high-FOV full-field seed is available"
                ),
                "full-field claim requires reference evidence before local optimization can be promoted",
            ],
        )
        return DesignStrategyDecision(
            status="selected",
            selected_strategy=selected,
            summary=(
                "selected strategy is to add or ingest a full-field high-FOV seed before "
                "claiming edge performance; current high-FOV branch remains partial-field evidence"
            ),
            target_fov_deg=fov_deg,
            provable_full_field_fov_deg=provable_fov,
            full_field_fov_gap_deg=fov_gap,
            partial_field_fov_deg=partial_fov,
            partial_field_mtf_field_frac=partial_field,
            recommended_candidate_id="seed-baseline",
            fallback_strategies=_unique_in_order(
                [
                    *(
                        ["stable_partial_field_sibling_seed"]
                        if stable_sibling_case is not None
                        else []
                    ),
                    *(
                        ["near_threshold_partial_field_seed"]
                        if near_threshold_partial_case is not None
                        else []
                    ),
                    "relax_fov_to_full_field_seed",
                    "partial_field_high_fov_draft",
                ]
            ),
            options=options,
            seed_acquisition_brief=seed_acquisition_brief,
            rationale=_unique_in_order(rationale),
            tradeoffs=tradeoffs,
            required_evidence=required_evidence,
        )

    design_strategy_decision = _build_design_strategy_decision()

    def _build_seed_intake_audit() -> SeedIntakeAudit | None:
        if (
            design_strategy_decision is None
            or design_strategy_decision.seed_acquisition_brief is None
        ):
            return None
        return build_seed_intake_audit(
            cases=cases,
            brief=design_strategy_decision.seed_acquisition_brief,
        )

    seed_intake_audit = _build_seed_intake_audit()

    def _build_delivery_gate() -> DesignDeliveryGate | None:
        if design_strategy_decision is None:
            return None

        current_field = best.metadata.mtf_max_field_frac
        blocking_evidence = [
            *(
                library_coverage_diagnostic.evidence
                if library_coverage_diagnostic is not None
                else []
            ),
            *(
                full_field_recovery_diagnostic.evidence[:4]
                if full_field_recovery_diagnostic is not None
                else []
            ),
        ]
        promotion_requirements = [
            *design_strategy_decision.required_evidence,
        ]
        if design_strategy_decision.seed_acquisition_brief is not None:
            promotion_requirements.extend(
                design_strategy_decision.seed_acquisition_brief.validation_requirements[:3]
            )
        return DesignDeliveryGate(
            status="conditional_partial_field",
            deliverable_type="partial-field concept only",
            summary=(
                "deliver as a high-FOV partial-field concept, not a full-field draft, "
                "until the strategy evidence path is resolved"
            ),
            allowed_claims=[
                f"matched real high-FOV seed {best.metadata.case_id}",
                f"geometry target is represented near {best.metadata.fov_deg:.1f} deg FOV",
                f"MTF evidence is available up to {format_mtf_field_fraction(current_field)} field",
                "strategy options and seed acquisition brief are provided for review",
            ],
            forbidden_claims=[
                "full-field edge-performance claim",
                "production-ready optical prescription",
                "full replacement of optical designer review for this high-FOV case",
            ],
            promotion_requirements=_unique_in_order(promotion_requirements),
            blocking_evidence=_unique_in_order(blocking_evidence)[:8],
        )

    delivery_gate = _build_delivery_gate()

    def _candidate_id_for(role: str) -> str | None:
        for candidate in candidate_comparison:
            if candidate.role == role:
                return candidate.case_id
        return None

    def _candidate_review_risk_value(candidate: CandidateComparison) -> float:
        tolerance = (
            candidate.tolerance_risk_score if candidate.tolerance_risk_score is not None else 1.0
        )
        process = (
            candidate.process_yield_score if candidate.process_yield_score is not None else 1.0
        )
        return tolerance * 0.45 + process * 0.55

    def _candidate_proxy_review_opportunity() -> (
        tuple[CandidateComparison, CandidateComparison, float, float] | None
    ):
        if not candidate_comparison:
            return None
        selected = candidate_comparison[0]
        leader = min(
            candidate_comparison,
            key=lambda candidate: (
                _candidate_review_risk_value(candidate),
                candidate.normalized_distance,
            ),
        )
        selected_risk = _candidate_review_risk_value(selected)
        leader_risk = _candidate_review_risk_value(leader)
        if leader.case_id == selected.case_id or leader_risk + 0.03 >= selected_risk:
            return None
        return selected, leader, selected_risk, leader_risk

    candidate_proxy_review_opportunity = _candidate_proxy_review_opportunity()

    def _candidate_proxy_next_step() -> str | None:
        if not candidate_comparison:
            return None
        selected = candidate_comparison[0]
        if (
            candidate_proxy_branch_resolution is not None
            and candidate_proxy_branch_resolution.status == "rejected_for_target_fit"
        ):
            blocker = (
                candidate_proxy_branch_resolution.blockers[0]
                if candidate_proxy_branch_resolution.blockers
                else "hard target miss"
            )
            return (
                "Candidate proxy check: lower-risk branch "
                f"{candidate_proxy_branch_resolution.candidate_case_id} was compared and rejected "
                f"({blocker}); keep {candidate_proxy_branch_resolution.selected_case_id} primary."
            )
        if candidate_proxy_review_opportunity is None:
            selected_levels = (
                f"{selected.tolerance_risk_level or 'unknown'} tolerance / "
                f"{selected.process_yield_level or 'unknown'} process-yield"
            )
            return (
                "Candidate proxy check: selected seed is the lowest review-risk branch "
                f"or within margin ({selected_levels}); carry that evidence into design review."
            )
        selected, leader, selected_risk, leader_risk = candidate_proxy_review_opportunity
        selected_levels = (
            f"{selected.tolerance_risk_level or 'unknown'} tolerance / "
            f"{selected.process_yield_level or 'unknown'} process-yield"
        )
        leader_levels = (
            f"{leader.tolerance_risk_level or 'unknown'} tolerance / "
            f"{leader.process_yield_level or 'unknown'} process-yield"
        )
        return (
            f"Candidate proxy check: compare lower-risk branch {leader.case_id} before "
            f"freezing the prescription ({leader_levels}, review risk {leader_risk:.2f}) "
            f"against selected seed {selected.case_id} ({selected_levels}, "
            f"review risk {selected_risk:.2f})."
        )

    def _next_steps() -> list[str]:
        steps = [
            (
                f"Use {best.metadata.case_id} as the starting prescription; "
                "freeze EFL/FOV/F# first, then locally optimize stop position, air gaps, "
                "center thicknesses, and asphere coefficients."
            )
        ]
        candidate_proxy_step = _candidate_proxy_next_step()
        if candidate_proxy_step is not None:
            steps.append(candidate_proxy_step)
        if (
            fov_spec_consistency is not None
            and fov_spec_consistency.status != "met"
            and abs(delta_fov) > 2.0
        ):
            steps.append(fov_spec_consistency.next_action)
        if abs(delta_fov) > 3.0:
            steps.append(
                "Resolve FOV mismatch before merit-function tuning; either relax target FOV "
                f"by {abs(delta_fov):.1f} deg or add a closer high-FOV seed to the library."
            )
        if delta_ttl is not None:
            if delta_ttl > 0:
                steps.append(
                    f"Raise the TTL ceiling by {delta_ttl:.2f} mm or branch from "
                    f"{_candidate_id_for('thin_variant') or best.metadata.case_id}."
                )
            else:
                steps.append(
                    f"Keep TTL ceiling at {max_total_track_mm:.2f} mm and verify the "
                    "chosen air-gap changes do not consume the remaining track margin."
                )
        if cost_like:
            steps.append(
                f"Run a cost-control branch from {_candidate_id_for('cost_variant') or best.metadata.case_id}; "
                "only add elements if edge-field MTF cannot close."
            )
        if performance_like:
            steps.append(
                f"Benchmark {_candidate_id_for('performance_variant') or best.metadata.case_id} "
                "against the selected seed on full-field MTF and tolerance sensitivity."
            )
        if design_strategy_decision is not None:
            steps.append(design_strategy_decision.summary)
            if design_strategy_decision.required_evidence:
                steps.append(design_strategy_decision.required_evidence[0])
        elif (
            library_coverage_diagnostic is not None and library_coverage_diagnostic.status == "gap"
        ):
            steps.append(library_coverage_diagnostic.recommended_strategy)
        if best.metadata.mtf_max_field_frac < 1.0:
            steps.append(
                "Re-run full-field ray aiming before claiming edge performance; current MTF "
                "evidence stops short of the 1.0 field."
            )
        if max_weight_g is not None:
            mass_proxy = mass_proxies[best.metadata.case_id]
            if mass_proxy.estimated_mass_g > max_weight_g:
                steps.append(
                    "Select a lighter seed or relax the requested mass budget before treating "
                    "weight as satisfied."
                )
            else:
                steps.append(
                    "Validate measured module mass later; current optical-stack proxy is inside "
                    "the requested budget."
                )
        if manufacturability_review.status != "pass" and (
            manufacturing_tier is not None or manufacturability_review.status == "blocked"
        ):
            flagged = next(
                (
                    check
                    for check in manufacturability_review.checks
                    if check.status in {"warning", "blocker"}
                ),
                None,
            )
            if flagged is not None:
                steps.append(
                    f"Resolve manufacturability review warning: {flagged.label} ({flagged.actual})."
                )
        while len(steps) < 3:
            steps.append(
                "After local optimization, validate RGB wavelengths, full field heights, "
                "relative illumination, and tolerance sensitivity before promoting the draft."
            )
        return steps[:5]

    def _risk_register() -> list[DesignRisk]:
        risks: list[DesignRisk] = []

        def add(risk: str, severity: str, evidence: str, mitigation: str) -> None:
            risks.append(
                DesignRisk(
                    risk=risk,
                    severity=severity,
                    evidence=evidence,
                    mitigation=mitigation,
                )
            )

        if (
            fov_spec_consistency is not None
            and fov_spec_consistency.status != "met"
            and abs(delta_fov) > 2.0
        ):
            add(
                "request-geometry inconsistency",
                "high" if fov_spec_consistency.status == "miss" else "medium",
                fov_spec_consistency.summary,
                fov_spec_consistency.next_action,
            )
        if abs(delta_fov) > 3.0:
            add(
                "field-of-view mismatch",
                "high" if abs(delta_fov) > 6.0 else "medium",
                f"selected seed FOV differs from target by {delta_fov:+.1f} deg",
                "close the field angle first or explicitly relax the FOV target",
            )
        if abs(delta_efl) > 0.25:
            add(
                "effective focal length mismatch",
                "medium",
                f"selected seed EFL differs from target by {delta_efl:+.2f} mm",
                "lock target EFL in the merit function before thickness/asphere tuning",
            )
        if delta_ttl is not None and delta_ttl > 0:
            add(
                "packaging track overrun",
                "high",
                f"selected seed exceeds TTL ceiling by {delta_ttl:+.2f} mm",
                "branch from the thin seed or increase the allowed total track",
            )
        elif delta_ttl is not None and abs(delta_ttl) < 0.2:
            add(
                "tight total-track margin",
                "medium",
                f"remaining TTL margin is only {abs(delta_ttl):.2f} mm",
                "keep air-gap and center-thickness edits inside a packaging budget",
            )
        if delta_n is not None and delta_n != 0:
            add(
                "element-count mismatch",
                "medium" if cost_like else "low",
                f"selected seed differs from requested count by {delta_n:+d} elements",
                "compare the cost branch before accepting extra optical complexity",
            )
        if best.metadata.mtf_max_field_frac < 1.0:
            add(
                "full-field MTF not proven",
                "high" if performance_like else "medium",
                "MTF currently reaches only "
                f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)} field",
                "rerun robust full-field ray aiming before claiming edge performance",
            )
        if library_coverage_diagnostic is not None and library_coverage_diagnostic.status == "gap":
            gap = library_coverage_diagnostic.full_field_fov_gap_deg
            add(
                "high-FOV full-field seed coverage gap",
                "high",
                (
                    f"nearest full-field seed is {gap:.1f} deg below target"
                    if gap is not None
                    else "no high-FOV full-field seed is available"
                ),
                (
                    design_strategy_decision.summary
                    if design_strategy_decision is not None
                    else library_coverage_diagnostic.recommended_strategy
                ),
            )
        if max_weight_g is not None:
            mass_proxy = mass_proxies[best.metadata.case_id]
            mass_delta = mass_proxy.estimated_mass_g - max_weight_g
            if mass_delta > 0:
                add(
                    "mass budget overrun",
                    "high" if mass_delta > max_weight_g * 0.25 else "medium",
                    f"optical-stack mass proxy exceeds budget by {mass_delta:+.3f} g",
                    "select a lighter seed, reduce envelope diameter, or relax the weight budget",
                )
            elif abs(mass_delta) <= max(0.01, max_weight_g * 0.15):
                add(
                    "tight mass budget margin",
                    "medium",
                    f"optical-stack mass proxy leaves only {-mass_delta:.3f} g reserve",
                    "protect diameter and spacer mass until measured module mass is available",
                )
        if manufacturability_review.status != "pass" and (
            manufacturing_tier is not None or manufacturability_review.status == "blocked"
        ):
            flagged = next(
                (
                    check
                    for check in manufacturability_review.checks
                    if check.status in {"blocker", "warning"}
                ),
                None,
            )
            if flagged is not None:
                add(
                    "manufacturability proxy warning",
                    "high" if flagged.status == "blocker" else "medium",
                    f"{flagged.label}: {flagged.actual} vs {flagged.target}",
                    flagged.mitigation or "run full tolerance/yield review before release",
                )
        if optimization_attempt.status != "proposal":
            add(
                "local optimizer not yet trusted",
                "medium",
                optimization_attempt.summary,
                "use the optimizer diagnostics to narrow safe variables before applying a prescription change",
            )
        elif (
            optimization_attempt.verification is not None
            and optimization_attempt.verification.status == "warning"
        ):
            add(
                "optimizer verification warning",
                "medium",
                optimization_attempt.verification.summary,
                "recover full-field MTF before applying the protected radius proposal",
            )
        if not risks:
            add(
                "local optimization still required",
                "low",
                "selected seed is a real production-like starting point, not a tuned target prescription",
                "run local optimization and tolerancing before promoting the draft",
            )
        return risks[:5]

    def _optimization_plan() -> list[OptimizationAction]:
        actions: list[OptimizationAction] = []

        def add(
            objective: str,
            parameter_focus: list[str],
            expected_effect: str,
            verification: str,
        ) -> None:
            actions.append(
                OptimizationAction(
                    priority=len(actions) + 1,
                    objective=objective,
                    parameter_focus=parameter_focus,
                    expected_effect=expected_effect,
                    verification=verification,
                )
            )

        if design_strategy_decision is not None:
            add(
                "resolve the high-FOV evidence strategy",
                ["seed library", "FOV target", "partial-field labeling"],
                (
                    "chooses whether to preserve FOV by adding a full-field seed, relax FOV, "
                    "or keep the current branch as partial-field evidence"
                ),
                "; ".join(design_strategy_decision.required_evidence[:2]),
            )
        if optimization_attempt.status == "proposal" and optimization_attempt.variable_changes:
            change = optimization_attempt.variable_changes[0]
            add(
                "verify protected radius-tweak proposal",
                [f"surface {change.surface_index} radius", "paraxial EFL", "ray trace stability"],
                (
                    f"reduces EFL miss by {optimization_attempt.improvement_efl_mm:.3f} mm "
                    "without mutating the delivered seed payload"
                ),
                (
                    "accept only if the post-tweak verification gate is passed or explicitly "
                    "handled as a full-field MTF warning"
                ),
            )
        elif optimization_attempt.status != "not_attempted":
            add(
                "stabilize the local optimizer contract",
                ["finite Jacobian", "bounded radius variables", "ray aiming"],
                "turns optimizer diagnostics into a safe prescription-change loop",
                "rerun protected optimization until failures are finite and reproducible",
            )
        if abs(delta_fov) > 3.0:
            add(
                "close the field-angle mismatch",
                ["field weights", "stop position", "asphere coefficients"],
                "moves the seed toward the requested diagonal FOV before MTF tuning",
                "recompute paraxial FOV and edge-field ray trace at 0.7 and 1.0 field",
            )
        add(
            "lock first-order targets on the selected seed",
            ["effective focal length", "F-number", "image height"],
            "keeps the optimizer from improving MTF by drifting away from the brief",
            "check EFL/F/#/image-height deltas after each merit-function solve",
        )
        if best.metadata.mtf_max_field_frac < 1.0 or performance_like:
            add(
                "recover full-field image quality evidence",
                ["edge-field rays", "higher-order aspheres", "chief-ray aiming"],
                "separates a true high-performance branch from a ray-aiming failure",
                "MTF must evaluate cleanly at 1.0 field before performance claims",
            )
        if max_total_track_mm is not None:
            add(
                "protect the module packaging budget",
                ["air gaps", "center thickness", "filter stack"],
                "keeps mechanical length from being consumed by optical cleanup",
                "verify total track after every structural edit",
            )
        if cost_like:
            add(
                "run the cost-control branch",
                ["element count", "material family", "manufacturing tolerance"],
                "tests whether fewer pieces can meet the same center and mid-field targets",
                "compare MTF and RMS against the selected seed before adding elements",
            )
        while len(actions) < 3:
            add(
                "validate the draft across production conditions",
                ["RGB wavelengths", "field heights", "tolerance sensitivity"],
                "turns a seed match into a manufacturable draft candidate",
                "run RGB MTF, RMS spot, relative illumination, and tolerance checks",
            )
        return actions[:5]

    def _readiness(risks: list[DesignRisk]) -> DesignReadiness:
        has_high = any(risk.severity == "high" for risk in risks)
        has_medium = any(risk.severity == "medium" for risk in risks)
        if score < 0.75 or has_high:
            level = "red"
        elif score < 0.92 or has_medium or warnings_out:
            level = "yellow"
        else:
            level = "green"

        confidence = min(score, best.metadata.mtf_max_field_frac)
        if has_high:
            confidence *= 0.82
        elif has_medium:
            confidence *= 0.92

        summaries = {
            "green": "credible seed; ready for local optimization and tolerancing",
            "yellow": "usable seed with explicit tradeoffs; optimize before external review",
            "red": "seed needs a feasibility branch before it should be treated as a draft",
        }
        return DesignReadiness(
            level=level,
            confidence=max(0.0, min(1.0, confidence)),
            summary=summaries[level],
        )

    risk_register = _risk_register()
    optimization_plan = _optimization_plan()
    readiness = _readiness(risk_register)

    def _change_label(change: OptimizationVariableChange) -> str:
        return f"S{change.surface_index} {change.variable} {change.before:.4f}->{change.after:.4f}"

    def _changes_label(changes: list[OptimizationVariableChange], *, limit: int = 4) -> str:
        labels = [_change_label(change) for change in changes[:limit]]
        if len(changes) > limit:
            labels.append(f"+{len(changes) - limit} more")
        return "; ".join(labels)

    def _promoted_merit_changes() -> list[OptimizationVariableChange]:
        if (
            merit_optimization_probe.status == "proposal"
            and merit_optimization_probe.variable_changes
            and merit_optimization_probe.after_metrics is not None
        ):
            return list(merit_optimization_probe.variable_changes)
        return []

    def _draft_candidates() -> tuple[list[DraftCandidate], str]:
        seed_id = "seed-baseline"
        optimizer_id = "optimizer-proposal"
        optimizer_gate = optimization_attempt.verification
        merit_changes = _promoted_merit_changes()
        promoted_merit_branch = bool(merit_changes)
        optimizer_metrics = (
            merit_optimization_probe.after_metrics
            if promoted_merit_branch
            else optimization_attempt.after_metrics
        )
        optimizer_floor = _evaluate_image_quality_floor(optimizer_metrics)
        optimizer_recommended = (
            optimization_attempt.status == "proposal"
            and optimizer_gate is not None
            and optimizer_gate.status == "passed"
            and optimizer_floor.status == "pass"
        )
        strategy_blocks_full_field_claim = design_strategy_decision is not None
        seed_metrics = seed_baseline_metrics
        recovery_floor_trial = floor_gap_recovery_trial
        full_field_recovery_trial = (
            full_field_recovery_diagnostic.best_recovery_trial
            if full_field_recovery_diagnostic is not None
            else None
        )
        floor_clean_full_field_trial = _floor_clean_full_field_recovery_trial()

        def metrics_for_case(
            case: OpticalSampleData,
            *,
            mtf_field_override: float | None = None,
        ) -> OptimizationMetricSnapshot:
            bands = mtf_multiband_summary(case.mtf)
            rms_values = [
                value for value in case.mtf.rms_spot_radius_um_by_field if math.isfinite(value)
            ]
            return OptimizationMetricSnapshot(
                effective_focal_length_mm=case.metadata.computed_efl_mm,
                f_number=case.paraxial.f_number,
                total_track_mm=case.paraxial.total_track_mm,
                mtf_max_field_frac=(
                    mtf_field_override
                    if mtf_field_override is not None
                    else case.metadata.mtf_max_field_frac
                ),
                mtf_50lpmm_min=bands.min_50,
                mtf_50lpmm_avg=bands.avg_50,
                mtf_100lpmm_min=bands.min_100,
                mtf_100lpmm_avg=bands.avg_100,
                mtf_150lpmm_min=bands.min_150,
                mtf_150lpmm_avg=bands.avg_150,
                mtf_200lpmm_min=bands.min_200,
                mtf_200lpmm_avg=bands.avg_200,
                mtf_250lpmm_min=bands.min_250,
                mtf_250lpmm_avg=bands.avg_250,
                mtf_multiband_min_score=bands.multiband_min_score,
                mtf_field_weighted_score=bands.field_weighted_score,
                max_rms_spot_radius_um=max(rms_values) if rms_values else None,
            )

        def fov_alternative_risks(case: OpticalSampleData) -> list[str]:
            assert case.metadata is not None
            risks: list[str] = []
            efl_delta = case.metadata.computed_efl_mm - efl_mm
            fnum_delta = case.paraxial.f_number - fnum
            imh_delta = (
                _case_image_height_mm(case) - image_height_mm
                if image_height_mm is not None
                else None
            )
            if abs(efl_delta) > 0.15:
                risks.append(f"EFL differs by {efl_delta:+.2f} mm")
            if fnum_delta > 0.15:
                risks.append(f"aperture is slower by {fnum_delta:+.2f} F/#")
            elif fnum_delta < -0.15:
                risks.append(
                    f"aperture is faster by {fnum_delta:+.2f} F/#; tolerance/cost review needed"
                )
            if imh_delta is not None and abs(imh_delta) > 0.20:
                risks.append(f"image height differs by {imh_delta:+.2f} mm")
            if case.metadata.mtf_max_field_frac < 1.0:
                risks.append(
                    "MTF evidence reaches only "
                    f"{format_mtf_field_fraction(case.metadata.mtf_max_field_frac)} field"
                )
            return risks[:4] or ["FOV branch needs normal tolerancing before promotion"]

        primary_seed_option = None
        partial_field_option = None
        stable_sibling_option = None
        near_threshold_option = None
        relaxed_option = None
        if design_strategy_decision is not None:
            primary_seed_option = next(
                (
                    option
                    for option in design_strategy_decision.options
                    if option.option_id == "add_full_field_high_fov_seed"
                ),
                None,
            )
            partial_field_option = next(
                (
                    option
                    for option in design_strategy_decision.options
                    if option.option_id == "partial_field_high_fov_draft"
                    and option.candidate_id is not None
                ),
                None,
            )
            stable_sibling_option = next(
                (
                    option
                    for option in design_strategy_decision.options
                    if option.option_id == "stable_partial_field_sibling_seed"
                    and option.candidate_id is not None
                ),
                None,
            )
            near_threshold_option = next(
                (
                    option
                    for option in design_strategy_decision.options
                    if option.option_id == "near_threshold_partial_field_seed"
                    and option.candidate_id is not None
                ),
                None,
            )
            relaxed_option = next(
                (
                    option
                    for option in design_strategy_decision.options
                    if option.option_id == "relax_fov_to_full_field_seed"
                    and option.candidate_id is not None
                ),
                None,
            )
        relaxed_case = (
            next(
                (
                    case
                    for case in cases
                    if case.metadata is not None
                    and relaxed_option is not None
                    and case.metadata.case_id == relaxed_option.candidate_id
                ),
                None,
            )
            if relaxed_option is not None
            else None
        )
        near_threshold_case = (
            next(
                (
                    case
                    for case in cases
                    if case.metadata is not None
                    and near_threshold_option is not None
                    and case.metadata.case_id == near_threshold_option.candidate_id
                ),
                None,
            )
            if near_threshold_option is not None
            else None
        )
        stable_sibling_case = (
            next(
                (
                    case
                    for case in cases
                    if case.metadata is not None
                    and stable_sibling_option is not None
                    and case.metadata.case_id == stable_sibling_option.candidate_id
                ),
                None,
            )
            if stable_sibling_option is not None
            else None
        )
        proxy_review_candidate = None
        proxy_review_case = None
        proxy_selected_risk = None
        proxy_candidate_risk = None
        if candidate_proxy_review_opportunity is not None:
            (
                _proxy_selected,
                proxy_review_candidate,
                proxy_selected_risk,
                proxy_candidate_risk,
            ) = candidate_proxy_review_opportunity
            proxy_review_case = next(
                (
                    case
                    for case in cases
                    if case.metadata is not None
                    and case.metadata.case_id == proxy_review_candidate.case_id
                ),
                None,
            )
        candidates = [
            DraftCandidate(
                candidate_id=seed_id,
                source="seed_baseline",
                strategy_option_id=(
                    "partial_field_high_fov_draft" if strategy_blocks_full_field_claim else None
                ),
                status="baseline",
                recommendation=(
                    "hold"
                    if optimizer_recommended or strategy_blocks_full_field_claim
                    else "continue"
                ),
                summary=(
                    "high-FOV seed is usable only as a partial-field draft until the strategy evidence path is resolved"
                    if strategy_blocks_full_field_claim
                    else (
                        "real seed baseline kept as rollback branch"
                        if optimizer_recommended
                        else "recommended branch until optimizer proposal is fully proven"
                    )
                ),
                metrics=seed_metrics,
                evidence=[
                    f"matched real case {best.metadata.case_id}",
                    f"score {score:.3f}",
                    "MTF evidence reaches "
                    f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)} field",
                ],
                risks=(
                    [
                        design_strategy_decision.summary,
                        *list(warnings_out[:2]),
                    ]
                    if design_strategy_decision is not None
                    else list(warnings_out[:3])
                ),
            )
        ]
        if recovery_floor_trial is not None:
            trial_label = f"{recovery_floor_trial.variable} S{recovery_floor_trial.surface_index}"
            if recovery_floor_trial.coefficient_index is not None:
                trial_label = f"{trial_label}:c{recovery_floor_trial.coefficient_index}"
            closure = recovery_floor_trial.image_quality_floor_gap_closure
            recovery_status = (
                "warning"
                if closure is not None
                and closure > 0
                and recovery_floor_trial.status in {"accepted", "improved"}
                else "diagnostic"
            )
            recovery_evidence = [
                "selected by floor-gap-first recovery probe",
                f"trial {trial_label}",
                f"trial status {recovery_floor_trial.status}",
                f"floor-gap closure={closure:+.3f}" if closure is not None else "",
                (
                    f"promotion score={recovery_floor_trial.promotion_score:.3f}"
                    if recovery_floor_trial.promotion_score is not None
                    else ""
                ),
                (
                    f"RMS delta={recovery_floor_trial.rms_improvement_um:+.2f}um"
                    if recovery_floor_trial.rms_improvement_um is not None
                    else ""
                ),
                f"verification gate={recovery_floor_trial.verification_status or 'n/a'}",
                "delivered payload not mutated",
            ]
            candidates.append(
                DraftCandidate(
                    candidate_id="floor-gap-recovery-candidate",
                    source="recovery_probe",
                    status=recovery_status,
                    recommendation="hold",
                    summary=(
                        "guarded MTF/RMS recovery edit selected for the next replay; "
                        "not a delivered prescription branch"
                    ),
                    metrics=merit_optimization_probe.after_metrics,
                    evidence=_unique_in_order([item for item in recovery_evidence if item])[:8],
                    risks=[
                        "guarded replay only; keep payload frozen until the MTF/RMS floor passes",
                        "verify first-order targets, full-field MTF, RMS, and manufacturability before promotion",
                    ],
                )
            )
        if (
            full_field_recovery_trial is not None
            and full_field_recovery_trial.variable_family == "compound_field_extension"
            and full_field_recovery_trial.status == "recovered"
            and full_field_recovery_trial.metrics is not None
            and full_field_recovery_trial.mtf_max_field_frac is not None
            and full_field_recovery_trial.mtf_max_field_frac >= 1.0
        ):
            full_field_gap = full_field_recovery_trial.image_quality_floor_gap_score
            floor_clean = floor_clean_full_field_trial is not None
            metrics = full_field_recovery_trial.metrics
            candidates.append(
                DraftCandidate(
                    candidate_id="full-field-floor-clean-recovery-candidate",
                    source="recovery_probe",
                    status="proposed" if floor_clean else "warning",
                    recommendation="continue" if floor_clean else "hold",
                    summary=(
                        "guarded compound field-extension branch clears 1.0-field "
                        "MTF/RMS floor; convert to a protected change-set before "
                        "using it as the draft payload"
                        if floor_clean
                        else "guarded compound field-extension branch reaches 1.0 field "
                        "but still needs MTF/RMS floor recovery"
                    ),
                    metrics=metrics,
                    evidence=_unique_in_order(
                        [
                            "selected by full-field recovery diagnostic",
                            full_field_recovery_trial.reason,
                            "MTF evidence reaches "
                            f"{format_mtf_field_fraction(full_field_recovery_trial.mtf_max_field_frac)} field",
                            (
                                f"floor gap={full_field_gap:.3f}"
                                if full_field_gap is not None
                                else "floor gap unavailable"
                            ),
                            (
                                f"MTF/RMS floor min={metrics.mtf_multiband_min_score:.3f}; "
                                f"weighted={metrics.mtf_field_weighted_score:.3f}; "
                                f"RMS={metrics.max_rms_spot_radius_um:.2f}um"
                                if metrics.mtf_multiband_min_score is not None
                                and metrics.mtf_field_weighted_score is not None
                                and metrics.max_rms_spot_radius_um is not None
                                else ""
                            ),
                            (
                                "protected changes="
                                f"{_changes_label(full_field_recovery_trial.variable_changes)}"
                                if full_field_recovery_trial.variable_changes
                                else "protected changes unavailable"
                            ),
                            "delivered payload not mutated",
                        ]
                    )[:8],
                    risks=[
                        "protected recovery candidate only; payload remains the selected seed until a reviewed change-set is created",
                        "aperture remains slower than the requested F/1.8 target",
                        "4P branch still differs from the requested 5P element count",
                        "large radius/refocus move needs tolerance and manufacturability review",
                    ],
                )
            )
        if fov_alternative_case is not None and fov_alternative_case.metadata is not None:
            fov_gap = fov_alternative_case.metadata.fov_deg - fov_deg
            selected_gap = best.metadata.fov_deg - fov_deg
            fov_resolution = fov_alternative_branch_resolution
            fov_blocked = (
                fov_resolution is not None and fov_resolution.status == "rejected_for_target_fit"
            )
            candidates.append(
                DraftCandidate(
                    candidate_id="fov-alternative-review",
                    source="requirement_branch",
                    status="blocked" if fov_blocked else "fallback",
                    recommendation="reject" if fov_blocked else "hold",
                    summary=(
                        (
                            "closer-FOV real seed rejected as a payload replacement "
                            "because it creates hard target-fit regressions"
                        )
                        if fov_blocked
                        else (
                            "closer-FOV real seed for reviewing the selected branch's "
                            "field-angle tradeoff"
                        )
                    ),
                    metrics=metrics_for_case(fov_alternative_case),
                    evidence=[
                        f"case {fov_alternative_case.metadata.case_id}",
                        f"selected FOV delta {selected_gap:+.1f} deg",
                        f"alternative FOV delta {fov_gap:+.1f} deg",
                        "MTF evidence reaches "
                        f"{format_mtf_field_fraction(fov_alternative_case.metadata.mtf_max_field_frac)} field",
                        *(list(fov_resolution.evidence[:2]) if fov_resolution is not None else []),
                    ],
                    risks=(
                        list(fov_resolution.blockers[:4])
                        if fov_blocked and fov_resolution is not None
                        else fov_alternative_risks(fov_alternative_case)
                    ),
                )
            )
        if (
            fov_spec_consistency is not None
            and fov_spec_consistency.status != "met"
            and abs(delta_fov) > 2.0
        ):
            candidates.append(
                DraftCandidate(
                    candidate_id="fov-spec-reconciliation",
                    source="requirement_branch",
                    status="proposed" if fov_spec_default_repair is not None else "conditional",
                    recommendation="continue" if fov_spec_default_repair is not None else "hold",
                    summary=(
                        "review repaired target specs before treating the FOV miss "
                        "as only a seed-library coverage gap"
                    ),
                    metrics=(
                        metrics_for_case(fov_spec_repair_replay.selected_case)
                        if fov_spec_repair_replay is not None
                        else None
                    ),
                    evidence=[
                        *(
                            [fov_spec_default_repair[0]]
                            if fov_spec_default_repair is not None
                            else []
                        ),
                        *(
                            list(fov_spec_repair_replay.evidence)
                            if fov_spec_repair_replay is not None
                            else []
                        ),
                        (
                            "repair options: keep image height "
                            f"{image_height_mm:.2f} mm -> EFL "
                            f"{fov_spec_consistency.implied_efl_mm:.2f} mm; "
                            f"keep EFL {efl_mm:.2f} mm -> image height "
                            f"{fov_spec_consistency.implied_image_height_mm:.2f} mm"
                        ),
                        fov_spec_consistency.summary,
                        (
                            f"current target EFL {efl_mm:.2f} mm / image height "
                            f"{image_height_mm:.2f} mm -> first-order FOV "
                            f"{fov_spec_consistency.first_order_fov_deg:.1f} deg"
                        ),
                        (
                            f"keep image height {image_height_mm:.2f} mm and FOV "
                            f"{fov_deg:.1f} deg -> EFL "
                            f"{fov_spec_consistency.implied_efl_mm:.2f} mm"
                        ),
                        (
                            f"keep EFL {efl_mm:.2f} mm and FOV {fov_deg:.1f} deg "
                            f"-> image height "
                            f"{fov_spec_consistency.implied_image_height_mm:.2f} mm"
                        ),
                    ],
                    risks=[
                        *(
                            [fov_spec_default_repair[2]]
                            if fov_spec_default_repair is not None
                            else []
                        ),
                        *(
                            list(fov_spec_repair_replay.risks)
                            if fov_spec_repair_replay is not None
                            else []
                        ),
                        "requirement repair changes the requested EFL or sensor format",
                        "rerun seed scoring and acceptance after choosing a repaired target",
                        "do not claim the original target triad is simultaneously satisfied",
                    ],
                )
            )
        if fov_target_seed_brief is not None:
            brief = fov_target_seed_brief
            evidence = [
                f"target FOV {brief.target_fov_deg:.1f} deg",
                f"minimum FOV {brief.minimum_fov_deg:.1f} deg",
                f"EFL window {brief.efl_window_mm[0]:.2f}-{brief.efl_window_mm[1]:.2f} mm",
                f"F/# window {brief.f_number_window[0]:.2f}-{brief.f_number_window[1]:.2f}",
                f"required MTF field {format_mtf_field_fraction(brief.required_mtf_field_frac)}",
            ]
            if brief.image_height_window_mm:
                evidence.append(
                    "image-height window "
                    f"{brief.image_height_window_mm[0]:.2f}-{brief.image_height_window_mm[1]:.2f} mm"
                )
            if brief.element_count_window:
                evidence.append(
                    f"element-count window {brief.element_count_window[0]}P-{brief.element_count_window[1]}P"
                )
            candidates.append(
                DraftCandidate(
                    candidate_id="fov-target-seed-needed",
                    source="requirement_gap",
                    status="blocked",
                    recommendation="hold",
                    summary=(
                        "target seed or optimizer branch needed to close FOV without "
                        "the rejected alternative's target-fit regressions"
                    ),
                    metrics=None,
                    evidence=evidence[:7],
                    risks=[
                        "current selected seed remains narrower than requested FOV",
                        *brief.rejection_filters[:3],
                    ],
                )
            )
            candidates.append(
                DraftCandidate(
                    candidate_id="fov-waiver-review",
                    source="requirement_gap",
                    status="conditional",
                    recommendation="hold",
                    summary=(
                        "explicit waiver option for accepting the selected seed's "
                        "narrower field of view without changing the requested target"
                    ),
                    metrics=seed_metrics,
                    evidence=[
                        f"requested FOV {fov_deg:.1f} deg",
                        f"selected actual FOV {best.metadata.fov_deg:.1f} deg",
                        f"FOV delta {best.metadata.fov_deg - fov_deg:+.1f} deg",
                        f"selected EFL delta {best.metadata.computed_efl_mm - efl_mm:+.2f} mm",
                        f"selected F/# delta {best.paraxial.f_number - fnum:+.2f}",
                        "selected seed MTF evidence reaches "
                        f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)} field",
                    ],
                    risks=[
                        "requires explicit product/design waiver before first-pass acceptance",
                        f"cannot claim {fov_deg:.1f} deg FOV from a {best.metadata.fov_deg:.1f} deg seed",
                        "report must label actual FOV and avoid target-FOV compliance claims",
                    ],
                )
            )
        if (
            design_strategy_decision is not None
            and primary_seed_option is not None
            and design_strategy_decision.seed_acquisition_brief is not None
        ):
            brief = design_strategy_decision.seed_acquisition_brief
            candidates.append(
                DraftCandidate(
                    candidate_id="high-fov-full-field-seed-needed",
                    source="strategy_option",
                    strategy_option_id=primary_seed_option.option_id,
                    status="blocked",
                    recommendation="hold",
                    summary=(
                        "primary branch is to acquire a visible-light high-FOV seed "
                        "before promoting a full-field draft"
                    ),
                    metrics=None,
                    evidence=[
                        f"strategy option {primary_seed_option.option_id}",
                        f"required FOV >= {brief.minimum_fov_deg:.1f} deg",
                        f"EFL window {brief.efl_window_mm[0]:.2f}-{brief.efl_window_mm[1]:.2f} mm",
                        f"F/# window {brief.f_number_window[0]:.2f}-{brief.f_number_window[1]:.2f}",
                        "required MTF field "
                        f"{format_mtf_field_fraction(brief.required_mtf_field_frac)}",
                    ],
                    risks=[
                        "no current visible-light high-FOV full-field seed backs this branch",
                        "full-field edge performance cannot be claimed until a real prescription passes validation",
                    ],
                )
            )
        if (
            design_strategy_decision is not None
            and stable_sibling_option is not None
            and stable_sibling_case is not None
            and stable_sibling_case.metadata is not None
            and stable_sibling_option.mtf_max_field_frac is not None
        ):
            stable_field_label = format_mtf_field_fraction(stable_sibling_option.mtf_max_field_frac)
            current_edge_field = (
                full_field_recovery_diagnostic.highest_scanned_stable_field_frac
                if full_field_recovery_diagnostic is not None
                and full_field_recovery_diagnostic.highest_scanned_stable_field_frac is not None
                else best.metadata.mtf_max_field_frac
            )
            current_edge_label = format_mtf_field_fraction(current_edge_field)
            candidates.append(
                DraftCandidate(
                    candidate_id="stable-partial-field-sibling",
                    source="strategy_option",
                    strategy_option_id=stable_sibling_option.option_id,
                    status="fallback",
                    recommendation="continue",
                    summary=(
                        "trade study: keep high-FOV geometry while using the sibling "
                        "with stronger scanned edge-field stability; still partial-field only"
                    ),
                    metrics=metrics_for_case(
                        stable_sibling_case,
                        mtf_field_override=stable_sibling_option.mtf_max_field_frac,
                    ),
                    evidence=[
                        f"strategy option {stable_sibling_option.option_id}",
                        f"edge-stability sibling real case {stable_sibling_case.metadata.case_id}",
                        f"FOV {stable_sibling_case.metadata.fov_deg:.1f} deg",
                        f"scanned edge field reaches {stable_field_label} field",
                        (
                            f"improves from {current_edge_label} to {stable_field_label} "
                            "versus selected partial branch"
                        ),
                    ],
                    risks=[
                        "still partial-field only; full-field edge-performance claims stay forbidden",
                        "does not replace missing >=85 deg / 1.0 field seed evidence",
                    ],
                )
            )
        if (
            design_strategy_decision is not None
            and partial_field_option is not None
            and partial_field_option.candidate_id == best.metadata.case_id
        ):
            field_label = format_mtf_field_fraction(best.metadata.mtf_max_field_frac)
            forbidden = (
                delivery_gate.forbidden_claims[0]
                if delivery_gate is not None and delivery_gate.forbidden_claims
                else "full-field edge performance cannot be claimed from partial-field evidence"
            )
            candidates.append(
                DraftCandidate(
                    candidate_id="partial-field-high-fov-draft",
                    source="strategy_option",
                    strategy_option_id=partial_field_option.option_id,
                    status="conditional",
                    recommendation="hold",
                    summary=(
                        "keep the requested high-FOV geometry only as a partial-field "
                        "concept until full-field evidence is acquired"
                    ),
                    metrics=seed_metrics,
                    evidence=[
                        f"strategy option {partial_field_option.option_id}",
                        f"partial-field real case {best.metadata.case_id}",
                        f"FOV {best.metadata.fov_deg:.1f} deg",
                        f"MTF evidence reaches {field_label} field",
                    ],
                    risks=[
                        forbidden,
                        "edge-field performance beyond the verified partial field remains unproven",
                    ],
                )
            )
        if (
            design_strategy_decision is not None
            and near_threshold_option is not None
            and near_threshold_case is not None
            and near_threshold_case.metadata is not None
        ):
            near_field_label = format_mtf_field_fraction(
                near_threshold_case.metadata.mtf_max_field_frac
            )
            current_field_label = format_mtf_field_fraction(best.metadata.mtf_max_field_frac)
            candidates.append(
                DraftCandidate(
                    candidate_id="near-threshold-partial-field",
                    source="strategy_option",
                    strategy_option_id=near_threshold_option.option_id,
                    status="fallback",
                    recommendation="hold",
                    summary=(
                        "intermediate trade study: reduce FOV toward a more stable "
                        "partial-field real seed, without making full-field claims"
                    ),
                    metrics=metrics_for_case(near_threshold_case),
                    evidence=[
                        f"strategy option {near_threshold_option.option_id}",
                        f"near-threshold real case {near_threshold_case.metadata.case_id}",
                        f"FOV {near_threshold_case.metadata.fov_deg:.1f} deg",
                        f"MTF evidence reaches {near_field_label} field",
                        (
                            f"field stability improves from {current_field_label} to "
                            f"{near_field_label} versus the current high-FOV partial branch"
                        ),
                    ],
                    risks=[
                        (
                            f"requested FOV is reduced by about "
                            f"{design_strategy_decision.target_fov_deg - near_threshold_case.metadata.fov_deg:.1f} deg"
                        ),
                        (
                            f"candidate remains below the {_ULTRAWIDE_FOV_MIN:.1f} deg "
                            "full-field seed-acquisition threshold"
                            if near_threshold_case.metadata.fov_deg < _ULTRAWIDE_FOV_MIN
                            else "candidate still lacks full-field MTF evidence"
                        ),
                        "full-field edge-performance claims remain forbidden",
                    ],
                )
            )
        if (
            design_strategy_decision is not None
            and relaxed_option is not None
            and relaxed_case is not None
            and relaxed_case.metadata is not None
        ):
            fov_gap = design_strategy_decision.full_field_fov_gap_deg
            candidates.append(
                DraftCandidate(
                    candidate_id="relaxed-fov-full-field",
                    source="strategy_option",
                    strategy_option_id=relaxed_option.option_id,
                    status="fallback",
                    recommendation="continue",
                    summary=(
                        "fallback full-field draft if the requester accepts relaxing FOV "
                        f"from {design_strategy_decision.target_fov_deg:.1f} deg to "
                        f"{relaxed_case.metadata.fov_deg:.1f} deg"
                    ),
                    metrics=metrics_for_case(relaxed_case),
                    evidence=[
                        f"strategy option {relaxed_option.option_id}",
                        f"full-field real case {relaxed_case.metadata.case_id}",
                        f"FOV {relaxed_case.metadata.fov_deg:.1f} deg",
                        "MTF evidence reaches "
                        f"{format_mtf_field_fraction(relaxed_case.metadata.mtf_max_field_frac)} field",
                    ],
                    risks=[
                        (
                            f"requested FOV is reduced by about {fov_gap:.1f} deg"
                            if fov_gap is not None
                            else "requested FOV is relaxed to match the nearest full-field seed"
                        ),
                        "target high-FOV geometry is no longer preserved on this fallback branch",
                    ],
                )
            )
        if (
            proxy_review_candidate is not None
            and proxy_review_case is not None
            and proxy_review_case.metadata is not None
            and proxy_selected_risk is not None
            and proxy_candidate_risk is not None
        ):
            proxy_rejected_for_target_fit = (
                candidate_proxy_branch_resolution is not None
                and candidate_proxy_branch_resolution.status == "rejected_for_target_fit"
                and candidate_proxy_branch_resolution.candidate_case_id
                == proxy_review_candidate.case_id
            )
            candidates.append(
                DraftCandidate(
                    candidate_id="low-risk-candidate-review",
                    source="candidate_proxy",
                    status="blocked" if proxy_rejected_for_target_fit else "fallback",
                    recommendation=(
                        "reject"
                        if proxy_rejected_for_target_fit
                        else "continue"
                        if cost_like
                        else "hold"
                    ),
                    summary=(
                        candidate_proxy_branch_resolution.summary
                        if proxy_rejected_for_target_fit
                        else (
                            "review lower-risk real seed before freezing the prescription "
                            f"when manufacturability, cost, or yield dominates: "
                            f"{proxy_review_candidate.case_id}"
                        )
                    ),
                    metrics=metrics_for_case(proxy_review_case),
                    evidence=_unique_in_order(
                        [
                            f"candidate role {proxy_review_candidate.role}",
                            f"case {proxy_review_candidate.case_id}",
                            f"review risk {proxy_candidate_risk:.2f} vs selected {proxy_selected_risk:.2f}",
                            (
                                f"tolerance {proxy_review_candidate.tolerance_risk_level}; "
                                f"process/yield {proxy_review_candidate.process_yield_level}"
                            ),
                            *(
                                candidate_proxy_branch_resolution.evidence
                                if proxy_rejected_for_target_fit
                                else []
                            ),
                        ]
                    )[:8],
                    risks=[
                        *(
                            candidate_proxy_branch_resolution.blockers
                            if proxy_rejected_for_target_fit
                            else proxy_review_candidate.tradeoffs[:2]
                        ),
                        (
                            "lower review-risk branch is rejected for target fit"
                            if proxy_rejected_for_target_fit
                            else "lower review-risk branch may sacrifice optical target fit"
                        ),
                    ],
                )
            )
        if optimization_attempt.variable_changes:
            gate_status = optimizer_gate.status if optimizer_gate is not None else "not_run"
            if gate_status == "passed" and optimizer_floor.status == "pass":
                status = "proposed"
            elif gate_status in {"passed", "warning"}:
                status = "warning"
            else:
                status = "diagnostic"
            metrics = optimizer_metrics
            evidence = [
                _changes_label(optimization_attempt.variable_changes),
                f"verification gate {gate_status}",
                f"MTF/RMS floor {optimizer_floor.status}",
                (
                    f"EFL miss improvement {optimization_attempt.improvement_efl_mm:.3f} mm"
                    if optimization_attempt.improvement_efl_mm is not None
                    else "EFL improvement not available"
                ),
            ]
            if promoted_merit_branch:
                evidence.extend(
                    [
                        f"merit changes {_changes_label(merit_changes)}",
                        (
                            f"verified RMS improvement "
                            f"{merit_optimization_probe.rms_improvement_um:.2f} um"
                            if merit_optimization_probe.rms_improvement_um is not None
                            else "verified RMS improvement unavailable"
                        ),
                    ]
                )
            candidates.append(
                DraftCandidate(
                    candidate_id=optimizer_id,
                    source="protected_optimizer",
                    status=status,
                    recommendation="continue" if optimizer_recommended else "hold",
                    summary=(
                        ("recommended protected optimizer branch with promoted local merit changes")
                        if optimizer_recommended and promoted_merit_branch
                        else "recommended protected optimizer branch"
                        if optimizer_recommended
                        else "hold for more verification before using as the draft branch"
                    ),
                    metrics=metrics,
                    evidence=evidence,
                    risks=[
                        *(
                            [
                                "optimizer branch does not clear the 0-250 lp/mm MTF/RMS floor",
                                *optimizer_floor.blockers[:2],
                            ]
                            if optimizer_floor.status != "pass"
                            else []
                        ),
                        (
                            optimizer_gate.summary
                            if optimizer_gate is not None and optimizer_gate.status != "passed"
                            else "proposal still requires full tolerancing before release"
                        ),
                    ],
                )
            )
        recommended = optimizer_id if optimizer_recommended else seed_id
        return candidates, recommended

    draft_candidates, recommended_candidate_id = _draft_candidates()

    def _recommended_candidate_metrics() -> OptimizationMetricSnapshot | None:
        return next(
            (
                candidate.metrics
                for candidate in draft_candidates
                if candidate.candidate_id == recommended_candidate_id
                and candidate.metrics is not None
            ),
            None,
        )

    recommended_image_quality_floor = _evaluate_image_quality_floor(
        _recommended_candidate_metrics()
    )
    recommended_image_quality_recovery_objective = _image_quality_recovery_objective(
        _recommended_candidate_metrics()
    )

    def _branch_selection_policy() -> DraftBranchSelectionPolicy | None:
        candidate_ids = {candidate.candidate_id for candidate in draft_candidates}
        if design_strategy_decision is None:
            if "fov-spec-reconciliation" in candidate_ids:
                if spec_repair_auto_closure is not None:
                    priority_order = _unique_in_order(
                        [
                            recommended_candidate_id,
                            "optimizer-proposal",
                            "fov-spec-reconciliation",
                            "fov-waiver-review",
                            "seed-baseline",
                            "fov-target-seed-needed",
                        ]
                    )
                    priority_order = [
                        candidate_id
                        for candidate_id in priority_order
                        if candidate_id in candidate_ids
                    ]
                    blocked_ids = [
                        candidate.candidate_id
                        for candidate in draft_candidates
                        if candidate.status == "blocked"
                    ]
                    fallback_ids = [
                        candidate.candidate_id
                        for candidate in draft_candidates
                        if candidate.status in {"fallback", "conditional"}
                    ]
                    return DraftBranchSelectionPolicy(
                        status="resolved",
                        active_candidate_id=recommended_candidate_id,
                        primary_candidate_id=recommended_candidate_id,
                        current_deliverable_candidate_id=recommended_candidate_id,
                        candidate_priority_order=priority_order,
                        blocked_candidate_ids=_unique_in_order(blocked_ids),
                        fallback_candidate_ids=_unique_in_order(fallback_ids),
                        summary=(
                            "minor target-spec repair is auto-closed for first-pass "
                            "review; remaining FOV tradeoff is disclosed as a review note"
                        ),
                        rationale=_unique_in_order(
                            [
                                spec_repair_auto_closure.summary,
                                *spec_repair_auto_closure.rationale,
                                *spec_repair_auto_closure.evidence[:3],
                                (
                                    f"active candidate {recommended_candidate_id} remains "
                                    "the review payload; selected prescription is unchanged"
                                ),
                            ]
                        )[:10],
                        promotion_requirements=[],
                        forbidden_claims=list(spec_repair_auto_closure.forbidden_claims[:4]),
                    )
                floor_clean_trial = _floor_clean_full_field_recovery_trial()
                if (
                    floor_clean_trial is not None
                    and not cost_like
                    and "full-field-floor-clean-recovery-candidate" in candidate_ids
                ):
                    priority_order = _unique_in_order(
                        [
                            "full-field-floor-clean-recovery-candidate",
                            "fov-spec-reconciliation",
                            recommended_candidate_id,
                            "fov-waiver-review",
                            "fov-target-seed-needed",
                            "optimizer-proposal",
                            "seed-baseline",
                        ]
                    )
                    priority_order = [
                        candidate_id
                        for candidate_id in priority_order
                        if candidate_id in candidate_ids
                    ]
                    blocked_ids = [
                        candidate.candidate_id
                        for candidate in draft_candidates
                        if candidate.status == "blocked"
                    ]
                    fallback_ids = [
                        candidate.candidate_id
                        for candidate in draft_candidates
                        if candidate.status in {"fallback", "conditional", "baseline"}
                        and candidate.candidate_id != "full-field-floor-clean-recovery-candidate"
                    ]
                    metrics = floor_clean_trial.metrics
                    recovery_quality = (
                        f"MTF/RMS floor min={metrics.mtf_multiband_min_score:.3f}, "
                        f"weighted={metrics.mtf_field_weighted_score:.3f}, "
                        f"RMS={metrics.max_rms_spot_radius_um:.2f}um"
                        if metrics is not None
                        and metrics.mtf_multiband_min_score is not None
                        and metrics.mtf_field_weighted_score is not None
                        and metrics.max_rms_spot_radius_um is not None
                        else "MTF/RMS floor clears on the recovery branch"
                    )
                    return DraftBranchSelectionPolicy(
                        status="strategy_resolution_required",
                        active_candidate_id=recommended_candidate_id,
                        primary_candidate_id="full-field-floor-clean-recovery-candidate",
                        current_deliverable_candidate_id=recommended_candidate_id,
                        candidate_priority_order=priority_order,
                        blocked_candidate_ids=_unique_in_order(blocked_ids),
                        fallback_candidate_ids=_unique_in_order(fallback_ids),
                        summary=(
                            "MTF-first review order: close the floor-clean 1.0-field "
                            "recovery branch before recording the target-spec repair "
                            "decision or promoting any payload change"
                        ),
                        rationale=_unique_in_order(
                            [
                                "user priority is MTF/RMS first for the phone main-camera draft",
                                (
                                    "full-field recovery candidate reaches "
                                    f"{format_mtf_field_fraction(floor_clean_trial.mtf_max_field_frac or 0.0)} field"
                                ),
                                "full-field recovery floor gap=0.000",
                                recovery_quality,
                                (
                                    "protected changes="
                                    f"{_changes_label(floor_clean_trial.variable_changes)}"
                                ),
                                "requested EFL/image-height/FOV triad still needs a recorded target-spec decision after MTF recovery",
                                *(
                                    list(fov_spec_repair_replay.evidence[:3])
                                    if fov_spec_repair_replay is not None
                                    else []
                                ),
                                (
                                    f"active candidate {recommended_candidate_id} remains "
                                    "the current payload because the protected branch has "
                                    "not been signed as the delivered prescription"
                                ),
                            ]
                        )[:10],
                        promotion_requirements=[
                            "run the full-field recovery replay gate before target-spec closeout",
                            (
                                fov_spec_default_repair[1]
                                if fov_spec_default_repair is not None
                                else "record a repaired target EFL or image height, or explicitly waive the original FOV target"
                            ),
                            "sign the slower-aperture and 4P-vs-requested-5P tradeoffs before replacing the seed payload",
                            "apply the protected recovery change-set only to a cloned prescription",
                            "rerun paraxial, 1.0-field MTF/RMS, manufacturability, and tolerance checks before promotion",
                        ],
                        forbidden_claims=[
                            "delivered payload already contains the protected recovery changes",
                            "original target EFL, image height, and FOV claimed as simultaneously satisfied",
                            "target-spec repair recorded before the MTF-first recovery evidence is closed",
                            "production-ready performance claim before tolerance review",
                        ],
                    )
                priority_order = _unique_in_order(
                    [
                        "fov-spec-reconciliation",
                        recommended_candidate_id,
                        "optimizer-proposal",
                        "fov-target-seed-needed",
                        "fov-waiver-review",
                        "seed-baseline",
                    ]
                )
                priority_order = [
                    candidate_id for candidate_id in priority_order if candidate_id in candidate_ids
                ]
                blocked_ids = [
                    candidate.candidate_id
                    for candidate in draft_candidates
                    if candidate.status == "blocked"
                ]
                fallback_ids = [
                    candidate.candidate_id
                    for candidate in draft_candidates
                    if candidate.status in {"fallback", "conditional"}
                    and candidate.candidate_id != "fov-spec-reconciliation"
                ]
                return DraftBranchSelectionPolicy(
                    status="strategy_resolution_required",
                    active_candidate_id=recommended_candidate_id,
                    primary_candidate_id="fov-spec-reconciliation",
                    current_deliverable_candidate_id=recommended_candidate_id,
                    candidate_priority_order=priority_order,
                    blocked_candidate_ids=_unique_in_order(blocked_ids),
                    fallback_candidate_ids=_unique_in_order(fallback_ids),
                    summary=(
                        "target-spec repair must be resolved before the optimizer-first "
                        "payload branch can be treated as the primary draft path"
                    ),
                    rationale=_unique_in_order(
                        [
                            "requested EFL/image-height/FOV triad is first-order inconsistent",
                            *(
                                [fov_spec_default_repair[0], fov_spec_default_repair[2]]
                                if fov_spec_default_repair is not None
                                else []
                            ),
                            *(
                                list(fov_spec_repair_replay.evidence[:4])
                                if fov_spec_repair_replay is not None
                                else []
                            ),
                            (
                                f"active candidate {recommended_candidate_id} remains the "
                                "current payload branch until the target-spec decision is made"
                            ),
                            *(
                                [fov_spec_consistency.summary]
                                if fov_spec_consistency is not None
                                else []
                            ),
                            *(
                                list(fov_spec_consistency.evidence[:3])
                                if fov_spec_consistency is not None
                                else []
                            ),
                        ]
                    )[:10],
                    promotion_requirements=[
                        (
                            fov_spec_default_repair[1]
                            if fov_spec_default_repair is not None
                            else "choose a repaired target EFL or repaired image height, or explicitly waive the original FOV target"
                        ),
                        (
                            "review the repaired-target replay coverage preview and record remaining tradeoffs"
                            if fov_spec_repair_replay is not None
                            else "rerun seed scoring and requirement coverage after the repaired target is chosen"
                        ),
                        "do not promote optimizer or seed-ingestion branches before the target-spec decision is recorded",
                    ],
                    forbidden_claims=[
                        "optimizer-first branch accepted before EFL/image-height/FOV reconciliation",
                        "original target EFL, image height, and FOV claimed as simultaneously satisfied",
                        "seed-library gap claimed before ruling out target-spec repair",
                    ],
                )
            if (
                performance_aperture_tradeoff_resolution is not None
                and "full-field-floor-clean-recovery-candidate" in candidate_ids
            ):
                priority_order = _unique_in_order(
                    [
                        "full-field-floor-clean-recovery-candidate",
                        recommended_candidate_id,
                        "seed-baseline",
                        "low-risk-candidate-review",
                        "optimizer-proposal",
                    ]
                )
                priority_order = [
                    candidate_id for candidate_id in priority_order if candidate_id in candidate_ids
                ]
                blocked_ids = [
                    candidate.candidate_id
                    for candidate in draft_candidates
                    if candidate.status == "blocked"
                ]
                fallback_ids = [
                    candidate.candidate_id
                    for candidate in draft_candidates
                    if candidate.status in {"fallback", "conditional"}
                    or candidate.candidate_id == recommended_candidate_id
                ]
                return DraftBranchSelectionPolicy(
                    status="strategy_resolution_required",
                    active_candidate_id=recommended_candidate_id,
                    primary_candidate_id="full-field-floor-clean-recovery-candidate",
                    current_deliverable_candidate_id=recommended_candidate_id,
                    candidate_priority_order=priority_order,
                    blocked_candidate_ids=_unique_in_order(blocked_ids),
                    fallback_candidate_ids=_unique_in_order(fallback_ids),
                    summary=(
                        "performance brief is conditionally routed to the floor-clean "
                        "full-field recovery branch, but the slower-aperture / lower-piece "
                        "tradeoff needs an explicit waiver before payload promotion"
                    ),
                    rationale=_unique_in_order(
                        [
                            performance_aperture_tradeoff_resolution.summary,
                            *performance_aperture_tradeoff_resolution.rationale,
                            *performance_aperture_tradeoff_resolution.evidence,
                            (
                                f"active candidate {recommended_candidate_id} remains the "
                                "unchanged seed payload until the protected recovery change-set "
                                "is applied to a clone"
                            ),
                        ]
                    )[:10],
                    promotion_requirements=[
                        *performance_aperture_tradeoff_resolution.promotion_requirements,
                        "apply the full-field recovery change-set only to a cloned prescription and rerun the replay gate",
                    ],
                    forbidden_claims=[
                        *performance_aperture_tradeoff_resolution.forbidden_claims,
                        "claiming the protected recovery changes are already in the delivered payload",
                    ],
                )
            if not cost_like or "low-risk-candidate-review" not in candidate_ids:
                floor_clean_trial = _floor_clean_full_field_recovery_trial()
                if (
                    performance_like
                    and floor_clean_trial is not None
                    and "full-field-floor-clean-recovery-candidate" in candidate_ids
                ):
                    priority_order = _unique_in_order(
                        [
                            "full-field-floor-clean-recovery-candidate",
                            recommended_candidate_id,
                            "optimizer-proposal",
                            "seed-baseline",
                            "low-risk-candidate-review",
                        ]
                    )
                    priority_order = [
                        candidate_id
                        for candidate_id in priority_order
                        if candidate_id in candidate_ids
                    ]
                    blocked_ids = [
                        candidate.candidate_id
                        for candidate in draft_candidates
                        if candidate.status == "blocked"
                    ]
                    fallback_ids = [
                        candidate.candidate_id
                        for candidate in draft_candidates
                        if candidate.status in {"fallback", "conditional", "baseline"}
                        and candidate.candidate_id != "full-field-floor-clean-recovery-candidate"
                    ]
                    metrics = floor_clean_trial.metrics
                    recovery_quality = (
                        f"MTF/RMS floor min={metrics.mtf_multiband_min_score:.3f}, "
                        f"weighted={metrics.mtf_field_weighted_score:.3f}, "
                        f"RMS={metrics.max_rms_spot_radius_um:.2f}um"
                        if metrics is not None
                        and metrics.mtf_multiband_min_score is not None
                        and metrics.mtf_field_weighted_score is not None
                        and metrics.max_rms_spot_radius_um is not None
                        else "MTF/RMS floor clears on the recovery branch"
                    )
                    return DraftBranchSelectionPolicy(
                        status="strategy_resolution_required",
                        active_candidate_id=recommended_candidate_id,
                        primary_candidate_id="full-field-floor-clean-recovery-candidate",
                        current_deliverable_candidate_id=recommended_candidate_id,
                        candidate_priority_order=priority_order,
                        blocked_candidate_ids=_unique_in_order(blocked_ids),
                        fallback_candidate_ids=_unique_in_order(fallback_ids),
                        summary=(
                            "performance intent should continue on the floor-clean "
                            "full-field recovery branch, while the delivered seed "
                            "payload stays frozen until aperture and element-count "
                            "tradeoffs are signed"
                        ),
                        rationale=_unique_in_order(
                            [
                                "priority/manufacturing tier is performance-like",
                                (
                                    "full-field recovery candidate reaches "
                                    f"{format_mtf_field_fraction(floor_clean_trial.mtf_max_field_frac or 0.0)} field"
                                ),
                                "full-field recovery floor gap=0.000",
                                recovery_quality,
                                (
                                    "protected changes="
                                    f"{_changes_label(floor_clean_trial.variable_changes)}"
                                ),
                                (
                                    f"active candidate {recommended_candidate_id} remains "
                                    "the current payload because the protected branch has "
                                    "not been signed as the delivered prescription"
                                ),
                            ]
                        )[:10],
                        promotion_requirements=[
                            "sign the slower-aperture tradeoff before replacing the seed payload",
                            "sign the 4P-vs-requested-5P element-count tradeoff before replacing the seed payload",
                            "apply the protected recovery change-set only to a cloned prescription",
                            "rerun paraxial, 1.0-field MTF/RMS, manufacturability, and tolerance checks before promotion",
                        ],
                        forbidden_claims=[
                            "delivered payload already contains the protected recovery changes",
                            "original F/1.8 aperture is satisfied by the recovery branch",
                            "requested 5P element count is satisfied by the 4P recovery branch",
                            "production-ready performance claim before tolerance review",
                        ],
                    )
                return None
            if (
                candidate_proxy_branch_resolution is not None
                and candidate_proxy_branch_resolution.status == "rejected_for_target_fit"
            ):
                priority_order = _unique_in_order(
                    [
                        recommended_candidate_id,
                        "optimizer-proposal",
                        "seed-baseline",
                        "low-risk-candidate-review",
                    ]
                )
                priority_order = [
                    candidate_id for candidate_id in priority_order if candidate_id in candidate_ids
                ]
                return DraftBranchSelectionPolicy(
                    status="resolved",
                    active_candidate_id=recommended_candidate_id,
                    primary_candidate_id=recommended_candidate_id,
                    current_deliverable_candidate_id=recommended_candidate_id,
                    candidate_priority_order=priority_order,
                    blocked_candidate_ids=["low-risk-candidate-review"],
                    fallback_candidate_ids=[
                        candidate_id
                        for candidate_id in ["seed-baseline", "low-risk-candidate-review"]
                        if candidate_id in candidate_ids
                    ],
                    summary=candidate_proxy_branch_resolution.summary,
                    rationale=_unique_in_order(
                        [
                            "priority or manufacturing tier is cost/consumer-like",
                            "candidate proxy review found a materially lower-risk real seed branch",
                            *candidate_proxy_branch_resolution.evidence,
                            *candidate_proxy_branch_resolution.blockers,
                        ]
                    )[:10],
                    promotion_requirements=[],
                    forbidden_claims=[
                        "production-ready process/yield claim",
                        "lower-risk candidate branch used despite unresolved hard target misses",
                    ],
                )
            priority_order = _unique_in_order(
                [
                    "low-risk-candidate-review",
                    recommended_candidate_id,
                    "optimizer-proposal",
                    "seed-baseline",
                ]
            )
            priority_order = [
                candidate_id for candidate_id in priority_order if candidate_id in candidate_ids
            ]
            return DraftBranchSelectionPolicy(
                status="strategy_resolution_required",
                active_candidate_id=recommended_candidate_id,
                primary_candidate_id="low-risk-candidate-review",
                current_deliverable_candidate_id=recommended_candidate_id,
                candidate_priority_order=priority_order,
                blocked_candidate_ids=[],
                fallback_candidate_ids=[
                    candidate_id
                    for candidate_id in [recommended_candidate_id, "seed-baseline"]
                    if candidate_id in candidate_ids and candidate_id != "low-risk-candidate-review"
                ],
                summary=(
                    "cost/yield-sensitive intent requires comparing the lower-risk "
                    "candidate branch before accepting the optimizer-first branch"
                ),
                rationale=[
                    "priority or manufacturing tier is cost/consumer-like",
                    "candidate proxy review found a materially lower-risk real seed branch",
                    (
                        f"active candidate {recommended_candidate_id} remains the current "
                        "payload branch until the lower-risk branch is reviewed"
                    ),
                ],
                promotion_requirements=[
                    "compare low-risk candidate EFL/FOV/F-number/TTL deltas against the selected branch",
                    "accept or reject the lower-risk branch before cost/yield-sensitive release claims",
                    "keep prescription changes on cloned branches until branch review is signed off",
                ],
                forbidden_claims=[
                    "cost/yield-preferred branch selected without candidate proxy review",
                    "production-ready process/yield claim",
                    "optimizer-first branch accepted for consumer tier without lower-risk seed comparison",
                ],
            )

        primary_id = (
            "high-fov-full-field-seed-needed"
            if "high-fov-full-field-seed-needed" in candidate_ids
            else design_strategy_decision.recommended_candidate_id
        )
        deliverable_id = (
            "partial-field-high-fov-draft"
            if "partial-field-high-fov-draft" in candidate_ids
            else recommended_candidate_id
        )
        priority_order = [
            candidate_id
            for candidate_id in [
                "high-fov-full-field-seed-needed",
                "stable-partial-field-sibling",
                "near-threshold-partial-field",
                "relaxed-fov-full-field",
                "partial-field-high-fov-draft",
                "low-risk-candidate-review",
                recommended_candidate_id,
                "optimizer-proposal",
            ]
            if candidate_id in candidate_ids
        ]
        blocked_ids = [
            candidate.candidate_id
            for candidate in draft_candidates
            if candidate.status == "blocked"
        ]
        fallback_ids = [
            candidate.candidate_id
            for candidate in draft_candidates
            if candidate.status in {"fallback", "conditional"}
        ]
        rationale = [
            f"selected strategy={design_strategy_decision.selected_strategy}",
            (
                f"active candidate {recommended_candidate_id} is the current payload branch, "
                "not a full-field approval"
            ),
            (
                f"primary candidate {primary_id} preserves requested high-FOV geometry but "
                "is blocked until reference evidence exists"
                if primary_id is not None
                else "primary candidate is unresolved"
            ),
            (
                f"current deliverable candidate {deliverable_id} is constrained by the delivery gate"
                if deliverable_id is not None
                else "current deliverable candidate is unresolved"
            ),
        ]
        if delivery_gate is not None:
            rationale.append(
                f"delivery gate={delivery_gate.status}/{delivery_gate.deliverable_type}"
            )
        return DraftBranchSelectionPolicy(
            status="strategy_resolution_required",
            active_candidate_id=recommended_candidate_id,
            primary_candidate_id=primary_id,
            current_deliverable_candidate_id=deliverable_id,
            candidate_priority_order=_unique_in_order(priority_order),
            blocked_candidate_ids=_unique_in_order(blocked_ids),
            fallback_candidate_ids=_unique_in_order(fallback_ids),
            summary=(
                "active payload remains a partial-field holding branch while the preferred "
                "full-field high-FOV strategy waits for seed evidence"
            ),
            rationale=_unique_in_order(rationale),
            promotion_requirements=(
                list(delivery_gate.promotion_requirements[:4])
                if delivery_gate is not None
                else list(design_strategy_decision.required_evidence[:4])
            ),
            forbidden_claims=(
                list(delivery_gate.forbidden_claims[:4]) if delivery_gate is not None else []
            ),
        )

    branch_selection_policy = _branch_selection_policy()

    def _strategy_tradeoff_matrix() -> list[DraftBranchTradeoffRow]:
        if not draft_candidates:
            return []

        candidates_by_id = {candidate.candidate_id: candidate for candidate in draft_candidates}
        options_by_id = (
            {option.option_id: option for option in design_strategy_decision.options}
            if design_strategy_decision is not None
            else {}
        )
        cases_by_id = {case.metadata.case_id: case for case in cases if case.metadata is not None}
        ordered_ids = (
            list(branch_selection_policy.candidate_priority_order)
            if branch_selection_policy is not None
            else []
        )
        ordered_ids.extend(candidate.candidate_id for candidate in draft_candidates)
        ordered_ids = [
            candidate_id
            for candidate_id in _unique_in_order(ordered_ids)
            if candidate_id in candidates_by_id
        ]

        def _role_tags(candidate_id: str) -> list[str]:
            tags: list[str] = []
            if branch_selection_policy is not None:
                if candidate_id == branch_selection_policy.primary_candidate_id:
                    tags.append("primary")
                if candidate_id == branch_selection_policy.active_candidate_id:
                    tags.append("active_payload")
                if candidate_id == branch_selection_policy.current_deliverable_candidate_id:
                    tags.append("current_deliverable")
                if candidate_id in branch_selection_policy.blocked_candidate_ids:
                    tags.append("blocked")
                if candidate_id in branch_selection_policy.fallback_candidate_ids:
                    tags.append("fallback")
            if candidate_id == recommended_candidate_id:
                tags.append("recommended_payload")
            candidate = candidates_by_id[candidate_id]
            if not tags:
                tags.append(candidate.recommendation)
            return _unique_in_order(tags)

        def _case_for_candidate(
            candidate: DraftCandidate,
            option: DesignStrategyOption | None,
        ) -> OpticalSampleData | None:
            case_id = option.candidate_id if option is not None else None
            if case_id is None and candidate.source in {
                "seed_baseline",
                "protected_optimizer",
            }:
                case_id = best.metadata.case_id
            return cases_by_id.get(case_id) if case_id is not None else None

        def _field_value(
            candidate: DraftCandidate,
            option: DesignStrategyOption | None,
            case: OpticalSampleData | None,
        ) -> tuple[
            str | None,
            float | None,
            float | None,
            float | None,
            float | None,
            float | None,
            int | None,
            float | None,
        ]:
            metrics = candidate.metrics
            case_id = (
                case.metadata.case_id
                if case is not None and case.metadata is not None
                else option.candidate_id
                if option is not None
                else None
            )
            fov = (
                option.fov_deg
                if option is not None and option.fov_deg is not None
                else case.metadata.fov_deg
                if case is not None and case.metadata is not None
                else None
            )
            mtf_field = (
                metrics.mtf_max_field_frac
                if metrics is not None and metrics.mtf_max_field_frac is not None
                else option.mtf_max_field_frac
                if option is not None
                else None
            )
            efl = (
                metrics.effective_focal_length_mm
                if metrics is not None and metrics.effective_focal_length_mm is not None
                else case.metadata.computed_efl_mm
                if case is not None and case.metadata is not None
                else efl_mm
                if option is not None and option.evidence_status == "needs_seed"
                else None
            )
            f_number = (
                metrics.f_number
                if metrics is not None and metrics.f_number is not None
                else case.paraxial.f_number
                if case is not None
                else fnum
                if option is not None and option.evidence_status == "needs_seed"
                else None
            )
            total_track = (
                metrics.total_track_mm
                if metrics is not None and metrics.total_track_mm is not None
                else case.paraxial.total_track_mm
                if case is not None
                else max_total_track_mm
                if option is not None and option.evidence_status == "needs_seed"
                else None
            )
            image_height = (
                _case_image_height_mm(case)
                if case is not None
                else image_height_mm
                if option is not None and option.evidence_status == "needs_seed"
                else None
            )
            pieces = (
                case.metadata.n_pieces
                if case is not None and case.metadata is not None
                else n_elements
                if option is not None and option.evidence_status == "needs_seed"
                else None
            )
            return case_id, fov, efl, f_number, image_height, total_track, pieces, mtf_field

        def _evidence_level(
            candidate: DraftCandidate,
            option: DesignStrategyOption | None,
            mtf_field: float | None,
        ) -> str:
            if option is not None and option.evidence_status == "needs_seed":
                return "missing_seed"
            if candidate.source == "protected_optimizer":
                return "optimizer_probe"
            if option is not None and option.evidence_status == "full_field_available":
                return "full_field"
            if option is not None and option.evidence_status == "partial_field_only":
                return "partial_field"
            if mtf_field is not None and mtf_field >= 0.999:
                return "full_field"
            if mtf_field is not None:
                return "partial_field"
            return "review_required"

        def _claim_status(
            candidate: DraftCandidate,
            option: DesignStrategyOption | None,
            evidence_level: str,
        ) -> str:
            if evidence_level == "missing_seed":
                return "blocked_until_reference_seed"
            if option is not None and option.option_id == "relax_fov_to_full_field_seed":
                return "full_field_available_if_fov_relaxed"
            if evidence_level == "partial_field":
                return "partial_field_only_no_edge_claim"
            if candidate.status in {"blocked", "conditional", "warning", "diagnostic"}:
                return "review_or_evidence_required"
            return "full_field_evidence_available"

        def _tradeoff_summary(
            candidate: DraftCandidate,
            option: DesignStrategyOption | None,
        ) -> str:
            parts = []
            if option is not None:
                parts.append(option.spec_impact)
                parts.extend(option.tradeoffs[:1])
            parts.append(candidate.summary)
            return "; ".join(_unique_in_order(parts))

        def _next_action(
            candidate: DraftCandidate,
            option: DesignStrategyOption | None,
        ) -> str:
            if option is not None and option.required_evidence:
                return option.required_evidence[0]
            if (
                candidate.status == "blocked"
                and branch_selection_policy is not None
                and branch_selection_policy.promotion_requirements
            ):
                return branch_selection_policy.promotion_requirements[0]
            if candidate.risks:
                return candidate.risks[0]
            if (
                branch_selection_policy is not None
                and branch_selection_policy.promotion_requirements
            ):
                return branch_selection_policy.promotion_requirements[0]
            return candidate.summary

        rows: list[DraftBranchTradeoffRow] = []
        for rank, candidate_id in enumerate(ordered_ids, start=1):
            candidate = candidates_by_id[candidate_id]
            option = (
                options_by_id.get(candidate.strategy_option_id)
                if candidate.strategy_option_id is not None
                else None
            )
            case = _case_for_candidate(candidate, option)
            (
                case_id,
                actual_fov,
                actual_efl,
                actual_f_number,
                actual_image_height,
                actual_total_track,
                actual_pieces,
                mtf_field,
            ) = _field_value(candidate, option, case)
            evidence_level = _evidence_level(candidate, option, mtf_field)
            rows.append(
                DraftBranchTradeoffRow(
                    priority_rank=rank,
                    candidate_id=candidate.candidate_id,
                    source=candidate.source,
                    strategy_option_id=candidate.strategy_option_id,
                    role_tags=_role_tags(candidate.candidate_id),
                    status=candidate.status,
                    recommendation=candidate.recommendation,
                    case_id=case_id,
                    fov_deg=actual_fov,
                    delta_fov_deg=(actual_fov - fov_deg if actual_fov is not None else None),
                    efl_mm=actual_efl,
                    delta_efl_mm=(actual_efl - efl_mm if actual_efl is not None else None),
                    f_number=actual_f_number,
                    image_height_mm=actual_image_height,
                    total_track_mm=actual_total_track,
                    n_pieces=actual_pieces,
                    mtf_max_field_frac=mtf_field,
                    evidence_level=evidence_level,
                    claim_status=_claim_status(candidate, option, evidence_level),
                    tradeoff_summary=_tradeoff_summary(candidate, option),
                    next_action=_next_action(candidate, option),
                )
            )
        return rows

    strategy_tradeoff_matrix = _strategy_tradeoff_matrix()

    def _reference_influence_audit() -> ReferenceInfluenceAudit:
        selected_reference_id = best.metadata.case_id
        supporting_ids = [selected_reference_id]
        constraining_ids: list[str] = []
        rejected_ids: list[str] = []
        data_gaps: list[str] = []
        notes = [
            (
                f"selected real reference {selected_reference_id} supplies materials, "
                f"paraxial data, ray trace, and MTF to "
                f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)} field"
            ),
            f"match score={score:.3f}; normalized distance={distance:.3f}",
        ]
        forbidden_claims = [
            "reference match alone is not a regenerated optical prescription",
            "do not claim production readiness without tolerance and yield evidence",
        ]
        status = "supported"
        confidence = 0.88 if score >= 0.85 else 0.72
        safe_next_action = (
            f"continue from {selected_reference_id} as the real seed while keeping "
            "optimizer changes protected until review"
        )

        if spec_repair_auto_closure is not None:
            notes.append(spec_repair_auto_closure.summary)
            notes.extend(spec_repair_auto_closure.evidence[:2])
            forbidden_claims.extend(spec_repair_auto_closure.forbidden_claims[:2])

        if fov_alternative_branch_resolution is not None:
            resolution = fov_alternative_branch_resolution
            if resolution.status == "rejected_for_target_fit":
                rejected_ids.append(resolution.candidate_case_id)
                notes.append(resolution.summary)
                notes.extend(resolution.blockers[:2])
            elif resolution.status == "review_required":
                constraining_ids.append(resolution.candidate_case_id)
                status = "conflicted"
                confidence = min(confidence, 0.68)
                safe_next_action = resolution.summary

        if candidate_proxy_branch_resolution is not None:
            resolution = candidate_proxy_branch_resolution
            if resolution.status == "rejected_for_target_fit":
                rejected_ids.append(resolution.candidate_case_id)
                notes.append(resolution.summary)
                notes.extend(resolution.blockers[:2])

        if library_coverage_diagnostic is not None:
            diagnostic = library_coverage_diagnostic
            if diagnostic.nearest_full_field_case_id is not None:
                constraining_ids.append(diagnostic.nearest_full_field_case_id)
            if diagnostic.nearest_high_fov_case_id is not None:
                supporting_ids.append(diagnostic.nearest_high_fov_case_id)
            if diagnostic.status == "gap":
                status = "constrained" if status != "conflicted" else status
                confidence = min(confidence, 0.62)
                data_gaps.extend(
                    [
                        "no high-FOV visible-light seed currently proves MTF at 1.0 field",
                        diagnostic.recommended_strategy,
                    ]
                )
                notes.extend(diagnostic.evidence[:4])
                safe_next_action = diagnostic.recommended_strategy
                forbidden_claims.append(
                    "do not use partial-field reference evidence for a full-field edge claim"
                )

        if branch_selection_policy is not None:
            notes.append(branch_selection_policy.summary)
            if branch_selection_policy.status == "strategy_resolution_required":
                status = "constrained" if status != "conflicted" else status
                confidence = min(confidence, 0.64)
                data_gaps.extend(branch_selection_policy.promotion_requirements[:2])
                if branch_selection_policy.promotion_requirements:
                    safe_next_action = branch_selection_policy.promotion_requirements[0]
                forbidden_claims.extend(branch_selection_policy.forbidden_claims[:2])

        if delivery_gate is not None:
            notes.append(delivery_gate.summary)
            data_gaps.extend(delivery_gate.promotion_requirements[:2])
            forbidden_claims.extend(delivery_gate.forbidden_claims[:2])

        if requirement_coverage_summary is not None and requirement_coverage_summary.miss_count:
            status = "conflicted"
            confidence = min(confidence, 0.55)
            data_gaps.append(requirement_coverage_summary.summary)
            safe_next_action = (
                "do not promote this reference branch until hard requirement misses are closed"
            )

        status_label = {
            "supported": "reference library supports this starting point",
            "constrained": "reference library constrains the draft boundary",
            "conflicted": "reference evidence conflicts and needs branch review",
        }[status]
        summary = (
            f"{status_label}: selected {selected_reference_id}; "
            f"{len(rejected_ids)} rejected reference branch(es), "
            f"{len(data_gaps)} data gap(s)"
        )

        return ReferenceInfluenceAudit(
            status=status,
            selected_reference_id=selected_reference_id,
            confidence=round(confidence, 3),
            summary=summary,
            supporting_reference_ids=_unique_in_order(supporting_ids),
            constraining_reference_ids=_unique_in_order(constraining_ids),
            rejected_reference_ids=_unique_in_order(rejected_ids),
            data_gaps=_unique_in_order(data_gaps)[:6],
            influence_notes=_unique_in_order(notes)[:8],
            safe_next_action=safe_next_action,
            forbidden_claims=_unique_in_order(forbidden_claims)[:6],
        )

    reference_influence_audit = _reference_influence_audit()

    def _prescription_change_set() -> PrescriptionChangeSet | None:
        full_field_recovery_trial = _floor_clean_full_field_recovery_trial()
        if full_field_recovery_trial is not None:
            metrics = full_field_recovery_trial.metrics
            metric_summary = (
                f"MTF/RMS floor min {metrics.mtf_multiband_min_score:.3f}, "
                f"weighted {metrics.mtf_field_weighted_score:.3f}, "
                f"RMS {metrics.max_rms_spot_radius_um:.2f} um"
                if metrics is not None
                and metrics.mtf_multiband_min_score is not None
                and metrics.mtf_field_weighted_score is not None
                and metrics.max_rms_spot_radius_um is not None
                else "MTF/RMS floor clears on the recovery branch"
            )
            return PrescriptionChangeSet(
                source_candidate_id="full-field-floor-clean-recovery-candidate",
                changes=list(full_field_recovery_trial.variable_changes),
                expected_effect=(
                    "recover full-field MTF evidence to 1.0 and clear the "
                    f"first-pass MTF/RMS floor; {metric_summary}"
                ),
                application_policy=(
                    "not applied to delivered payload; apply only to a cloned "
                    "full-field recovery branch after the replay gate passes and "
                    "aperture/element-count tradeoffs are reviewed"
                ),
                verification_checklist=[
                    "apply the listed recovery changes only to a cloned prescription",
                    "recompute paraxial EFL, F-number, and total track after applying the delta",
                    "rerun finite ray trace and MTF through the 1.0 field",
                    "confirm the MTF/RMS floor gap remains 0.0",
                    "review the remaining F-number and element-count tradeoffs before payload promotion",
                    "run tolerance sensitivity before external release",
                ],
            )
        if optimization_attempt.status != "proposal" or not optimization_attempt.variable_changes:
            return None
        gate = optimization_attempt.verification
        merit_changes = _promoted_merit_changes()
        changes = [*optimization_attempt.variable_changes, *merit_changes]
        optimizer_metrics = (
            merit_optimization_probe.after_metrics
            if merit_changes
            else optimization_attempt.after_metrics
        )
        optimizer_floor = _evaluate_image_quality_floor(optimizer_metrics)
        if gate is None or gate.status != "passed" or optimizer_floor.status != "pass":
            return None
        checklist = [
            "apply the listed variable changes only to a cloned prescription",
            "recompute paraxial EFL, F-number, and total track after applying the delta",
            "rerun finite ray trace on sampled chief and marginal rays",
            "compare max RMS spot before/after the change",
            "run tolerance sensitivity before external release",
        ]
        if gate is not None and gate.status == "warning":
            checklist.insert(3, "recover MTF at the full 1.0 field before promoting the branch")
        else:
            checklist.insert(3, "confirm MTF remains finite at the verification-gate field set")
        improvement = optimization_attempt.improvement_efl_mm
        if merit_changes and merit_optimization_probe.rms_improvement_um is not None:
            first_order_effect = (
                f"reduce first-order EFL miss by {improvement:.3f} mm"
                if improvement is not None
                else "reduce first-order EFL miss"
            )
            expected_effect = (
                f"{first_order_effect}; reduce verified RMS by "
                f"{merit_optimization_probe.rms_improvement_um:.2f} um"
            )
        else:
            expected_effect = (
                f"reduce first-order EFL miss by {improvement:.3f} mm"
                if improvement is not None
                else "reduce first-order EFL miss"
            )
        return PrescriptionChangeSet(
            source_candidate_id="optimizer-proposal",
            changes=changes,
            expected_effect=expected_effect,
            application_policy=(
                "not applied to delivered payload; apply only to the optimizer-proposal clone "
                "after the verification checklist passes"
            ),
            verification_checklist=checklist,
        )

    prescription_change_set = _prescription_change_set()

    def _manufacturing_sensitivity_audit() -> ManufacturingSensitivityAudit:
        factors: list[ManufacturingSensitivityFactor] = []
        best_review_proxy = _candidate_review_proxy(best)

        def _check_factor_status(check: ManufacturabilityCheck) -> tuple[str, str]:
            if check.status == "blocker":
                return "blocked", "high"
            if check.status == "warning":
                return "watch", "medium"
            return "pass", "low"

        def add_factor(
            factor_id: str,
            label: str,
            status: str,
            sensitivity: str,
            source: str,
            metric: str,
            evidence: list[str],
            next_action: str,
        ) -> None:
            factors.append(
                ManufacturingSensitivityFactor(
                    factor_id=factor_id,
                    label=label,
                    status=status,
                    sensitivity=sensitivity,
                    source=source,
                    metric=metric,
                    evidence=_unique_in_order([item for item in evidence if item])[:6],
                    next_action=next_action,
                )
            )

        proxy_source_ids = {"tolerance_risk_proxy", "process_yield_proxy", "mass_proxy_budget"}
        for check in manufacturability_review.checks:
            if check.status == "not_applicable":
                continue
            status, sensitivity = _check_factor_status(check)
            source = (
                "candidate_review_proxy"
                if check.check_id in proxy_source_ids
                else "manufacturability_review"
            )
            evidence = [f"target={check.target}", *check.evidence]
            if check.check_id in {"tolerance_risk_proxy", "process_yield_proxy"}:
                evidence.extend(best_review_proxy.notes[:3])
            next_action = check.mitigation or (
                f"keep {check.label.lower()} inside the current pass band during protected replay"
            )
            add_factor(
                check.check_id,
                check.label,
                status,
                sensitivity,
                source,
                check.actual,
                evidence,
                next_action,
            )

        if guarded_asphere_candidates:
            first_asphere = guarded_asphere_candidates[0]
            asphere_evidence = [
                f"guarded asphere candidates={len(guarded_asphere_candidates)}",
                f"merit probe={merit_optimization_probe.status}",
                f"S{first_asphere.surface_index}:c{first_asphere.coefficient_index}",
            ]
            if first_asphere.edge_sag_delta_um is not None:
                asphere_evidence.append(f"edge sag delta={first_asphere.edge_sag_delta_um:.2f} um")
            if first_asphere.edge_slope_delta_mrad is not None:
                asphere_evidence.append(
                    f"edge slope delta={first_asphere.edge_slope_delta_mrad:.2f} mrad"
                )
            add_factor(
                "guarded_asphere_coefficients",
                "Guarded asphere coefficients",
                "watch",
                "medium",
                "protected_merit_probe",
                f"{len(guarded_asphere_candidates)} audited-only coefficient(s)",
                asphere_evidence,
                "keep asphere coefficient edits audit-only until slope/sag and tolerance replay pass",
            )

        if prescription_change_set is not None:
            change_labels = [
                f"{change.variable} S{change.surface_index} {change.delta:+.4g}"
                for change in prescription_change_set.changes[:4]
            ]
            add_factor(
                "protected_prescription_change_set",
                "Protected prescription change set",
                "watch",
                "medium",
                "optimizer_proposal",
                f"{len(prescription_change_set.changes)} variable change(s)",
                [
                    prescription_change_set.application_policy,
                    *change_labels,
                    *prescription_change_set.verification_checklist[:4],
                ],
                "replay the protected change set with paraxial, ray, MTF, and tolerance checks before release",
            )

        severity_rank = {"pass": 0, "watch": 1, "risk": 2, "blocked": 3}
        actionable_factors = [
            factor for factor in factors if severity_rank.get(factor.status, 0) > 0
        ]
        dominant_factor = (
            max(actionable_factors, key=lambda factor: severity_rank.get(factor.status, 0))
            if actionable_factors
            else None
        )
        max_severity = (
            max(severity_rank.get(factor.status, 0) for factor in factors) if factors else 0
        )
        if max_severity >= 3:
            audit_status = "blocked"
        elif max_severity >= 2 or len(actionable_factors) >= 3:
            audit_status = "risk"
        elif actionable_factors:
            audit_status = "watch"
        else:
            audit_status = "clear"

        required_evidence: list[str] = []
        if actionable_factors:
            required_evidence.extend(factor.next_action for factor in actionable_factors[:5])
            factor_ids = {factor.factor_id for factor in actionable_factors}
            if {
                "tolerance_risk_proxy",
                "minimum_axial_spacing",
                "minimum_curvature_radius",
            } & factor_ids:
                required_evidence.append(
                    "run first-order tolerance sensitivity or Monte Carlo replay before release claims"
                )
            if {"process_yield_proxy", "material_diversity", "mass_proxy_budget"} & factor_ids:
                required_evidence.append(
                    "obtain supplier/process review before cost, yield, or mass claims"
                )
            if "guarded_asphere_coefficients" in factor_ids:
                required_evidence.append(
                    "keep guarded asphere coefficients out of the payload until slope/sag audit passes"
                )
            if "protected_prescription_change_set" in factor_ids:
                required_evidence.append(
                    "apply optimizer deltas only to a cloned branch and replay all verification gates"
                )

        if audit_status == "clear":
            summary = (
                "clear: first-pass geometry, tolerance, and process proxies are low sensitivity"
            )
            confidence = 0.86
            safe_next_action = (
                "carry current manufacturing pass evidence into review; no immediate sensitivity "
                "closure is required"
            )
        elif audit_status == "watch":
            summary = (
                f"watch: {len(actionable_factors)} manufacturing-sensitive factor(s) "
                f"need review; dominant={dominant_factor.factor_id if dominant_factor else 'none'}"
            )
            confidence = 0.78
            safe_next_action = actionable_factors[0].next_action
        elif audit_status == "risk":
            summary = (
                f"risk: {len(actionable_factors)} manufacturing-sensitive factor(s) "
                "compound before release"
            )
            confidence = 0.72
            safe_next_action = (
                dominant_factor.next_action
                if dominant_factor is not None
                else "run manufacturing sensitivity review before release"
            )
        else:
            summary = (
                f"blocked: {len(actionable_factors)} manufacturing-sensitive factor(s) "
                "must be closed by branch change"
            )
            confidence = 0.66
            safe_next_action = (
                dominant_factor.next_action
                if dominant_factor is not None
                else "select a less sensitive seed before release"
            )

        return ManufacturingSensitivityAudit(
            status=audit_status,
            confidence=confidence,
            summary=summary,
            dominant_factor_id=dominant_factor.factor_id if dominant_factor else None,
            factors=factors,
            required_evidence=_unique_in_order(required_evidence)[:7],
            safe_next_action=safe_next_action,
            limitations=[
                "deterministic first-pass audit; not a Monte-Carlo tolerance simulation",
                "process/yield sensitivity is inferred from geometry, materials, tier, and proxy scores",
                "optimizer and asphere factors are protected evidence and are not applied to payload",
                "supplier limits, molded part CAD, spacer stack, and active alignment data are not modeled",
            ],
        )

    manufacturing_sensitivity_audit = _manufacturing_sensitivity_audit()

    def _manufacturing_clearance_checklist() -> ManufacturingClearanceChecklist:
        severity_rank = {"pass": 0, "watch": 1, "risk": 2, "blocked": 3}
        actionable_factors = [
            factor
            for factor in manufacturing_sensitivity_audit.factors
            if severity_rank.get(factor.status, 0) > 0
        ]

        def _slug(value: str) -> str:
            return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:56] or "item"

        def _owner_for_factor(factor_id: str) -> str:
            if any(
                key in factor_id for key in ("process", "yield", "material", "mass", "supplier")
            ):
                return "manufacturing_engineer"
            if "asphere" in factor_id or "curvature" in factor_id:
                return "optical_designer + manufacturing_engineer"
            return "optical_designer"

        def _required_evidence_for_factor(factor: ManufacturingSensitivityFactor) -> list[str]:
            factor_id = factor.factor_id
            if factor_id == "minimum_axial_spacing":
                return [
                    "first-order tolerance sensitivity at the current minimum air gap",
                    "spacer/process capability review for the recorded gap",
                    "post-optimization check that no protected edit reduces the minimum gap",
                ]
            if factor_id == "minimum_curvature_radius":
                return [
                    "curvature manufacturability review for the tightest radius",
                    "bounded radius replay proving the radius does not cross the process floor",
                ]
            if factor_id == "tolerance_risk_proxy":
                return [
                    "first-order tolerance sensitivity or Monte Carlo replay",
                    "dominant surface/gap sensitivity ranking",
                    "reviewer sign-off that proxy tolerance risk is acceptable",
                ]
            if factor_id == "process_yield_proxy":
                return [
                    "supplier/process review for the proposed stack complexity",
                    "yield-risk acceptance note or branch change recommendation",
                ]
            if factor_id == "material_diversity":
                return [
                    "material availability and substitution review",
                    "supplier confirmation for uncommon material families",
                ]
            if factor_id == "mass_proxy_budget":
                return [
                    "module-level CAD or supplier mass estimate",
                    "reserve check against the requested mass budget",
                ]
            if factor_id == "guarded_asphere_coefficients":
                return [
                    "sag/slope audit for every guarded coefficient",
                    "tolerance replay before any coefficient reaches the delivered payload",
                ]
            if factor_id == "protected_prescription_change_set":
                return [
                    "cloned-branch replay of protected optimizer deltas",
                    "paraxial, ray, MTF, tolerance, and packaging gate rerun",
                ]
            return [factor.next_action]

        def _validation_steps_for_factor(factor: ManufacturingSensitivityFactor) -> list[str]:
            factor_id = factor.factor_id
            if factor_id in {"minimum_axial_spacing", "tolerance_risk_proxy"}:
                return [
                    "extract current finite surface spacings",
                    "run tolerance sensitivity or Monte Carlo replay",
                    "record dominant tolerance contributor and pass/fail margin",
                ]
            if factor_id == "minimum_curvature_radius":
                return [
                    "extract finite curved radii",
                    "compare against preferred and hard process floors",
                    "rerun bounded radius proposal if curvature is touched",
                ]
            if factor_id in {"process_yield_proxy", "material_diversity"}:
                return [
                    "send material/process stack to manufacturing review",
                    "record supplier limitation or approval note",
                    "rerun acceptance gate if the stack changes",
                ]
            if factor_id == "mass_proxy_budget":
                return [
                    "replace optical-stack mass proxy with module estimate",
                    "rerun the mass-budget check",
                ]
            if factor_id == "guarded_asphere_coefficients":
                return [
                    "run sag/slope audit for guarded asphere trials",
                    "rerun tolerance and MTF gates before payload promotion",
                ]
            if factor_id == "protected_prescription_change_set":
                return [
                    "apply changes only on a cloned prescription",
                    "rerun paraxial, ray trace, MTF, and acceptance gates",
                ]
            return ["record reviewer evidence", "rerun fixed design-agent eval"]

        def _acceptance_criteria_for_factor(factor: ManufacturingSensitivityFactor) -> list[str]:
            factor_id = factor.factor_id
            if factor_id == "minimum_axial_spacing":
                return [
                    "minimum spacing remains above the protected hard floor",
                    "tolerance replay identifies no unaccepted gap sensitivity blocker",
                ]
            if factor_id == "minimum_curvature_radius":
                return [
                    "minimum finite radius stays above the process floor",
                    "radius sensitivity is accepted or branch is changed",
                ]
            if factor_id in {"tolerance_risk_proxy", "process_yield_proxy"}:
                return [
                    "proxy warning is replaced by recorded review evidence",
                    "draft acceptance gate remains ready_for_review or records a branch change",
                ]
            if factor_id in {"material_diversity", "mass_proxy_budget"}:
                return [
                    "supplier/module estimate confirms the current branch or rejects it explicitly",
                ]
            if factor_id in {"guarded_asphere_coefficients", "protected_prescription_change_set"}:
                return [
                    "all protected edits pass replay gates before any payload mutation",
                    "forbidden production claims remain blocked until replay passes",
                ]
            return ["review evidence is recorded and the checklist item is closed"]

        def _item_status_for_factor(factor: ManufacturingSensitivityFactor) -> str:
            if factor.status == "blocked":
                return "blocked"
            if factor.factor_id in {
                "process_yield_proxy",
                "material_diversity",
                "mass_proxy_budget",
            }:
                return "external_evidence_required"
            return "ready"

        items: list[ManufacturingClearanceItem] = []
        for factor in actionable_factors:
            item_status = _item_status_for_factor(factor)
            priority = (
                1
                if factor.status == "blocked"
                or factor.factor_id == manufacturing_sensitivity_audit.dominant_factor_id
                else 2
                if factor.status == "risk"
                else 3
            )
            item_id = f"{priority}-{_slug(factor.factor_id)}"
            items.append(
                ManufacturingClearanceItem(
                    item_id=item_id,
                    source_factor_id=factor.factor_id,
                    priority=priority,
                    status=item_status,
                    owner_role=_owner_for_factor(factor.factor_id),
                    clearance_objective=factor.next_action,
                    required_evidence=_required_evidence_for_factor(factor)[:4],
                    validation_steps=_validation_steps_for_factor(factor)[:4],
                    acceptance_criteria=_acceptance_criteria_for_factor(factor)[:4],
                    current_evidence=_unique_in_order(
                        [
                            f"{factor.label}: {factor.status}/{factor.sensitivity}",
                            f"metric={factor.metric}",
                            *factor.evidence,
                        ]
                    )[:6],
                    next_action=factor.next_action,
                    blocks_review=factor.status == "blocked",
                    blocks_production_claims=True,
                )
            )

        items.sort(key=lambda item: (item.priority, item.item_id))
        review_blocking_count = sum(item.blocks_review for item in items)
        production_blocking_count = sum(item.blocks_production_claims for item in items)
        external_dependency_count = sum(
            item.status == "external_evidence_required" for item in items
        )
        dominant_item = items[0] if items else None
        if review_blocking_count:
            checklist_status = "blocked"
            summary = (
                f"{review_blocking_count} manufacturing clearance item(s) block review; "
                f"{production_blocking_count} production-claim item(s) remain"
            )
        elif production_blocking_count:
            checklist_status = "production_evidence_required"
            summary = (
                f"{production_blocking_count} manufacturing clearance item(s) must close "
                "before manufacturability, yield, or production claims strengthen"
            )
        else:
            checklist_status = "clear"
            summary = "no manufacturing-sensitive clearance item is active for this draft"

        next_action = (
            dominant_item.next_action
            if dominant_item is not None
            else "carry clear manufacturing proxy evidence into human review"
        )
        forbidden_claims = [
            "do not claim production-ready manufacturability from proxy evidence alone",
            "do not claim measured yield without supplier/process evidence",
            "do not apply protected optimizer/asphere edits without replaying clearance gates",
        ]
        if checklist_status == "blocked":
            forbidden_claims.append(
                "do not hand off as manufacturing-review-ready until blockers close"
            )
        return ManufacturingClearanceChecklist(
            status=checklist_status,
            summary=summary,
            dominant_item_id=dominant_item.item_id if dominant_item is not None else None,
            items=items[:8],
            review_blocking_count=review_blocking_count,
            production_blocking_count=production_blocking_count,
            external_dependency_count=external_dependency_count,
            next_clearance_action=next_action,
            forbidden_claims=forbidden_claims,
        )

    manufacturing_clearance_checklist = _manufacturing_clearance_checklist()

    def _tolerance_sensitivity_audit() -> ToleranceSensitivityAudit:
        items: list[ToleranceSensitivityItem] = []
        review_proxy = _candidate_review_proxy(best)

        def _score_status(score: float) -> str:
            if score >= 0.90:
                return "blocked"
            if score >= 0.70:
                return "risk"
            if score >= 0.32:
                return "watch"
            return "pass"

        def _add_item(
            *,
            item_id: str,
            label: str,
            variable_type: str,
            sensitivity_score: float,
            surface_index: int | None,
            coupled_surface_index: int | None = None,
            nominal_value: str,
            perturbation: str,
            margin: str,
            evidence: list[str],
            next_action: str,
        ) -> None:
            score_value = max(0.0, min(1.0, sensitivity_score))
            items.append(
                ToleranceSensitivityItem(
                    item_id=item_id,
                    label=label,
                    variable_type=variable_type,
                    status=_score_status(score_value),
                    sensitivity_score=round(score_value, 3),
                    surface_index=surface_index,
                    coupled_surface_index=coupled_surface_index,
                    nominal_value=nominal_value,
                    perturbation=perturbation,
                    margin=margin,
                    evidence=_unique_in_order([item for item in evidence if item])[:6],
                    next_action=next_action,
                )
            )

        finite_surfaces = [
            surface
            for surface in best.surfaces
            if math.isfinite(surface.z_mm) and abs(surface.z_mm) < 1e8 and not surface.is_object
        ]
        gap_candidates: list[tuple[float, int, int]] = []
        for before, after in zip(finite_surfaces, finite_surfaces[1:], strict=False):
            gap = after.z_mm - before.z_mm
            if gap > 1e-4:
                gap_candidates.append((gap, before.index, after.index))
        if gap_candidates:
            gap, before_index, after_index = min(gap_candidates, key=lambda item: item[0])
            if gap < 0.025:
                gap_score = 0.95
            elif gap < 0.05:
                gap_score = 0.76
            elif gap < 0.08:
                gap_score = 0.56
            elif gap < 0.10:
                gap_score = 0.34
            else:
                gap_score = 0.14
            _add_item(
                item_id="minimum-air-gap",
                label="Minimum air gap",
                variable_type="air_gap",
                sensitivity_score=gap_score,
                surface_index=before_index,
                coupled_surface_index=after_index,
                nominal_value=f"{gap:.3f} mm",
                perturbation="+/-0.010 mm first-order spacing watch",
                margin=f"{gap - 0.025:+.3f} mm above protected hard floor",
                evidence=[
                    f"S{before_index}->S{after_index}",
                    "preferred first-pass reserve >=0.080 mm",
                    "protected hard floor 0.025 mm",
                    f"selected seed={best.metadata.case_id}",
                ],
                next_action=(
                    "run spacing tolerance replay around the minimum air gap before release claims"
                    if gap_score >= 0.32
                    else "preserve minimum air gap during local optimization"
                ),
            )

        radius_candidates = [
            (abs(surface.radius_mm), surface.index)
            for surface in best.surfaces
            if math.isfinite(surface.radius_mm)
            and 0.02 < abs(surface.radius_mm) < 1e8
            and not surface.is_object
            and not surface.is_image
        ]
        if radius_candidates:
            radius, surface_index = min(radius_candidates, key=lambda item: item[0])
            if radius < 0.30:
                radius_score = 0.92
            elif radius < 0.50:
                radius_score = 0.72
            elif radius < 0.75:
                radius_score = 0.42
            elif radius < 1.00:
                radius_score = 0.28
            else:
                radius_score = 0.12
            _add_item(
                item_id="minimum-curvature-radius",
                label="Minimum curvature radius",
                variable_type="curvature_radius",
                sensitivity_score=radius_score,
                surface_index=surface_index,
                nominal_value=f"{radius:.3f} mm",
                perturbation="+/-1.0% radius first-order watch",
                margin=f"{radius - 0.50:+.3f} mm vs preferred radius floor",
                evidence=[
                    f"S{surface_index}",
                    "preferred first-pass radius >=0.500 mm",
                    "radius edits must stay bounded before merit tuning",
                ],
                next_action=(
                    "request curvature process review before touching the tightest radius"
                    if radius_score >= 0.32
                    else "keep radius variables bounded during replay"
                ),
            )

        aperture_score = 0.12
        if best.paraxial.f_number <= 1.70:
            aperture_score = 0.74
        elif best.paraxial.f_number <= 1.85:
            aperture_score = 0.58
        elif best.paraxial.f_number <= 2.10:
            aperture_score = 0.38
        _add_item(
            item_id="aperture-tolerance-coupling",
            label="Aperture tolerance coupling",
            variable_type="aperture",
            sensitivity_score=aperture_score,
            surface_index=None,
            nominal_value=f"F/{best.paraxial.f_number:.2f}",
            perturbation="+/-0.05 F-number review band",
            margin=f"{best.paraxial.f_number - 1.85:+.2f} F/# vs fast-aperture watch line",
            evidence=[
                "faster apertures narrow tolerance margin before MTF review",
                f"MTF field={format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}",
                f"pieces={best.metadata.n_pieces}P",
            ],
            next_action=(
                "compare aperture tradeoff against tolerance and MTF sensitivity"
                if aperture_score >= 0.32
                else "carry aperture as low-sensitivity review context"
            ),
        )

        plastic_count = _plastic_material_count(best)
        material_count = len(best.metadata.materials)
        stack_score = min(
            1.0,
            (0.20 if best.metadata.n_pieces >= 5 else 0.08 if best.metadata.n_pieces == 4 else 0.0)
            + (0.18 if plastic_count >= 3 else 0.08 if plastic_count else 0.0)
            + (0.16 if material_count >= 5 else 0.08 if material_count == 4 else 0.02),
        )
        _add_item(
            item_id="material-stack-coupling",
            label="Material / stack coupling",
            variable_type="material_stack",
            sensitivity_score=stack_score,
            surface_index=None,
            nominal_value=f"{best.metadata.n_pieces}P / {material_count} material families",
            perturbation="supplier/process capability review",
            margin=f"plastic families={plastic_count}",
            evidence=[
                ", ".join(best.metadata.materials[:5]),
                "stack complexity couples tolerance and yield risk",
                f"process proxy={review_proxy.process_yield_level}",
            ],
            next_action=(
                "obtain supplier/process review for stack complexity before yield claims"
                if stack_score >= 0.32
                else "keep stack complexity in review notes"
            ),
        )

        field_score = 0.08 if best.metadata.mtf_max_field_frac >= 1.0 else 0.82
        _add_item(
            item_id="field-coverage-sensitivity",
            label="Field coverage sensitivity",
            variable_type="field_coverage",
            sensitivity_score=field_score,
            surface_index=None,
            nominal_value=f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)} field",
            perturbation="field-edge ray aiming replay",
            margin=(
                "full-field MTF evidence present"
                if best.metadata.mtf_max_field_frac >= 1.0
                else "full-field MTF evidence missing"
            ),
            evidence=[
                "full-field MTF is required before edge-performance claims",
                f"seed MTF field={format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}",
            ],
            next_action=(
                "recover 1.0-field MTF before edge-performance claims"
                if best.metadata.mtf_max_field_frac < 1.0
                else "preserve full-field MTF evidence during tolerance replay"
            ),
        )

        items.sort(key=lambda item: (-item.sensitivity_score, item.item_id))
        dominant = items[0] if items else None
        actionable_count = sum(item.status != "pass" for item in items)
        has_blocker = any(item.status == "blocked" for item in items)
        has_risk = any(item.status == "risk" for item in items)
        if has_blocker:
            status_value = "blocked"
            confidence = 0.66
        elif has_risk or actionable_count >= 3:
            status_value = "risk"
            confidence = 0.72
        elif actionable_count:
            status_value = "watch"
            confidence = 0.78
        else:
            status_value = "clear"
            confidence = 0.86

        summary = (
            f"{status_value}: dominant {dominant.label} "
            f"{dominant.sensitivity_score:.2f} ({dominant.nominal_value})"
            if dominant is not None
            else "clear: no first-order tolerance contributors detected"
        )
        safe_next_action = (
            dominant.next_action
            if dominant is not None and dominant.status != "pass"
            else "carry first-order tolerance watch list into human review"
        )

        return ToleranceSensitivityAudit(
            status=status_value,
            confidence=confidence,
            summary=summary,
            dominant_item_id=dominant.item_id if dominant is not None else None,
            items=items[:6],
            pass_criteria=[
                "no air gap crosses the 0.025 mm protected hard floor",
                "tightest radius stays above the process floor or has review sign-off",
                "full-field MTF evidence remains present after any tolerance replay",
                "production claims wait for Monte-Carlo or supplier/process evidence",
            ],
            safe_next_action=safe_next_action,
            limitations=[
                "first-order deterministic watch list; not a Monte-Carlo tolerance simulation",
                "does not perturb the delivered seed prescription",
                "uses serialized surface spacing/radius, aperture, material, and field-coverage proxies",
                "supplier process capability, active alignment, and molded-part CAD are not modeled",
            ],
        )

    tolerance_sensitivity_audit = _tolerance_sensitivity_audit()

    branch_selection_resolved = (
        branch_selection_policy is None or branch_selection_policy.status == "resolved"
    )

    hard_requirement_tradeoff_ids = {
        item.requirement_id
        for item in requirement_coverage
        if item.status in {"miss", "unscored"}
        or (item.status == "tradeoff" and item.priority in {"critical", "important"})
    }
    if spec_repair_auto_closure is not None:
        hard_requirement_tradeoff_ids.difference_update(
            spec_repair_auto_closure.accepted_tradeoff_ids
        )
    if performance_aperture_tradeoff_resolution is not None:
        hard_requirement_tradeoff_ids.difference_update(
            performance_aperture_tradeoff_resolution.accepted_tradeoff_ids
        )
        if (
            prescription_change_set is not None
            and prescription_change_set.source_candidate_id
            == "full-field-floor-clean-recovery-candidate"
            and _floor_clean_full_field_recovery_trial() is not None
        ):
            hard_requirement_tradeoff_ids.discard("mtf_field_evidence")

    seed_baseline_hold_reviewable = (
        recommended_candidate_id == "seed-baseline"
        and delivery_gate is None
        and branch_selection_resolved
        and prescription_change_set is None
        and requirement_coverage_summary is not None
        and requirement_coverage_summary.status in {"met", "tradeoff"}
        and not hard_requirement_tradeoff_ids
        and manufacturability_review.status != "blocked"
        and best.metadata.mtf_max_field_frac >= 1.0
        and optimization_attempt.status in {"not_attempted", "diagnostic_only"}
        and not optimization_attempt.variable_changes
        and merit_optimization_probe.status == "not_attempted"
        and not merit_optimization_probe.variable_changes
    )

    seed_baseline_first_order_locked_for_floor_recovery = (
        recommended_candidate_id == "seed-baseline"
        and delivery_gate is None
        and branch_selection_resolved
        and prescription_change_set is None
        and requirement_coverage_summary is not None
        and requirement_coverage_summary.status in {"met", "tradeoff"}
        and not hard_requirement_tradeoff_ids
        and manufacturability_review.status != "blocked"
        and best.metadata.mtf_max_field_frac >= 1.0
        and not optimization_attempt.variable_changes
        and abs(delta_efl) <= 0.10
        and abs(delta_fnum) <= 0.10
        and recommended_image_quality_floor.status == "blocker"
        and merit_optimization_probe.probe_purpose == "image_quality_floor_recovery"
    )

    optimizer_proposal_reviewable = (
        recommended_candidate_id == "optimizer-proposal"
        and delivery_gate is None
        and branch_selection_resolved
        and prescription_change_set is not None
        and requirement_coverage_summary is not None
        and requirement_coverage_summary.status in {"met", "tradeoff"}
        and not hard_requirement_tradeoff_ids
        and manufacturability_review.status != "blocked"
        and optimization_attempt.status == "proposal"
        and optimization_attempt.verification is not None
        and optimization_attempt.verification.status == "passed"
        and best.metadata.mtf_max_field_frac >= 1.0
    )

    stable_sibling_strategy_option = (
        next(
            (
                option
                for option in design_strategy_decision.options
                if option.option_id == "stable_partial_field_sibling_seed"
                and option.candidate_id is not None
            ),
            None,
        )
        if design_strategy_decision is not None
        else None
    )
    stable_sibling_draft_candidate = next(
        (
            candidate
            for candidate in draft_candidates
            if candidate.candidate_id == "stable-partial-field-sibling"
        ),
        None,
    )

    def _replay_gate_failed_check_ids(
        trial: OptimizationVariableTrial | None,
    ) -> list[str]:
        if trial is None:
            return ["trial_available"]
        closure = trial.image_quality_floor_gap_closure
        after_gap = trial.image_quality_floor_gap_after
        rms_delta = trial.rms_improvement_um
        verification_status = trial.verification_status or "not_run"
        checks = [
            (
                "floor_gap_closure_positive",
                closure is not None and closure > 0.0,
            ),
            ("floor_gap_cleared", after_gap is not None and after_gap <= 0.0),
            ("rms_non_regressed", rms_delta is not None and rms_delta >= 0.0),
            ("mtf_multiband_non_regressed", trial.mtf_band_non_regressed is True),
            (
                "mtf_field_weighted_non_regressed",
                trial.mtf_field_weighted_non_regressed is True,
            ),
            ("first_order_locked", trial.efl_locked is True),
            ("verification_passed", verification_status == "passed"),
            ("payload_frozen", True),
        ]
        return [check_id for check_id, passed in checks if not passed]

    def _replay_gate_remediation_for_checks(
        failed_check_ids: list[str],
    ) -> tuple[list[str], list[str]]:
        remediation_by_check = {
            "trial_available": (
                list(recommended_image_quality_recovery_objective.variables),
                "select a bounded floor-gap recovery trial before replay gating",
            ),
            "floor_gap_closure_positive": (
                list(recommended_image_quality_recovery_objective.variables),
                "rerun floor-gap-first bounded search with the routed recovery variable priority",
            ),
            "floor_gap_cleared": (
                list(recommended_image_quality_recovery_objective.variables),
                "continue MTF/RMS floor recovery until the normalized floor gap reaches zero",
            ),
            "rms_non_regressed": (
                ["focus position", "air gaps", "radius", "stop position"],
                "prioritize RMS non-regression before accepting local MTF-only gains",
            ),
            "mtf_multiband_non_regressed": (
                ["asphere coefficients", "stop position", "air gaps"],
                "recover 50/100/150/200/250 lp/mm MTF before replay promotion",
            ),
            "mtf_field_weighted_non_regressed": (
                ["stop position", "air gaps", "asphere coefficients"],
                "recover field-weighted MTF before replay promotion",
            ),
            "first_order_locked": (
                ["effective focal length", "F-number", "total track"],
                "relock first-order targets before image-quality replay promotion",
            ),
            "verification_passed": (
                ["ray trace", "full-field MTF", "verification gate"],
                "rerun protected verification on the replay clone before promotion",
            ),
            "payload_frozen": (
                ["payload policy"],
                "restore payload-freeze policy before any replay promotion",
            ),
        }
        recommended_variables = _unique_in_order(
            [
                variable
                for check_id in failed_check_ids
                for variable in remediation_by_check.get(check_id, ([], ""))[0]
            ]
        )
        remediation_actions = _unique_in_order(
            [
                action
                for check_id in failed_check_ids
                for action in [remediation_by_check.get(check_id, ([], ""))[1]]
                if action
            ]
        )
        return recommended_variables, remediation_actions

    replay_gate_failed_check_ids = _replay_gate_failed_check_ids(floor_gap_recovery_trial)
    (
        replay_gate_recommended_variables,
        replay_gate_remediation_actions,
    ) = _replay_gate_remediation_for_checks(replay_gate_failed_check_ids)
    replay_gate_requires_remediation = floor_gap_recovery_trial is not None and bool(
        replay_gate_failed_check_ids
    )
    remediation_base_variables = tuple(
        replay_gate_recommended_variables
        or list(recommended_image_quality_recovery_objective.variables)
    )
    if (
        floor_gap_recovery_trial is not None
        and floor_gap_recovery_trial.variable
        in {"radius", "thickness", "stop_position", "focus_position"}
        and floor_gap_recovery_trial.after is not None
    ):
        remediation_baseline_variable_changes = (
            (
                floor_gap_recovery_trial.variable,
                floor_gap_recovery_trial.surface_index,
                floor_gap_recovery_trial.after,
            ),
        )
    elif (
        floor_gap_recovery_trial is not None
        and floor_gap_recovery_trial.variable == "compound_merit"
        and merit_optimization_probe.variable_changes
    ):
        remediation_baseline_variable_changes = tuple(
            (change.variable, change.surface_index, change.after)
            for change in merit_optimization_probe.variable_changes
            if change.variable in {"radius", "thickness", "stop_position", "focus_position"}
        )
    else:
        remediation_baseline_variable_changes = ()
    remediation_probe_before = (
        merit_optimization_probe.after_metrics
        if merit_optimization_probe.after_metrics is not None
        else merit_probe_before
    )
    remediation_optimization_probe = (
        protected_rms_merit_probe(
            source_zmx=best.metadata.source_zmx,
            nominal_fov_deg=best.metadata.fov_deg,
            target_efl_mm=efl_mm,
            max_total_track_mm=max_total_track_mm,
            radius_changes=merit_probe_radius_changes,
            before_effective_focal_length_mm=(
                remediation_probe_before.effective_focal_length_mm
                if remediation_probe_before
                else None
            ),
            before_f_number=(
                remediation_probe_before.f_number if remediation_probe_before else None
            ),
            before_total_track_mm=(
                remediation_probe_before.total_track_mm if remediation_probe_before else None
            ),
            before_mtf_max_field_frac=(
                remediation_probe_before.mtf_max_field_frac if remediation_probe_before else None
            ),
            before_mtf_bands=mtf_bands_from_snapshot(remediation_probe_before),
            before_max_rms_spot_radius_um=(
                remediation_probe_before.max_rms_spot_radius_um
                if remediation_probe_before
                else None
            ),
            baseline_variable_changes=remediation_baseline_variable_changes,
            variable_priority=remediation_base_variables,
            probe_purpose="replay_gate_remediation",
        )
        if replay_gate_requires_remediation
        and remediation_baseline_variable_changes
        and merit_probe_radius_changes
        else None
    )
    if remediation_optimization_probe is not None:
        rationale.append(
            f"ran replay-gate remediation probe: {remediation_optimization_probe.status}"
        )

    def _remediation_variable_key(variable: str) -> str:
        normalized = variable.strip().lower().replace("_", " ").replace("-", " ")
        if normalized in {"air gap", "air gaps", "thickness"}:
            return "thickness"
        if normalized in {"radius", "curvature radius", "surface radius"}:
            return "radius"
        if normalized in {"stop position", "stop"}:
            return "stop_position"
        if normalized in {
            "focus position",
            "image plane",
            "image plane position",
            "back focal distance",
        }:
            return "focus_position"
        if normalized in {"asphere", "asphere coefficient", "asphere coefficients"}:
            return "asphere_coefficient"
        return normalized.replace(" ", "_")

    def _switched_remediation_variables(
        variables: tuple[str, ...],
        baseline_changes: tuple[tuple[str, int, float], ...],
    ) -> tuple[str, ...]:
        if not variables or not baseline_changes:
            return variables
        exhausted_family = _remediation_variable_key(baseline_changes[0][0])
        preferred = [
            variable
            for variable in variables
            if _remediation_variable_key(variable) != exhausted_family
        ]
        deferred = [
            variable
            for variable in variables
            if _remediation_variable_key(variable) == exhausted_family
        ]
        switched = _unique_in_order([*preferred, *deferred])
        return tuple(switched or variables)

    def _remediation_continuation_policy() -> tuple[str, str, float | None, float | None]:
        recovery_candidate_gap_after = (
            floor_gap_recovery_trial.image_quality_floor_gap_after
            if floor_gap_recovery_trial is not None
            else None
        )
        if remediation_optimization_probe is None:
            return (
                "probe_not_attempted",
                "request a replayable single-variable recovery candidate or stronger seed evidence",
                recovery_candidate_gap_after,
                None,
            )

        second_pass_gap_after = _image_quality_floor_gap_score(
            remediation_optimization_probe.after_metrics
        )
        if second_pass_gap_after is None:
            return (
                "probe_inconclusive",
                "collect finite second-pass MTF/RMS evidence before choosing variables",
                recovery_candidate_gap_after,
                second_pass_gap_after,
            )
        if second_pass_gap_after <= 0.0:
            return (
                "candidate_ready_for_replay_gate",
                "promote the second-pass remediation candidate into guarded replay review",
                recovery_candidate_gap_after,
                second_pass_gap_after,
            )
        if recovery_candidate_gap_after is None:
            return (
                "probe_inconclusive",
                "collect finite held-candidate floor-gap evidence before choosing variables",
                recovery_candidate_gap_after,
                second_pass_gap_after,
            )
        if second_pass_gap_after < recovery_candidate_gap_after:
            return (
                "continue_second_pass_branch",
                "continue the second-pass remediation branch with the same variable priority",
                recovery_candidate_gap_after,
                second_pass_gap_after,
            )
        if second_pass_gap_after > recovery_candidate_gap_after:
            return (
                "switch_variable_family",
                "switch remediation search to the next variable family or request a stronger seed",
                recovery_candidate_gap_after,
                second_pass_gap_after,
            )
        return (
            "hold_no_second_pass_gain",
            "hold the remediation branch until a different variable family is available",
            recovery_candidate_gap_after,
            second_pass_gap_after,
        )

    (
        remediation_policy,
        remediation_policy_action,
        remediation_recovery_gap_after,
        remediation_second_pass_gap_after,
    ) = _remediation_continuation_policy()
    switched_remediation_variables = _switched_remediation_variables(
        remediation_base_variables,
        remediation_baseline_variable_changes,
    )
    remediation_downstream_variables = remediation_base_variables
    remediation_downstream_policy = remediation_policy
    remediation_downstream_unlocked = remediation_policy == "continue_second_pass_branch"
    if remediation_policy == "switch_variable_family":
        remediation_downstream_variables = switched_remediation_variables
        remediation_downstream_unlocked = (
            bool(remediation_downstream_variables)
            and remediation_downstream_variables != remediation_base_variables
        )
        if not remediation_downstream_unlocked:
            remediation_downstream_policy = "hold_no_alternative_variable_family"

    switched_remediation_optimization_probe = (
        protected_rms_merit_probe(
            source_zmx=best.metadata.source_zmx,
            nominal_fov_deg=best.metadata.fov_deg,
            target_efl_mm=efl_mm,
            max_total_track_mm=max_total_track_mm,
            radius_changes=merit_probe_radius_changes,
            before_effective_focal_length_mm=(
                remediation_probe_before.effective_focal_length_mm
                if remediation_probe_before
                else None
            ),
            before_f_number=(
                remediation_probe_before.f_number if remediation_probe_before else None
            ),
            before_total_track_mm=(
                remediation_probe_before.total_track_mm if remediation_probe_before else None
            ),
            before_mtf_max_field_frac=(
                remediation_probe_before.mtf_max_field_frac if remediation_probe_before else None
            ),
            before_mtf_bands=mtf_bands_from_snapshot(remediation_probe_before),
            before_max_rms_spot_radius_um=(
                remediation_probe_before.max_rms_spot_radius_um
                if remediation_probe_before
                else None
            ),
            baseline_variable_changes=remediation_baseline_variable_changes,
            variable_priority=remediation_downstream_variables,
            probe_purpose="replay_gate_remediation",
        )
        if replay_gate_requires_remediation
        and remediation_policy == "switch_variable_family"
        and remediation_downstream_unlocked
        else None
    )

    if (
        remediation_optimization_probe is not None
        and remediation_optimization_probe.status == "proposal"
        and remediation_optimization_probe.after_metrics is not None
        and remediation_optimization_probe.variable_changes
        and not any(
            candidate.candidate_id == "second-pass-recovery-candidate"
            for candidate in draft_candidates
        )
    ):
        second_pass_gap = _image_quality_floor_gap_score(
            remediation_optimization_probe.after_metrics
        )
        draft_candidates.append(
            DraftCandidate(
                candidate_id="second-pass-recovery-candidate",
                source="recovery_probe",
                status="warning",
                recommendation="hold",
                summary=(
                    "second-pass remediation branch has gate-clean MTF/RMS evidence; "
                    "hold until replay gate promotion"
                ),
                metrics=remediation_optimization_probe.after_metrics,
                evidence=_unique_in_order(
                    [
                        "source=replay_gate_remediation",
                        f"merit changes {_changes_label(remediation_optimization_probe.variable_changes)}",
                        (
                            f"second-pass floor gap={second_pass_gap:.3f}"
                            if second_pass_gap is not None
                            else "second-pass floor gap unavailable"
                        ),
                        (
                            f"RMS delta={remediation_optimization_probe.rms_improvement_um:+.2f}um"
                            if remediation_optimization_probe.rms_improvement_um is not None
                            else "RMS delta unavailable"
                        ),
                        *[
                            item
                            for item in remediation_optimization_probe.diagnostics
                            if item.startswith("compound continuation branch=")
                            or item.startswith("image-quality floor gap closure=")
                        ][:3],
                        "delivered payload not mutated",
                    ]
                )[:8],
                risks=[
                    "second-pass branch is not yet replay-gate promoted",
                    "recommended candidate metrics remain on the primary optimizer branch",
                    "keep payload frozen until replay checks and manufacturability review pass",
                ],
            )
        )

    def _remediation_resolution_packet() -> RemediationResolutionPacket:
        known_families = [
            "air gaps",
            "radius",
            "stop position",
            "focus position",
            "asphere coefficients",
            "field weighting",
        ]
        used_family_keys = {
            _remediation_variable_key(variable)
            for variable in [
                *remediation_base_variables,
                *remediation_downstream_variables,
            ]
        }
        alternate_families = [
            family
            for family in known_families
            if _remediation_variable_key(family) not in used_family_keys
        ]
        failed_checks = ", ".join(replay_gate_failed_check_ids) or "none"
        base_family_label = (
            ", ".join(remediation_base_variables) if remediation_base_variables else "none"
        )
        if seed_intake_audit is not None:
            seed_command = seed_intake_audit.candidate_preflight_command
            seed_required_evidence = _unique_in_order(
                [
                    *seed_intake_audit.missing_evidence[:4],
                    "accepted_seed_count must be greater than 0",
                    "candidate must appear in accepted_seed_candidates",
                ]
            )
            seed_status = "gap" if seed_intake_audit.status == "gap" else "available"
            seed_next_check = (
                "rerun candidate preflight and require seed_intake_audit.status=satisfied"
            )
            seed_evidence = (
                f"accepted {seed_intake_audit.accepted_seed_count}/"
                f"{seed_intake_audit.total_seed_count}; missing="
                + "; ".join(seed_intake_audit.missing_evidence[:2])
            )
        elif (
            design_strategy_decision is not None
            and design_strategy_decision.seed_acquisition_brief is not None
        ):
            brief = design_strategy_decision.seed_acquisition_brief
            seed_command = None
            seed_required_evidence = brief.validation_requirements[:4]
            seed_status = "manual_required"
            seed_next_check = "ingest candidate seed and rerun seed-intake audit"
            seed_evidence = (
                f"FOV>={brief.minimum_fov_deg:.1f} "
                f"EFL={brief.efl_window_mm[0]:.2f}-{brief.efl_window_mm[1]:.2f} "
                f"F#={brief.f_number_window[0]:.2f}-{brief.f_number_window[1]:.2f}"
            )
        else:
            seed_command = None
            seed_required_evidence = [
                "visible-light prescription with material metadata",
                "finite MTF/RMS replay evidence on a safer seed or cloned branch",
                "same brief target window remains traceable",
            ]
            seed_status = "manual_required"
            seed_next_check = "rerun fixed eval case after seed or clone evidence is available"
            seed_evidence = (
                f"case={best.metadata.case_id} FOV={fov_deg:.1f} EFL={efl_mm:.2f} F#={fnum:.2f}"
            )
        alternate_evidence = (
            [
                "candidate families=" + ", ".join(alternate_families),
                f"base families={base_family_label}",
            ]
            if alternate_families
            else [
                "no alternate family remains inside the current bounded probe",
                f"base families={base_family_label}",
            ]
        )
        replay_required_evidence = [
            "finite MTF/RMS metrics",
            "floor gap cleared",
            "MTF/RMS non-regression",
            "first-order lock",
            "payload remains frozen",
        ]
        paths = [
            RemediationResolutionPath(
                path_id="stronger-seed",
                label="Stronger seed or preflight evidence",
                status=seed_status,
                required_evidence=seed_required_evidence,
                command=seed_command,
                next_check=seed_next_check,
            ),
            RemediationResolutionPath(
                path_id="alternate-variable-family",
                label="Alternate variable-family probe",
                status="available" if alternate_families else "blocked",
                required_evidence=alternate_evidence,
                command=None,
                next_check=(
                    "rerun remediation probe with a variable family not exhausted by "
                    "the held baseline"
                ),
            ),
            RemediationResolutionPath(
                path_id="replay-evidence",
                label="Finite replay gate evidence",
                status="blocked" if replay_gate_failed_check_ids else "available",
                required_evidence=replay_required_evidence,
                command=None,
                next_check="rerun floor-gap-recovery-replay gate",
            ),
        ]
        evidence = _unique_in_order(
            [
                "resolution packet=remediation-policy-block",
                (
                    f"resolution path=stronger-seed; preflight={seed_command}"
                    if seed_command
                    else f"resolution path=stronger-seed; target={seed_evidence}"
                ),
                f"seed gap={seed_evidence}",
                (
                    "resolution path=alternate-variable-family; candidates="
                    f"{', '.join(alternate_families) if alternate_families else 'none available in current bounded probe'}"
                ),
                (
                    "alternate-variable-family rule=must differ from base families "
                    f"{base_family_label}"
                ),
                f"resolution path=replay-evidence; failed checks={failed_checks}",
                (
                    "replay evidence required=finite MTF/RMS metrics + floor-gap "
                    "clearance + non-regression + first-order lock"
                ),
                (
                    "resume criterion=policy changes to continue_second_pass_branch, "
                    "switch_variable_family, or candidate_ready_for_replay_gate"
                ),
            ]
        )
        return RemediationResolutionPacket(
            packet_id="remediation-policy-block",
            policy=remediation_downstream_policy,
            policy_action=remediation_policy_action,
            failed_check_ids=list(replay_gate_failed_check_ids),
            base_variables=list(remediation_base_variables),
            policy_selected_variables=list(remediation_downstream_variables),
            paths=paths,
            resume_criteria=[
                "policy changes to continue_second_pass_branch",
                "policy changes to switch_variable_family",
                "policy changes to candidate_ready_for_replay_gate",
            ],
            evidence=evidence,
        )

    def _optimization_task_queue() -> list[OptimizationTask]:
        tasks: list[OptimizationTask] = []

        def add(
            task_id: str,
            candidate_id: str,
            stage: str,
            status: str,
            objective: str,
            variables: list[str],
            entry_condition: str,
            stop_condition: str,
            verification: str,
            *,
            depends_on: list[str] | None = None,
            evidence: list[str] | None = None,
            resolution_packet: RemediationResolutionPacket | None = None,
        ) -> None:
            tasks.append(
                OptimizationTask(
                    task_id=task_id,
                    candidate_id=candidate_id,
                    stage=stage,
                    status=status,
                    objective=objective,
                    variables=variables,
                    entry_condition=entry_condition,
                    stop_condition=stop_condition,
                    verification=verification,
                    depends_on=depends_on or [],
                    evidence=evidence or [],
                    resolution_packet=resolution_packet,
                )
            )

        gate = optimization_attempt.verification
        gate_status = gate.status if gate is not None else "not_run"
        needs_full_field = best.metadata.mtf_max_field_frac < 1.0 or gate_status == "warning"
        has_application_delta = prescription_change_set is not None and bool(
            prescription_change_set.changes
        )
        floor_clean_full_field_trial = _floor_clean_full_field_recovery_trial()
        full_field_recovery_change_set_selected = (
            prescription_change_set is not None
            and prescription_change_set.source_candidate_id
            == "full-field-floor-clean-recovery-candidate"
            and floor_clean_full_field_trial is not None
        )
        strategy_blocks_full_field = design_strategy_decision is not None
        cost_yield_branch_review_required = (
            branch_selection_policy is not None
            and branch_selection_policy.status == "strategy_resolution_required"
            and branch_selection_policy.primary_candidate_id == "low-risk-candidate-review"
            and design_strategy_decision is None
        )
        spec_repair_branch_review_required = (
            branch_selection_policy is not None
            and branch_selection_policy.status == "strategy_resolution_required"
            and branch_selection_policy.primary_candidate_id
            in {
                "fov-spec-reconciliation",
                "full-field-floor-clean-recovery-candidate",
            }
            and spec_repair_preview is not None
            and spec_repair_decision is not None
            and design_strategy_decision is None
        )
        mtf_first_spec_repair_closeout = (
            spec_repair_branch_review_required
            and branch_selection_policy is not None
            and branch_selection_policy.primary_candidate_id
            == "full-field-floor-clean-recovery-candidate"
        )
        local_merit_dependencies = ["lock-first-order"]
        local_merit_status = "queued"
        local_merit_variables = [
            "focus position",
            "stop position",
            "air gaps",
            "asphere coefficients",
        ]
        local_merit_evidence = [
            (
                f"entry max RMS={optimization_attempt.after_metrics.max_rms_spot_radius_um:.2f} um"
                if optimization_attempt.after_metrics
                and optimization_attempt.after_metrics.max_rms_spot_radius_um is not None
                else "RMS target must be recomputed on the active branch"
            )
        ]

        def add_spec_repair_target_task(
            *,
            status: str,
            objective: str,
            entry_condition: str,
            depends_on: list[str] | None = None,
            evidence_prefix: list[str] | None = None,
        ) -> None:
            preview = spec_repair_preview
            policy = branch_selection_policy
            decision = spec_repair_decision
            contract = decision.rerun_contract if decision is not None else None
            if preview is None:
                return
            add(
                "record-spec-repair-target",
                "fov-spec-reconciliation",
                "target_spec_resolution",
                status,
                objective,
                ["target EFL", "image height", "FOV waiver", "branch selection"],
                entry_condition,
                (
                    "default repaired target is recorded, or image-height repair / "
                    "FOV waiver is explicitly chosen"
                ),
                "repaired-target replay coverage + rerun contract + recorded branch-selection decision",
                depends_on=depends_on,
                evidence=_unique_in_order(
                    [
                        *(evidence_prefix or []),
                        policy.summary if policy is not None else "",
                        *(policy.promotion_requirements if policy is not None else []),
                        (
                            f"default repaired EFL={preview.repaired_target_focal_length_mm:.2f} mm; "
                            f"image height={preview.repaired_target_image_height_mm:.2f} mm; "
                            f"FOV={preview.target_fov_deg:.1f} deg"
                            if preview.repaired_target_image_height_mm is not None
                            else (
                                f"default repaired EFL={preview.repaired_target_focal_length_mm:.2f} mm; "
                                f"FOV={preview.target_fov_deg:.1f} deg"
                            )
                        ),
                        (
                            "preview coverage="
                            f"{preview.coverage_summary.met_count} met / "
                            f"{preview.coverage_summary.tradeoff_count} tradeoff / "
                            f"{preview.coverage_summary.miss_count} miss"
                        ),
                        decision.decision_summary if decision is not None else "",
                        contract.query_summary if contract is not None else "",
                        *(contract.validation_checks if contract is not None else []),
                        *preview.remaining_tradeoffs,
                        *preview.evidence,
                    ]
                ),
            )

        if strategy_blocks_full_field:
            add(
                "resolve-design-strategy",
                design_strategy_decision.recommended_candidate_id or recommended_candidate_id,
                "strategy_decision",
                "ready",
                "select the evidence path before more local full-field recovery work",
                ["seed library", "FOV relaxation", "partial-field label"],
                "high-FOV full-field coverage gap is present",
                "one path is backed by new seed evidence, approved FOV relaxation, or an explicit partial-field label",
                "library coverage + full-field MTF evidence or report labeling contract",
                evidence=_unique_in_order(
                    [
                        design_strategy_decision.summary,
                        *design_strategy_decision.rationale,
                        *design_strategy_decision.required_evidence,
                        *(
                            f"option={option.option_id} candidate={option.candidate_id or 'new-seed'} "
                            f"FOV={option.fov_deg:.1f} field={format_mtf_field_fraction(option.mtf_max_field_frac)}"
                            for option in design_strategy_decision.options
                            if option.fov_deg is not None
                        ),
                        *(
                            [
                                "seed brief="
                                f"FOV>={design_strategy_decision.seed_acquisition_brief.minimum_fov_deg:.1f} "
                                f"EFL={design_strategy_decision.seed_acquisition_brief.efl_window_mm[0]:.2f}-"
                                f"{design_strategy_decision.seed_acquisition_brief.efl_window_mm[1]:.2f} "
                                f"F#={design_strategy_decision.seed_acquisition_brief.f_number_window[0]:.2f}-"
                                f"{design_strategy_decision.seed_acquisition_brief.f_number_window[1]:.2f}",
                                "seed validation="
                                + "; ".join(
                                    design_strategy_decision.seed_acquisition_brief.validation_requirements[
                                        :2
                                    ]
                                ),
                            ]
                            if design_strategy_decision.seed_acquisition_brief is not None
                            else []
                        ),
                        *(
                            [
                                f"delivery gate={delivery_gate.status}",
                                "allowed claims=" + "; ".join(delivery_gate.allowed_claims[:2]),
                                "forbidden claims=" + "; ".join(delivery_gate.forbidden_claims[:2]),
                            ]
                            if delivery_gate is not None
                            else []
                        ),
                    ]
                ),
            )

            if (
                stable_sibling_strategy_option is not None
                and stable_sibling_draft_candidate is not None
                and stable_sibling_strategy_option.mtf_max_field_frac is not None
            ):
                add(
                    "review-stable-sibling-branch",
                    "stable-partial-field-sibling",
                    "branch_review",
                    "queued",
                    (
                        "clone and review the more edge-stable high-FOV sibling "
                        "before choosing any payload replacement"
                    ),
                    [
                        "sibling seed prescription",
                        "edge-field scan",
                        "full-field promotion gate",
                    ],
                    "resolve-design-strategy records the sibling as an approved partial-field trade study",
                    (
                        "branch review either accepts the sibling as a partial-field "
                        "study or rejects it before any selected-payload replacement"
                    ),
                    (
                        "strategy tradeoff matrix + edge-field scan + canonical "
                        "1.0-field preflight result"
                    ),
                    depends_on=["resolve-design-strategy"],
                    evidence=_unique_in_order(
                        [
                            (f"strategy option={stable_sibling_strategy_option.option_id}"),
                            (f"sibling candidate={stable_sibling_strategy_option.candidate_id}"),
                            (
                                "sibling scanned field="
                                f"{format_mtf_field_fraction(stable_sibling_strategy_option.mtf_max_field_frac)}"
                            ),
                            (
                                "selected seed field="
                                f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}"
                            ),
                            "full-field promotion still requires >=85 deg / 1.0 field evidence",
                            *stable_sibling_draft_candidate.risks,
                        ]
                    ),
                )

        if spec_repair_branch_review_required and not mtf_first_spec_repair_closeout:
            add_spec_repair_target_task(
                status="ready",
                objective=(
                    "record the repaired target decision before promoting the "
                    "optimizer-first payload branch"
                ),
                entry_condition=(
                    "spec-repair preview is available and branch selection is unresolved"
                ),
            )

        if cost_yield_branch_review_required:
            add(
                "resolve-candidate-proxy-branch",
                "low-risk-candidate-review",
                "branch_review",
                "ready",
                "compare the lower-risk real seed against the optimizer-first branch before cost/yield-sensitive promotion",
                ["candidate proxy", "EFL/FOV/F-number deltas", "TTL", "process/yield risk"],
                "cost-like intent and a materially lower-risk candidate branch are both present",
                "one branch is accepted explicitly for first-pass review or the cost/yield claim is withheld",
                "candidate comparison + manufacturability proxy + requirement coverage",
                evidence=_unique_in_order(
                    [
                        branch_selection_policy.summary
                        if branch_selection_policy is not None
                        else "",
                        *(
                            branch_selection_policy.rationale
                            if branch_selection_policy is not None
                            else []
                        ),
                        *(
                            branch_selection_policy.promotion_requirements
                            if branch_selection_policy is not None
                            else []
                        ),
                    ]
                ),
            )

        if needs_full_field:
            recovery_variables = ["chief-ray aiming", "stop position", "edge-field rays"]
            recovery_candidate_id = recommended_candidate_id
            recovery_status = "blocked" if strategy_blocks_full_field else "ready"
            recovery_entry_condition = (
                "design strategy path has been resolved"
                if strategy_blocks_full_field
                else "MTF or optimizer verification does not currently prove the 1.0 field"
            )
            recovery_stop_condition = (
                "MTF evaluates without NaN at 1.0 field and ray trace remains finite"
            )
            if full_field_recovery_change_set_selected and floor_clean_full_field_trial is not None:
                recovery_candidate_id = "full-field-floor-clean-recovery-candidate"
                recovery_variables = _unique_in_order(
                    [
                        f"surface {change.surface_index} {change.variable}"
                        for change in floor_clean_full_field_trial.variable_changes
                    ]
                )
                recovery_entry_condition = "floor-clean compound field-extension trial is available as a structured change-set"
                recovery_stop_condition = (
                    "full-field recovery replay gate passes with floor gap 0.0 and payload frozen"
                )
            if (
                full_field_recovery_diagnostic is not None
                and "asphere" in full_field_recovery_diagnostic.recommended_variable_family
            ):
                recovery_variables.append("asphere coefficients (audit-only)")
            recovery_evidence = [
                f"seed MTF field={format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}",
                f"optimizer gate={gate_status}",
            ]
            if full_field_recovery_diagnostic is not None:
                recovery_evidence.extend(full_field_recovery_diagnostic.evidence[:8])
            if library_coverage_diagnostic is not None:
                recovery_evidence.extend(library_coverage_diagnostic.evidence[:4])
            add(
                "recover-full-field",
                recovery_candidate_id,
                "full_field_recovery",
                recovery_status,
                "recover stable edge-field evidence before accepting performance claims",
                recovery_variables,
                recovery_entry_condition,
                recovery_stop_condition,
                "full-field MTF + finite ray trace at 0.7 and 1.0 field",
                depends_on=["resolve-design-strategy"] if strategy_blocks_full_field else [],
                evidence=_unique_in_order(recovery_evidence),
            )

            if spec_repair_branch_review_required and mtf_first_spec_repair_closeout:
                add_spec_repair_target_task(
                    status="queued",
                    objective=(
                        "record the repaired target decision after the MTF-first "
                        "full-field recovery replay closes"
                    ),
                    entry_condition=(
                        "full-field recovery replay gate has passed and MTF-first "
                        "branch evidence is recorded"
                    ),
                    depends_on=["recover-full-field"],
                    evidence_prefix=[
                        "MTF-first order: recover-full-field precedes target-spec recording"
                    ],
                )

        if seed_baseline_hold_reviewable:
            add(
                "package-seed-baseline-review",
                recommended_candidate_id,
                "review_package",
                "ready",
                "package the unchanged real seed baseline as the first-pass review draft",
                ["paraxial summary", "MTF evidence", "surface table", "acceptance gate"],
                "requirements and manufacturability pass with no delivery or branch gate",
                "review package keeps the seed prescription unchanged and draft acceptance remains ready",
                "confirm requirement coverage, manufacturability, MTF evidence, and allowed claims",
                evidence=[
                    "unchanged seed-baseline is the accepted deliverable",
                    "no protected optimizer change is required for first-pass review",
                    f"acceptance candidate={recommended_candidate_id}",
                ],
            )
            first_order_dependency = ["package-seed-baseline-review"]
            first_order_candidate = recommended_candidate_id
        elif optimizer_proposal_reviewable:
            add(
                "package-optimizer-proposal-review",
                recommended_candidate_id,
                "review_package",
                "ready",
                "package the verified optimizer proposal as the first-pass review draft",
                ["prescription change set", "verification gate", "metric deltas", "review notes"],
                "protected optimizer proposal has passed full-field verification and no hard acceptance warnings remain",
                "review package carries the protected change set without mutating the selected seed payload",
                "confirm change-set policy, verification gate, metric deltas, and allowed claims",
                evidence=[
                    "optimizer-proposal is the reviewable draft candidate",
                    "protected change set remains unapplied to the delivered payload",
                    f"verification gate={gate_status}",
                    f"acceptance candidate={recommended_candidate_id}",
                ],
            )
            first_order_dependency = ["package-optimizer-proposal-review"]
            first_order_candidate = recommended_candidate_id
        elif has_application_delta:
            waiting_for_full_field_replay = (
                needs_full_field
                and gate_status != "passed"
                and full_field_recovery_change_set_selected
            )
            blocked_by_full_field = (
                needs_full_field
                and gate_status != "passed"
                and not full_field_recovery_change_set_selected
            )
            blocked_by_branch_review = cost_yield_branch_review_required
            blocked_by_mtf_first_spec_record = mtf_first_spec_repair_closeout
            change_set_status = (
                "queued"
                if (
                    blocked_by_branch_review
                    or waiting_for_full_field_replay
                    or blocked_by_mtf_first_spec_record
                )
                else ("blocked" if blocked_by_full_field else "ready")
            )
            add(
                "apply-protected-change-set",
                prescription_change_set.source_candidate_id,
                "apply_change_set",
                change_set_status,
                "apply the protected prescription change set to a cloned branch",
                [
                    f"surface {item.surface_index} {item.variable}"
                    for item in prescription_change_set.changes[:4]
                ],
                (
                    "candidate proxy branch review is complete"
                    if blocked_by_branch_review
                    else (
                        "MTF-first recovery replay and target-spec record are complete"
                        if blocked_by_mtf_first_spec_record
                        else (
                            "full-field recovery replay gate has passed"
                            if waiting_for_full_field_replay or blocked_by_full_field
                            else "verification gate passed on the protected optimizer proposal"
                        )
                    )
                ),
                "post-apply EFL, F-number, TTL, ray trace, and MTF stay inside the checked bounds",
                "recompute paraxial summary, sampled ray trace, and MTF after applying the delta",
                depends_on=(
                    ["resolve-candidate-proxy-branch"]
                    if blocked_by_branch_review
                    else (
                        ["record-spec-repair-target"]
                        if blocked_by_mtf_first_spec_record
                        else (
                            ["recover-full-field"]
                            if blocked_by_full_field or waiting_for_full_field_replay
                            else []
                        )
                    )
                ),
                evidence=[
                    *[
                        (
                            f"{item.variable} S{item.surface_index} "
                            f"{item.before:.4f}->{item.after:.4f}"
                        )
                        for item in prescription_change_set.changes[:4]
                    ],
                    f"expected effect: {prescription_change_set.expected_effect}",
                ],
            )
            first_order_dependency = ["apply-protected-change-set"]
            first_order_candidate = prescription_change_set.source_candidate_id
        elif (
            optimization_attempt.status != "not_attempted"
            and not seed_baseline_first_order_locked_for_floor_recovery
        ):
            add(
                "stabilize-optimizer",
                recommended_candidate_id,
                "optimizer_stabilization",
                "ready",
                "turn optimizer diagnostics into a reproducible bounded proposal",
                ["finite Jacobian", "radius variables", "ray aiming"],
                "optimizer returned diagnostic-only evidence",
                "a bounded proposal carries verification gate evidence or explains a deterministic failure",
                "rerun protected optimizer on the same seed and compare diagnostics",
                evidence=[optimization_attempt.summary, *optimization_attempt.failures[:2]],
            )
            first_order_dependency = ["stabilize-optimizer"]
            first_order_candidate = recommended_candidate_id
        else:
            first_order_dependency = []
            first_order_candidate = recommended_candidate_id

        add(
            "lock-first-order",
            first_order_candidate,
            "first_order_lock",
            "queued" if first_order_dependency else "ready",
            "lock EFL, F-number, image height, and TTL before image-quality merit tuning",
            ["effective focal length", "F-number", "image height", "total track"],
            "selected branch has a stable prescription clone",
            "EFL/F-number/image-height/TTL deltas remain inside the design review tolerances",
            "compare paraxial deltas after every solve",
            depends_on=first_order_dependency,
            evidence=[
                f"dEFL={delta_efl:+.3f} mm",
                f"dF#={delta_fnum:+.3f}",
                f"dFOV={delta_fov:+.2f} deg",
            ],
        )

        if recommended_image_quality_floor.status == "blocker":
            add(
                "recover-image-quality-floor",
                first_order_candidate,
                "image_quality_recovery",
                "queued",
                "recover recommended-branch MTF/RMS before draft_ready promotion",
                recommended_image_quality_recovery_objective.variables,
                "first-order targets are locked on the recommended branch",
                (
                    "50/100/150/200/250 lp/mm min MTF>=0.08, "
                    "field-weighted MTF>=0.15, and max RMS<=100um"
                ),
                ("rerun bounded merit tuning and verify MTF/RMS floor without EFL/FOV/TTL drift"),
                depends_on=["lock-first-order"],
                evidence=_unique_in_order(
                    [
                        f"recommended candidate={recommended_candidate_id}",
                        *recommended_image_quality_recovery_objective.evidence,
                        *recommended_image_quality_floor.evidence,
                        *recommended_image_quality_floor.blockers,
                    ]
                ),
            )
            if floor_gap_recovery_trial is not None:
                trial_label = _trial_label(floor_gap_recovery_trial)
                add(
                    "replay-floor-gap-recovery-candidate",
                    "floor-gap-recovery-candidate",
                    "image_quality_recovery_replay",
                    "queued",
                    "replay the selected floor-gap recovery trial on a protected clone",
                    [trial_label, "MTF/RMS floor", "first-order lock"],
                    "recover-image-quality-floor selected a held recovery candidate",
                    (
                        "floor gap closes while EFL, F-number, TTL, full-field MTF, "
                        "RMS, and manufacturability guards remain acceptable"
                    ),
                    "protected clone replay with paraxial, ray trace, MTF/RMS, and manufacturability evidence",
                    depends_on=["recover-image-quality-floor"],
                    evidence=_unique_in_order(
                        [
                            "recovery candidate=floor-gap-recovery-candidate",
                            f"trial={trial_label}",
                            f"trial status={floor_gap_recovery_trial.status}",
                            (
                                "floor-gap closure="
                                f"{floor_gap_recovery_trial.image_quality_floor_gap_closure:+.3f}"
                                if floor_gap_recovery_trial.image_quality_floor_gap_closure
                                is not None
                                else ""
                            ),
                            f"verification gate={floor_gap_recovery_trial.verification_status or 'n/a'}",
                            "delivered payload remains frozen",
                        ]
                    ),
                )
                if replay_gate_requires_remediation:
                    remediation_variables = list(remediation_base_variables)
                    downstream_variables = list(remediation_downstream_variables)
                    remediation_action = (
                        replay_gate_remediation_actions[0]
                        if replay_gate_remediation_actions
                        else "rerun bounded search after replay gate failure"
                    )
                    add(
                        "remediate-recovery-replay-gate",
                        "floor-gap-recovery-candidate",
                        "image_quality_recovery_remediation",
                        "queued",
                        "rerun bounded search with replay-gate remediation variables",
                        remediation_variables,
                        "floor-gap recovery replay gate blocked promotion",
                        "failed replay checks are cleared or a safer recovery candidate is selected",
                        (
                            "bounded merit probe with replay-gate variable priority, "
                            "then protected replay verification"
                        ),
                        depends_on=["replay-floor-gap-recovery-candidate"],
                        evidence=_unique_in_order(
                            [
                                "replay gate=floor-gap-recovery-replay",
                                (f"failed checks={', '.join(replay_gate_failed_check_ids)}"),
                                (
                                    "remediation variable priority="
                                    f"{', '.join(remediation_variables)}"
                                ),
                                (
                                    f"policy downstream variables={', '.join(downstream_variables)}"
                                    if downstream_variables
                                    else "policy downstream variables=none"
                                ),
                                f"remediation action={remediation_action}",
                                f"remediation policy={remediation_policy}",
                                "delivered payload remains frozen",
                            ]
                        ),
                    )
                    if not remediation_downstream_unlocked:
                        resolution_packet = _remediation_resolution_packet()
                        add(
                            "resolve-remediation-policy-block",
                            "floor-gap-recovery-candidate",
                            "remediation_policy_followup",
                            "queued",
                            "collect evidence or a safer variable family before resuming bounded merit tuning",
                            [
                                "stronger seed evidence",
                                "alternate variable family",
                                "finite MTF/RMS replay evidence",
                            ],
                            "remediation policy blocked downstream local merit tuning",
                            "a replayable candidate, stronger seed, or alternate variable family is available",
                            (
                                "seed intake/preflight evidence + replay gate checks "
                                "+ policy-selected variable-family brief"
                            ),
                            depends_on=["remediate-recovery-replay-gate"],
                            evidence=_unique_in_order(
                                [
                                    f"remediation policy={remediation_downstream_policy}",
                                    f"policy action={remediation_policy_action}",
                                    (
                                        "blocked replay checks="
                                        f"{', '.join(replay_gate_failed_check_ids)}"
                                    ),
                                    (
                                        "base remediation variables="
                                        f"{', '.join(remediation_variables)}"
                                    ),
                                    (
                                        "policy-selected variables="
                                        f"{', '.join(downstream_variables)}"
                                        if downstream_variables
                                        else "policy-selected variables=none"
                                    ),
                                    "do not resume local merit until this packet is resolved",
                                    *resolution_packet.evidence,
                                ]
                            ),
                            resolution_packet=resolution_packet,
                        )
                    local_merit_dependencies = ["remediate-recovery-replay-gate"]
                    local_merit_status = "queued" if remediation_downstream_unlocked else "blocked"
                    local_merit_variables = downstream_variables
                    local_merit_evidence = _unique_in_order(
                        [
                            *local_merit_evidence,
                            (
                                "replay-gate remediation variables="
                                f"{', '.join(remediation_variables)}"
                            ),
                            (
                                f"policy-selected variables={', '.join(downstream_variables)}"
                                if downstream_variables
                                else "policy-selected variables=none"
                            ),
                            f"remediation policy={remediation_downstream_policy}",
                            f"policy action={remediation_policy_action}",
                            f"blocked replay checks={', '.join(replay_gate_failed_check_ids)}",
                            f"first remediation action={remediation_action}",
                        ]
                    )

        if max_total_track_mm is not None:
            add(
                "protect-packaging-budget",
                first_order_candidate,
                "packaging_guard",
                "queued",
                "keep air gaps, center thickness, and filter stack inside the module envelope",
                ["air gaps", "center thickness", "filter stack"],
                "first-order targets are locked",
                "total track stays at or below the requested ceiling with reserve for tolerance cleanup",
                "verify total track after every structural edit",
                depends_on=["lock-first-order"],
                evidence=[
                    (
                        f"TTL delta={delta_ttl:+.3f} mm"
                        if delta_ttl is not None
                        else "TTL ceiling present"
                    )
                ],
            )

        add(
            "local-merit-tuning",
            first_order_candidate,
            "image_quality_tuning",
            local_merit_status,
            "improve mid-field and edge-field image quality without drifting off the brief",
            local_merit_variables,
            (
                "remediation policy allows downstream bounded merit search"
                if local_merit_status == "queued"
                else "remediation policy must produce a continued or switched variable family"
            ),
            "RMS/MTF improve while first-order targets remain locked",
            "compare MTF, RMS spot, and ray trace against seed baseline and optimizer branch",
            depends_on=local_merit_dependencies,
            evidence=local_merit_evidence,
        )

        second_pass_candidate = next(
            (
                candidate
                for candidate in draft_candidates
                if candidate.candidate_id == "second-pass-recovery-candidate"
            ),
            None,
        )
        if second_pass_candidate is not None:
            second_pass_gap = _image_quality_floor_gap_score(second_pass_candidate.metrics)
            add(
                "replay-second-pass-recovery-candidate",
                "second-pass-recovery-candidate",
                "image_quality_recovery_replay",
                "queued" if local_merit_status == "queued" else "blocked",
                "replay the second-pass recovery candidate before promotion",
                ["second-pass recovery candidate", "MTF/RMS floor", "payload freeze"],
                "local-merit-tuning has produced a gate-clean second-pass branch",
                (
                    "second-pass branch replay keeps full-field MTF, RMS, EFL, "
                    "and payload-freeze checks acceptable"
                ),
                "run replay-gate promotion on the held second-pass recovery candidate",
                depends_on=["local-merit-tuning"],
                evidence=_unique_in_order(
                    [
                        "candidate=second-pass-recovery-candidate",
                        (
                            f"second-pass floor gap={second_pass_gap:.3f}"
                            if second_pass_gap is not None
                            else "second-pass floor gap unavailable"
                        ),
                        *second_pass_candidate.evidence[:4],
                        "recommended candidate metrics remain unchanged until promotion",
                    ]
                ),
            )

        if needs_asphere_guarded_audit:
            first_asphere = guarded_asphere_candidates[0]
            add(
                "asphere-guarded-audit",
                first_order_candidate,
                "asphere_guarded_audit",
                "queued",
                "replay guarded asphere coefficient perturbations after radius/air-gap gates stall",
                ["asphere coefficients"],
                "local merit tuning improved RMS but did not pass MTF promotion gates",
                "candidate perturbations stay inside sag/slope guards and improve MTF gates",
                "audit-only asphere replay with full-field MTF and manufacturability guard evidence",
                depends_on=["local-merit-tuning"],
                evidence=[
                    f"guarded asphere candidates={len(guarded_asphere_candidates)}",
                    (
                        f"first S{first_asphere.surface_index}:c{first_asphere.coefficient_index} "
                        f"r^{first_asphere.asphere_power}"
                    ),
                    (
                        f"sag={first_asphere.edge_sag_delta_um:.2f}um "
                        f"slope={first_asphere.edge_slope_delta_mrad:.2f}mrad"
                        if first_asphere.edge_sag_delta_um is not None
                        and first_asphere.edge_slope_delta_mrad is not None
                        else "sag/slope guard pending"
                    ),
                ],
            )

        production_dependency = (
            "asphere-guarded-audit" if needs_asphere_guarded_audit else "local-merit-tuning"
        )
        add(
            "production-validation",
            first_order_candidate,
            "tolerance_validation",
            "queued",
            "validate the draft across wavelengths, fields, relative illumination, and tolerances",
            ["RGB wavelengths", "field heights", "manufacturing tolerances"],
            "image-quality merit tuning is stable",
            "RGB MTF, RMS spot, relative illumination, and tolerance sensitivity are acceptable",
            "run RGB MTF, sampled ray trace, relative illumination, and tolerance checks",
            depends_on=[production_dependency],
            evidence=[
                readiness.summary if readiness is not None else "readiness not computed",
                f"risk count={len(risk_register)}",
            ],
        )

        return tasks[:7]

    optimization_task_queue = _optimization_task_queue()

    def _metric_direction(
        before: float | None,
        after: float | None,
        *,
        higher_is_better: bool,
        tolerance: float = 1e-6,
    ) -> str:
        if before is None or after is None:
            return "diagnostic"
        if math.isclose(before, after, abs_tol=tolerance):
            return "unchanged"
        if higher_is_better:
            return "improved" if after > before else "regressed"
        return "improved" if after < before else "regressed"

    def _metric_updates_from_attempt() -> list[OptimizationMetricUpdate]:
        before = optimization_attempt.before_metrics
        after = optimization_attempt.after_metrics
        if before is None or after is None:
            return []

        updates: list[OptimizationMetricUpdate] = []
        if (
            before.effective_focal_length_mm is not None
            and after.effective_focal_length_mm is not None
        ):
            before_error = abs(before.effective_focal_length_mm - efl_mm)
            after_error = abs(after.effective_focal_length_mm - efl_mm)
            updates.append(
                OptimizationMetricUpdate(
                    metric="efl_error",
                    before=before_error,
                    after=after_error,
                    unit="mm",
                    direction=_metric_direction(
                        before_error,
                        after_error,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        f"EFL miss {before_error:.3f}->{after_error:.3f} mm "
                        f"against target {efl_mm:.3f} mm"
                    ),
                )
            )
        if before.total_track_mm is not None and after.total_track_mm is not None:
            updates.append(
                OptimizationMetricUpdate(
                    metric="total_track",
                    before=before.total_track_mm,
                    after=after.total_track_mm,
                    unit="mm",
                    direction=_metric_direction(
                        before.total_track_mm,
                        after.total_track_mm,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        f"TTL {before.total_track_mm:.3f}->{after.total_track_mm:.3f} mm"
                    ),
                )
            )
        if before.mtf_max_field_frac is not None and after.mtf_max_field_frac is not None:
            updates.append(
                OptimizationMetricUpdate(
                    metric="mtf_max_field_frac",
                    before=before.mtf_max_field_frac,
                    after=after.mtf_max_field_frac,
                    unit="field",
                    direction=_metric_direction(
                        before.mtf_max_field_frac,
                        after.mtf_max_field_frac,
                        higher_is_better=True,
                    ),
                    interpretation=(
                        "MTF evidence field "
                        f"{format_mtf_field_fraction(before.mtf_max_field_frac)}->"
                        f"{format_mtf_field_fraction(after.mtf_max_field_frac)}"
                    ),
                )
            )
        if before.mtf_multiband_min_score is not None and after.mtf_multiband_min_score is not None:
            updates.append(
                OptimizationMetricUpdate(
                    metric="mtf_multiband_min_score",
                    before=before.mtf_multiband_min_score,
                    after=after.mtf_multiband_min_score,
                    unit=None,
                    direction=_metric_direction(
                        before.mtf_multiband_min_score,
                        after.mtf_multiband_min_score,
                        higher_is_better=True,
                    ),
                    interpretation=(
                        f"weighted minimum MTF score "
                        f"{before.mtf_multiband_min_score:.3f}->"
                        f"{after.mtf_multiband_min_score:.3f}"
                    ),
                )
            )
        if (
            before.mtf_field_weighted_score is not None
            and after.mtf_field_weighted_score is not None
        ):
            updates.append(
                OptimizationMetricUpdate(
                    metric="mtf_field_weighted_score",
                    before=before.mtf_field_weighted_score,
                    after=after.mtf_field_weighted_score,
                    unit=None,
                    direction=_metric_direction(
                        before.mtf_field_weighted_score,
                        after.mtf_field_weighted_score,
                        higher_is_better=True,
                    ),
                    interpretation=(
                        f"field-weighted MTF score "
                        f"{before.mtf_field_weighted_score:.3f}->"
                        f"{after.mtf_field_weighted_score:.3f}"
                    ),
                )
            )
        if before.max_rms_spot_radius_um is not None and after.max_rms_spot_radius_um is not None:
            updates.append(
                OptimizationMetricUpdate(
                    metric="max_rms_spot_radius",
                    before=before.max_rms_spot_radius_um,
                    after=after.max_rms_spot_radius_um,
                    unit="um",
                    direction=_metric_direction(
                        before.max_rms_spot_radius_um,
                        after.max_rms_spot_radius_um,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        f"max RMS {before.max_rms_spot_radius_um:.2f}->"
                        f"{after.max_rms_spot_radius_um:.2f} um"
                    ),
                )
            )
        return updates

    def _unlocked_tasks_after(task_id: str, *, passed: bool) -> list[str]:
        if not passed:
            return []
        return [
            task.task_id
            for task in optimization_task_queue
            if task.status == "queued" and task_id in task.depends_on
        ]

    def _clean_evidence(items: list[str], *, limit: int = 6) -> list[str]:
        return [item for item in items if item][:limit]

    def _gate_check(
        *,
        check_id: str,
        label: str,
        passed: bool | None,
        evidence: list[str],
        required_for_promotion: bool = True,
        comparator: str | None = None,
        measured_value: float | None = None,
        target_value: float | None = None,
        unit: str | None = None,
    ) -> OptimizationReplayGateCheck:
        status = "not_run" if passed is None else ("pass" if passed else "fail")
        return OptimizationReplayGateCheck(
            check_id=check_id,
            label=label,
            status=status,
            required_for_promotion=required_for_promotion,
            comparator=comparator,
            measured_value=measured_value,
            target_value=target_value,
            unit=unit,
            evidence=_clean_evidence(evidence, limit=4),
        )

    def _recovery_replay_gate(
        trial: OptimizationVariableTrial | None,
    ) -> OptimizationReplayGate:
        if trial is None:
            failed_check_ids = _replay_gate_failed_check_ids(trial)
            recommended_variables, remediation_actions = _replay_gate_remediation_for_checks(
                failed_check_ids
            )
            return OptimizationReplayGate(
                gate_id="floor-gap-recovery-replay",
                status="not_run",
                promotion_allowed=False,
                summary="no floor-gap recovery trial is available for replay gating",
                checks=[
                    OptimizationReplayGateCheck(
                        check_id="trial_available",
                        label="Trial available",
                        status="not_run",
                        required_for_promotion=True,
                        evidence=["no floor-gap recovery trial is available"],
                    )
                ],
                failed_check_ids=failed_check_ids,
                recommended_variables=recommended_variables,
                remediation_actions=remediation_actions,
                next_action="select a bounded floor-gap recovery trial before replay gating",
            )

        closure = trial.image_quality_floor_gap_closure
        after_gap = trial.image_quality_floor_gap_after
        rms_delta = trial.rms_improvement_um
        verification_status = trial.verification_status or "not_run"
        checks = [
            _gate_check(
                check_id="floor_gap_closure_positive",
                label="Floor-gap closure is positive",
                passed=closure is not None and closure > 0.0,
                comparator="> 0",
                measured_value=closure,
                target_value=0.0,
                evidence=[
                    (
                        f"floor-gap closure={closure:+.3f}"
                        if closure is not None
                        else "floor-gap closure unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="floor_gap_cleared",
                label="MTF/RMS floor gap is cleared",
                passed=after_gap is not None and after_gap <= 0.0,
                comparator="<= 0",
                measured_value=after_gap,
                target_value=0.0,
                evidence=[
                    (
                        f"floor-gap after={after_gap:.3f}"
                        if after_gap is not None
                        else "floor-gap after unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="rms_non_regressed",
                label="RMS does not regress",
                passed=rms_delta is not None and rms_delta >= 0.0,
                comparator=">= 0",
                measured_value=rms_delta,
                target_value=0.0,
                unit="um",
                evidence=[
                    (
                        f"RMS delta={rms_delta:+.2f}um"
                        if rms_delta is not None
                        else "RMS delta unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="mtf_multiband_non_regressed",
                label="Multiband MTF does not regress",
                passed=trial.mtf_band_non_regressed,
                evidence=[f"mtf_band_non_regressed={trial.mtf_band_non_regressed}"],
            ),
            _gate_check(
                check_id="mtf_field_weighted_non_regressed",
                label="Field-weighted MTF does not regress",
                passed=trial.mtf_field_weighted_non_regressed,
                evidence=[
                    f"mtf_field_weighted_non_regressed={trial.mtf_field_weighted_non_regressed}"
                ],
            ),
            _gate_check(
                check_id="first_order_locked",
                label="First-order targets stay locked",
                passed=trial.efl_locked,
                evidence=[f"efl_locked={trial.efl_locked}"],
            ),
            _gate_check(
                check_id="verification_passed",
                label="Protected verification gate passed",
                passed=verification_status == "passed",
                evidence=[f"verification gate={verification_status}"],
            ),
            _gate_check(
                check_id="payload_frozen",
                label="Delivered payload remains frozen",
                passed=True,
                evidence=["delivered payload remains frozen"],
            ),
        ]
        required_checks = [check for check in checks if check.required_for_promotion]
        failed_check_ids = _replay_gate_failed_check_ids(trial)
        recommended_variables, remediation_actions = _replay_gate_remediation_for_checks(
            failed_check_ids
        )
        promotion_allowed = all(check.status == "pass" for check in required_checks)
        if promotion_allowed:
            status = "pass"
            summary = "recovery replay gate passes; candidate may be reviewed for promotion"
            next_action = "package the recovery candidate for promotion review"
        elif any(check.status == "fail" for check in required_checks):
            status = "fail"
            summary = "recovery replay gate blocks promotion until failed checks clear"
            next_action = (
                remediation_actions[0]
                if remediation_actions
                else ("rerun guarded replay after closing failed floor, MTF, RMS, or lock checks")
            )
        else:
            status = "blocked"
            summary = "recovery replay gate is waiting for required replay evidence"
            next_action = (
                remediation_actions[0]
                if remediation_actions
                else ("collect missing replay evidence before promotion")
            )
        return OptimizationReplayGate(
            gate_id="floor-gap-recovery-replay",
            status=status,
            promotion_allowed=promotion_allowed,
            summary=summary,
            checks=checks,
            failed_check_ids=failed_check_ids,
            recommended_variables=recommended_variables,
            remediation_actions=remediation_actions,
            next_action=next_action,
        )

    def _full_field_recovery_replay_gate(
        trial: FullFieldRecoveryTrial | None,
    ) -> OptimizationReplayGate:
        if trial is None:
            return OptimizationReplayGate(
                gate_id="full-field-recovery-replay",
                status="not_run",
                promotion_allowed=False,
                summary="no floor-clean full-field recovery trial is available",
                checks=[
                    OptimizationReplayGateCheck(
                        check_id="trial_available",
                        label="Recovery trial available",
                        status="not_run",
                        required_for_promotion=True,
                        evidence=["no floor-clean full-field recovery trial is available"],
                    )
                ],
                failed_check_ids=["trial_available"],
                recommended_variables=["compound field-extension"],
                remediation_actions=[
                    "find a recovered full-field branch that also clears the MTF/RMS floor"
                ],
                next_action="continue guarded full-field recovery before creating a change-set",
            )

        floor_gap = trial.image_quality_floor_gap_score
        efl_delta_abs = abs(trial.efl_delta_mm) if trial.efl_delta_mm is not None else None
        ttl_delta_abs = (
            abs(trial.total_track_delta_mm) if trial.total_track_delta_mm is not None else None
        )
        metrics = trial.metrics
        checks = [
            _gate_check(
                check_id="variable_changes_structured",
                label="Structured variable changes are available",
                passed=bool(trial.variable_changes),
                evidence=[
                    (
                        "changes=" + _changes_label(trial.variable_changes)
                        if trial.variable_changes
                        else "structured changes unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="full_field_recovered",
                label="Full-field MTF evidence recovered",
                passed=trial.mtf_max_field_frac is not None and trial.mtf_max_field_frac >= 1.0,
                comparator=">= 1.0",
                measured_value=trial.mtf_max_field_frac,
                target_value=1.0,
                unit="field",
                evidence=[
                    (
                        f"recovered field={format_mtf_field_fraction(trial.mtf_max_field_frac)}"
                        if trial.mtf_max_field_frac is not None
                        else "recovered field unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="floor_gap_cleared",
                label="MTF/RMS floor gap is cleared",
                passed=floor_gap is not None and floor_gap <= 0.0,
                comparator="<= 0",
                measured_value=floor_gap,
                target_value=0.0,
                evidence=[
                    (
                        f"floor gap={floor_gap:.3f}"
                        if floor_gap is not None
                        else "floor gap unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="mtf_rms_metrics_available",
                label="MTF/RMS metrics are available",
                passed=(
                    metrics is not None
                    and metrics.mtf_multiband_min_score is not None
                    and metrics.mtf_field_weighted_score is not None
                    and metrics.max_rms_spot_radius_um is not None
                ),
                evidence=[
                    (
                        f"min={metrics.mtf_multiband_min_score:.3f}; "
                        f"weighted={metrics.mtf_field_weighted_score:.3f}; "
                        f"RMS={metrics.max_rms_spot_radius_um:.2f}um"
                        if metrics is not None
                        and metrics.mtf_multiband_min_score is not None
                        and metrics.mtf_field_weighted_score is not None
                        and metrics.max_rms_spot_radius_um is not None
                        else "MTF/RMS metric snapshot unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="efl_drift_within_review_band",
                label="EFL drift stays inside first-pass review band",
                passed=efl_delta_abs is not None and efl_delta_abs <= 0.15,
                comparator="<= 0.15",
                measured_value=efl_delta_abs,
                target_value=0.15,
                unit="mm",
                evidence=[
                    (
                        f"EFL delta={trial.efl_delta_mm:+.3f} mm"
                        if trial.efl_delta_mm is not None
                        else "EFL delta unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="ttl_drift_within_review_band",
                label="TTL drift stays inside first-pass review band",
                passed=ttl_delta_abs is not None and ttl_delta_abs <= 0.10,
                comparator="<= 0.10",
                measured_value=ttl_delta_abs,
                target_value=0.10,
                unit="mm",
                evidence=[
                    (
                        f"TTL delta={trial.total_track_delta_mm:+.3f} mm"
                        if trial.total_track_delta_mm is not None
                        else "TTL delta unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="payload_frozen",
                label="Delivered payload remains frozen",
                passed=True,
                evidence=["delivered payload remains the selected real seed"],
            ),
            OptimizationReplayGateCheck(
                check_id="aperture_element_tradeoff_review",
                label="Aperture and element-count tradeoffs require review",
                status="warning",
                required_for_promotion=False,
                evidence=[
                    f"F/# request {fnum:.2f}; recovery branch F/# {metrics.f_number:.2f}"
                    if metrics is not None and metrics.f_number is not None
                    else f"F/# request {fnum:.2f}; recovery branch F/# unavailable",
                    (
                        f"requested {n_elements}P; selected seed {best.metadata.n_pieces}P"
                        if n_elements is not None
                        else f"selected seed {best.metadata.n_pieces}P"
                    ),
                ],
            ),
        ]
        required_checks = [check for check in checks if check.required_for_promotion]
        failed_check_ids = [check.check_id for check in required_checks if check.status != "pass"]
        promotion_allowed = not failed_check_ids
        status = "pass" if promotion_allowed else "fail"
        summary = (
            "full-field recovery replay passes; protected change-set can move to review"
            if promotion_allowed
            else "full-field recovery replay blocks promotion until required checks clear"
        )
        remediation_actions = (
            []
            if promotion_allowed
            else [
                "rerun guarded full-field recovery after closing structured delta, field, floor, EFL, or TTL checks"
            ]
        )
        return OptimizationReplayGate(
            gate_id="full-field-recovery-replay",
            status=status,
            promotion_allowed=promotion_allowed,
            summary=summary,
            checks=checks,
            failed_check_ids=failed_check_ids,
            recommended_variables=[
                _changes_label(trial.variable_changes)
                if trial.variable_changes
                else "compound field-extension"
            ],
            remediation_actions=remediation_actions,
            next_action=(
                "review the protected full-field recovery change-set before payload promotion"
                if promotion_allowed
                else remediation_actions[0]
            ),
        )

    def _find_task(task_id: str) -> OptimizationTask | None:
        return next(
            (task for task in optimization_task_queue if task.task_id == task_id),
            None,
        )

    def _lock_first_order_run(task: OptimizationTask) -> OptimizationTaskRun:
        active_metrics = (
            optimization_attempt.after_metrics
            or optimization_attempt.before_metrics
            or seed_baseline_metrics
        )
        active_efl = (
            active_metrics.effective_focal_length_mm if active_metrics is not None else None
        )
        active_f_number = active_metrics.f_number if active_metrics is not None else None
        active_total_track = active_metrics.total_track_mm if active_metrics is not None else None

        before_efl_error = abs(best.metadata.computed_efl_mm - efl_mm)
        after_efl_error = abs(active_efl - efl_mm) if active_efl is not None else None
        before_f_number_delta = abs(delta_fnum)
        after_f_number_delta = abs(active_f_number - fnum) if active_f_number is not None else None
        before_image_height_delta = abs(delta_imh) if delta_imh is not None else None
        after_image_height_delta = before_image_height_delta

        metric_updates = [
            OptimizationMetricUpdate(
                metric="efl_error",
                before=before_efl_error,
                after=after_efl_error,
                unit="mm",
                direction=_metric_direction(
                    before_efl_error,
                    after_efl_error,
                    higher_is_better=False,
                ),
                interpretation=(
                    f"first-order EFL error after protected proposal is {after_efl_error:.3f} mm"
                    if after_efl_error is not None
                    else "first-order EFL error is unavailable"
                ),
            ),
            OptimizationMetricUpdate(
                metric="f_number_delta",
                before=before_f_number_delta,
                after=after_f_number_delta,
                unit="F/#",
                direction=_metric_direction(
                    before_f_number_delta,
                    after_f_number_delta,
                    higher_is_better=False,
                ),
                interpretation=(
                    "F-number delta remains within review tolerance"
                    if after_f_number_delta is not None and after_f_number_delta <= 0.25
                    else "F-number needs a constrained solve before image-quality tuning"
                ),
            ),
        ]
        if before_image_height_delta is not None:
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="image_height_delta",
                    before=before_image_height_delta,
                    after=after_image_height_delta,
                    unit="mm",
                    direction=_metric_direction(
                        before_image_height_delta,
                        after_image_height_delta,
                        higher_is_better=False,
                    ),
                    interpretation=("image-height class remains tied to the selected real seed"),
                )
            )
        if max_total_track_mm is not None and active_total_track is not None:
            before_ttl_margin = max_total_track_mm - best.paraxial.total_track_mm
            after_ttl_margin = max_total_track_mm - active_total_track
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="ttl_margin",
                    before=before_ttl_margin,
                    after=after_ttl_margin,
                    unit="mm",
                    direction=_metric_direction(
                        before_ttl_margin,
                        after_ttl_margin,
                        higher_is_better=True,
                    ),
                    interpretation=(f"TTL margin after proposal is {after_ttl_margin:.3f} mm"),
                )
            )

        efl_ok = after_efl_error is not None and after_efl_error <= 0.10
        f_number_ok = after_f_number_delta is not None and after_f_number_delta <= 0.25
        image_height_ok = after_image_height_delta is None or after_image_height_delta <= 0.25
        ttl_ok = max_total_track_mm is None or (
            active_total_track is not None and active_total_track <= max_total_track_mm
        )
        passed = efl_ok and f_number_ok and image_height_ok and ttl_ok
        unlocked = _unlocked_tasks_after(task.task_id, passed=passed)
        evidence = [
            *task.evidence,
            f"EFL ok={efl_ok}",
            f"F-number ok={f_number_ok}",
            f"image height ok={image_height_ok}",
            f"TTL ok={ttl_ok}",
        ]
        return OptimizationTaskRun(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            status="passed" if passed else "warning",
            summary=(
                "first-order targets are inside review tolerance on the protected branch"
                if passed
                else "first-order targets still need a constrained solve before merit tuning"
            ),
            metric_updates=metric_updates,
            unlocked_tasks=unlocked,
            next_action=(
                f"unlock {', '.join(unlocked)} for image-quality and packaging work"
                if unlocked
                else "rerun a first-order constrained solve before image-quality tuning"
            ),
            evidence=_clean_evidence(evidence),
        )

    def _image_quality_floor_recovery_run(task: OptimizationTask) -> OptimizationTaskRun:
        metrics = _recommended_candidate_metrics()
        floor = recommended_image_quality_floor
        recovery_objective = _image_quality_recovery_objective(metrics)
        metric_updates: list[OptimizationMetricUpdate] = []
        baseline_metrics = (
            merit_optimization_probe.before_metrics
            or optimization_attempt.before_metrics
            or metrics
        )
        before_gap = _image_quality_floor_gap_score(baseline_metrics)
        after_gap = _image_quality_floor_gap_score(metrics)
        if before_gap is not None or after_gap is not None:
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="image_quality_floor_gap_score",
                    before=before_gap,
                    after=after_gap,
                    unit=None,
                    direction=_metric_direction(before_gap, after_gap, higher_is_better=False),
                    interpretation=("normalized MTF/RMS floor gap; lower is closer to draft_ready"),
                )
            )
        probe_before_gap = _image_quality_floor_gap_score(merit_optimization_probe.before_metrics)
        probe_after_gap = _image_quality_floor_gap_score(merit_optimization_probe.after_metrics)
        if probe_before_gap is not None or probe_after_gap is not None:
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="recovery_probe_floor_gap_score",
                    before=probe_before_gap,
                    after=probe_after_gap,
                    unit=None,
                    direction=_metric_direction(
                        probe_before_gap,
                        probe_after_gap,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        "dedicated recovery probe floor gap; lower is closer to draft_ready"
                    ),
                )
            )
        if metrics is not None:
            for metric_name, before, target, interpretation in (
                (
                    "mtf_multiband_floor_gap",
                    metrics.mtf_multiband_min_score,
                    _IMAGE_QUALITY_FLOOR_MIN_MTF,
                    "multiband minimum MTF must clear the first-pass review floor",
                ),
                (
                    "mtf_field_weighted_floor_gap",
                    metrics.mtf_field_weighted_score,
                    _IMAGE_QUALITY_FLOOR_WEIGHTED_MTF,
                    "field-weighted MTF must clear the first-pass review floor",
                ),
                (
                    "max_rms_floor_gap",
                    metrics.max_rms_spot_radius_um,
                    _IMAGE_QUALITY_FLOOR_MAX_RMS_UM,
                    "max RMS spot radius must fall below the first-pass review floor",
                ),
            ):
                metric_updates.append(
                    OptimizationMetricUpdate(
                        metric=metric_name,
                        before=before,
                        after=target,
                        unit="um" if metric_name == "max_rms_floor_gap" else None,
                        direction="diagnostic",
                        interpretation=interpretation,
                    )
                )
            for component in image_quality_floor_components(metrics):
                if component.component_id in {
                    "mtf_multiband_floor_gap",
                    "mtf_field_weighted_floor_gap",
                    "max_rms_floor_gap",
                }:
                    continue
                metric_updates.append(
                    OptimizationMetricUpdate(
                        metric=component.component_id,
                        before=component.metric_value,
                        after=component.target_value,
                        unit=None,
                        direction="diagnostic",
                        interpretation=(
                            f"{component.label} normalized floor gap "
                            f"{component.normalized_gap:.3f}; target "
                            f"{component.target_value:.3f}"
                        ),
                    )
                )
        passed = floor.status == "pass"
        status = "passed" if passed else ("warning" if floor.status == "blocker" else "diagnostic")
        if passed:
            unlocked = _unlocked_tasks_after(task.task_id, passed=True)
        elif floor.status == "blocker":
            unlocked = []
            if _find_task("replay-floor-gap-recovery-candidate") is not None:
                unlocked.append("replay-floor-gap-recovery-candidate")
            elif _find_task("local-merit-tuning") is not None:
                unlocked.append("local-merit-tuning")
        else:
            unlocked = []
        next_action = (
            f"unlock {', '.join(unlocked)} after MTF/RMS floor recovery; {recovery_objective.next_action}"
            if unlocked
            else (floor.action or recovery_objective.next_action)
        )
        recovery_hint = (
            recovery_objective.next_action
            if floor.status == "blocker"
            else "recommended branch has no blocking MTF/RMS recovery gap"
        )
        best_floor_trial = _best_floor_gap_trial(merit_optimization_probe)
        probe_ranking_policy = (
            "floor_gap_first"
            if merit_optimization_probe.probe_purpose == "image_quality_floor_recovery"
            else "promotion_score_first"
        )
        probe_evidence = [
            f"floor recovery probe={merit_optimization_probe.status}",
            f"probe purpose={merit_optimization_probe.probe_purpose or 'rms_merit'}",
            f"probe ranking policy={probe_ranking_policy}",
            (
                f"probe variable priority={','.join(merit_optimization_probe.variable_priority)}"
                if merit_optimization_probe.variable_priority
                else ""
            ),
            (
                f"best floor-gap trial={best_floor_trial.variable} "
                f"S{best_floor_trial.surface_index} "
                f"closure={best_floor_trial.image_quality_floor_gap_closure:+.3f} "
                f"status={best_floor_trial.status} "
                f"verification={best_floor_trial.verification_status or 'n/a'}"
                if best_floor_trial is not None
                and best_floor_trial.image_quality_floor_gap_closure is not None
                else ""
            ),
        ]
        return OptimizationTaskRun(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            status=status,
            summary=(
                "recommended branch clears the first-pass MTF/RMS review floor"
                if passed
                else "recommended branch still needs MTF/RMS floor recovery"
            ),
            metric_updates=metric_updates,
            unlocked_tasks=unlocked,
            next_action=next_action,
            evidence=_clean_evidence(
                [
                    *probe_evidence,
                    *task.evidence,
                    recovery_hint,
                    *floor.evidence,
                    *floor.blockers,
                ],
                limit=16,
            ),
        )

    def _replay_floor_gap_recovery_candidate_run(
        task: OptimizationTask,
    ) -> OptimizationTaskRun:
        trial = floor_gap_recovery_trial
        replay_gate = _recovery_replay_gate(trial)
        metric_updates: list[OptimizationMetricUpdate] = []
        evidence = [*task.evidence]
        if trial is not None:
            trial_label = _trial_label(trial)
            if (
                trial.image_quality_floor_gap_before is not None
                or trial.image_quality_floor_gap_after is not None
            ):
                metric_updates.append(
                    OptimizationMetricUpdate(
                        metric="recovery_candidate_floor_gap_score",
                        before=trial.image_quality_floor_gap_before,
                        after=trial.image_quality_floor_gap_after,
                        unit=None,
                        direction=_metric_direction(
                            trial.image_quality_floor_gap_before,
                            trial.image_quality_floor_gap_after,
                            higher_is_better=False,
                        ),
                        interpretation=(
                            "selected recovery candidate floor gap; lower is closer to draft_ready"
                        ),
                    )
                )
            evidence.extend(
                [
                    f"trial={trial_label}",
                    f"trial status={trial.status}",
                    (
                        f"floor-gap closure={trial.image_quality_floor_gap_closure:+.3f}"
                        if trial.image_quality_floor_gap_closure is not None
                        else "floor-gap closure unavailable"
                    ),
                    f"verification gate={trial.verification_status or 'n/a'}",
                    "replay is queued as guarded work; delivered payload remains frozen",
                ]
            )
        else:
            evidence.append("no floor-gap recovery trial is available for replay")
        evidence.extend(
            [
                f"replay gate={replay_gate.status}",
                f"promotion allowed={replay_gate.promotion_allowed}",
                f"required gate checks={len([check for check in replay_gate.checks if check.required_for_promotion])}",
                (f"failed replay checks={', '.join(replay_gate.failed_check_ids) or 'none'}"),
                (
                    "recommended replay variables="
                    f"{', '.join(replay_gate.recommended_variables) or 'none'}"
                ),
                (
                    f"remediation action={replay_gate.remediation_actions[0]}"
                    if replay_gate.remediation_actions
                    else "remediation action=none"
                ),
            ]
        )
        remediation_task = _find_task("remediate-recovery-replay-gate")
        if remediation_task is not None and replay_gate.failed_check_ids:
            unlocked = [remediation_task.task_id]
        else:
            unlocked = (
                ["local-merit-tuning"] if _find_task("local-merit-tuning") is not None else []
            )
        replay_next_action = (
            replay_gate.remediation_actions[0]
            if replay_gate.remediation_actions
            else replay_gate.next_action
        )
        return OptimizationTaskRun(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            status="diagnostic",
            summary=("floor-gap recovery candidate is queued for guarded replay before promotion"),
            metric_updates=metric_updates,
            unlocked_tasks=unlocked,
            next_action=(
                f"{replay_next_action}; then continue with {', '.join(unlocked)}"
                if unlocked
                else replay_next_action
            ),
            evidence=_clean_evidence(evidence, limit=20),
            replay_gate=replay_gate,
        )

    def _recovery_replay_remediation_run(task: OptimizationTask) -> OptimizationTaskRun:
        replay_gate = _recovery_replay_gate(floor_gap_recovery_trial)
        variables = (
            list(remediation_base_variables) or replay_gate.recommended_variables or task.variables
        )
        remediation_action = (
            replay_gate.remediation_actions[0]
            if replay_gate.remediation_actions
            else "rerun bounded search after replay gate failure"
        )
        probe = remediation_optimization_probe
        metric_updates = [
            OptimizationMetricUpdate(
                metric="failed_replay_gate_checks",
                before=float(len(replay_gate.failed_check_ids)),
                after=0.0,
                unit="count",
                direction="diagnostic",
                interpretation=("required replay checks that must clear before recovery promotion"),
            ),
            OptimizationMetricUpdate(
                metric="remediation_variable_priority_count",
                before=None,
                after=float(len(variables)),
                unit="count",
                direction="diagnostic",
                interpretation=("variable families routed into the next bounded search"),
            ),
        ]
        probe_evidence = ["remediation probe=not_attempted"]
        if probe is not None:
            probe_before_gap = _image_quality_floor_gap_score(probe.before_metrics)
            probe_after_gap = _image_quality_floor_gap_score(probe.after_metrics)
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="remediation_probe_floor_gap_score",
                    before=probe_before_gap,
                    after=probe_after_gap,
                    unit=None,
                    direction=_metric_direction(
                        probe_before_gap,
                        probe_after_gap,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        "second-pass remediation probe floor gap; lower is closer to draft_ready"
                    ),
                )
            )
            if remediation_recovery_gap_after is not None and probe_after_gap is not None:
                metric_updates.append(
                    OptimizationMetricUpdate(
                        metric="second_pass_floor_gap_vs_recovery_candidate",
                        before=remediation_recovery_gap_after,
                        after=probe_after_gap,
                        unit=None,
                        direction=_metric_direction(
                            remediation_recovery_gap_after,
                            probe_after_gap,
                            higher_is_better=False,
                        ),
                        interpretation=(
                            "second-pass gap compared with the held recovery candidate"
                        ),
                    )
                )
            probe_evidence = [
                f"remediation probe={probe.status}",
                f"probe purpose={probe.probe_purpose or 'replay_gate_remediation'}",
                (
                    "baseline variable changes="
                    + ",".join(
                        f"{variable} S{surface_index}->{value:.6g}"
                        for variable, surface_index, value in remediation_baseline_variable_changes
                    )
                    if remediation_baseline_variable_changes
                    else "baseline variable changes=none"
                ),
                f"candidate trials={len(probe.candidate_trials)}",
                (
                    f"second-pass floor gap={probe_after_gap:.3f}"
                    if probe_after_gap is not None
                    else "second-pass floor gap unavailable"
                ),
                *[
                    item
                    for item in probe.diagnostics
                    if item.startswith("ranking policy=") or item.startswith("variable priority:")
                ][:2],
            ]
        local_merit_task = _find_task("local-merit-tuning")
        followup_task = _find_task("resolve-remediation-policy-block")
        unlocked = (
            ["local-merit-tuning"]
            if local_merit_task is not None
            and local_merit_task.status == "queued"
            and remediation_downstream_unlocked
            else (
                ["resolve-remediation-policy-block"]
                if followup_task is not None and followup_task.status == "queued"
                else []
            )
        )
        return OptimizationTaskRun(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            status="diagnostic",
            summary=("replay-gate remediation routes the next bounded search variable priority"),
            metric_updates=metric_updates,
            unlocked_tasks=unlocked,
            next_action=(
                f"{remediation_policy_action}; then continue with {', '.join(unlocked)}"
                if unlocked
                else remediation_policy_action
            ),
            evidence=_clean_evidence(
                [
                    *task.evidence,
                    f"failed replay checks={', '.join(replay_gate.failed_check_ids)}",
                    f"bounded search variable priority={', '.join(variables)}",
                    (
                        "policy-selected downstream variables="
                        f"{', '.join(remediation_downstream_variables)}"
                        if remediation_downstream_variables
                        else "policy-selected downstream variables=none"
                    ),
                    f"remediation action={remediation_action}",
                    *probe_evidence,
                    f"remediation policy={remediation_policy}",
                    f"downstream policy={remediation_downstream_policy}",
                    f"policy action={remediation_policy_action}",
                    (
                        f"second-pass delta vs recovery candidate={remediation_recovery_gap_after - remediation_second_pass_gap_after:+.3f}"
                        if remediation_recovery_gap_after is not None
                        and remediation_second_pass_gap_after is not None
                        else ""
                    ),
                    "delivered payload remains frozen",
                ],
                limit=24,
            ),
        )

    def _remediation_policy_followup_run(task: OptimizationTask) -> OptimizationTaskRun:
        return OptimizationTaskRun(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            status="diagnostic",
            summary=(
                "remediation policy blocked downstream merit tuning and requires "
                "stronger evidence before optimization resumes"
            ),
            metric_updates=[
                OptimizationMetricUpdate(
                    metric="blocked_replay_gate_checks",
                    before=float(len(replay_gate_failed_check_ids)),
                    after=float(len(replay_gate_failed_check_ids)),
                    unit="count",
                    direction="diagnostic",
                    interpretation=("replay-gate checks still blocking policy-driven promotion"),
                )
            ],
            unlocked_tasks=[],
            next_action=remediation_policy_action,
            evidence=_clean_evidence(
                [
                    *task.evidence,
                    (
                        f"second-pass floor gap={remediation_second_pass_gap_after:.3f}"
                        if remediation_second_pass_gap_after is not None
                        else "second-pass floor gap unavailable"
                    ),
                    "resume only after follow-up evidence changes the policy",
                ],
                limit=16,
            ),
            resolution_packet=task.resolution_packet,
        )

    def _local_merit_tuning_run(task: OptimizationTask) -> OptimizationTaskRun:
        active_merit_probe = merit_optimization_probe
        active_merit_probe_source = "primary-merit-probe"
        if "remediate-recovery-replay-gate" in task.depends_on:
            if (
                remediation_policy == "continue_second_pass_branch"
                and remediation_optimization_probe is not None
            ):
                active_merit_probe = remediation_optimization_probe
                active_merit_probe_source = "second-pass-continuation-probe"
            elif (
                remediation_policy == "switch_variable_family"
                and switched_remediation_optimization_probe is not None
            ):
                active_merit_probe = switched_remediation_optimization_probe
                active_merit_probe_source = "policy-switched-remediation-probe"
        uses_merit_probe = (
            active_merit_probe.status in {"proposal", "warning"}
            and active_merit_probe.before_metrics is not None
            and active_merit_probe.after_metrics is not None
        )
        before = (
            active_merit_probe.before_metrics
            if uses_merit_probe
            else optimization_attempt.before_metrics
        )
        after = (
            active_merit_probe.after_metrics
            if uses_merit_probe
            else optimization_attempt.after_metrics
        )
        metric_updates: list[OptimizationMetricUpdate] = []
        rms_passed = False
        mtf_field_passed = False
        mtf_band_passed = False
        mtf_field_weighted_passed = False
        before_bands = mtf_bands_from_snapshot(before)
        after_bands = mtf_bands_from_snapshot(after)
        before_floor_gap = _image_quality_floor_gap_score(before)
        after_floor_gap = _image_quality_floor_gap_score(after)

        if before_floor_gap is not None or after_floor_gap is not None:
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="local_merit_floor_gap_score",
                    before=before_floor_gap,
                    after=after_floor_gap,
                    unit=None,
                    direction=_metric_direction(
                        before_floor_gap,
                        after_floor_gap,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        "combined MTF/RMS floor gap on the active merit branch; "
                        "lower is closer to draft_ready"
                    ),
                )
            )

        if (
            before is not None
            and after is not None
            and before.max_rms_spot_radius_um is not None
            and after.max_rms_spot_radius_um is not None
        ):
            rms_passed = after.max_rms_spot_radius_um <= before.max_rms_spot_radius_um
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="max_rms_spot_radius",
                    before=before.max_rms_spot_radius_um,
                    after=after.max_rms_spot_radius_um,
                    unit="um",
                    direction=_metric_direction(
                        before.max_rms_spot_radius_um,
                        after.max_rms_spot_radius_um,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        f"protected branch max RMS {before.max_rms_spot_radius_um:.2f}->"
                        f"{after.max_rms_spot_radius_um:.2f} um"
                    ),
                )
            )
        if (
            before is not None
            and after is not None
            and before.mtf_max_field_frac is not None
            and after.mtf_max_field_frac is not None
        ):
            mtf_field_passed = after.mtf_max_field_frac >= before.mtf_max_field_frac
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="mtf_max_field_frac",
                    before=before.mtf_max_field_frac,
                    after=after.mtf_max_field_frac,
                    unit="field",
                    direction=_metric_direction(
                        before.mtf_max_field_frac,
                        after.mtf_max_field_frac,
                        higher_is_better=True,
                    ),
                    interpretation=(
                        "MTF evidence field "
                        f"{format_mtf_field_fraction(before.mtf_max_field_frac)}->"
                        f"{format_mtf_field_fraction(after.mtf_max_field_frac)}"
                    ),
                )
            )
        if (
            before_bands.multiband_min_score is not None
            and after_bands.multiband_min_score is not None
        ):
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="mtf_multiband_min_score",
                    before=before_bands.multiband_min_score,
                    after=after_bands.multiband_min_score,
                    unit=None,
                    direction=_metric_direction(
                        before_bands.multiband_min_score,
                        after_bands.multiband_min_score,
                        higher_is_better=True,
                    ),
                    interpretation=(
                        f"minimum MTF score across 50-250 lp/mm "
                        f"{before_bands.multiband_min_score:.3f}->"
                        f"{after_bands.multiband_min_score:.3f}"
                    ),
                )
            )
        if (
            before_bands.field_weighted_score is not None
            and after_bands.field_weighted_score is not None
        ):
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="mtf_field_weighted_score",
                    before=before_bands.field_weighted_score,
                    after=after_bands.field_weighted_score,
                    unit=None,
                    direction=_metric_direction(
                        before_bands.field_weighted_score,
                        after_bands.field_weighted_score,
                        higher_is_better=True,
                    ),
                    interpretation=(
                        f"field-weighted MTF score "
                        f"{before_bands.field_weighted_score:.3f}->"
                        f"{after_bands.field_weighted_score:.3f}"
                    ),
                )
            )
        for metric, label, before_value, after_value in (
            ("mtf_50lpmm_min", "50", before_bands.min_50, after_bands.min_50),
            ("mtf_100lpmm_min", "100", before_bands.min_100, after_bands.min_100),
            ("mtf_150lpmm_min", "150", before_bands.min_150, after_bands.min_150),
            ("mtf_200lpmm_min", "200", before_bands.min_200, after_bands.min_200),
            ("mtf_250lpmm_min", "250", before_bands.min_250, after_bands.min_250),
        ):
            if before_value is None or after_value is None:
                continue
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric=metric,
                    before=before_value,
                    after=after_value,
                    unit=None,
                    direction=_metric_direction(
                        before_value,
                        after_value,
                        higher_is_better=True,
                    ),
                    interpretation=(
                        f"minimum MTF near {label} lp/mm {before_value:.3f}->{after_value:.3f}"
                    ),
                )
            )
        mtf_field_weighted_passed = mtf_field_weighted_non_regressed(
            before_bands,
            after_bands,
        )
        mtf_band_passed = (
            before_bands.multiband_min_score is not None
            and after_bands.multiband_min_score is not None
            and before_bands.min_100 is not None
            and after_bands.min_100 is not None
            and mtf_multiband_non_regressed(before_bands, after_bands)
            and mtf_field_weighted_passed
        )
        if (
            before is not None
            and after is not None
            and before.effective_focal_length_mm is not None
            and after.effective_focal_length_mm is not None
        ):
            before_error = abs(before.effective_focal_length_mm - efl_mm)
            after_error = abs(after.effective_focal_length_mm - efl_mm)
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="efl_error",
                    before=before_error,
                    after=after_error,
                    unit="mm",
                    direction=_metric_direction(
                        before_error,
                        after_error,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        f"EFL remains locked while merit evidence changes "
                        f"{before_error:.3f}->{after_error:.3f} mm"
                    ),
                )
            )

        passed = (
            uses_merit_probe
            and active_merit_probe.status == "proposal"
            and rms_passed
            and mtf_field_passed
            and mtf_band_passed
        )
        unlocked = _unlocked_tasks_after(task.task_id, passed=passed)
        if not passed and needs_asphere_guarded_audit:
            asphere_task = _find_task("asphere-guarded-audit")
            if asphere_task is not None:
                unlocked = [asphere_task.task_id]
        if uses_merit_probe:
            summary = (
                "protected RMS merit probe improved verified RMS/MTF evidence"
                if passed
                else "protected RMS merit probe did not pass promotion gates"
            )
            next_action = (
                f"unlock {', '.join(unlocked)} for production validation"
                if unlocked
                else "calibrate or rerun the bounded RMS merit probe before production validation"
            )
            selected_variable = ""
            if active_merit_probe.variable_changes:
                if len(active_merit_probe.variable_changes) == 1:
                    change = active_merit_probe.variable_changes[0]
                    selected_variable = (
                        f"variable={change.variable} S{change.surface_index} "
                        f"{change.before:.4f}->{change.after:.4f}"
                    )
                else:
                    selected_variable = (
                        f"variable=compound {_changes_label(active_merit_probe.variable_changes)}"
                    )
            eligible_variables = [
                f"{candidate.variable} S{candidate.surface_index}"
                for candidate in active_merit_probe.variable_candidates
                if candidate.status == "eligible"
            ]
            asphere_audit_count = sum(
                1
                for candidate in active_merit_probe.variable_candidates
                if candidate.variable == "asphere_coefficient"
                and candidate.status == "audited_only"
            )
            guarded_asphere_count = sum(
                1
                for candidate in active_merit_probe.variable_candidates
                if candidate.variable == "asphere_coefficient"
                and candidate.status == "audited_only"
                and candidate.manufacturability_status == "guarded"
            )
            asphere_audit_trials = [
                trial
                for trial in active_merit_probe.candidate_trials
                if trial.variable == "asphere_coefficient"
            ]
            joint_audit_trials = [
                trial
                for trial in active_merit_probe.candidate_trials
                if trial.variable == "joint_asphere_merit"
            ]
            asphere_prescreen_detail = next(
                (
                    item
                    for item in active_merit_probe.diagnostics
                    if item.startswith("asphere prescreen trials=")
                ),
                "asphere prescreen trials=0",
            )
            first_rejected_trial = next(
                (
                    trial
                    for trial in active_merit_probe.candidate_trials
                    if trial.status in {"rejected", "failed", "skipped"}
                ),
                None,
            )
            promotion_scores = [
                trial.promotion_score
                for trial in active_merit_probe.candidate_trials
                if trial.promotion_score is not None
            ]
            best_floor_gap_trial = _best_floor_gap_trial(active_merit_probe)
            if (
                best_floor_gap_trial is not None
                and best_floor_gap_trial.image_quality_floor_gap_closure is not None
            ):
                floor_gap_evidence_prefix = (
                    "best accepted image-quality floor gap closure"
                    if best_floor_gap_trial.status == "accepted"
                    else "best gate-ranked image-quality floor gap closure"
                )
                best_floor_gap_evidence = (
                    f"{floor_gap_evidence_prefix}="
                    f"{best_floor_gap_trial.image_quality_floor_gap_closure:+.3f}; "
                    f"trial={best_floor_gap_trial.variable} "
                    f"S{best_floor_gap_trial.surface_index}; "
                    f"status={best_floor_gap_trial.status}"
                )
            else:
                best_floor_gap_evidence = ""
            probe_evidence = [
                f"merit probe={active_merit_probe.status}",
                f"merit probe source={active_merit_probe_source}",
                f"operand={active_merit_probe.operand}",
                selected_variable,
                f"candidate variables={','.join(eligible_variables[:6])}",
                (
                    f"candidate trials={len(active_merit_probe.candidate_trials)}; "
                    f"asphere guarded count={guarded_asphere_count}; "
                    f"asphere audit trials={len(asphere_audit_trials)}; "
                    f"joint audit trials={len(joint_audit_trials)}"
                ),
                asphere_prescreen_detail,
                (f"best promotion score={max(promotion_scores):.3f}" if promotion_scores else ""),
                best_floor_gap_evidence,
                (
                    f"first rejected trial={first_rejected_trial.variable} "
                    f"S{first_rejected_trial.surface_index} {first_rejected_trial.reason}"
                    if first_rejected_trial is not None
                    else ""
                ),
                f"asphere audited-only count={asphere_audit_count}",
                f"fields={','.join(f'{value:.1f}' for value in active_merit_probe.field_samples)}",
                (
                    f"rms improvement={active_merit_probe.rms_improvement_um:.2f} um"
                    if active_merit_probe.rms_improvement_um is not None
                    else "rms improvement unavailable"
                ),
            ]
        else:
            summary = "protected branch merit evidence is verification-only; dedicated RMS probe was not trusted"
            next_action = "run a calibrated bounded RMS merit probe before production validation"
            probe_evidence = [
                f"merit probe={active_merit_probe.status}",
                f"merit probe source={active_merit_probe_source}",
                *active_merit_probe.failures[:2],
            ]
        return OptimizationTaskRun(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            status="passed" if passed else "warning",
            summary=summary,
            metric_updates=metric_updates,
            unlocked_tasks=unlocked,
            next_action=next_action,
            evidence=_clean_evidence(
                [
                    *task.evidence,
                    *probe_evidence,
                    f"RMS non-worse={rms_passed}",
                    f"MTF field non-worse={mtf_field_passed}",
                    f"MTF 50/100/150/200/250 lp/mm non-worse={mtf_band_passed}",
                    f"MTF field-weighted score non-worse={mtf_field_weighted_passed}",
                ],
                limit=16,
            ),
        )

    def _second_pass_recovery_replay_run(task: OptimizationTask) -> OptimizationTaskRun:
        second_pass_candidate = next(
            (
                candidate
                for candidate in draft_candidates
                if candidate.candidate_id == "second-pass-recovery-candidate"
            ),
            None,
        )
        recommended_candidate = next(
            (
                candidate
                for candidate in draft_candidates
                if candidate.candidate_id == recommended_candidate_id
            ),
            None,
        )
        before = (
            recommended_candidate.metrics
            if recommended_candidate is not None and recommended_candidate.metrics is not None
            else optimization_attempt.after_metrics
        )
        after = second_pass_candidate.metrics if second_pass_candidate is not None else None
        before_gap = _image_quality_floor_gap_score(before)
        after_gap = _image_quality_floor_gap_score(after)
        gap_closure = (
            before_gap - after_gap if before_gap is not None and after_gap is not None else None
        )

        before_bands = mtf_bands_from_snapshot(before)
        after_bands = mtf_bands_from_snapshot(after)
        rms_non_regressed = (
            before is not None
            and after is not None
            and before.max_rms_spot_radius_um is not None
            and after.max_rms_spot_radius_um is not None
            and after.max_rms_spot_radius_um <= before.max_rms_spot_radius_um
        )
        mtf_field_non_regressed = (
            before is not None
            and after is not None
            and before.mtf_max_field_frac is not None
            and after.mtf_max_field_frac is not None
            and after.mtf_max_field_frac >= before.mtf_max_field_frac
        )
        mtf_band_non_regressed = (
            before_bands.multiband_min_score is not None
            and after_bands.multiband_min_score is not None
            and before_bands.min_100 is not None
            and after_bands.min_100 is not None
            and mtf_multiband_non_regressed(before_bands, after_bands)
        )
        mtf_field_weighted_passed = mtf_field_weighted_non_regressed(
            before_bands,
            after_bands,
        )
        before_efl_error = (
            abs(before.effective_focal_length_mm - efl_mm)
            if before is not None and before.effective_focal_length_mm is not None
            else None
        )
        after_efl_error = (
            abs(after.effective_focal_length_mm - efl_mm)
            if after is not None and after.effective_focal_length_mm is not None
            else None
        )
        first_order_locked = (
            before_efl_error is not None
            and after_efl_error is not None
            and after_efl_error <= max(before_efl_error + 1e-6, 0.05)
        )
        source_probe_passed = (
            remediation_optimization_probe is not None
            and remediation_optimization_probe.status == "proposal"
            and remediation_optimization_probe.after_metrics == after
        )

        checks = [
            _gate_check(
                check_id="candidate_available",
                label="Second-pass candidate is available",
                passed=second_pass_candidate is not None and after is not None,
                evidence=[
                    (
                        f"candidate={second_pass_candidate.candidate_id}"
                        if second_pass_candidate is not None
                        else "second-pass candidate missing"
                    )
                ],
            ),
            _gate_check(
                check_id="floor_gap_closure_positive",
                label="Second-pass replay improves floor gap",
                passed=gap_closure is not None and gap_closure > 0.0,
                comparator="> 0",
                measured_value=gap_closure,
                target_value=0.0,
                evidence=[
                    (
                        f"floor-gap closure={gap_closure:+.3f}"
                        if gap_closure is not None
                        else "floor-gap closure unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="floor_gap_cleared",
                label="MTF/RMS floor gap is cleared",
                passed=after_gap is not None and after_gap <= 0.0,
                comparator="<= 0",
                measured_value=after_gap,
                target_value=0.0,
                evidence=[
                    (
                        f"second-pass floor gap={after_gap:.3f}"
                        if after_gap is not None
                        else "second-pass floor gap unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="rms_non_regressed",
                label="RMS does not regress",
                passed=rms_non_regressed,
                evidence=[
                    (
                        f"RMS {before.max_rms_spot_radius_um:.2f}->"
                        f"{after.max_rms_spot_radius_um:.2f}um"
                        if before is not None
                        and after is not None
                        and before.max_rms_spot_radius_um is not None
                        and after.max_rms_spot_radius_um is not None
                        else "RMS comparison unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="mtf_field_non_regressed",
                label="MTF field coverage does not regress",
                passed=mtf_field_non_regressed,
                evidence=[
                    (
                        "MTF field "
                        f"{format_mtf_field_fraction(before.mtf_max_field_frac)}->"
                        f"{format_mtf_field_fraction(after.mtf_max_field_frac)}"
                        if before is not None
                        and after is not None
                        and before.mtf_max_field_frac is not None
                        and after.mtf_max_field_frac is not None
                        else "MTF field comparison unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="mtf_multiband_non_regressed",
                label="Multiband MTF does not regress",
                passed=mtf_band_non_regressed,
                evidence=[
                    (
                        f"multiband min {before_bands.multiband_min_score:.3f}->"
                        f"{after_bands.multiband_min_score:.3f}"
                        if before_bands.multiband_min_score is not None
                        and after_bands.multiband_min_score is not None
                        else "multiband MTF comparison unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="mtf_field_weighted_non_regressed",
                label="Field-weighted MTF does not regress",
                passed=mtf_field_weighted_passed,
                evidence=[
                    (
                        f"field-weighted MTF {before_bands.field_weighted_score:.3f}->"
                        f"{after_bands.field_weighted_score:.3f}"
                        if before_bands.field_weighted_score is not None
                        and after_bands.field_weighted_score is not None
                        else "field-weighted MTF comparison unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="first_order_locked",
                label="First-order targets stay locked",
                passed=first_order_locked,
                evidence=[
                    (
                        f"EFL error {before_efl_error:.3f}->{after_efl_error:.3f}mm"
                        if before_efl_error is not None and after_efl_error is not None
                        else "EFL comparison unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="source_probe_gate_clean",
                label="Source remediation probe is gate-clean",
                passed=source_probe_passed,
                evidence=[
                    (
                        f"remediation probe={remediation_optimization_probe.status}"
                        if remediation_optimization_probe is not None
                        else "remediation probe unavailable"
                    )
                ],
            ),
            _gate_check(
                check_id="payload_frozen",
                label="Delivered payload remains frozen",
                passed=True,
                evidence=["recommended candidate metrics remain unchanged until promotion"],
            ),
        ]
        required_checks = [check for check in checks if check.required_for_promotion]
        failed_check_ids = [check.check_id for check in required_checks if check.status != "pass"]
        recommended_variables, remediation_actions = _replay_gate_remediation_for_checks(
            failed_check_ids
        )
        if "mtf_field_non_regressed" in failed_check_ids:
            recommended_variables = _unique_in_order([*recommended_variables, "full-field MTF"])
            remediation_actions = _unique_in_order(
                [
                    *remediation_actions,
                    "recover full-field MTF coverage before second-pass promotion",
                ]
            )
        if "source_probe_gate_clean" in failed_check_ids:
            recommended_variables = _unique_in_order(
                [*recommended_variables, "replay-gate verification"]
            )
            remediation_actions = _unique_in_order(
                [
                    *remediation_actions,
                    "rerun second-pass remediation probe before promotion review",
                ]
            )

        promotion_allowed = all(check.status == "pass" for check in required_checks)
        gate_status = (
            "pass"
            if promotion_allowed
            else ("fail" if any(check.status == "fail" for check in required_checks) else "blocked")
        )
        gate_summary = (
            "second-pass replay gate passes; candidate may be reviewed for promotion"
            if promotion_allowed
            else (
                "second-pass replay improves local MTF/RMS evidence but still blocks promotion"
                if gap_closure is not None and gap_closure > 0.0
                else "second-pass replay lacks enough evidence for promotion"
            )
        )
        replay_gate = OptimizationReplayGate(
            gate_id="second-pass-recovery-replay",
            status=gate_status,
            promotion_allowed=promotion_allowed,
            summary=gate_summary,
            checks=checks,
            failed_check_ids=failed_check_ids,
            recommended_variables=recommended_variables,
            remediation_actions=remediation_actions,
            next_action=(
                "package the second-pass recovery candidate for promotion review"
                if promotion_allowed
                else (
                    remediation_actions[0]
                    if remediation_actions
                    else "continue second-pass MTF/RMS floor recovery before promotion"
                )
            ),
        )

        metric_updates = [
            OptimizationMetricUpdate(
                metric="second_pass_replay_floor_gap_score",
                before=before_gap,
                after=after_gap,
                unit=None,
                direction=_metric_direction(
                    before_gap,
                    after_gap,
                    higher_is_better=False,
                ),
                interpretation=(
                    "held second-pass candidate floor gap compared with the "
                    "current recommended branch"
                ),
            )
        ]
        if (
            before is not None
            and after is not None
            and before.max_rms_spot_radius_um is not None
            and after.max_rms_spot_radius_um is not None
        ):
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric="second_pass_replay_max_rms_spot_radius",
                    before=before.max_rms_spot_radius_um,
                    after=after.max_rms_spot_radius_um,
                    unit="um",
                    direction=_metric_direction(
                        before.max_rms_spot_radius_um,
                        after.max_rms_spot_radius_um,
                        higher_is_better=False,
                    ),
                    interpretation=(
                        f"second-pass RMS {before.max_rms_spot_radius_um:.2f}->"
                        f"{after.max_rms_spot_radius_um:.2f} um"
                    ),
                )
            )
        for metric, before_value, after_value, higher_is_better in (
            (
                "second_pass_replay_mtf_multiband_min_score",
                before_bands.multiband_min_score,
                after_bands.multiband_min_score,
                True,
            ),
            (
                "second_pass_replay_mtf_field_weighted_score",
                before_bands.field_weighted_score,
                after_bands.field_weighted_score,
                True,
            ),
            (
                "second_pass_replay_efl_error",
                before_efl_error,
                after_efl_error,
                False,
            ),
        ):
            if before_value is None and after_value is None:
                continue
            metric_updates.append(
                OptimizationMetricUpdate(
                    metric=metric,
                    before=before_value,
                    after=after_value,
                    unit="mm" if metric.endswith("efl_error") else None,
                    direction=_metric_direction(
                        before_value,
                        after_value,
                        higher_is_better=higher_is_better,
                    ),
                    interpretation=(
                        "second-pass replay metric compared with the current recommended branch"
                    ),
                )
            )

        status = "passed" if promotion_allowed else "warning"
        return OptimizationTaskRun(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            status=status,
            summary=replay_gate.summary,
            metric_updates=metric_updates,
            unlocked_tasks=_unlocked_tasks_after(task.task_id, passed=promotion_allowed),
            next_action=replay_gate.next_action,
            evidence=_clean_evidence(
                [
                    *task.evidence,
                    (
                        f"recommended candidate={recommended_candidate_id}"
                        if recommended_candidate is not None
                        else "recommended candidate metrics unavailable"
                    ),
                    (
                        f"second-pass floor gap {before_gap:.3f}->{after_gap:.3f}"
                        if before_gap is not None and after_gap is not None
                        else "second-pass floor gap comparison unavailable"
                    ),
                    (
                        f"second-pass floor-gap closure={gap_closure:+.3f}"
                        if gap_closure is not None
                        else "second-pass floor-gap closure unavailable"
                    ),
                    f"promotion allowed={promotion_allowed}",
                    f"failed replay checks={', '.join(failed_check_ids) or 'none'}",
                    "recommended metrics remain frozen until replay gate promotion",
                ],
                limit=24,
            ),
            replay_gate=replay_gate,
        )

    def _asphere_guarded_audit_run(task: OptimizationTask) -> OptimizationTaskRun:
        first_asphere = guarded_asphere_candidates[0] if guarded_asphere_candidates else None
        asphere_trials = [
            trial
            for trial in merit_optimization_probe.candidate_trials
            if trial.variable == "asphere_coefficient"
        ]
        joint_trials = [
            trial
            for trial in merit_optimization_probe.candidate_trials
            if trial.variable == "joint_asphere_merit"
        ]
        best_trial = max(
            asphere_trials,
            key=lambda trial: (
                1 if trial.status == "improved" else 0,
                trial.rms_improvement_um if trial.rms_improvement_um is not None else -math.inf,
            ),
            default=None,
        )
        prescreen_detail = next(
            (
                item
                for item in merit_optimization_probe.diagnostics
                if item.startswith("asphere prescreen trials=")
            ),
            "asphere prescreen trials=0",
        )
        evidence = [
            prescreen_detail,
            f"audit trials={len(asphere_trials)}",
            f"joint audit trials={len(joint_trials)}",
            f"guarded asphere candidates={len(guarded_asphere_candidates)}",
        ]
        if best_trial is not None:
            evidence.extend(
                [
                    (
                        f"best trial={best_trial.status} "
                        f"rank={best_trial.prescreen_rank} "
                        f"step={best_trial.step_fraction:.3f} "
                        f"S{best_trial.surface_index}:c{best_trial.coefficient_index} "
                        f"{best_trial.before:.3g}->{best_trial.after:.3g}"
                        if best_trial.before is not None and best_trial.after is not None
                        else f"best trial={best_trial.status}"
                    ),
                    (
                        f"trial rms delta={best_trial.rms_improvement_um:+.2f}um"
                        if best_trial.rms_improvement_um is not None
                        else "trial rms delta unavailable"
                    ),
                    (
                        f"prescreen merit={best_trial.merit_before:.4f}->"
                        f"{best_trial.merit_after:.4f}"
                        if best_trial.merit_before is not None
                        and best_trial.merit_after is not None
                        else "prescreen merit unavailable"
                    ),
                    (
                        f"trial gates field={best_trial.mtf_field_non_regressed} "
                        f"band={best_trial.mtf_band_non_regressed} "
                        f"weighted={best_trial.mtf_field_weighted_non_regressed} "
                        f"efl={best_trial.efl_locked}"
                    ),
                ]
            )
        best_joint = max(
            joint_trials,
            key=lambda trial: (
                1 if trial.status == "improved" else 0,
                trial.rms_improvement_um if trial.rms_improvement_um is not None else -math.inf,
            ),
            default=None,
        )
        if best_joint is not None:
            evidence.extend(
                [
                    (
                        f"best joint={best_joint.status} "
                        f"{best_joint.coupled_variable} S{best_joint.coupled_surface_index} + "
                        f"S{best_joint.surface_index}:c{best_joint.coefficient_index} "
                        f"step={best_joint.step_fraction:.3f}"
                    ),
                    (
                        f"joint rms delta={best_joint.rms_improvement_um:+.2f}um"
                        if best_joint.rms_improvement_um is not None
                        else "joint rms delta unavailable"
                    ),
                ]
            )
        evidence.extend(task.evidence)
        if first_asphere is not None:
            evidence.extend(
                [
                    f"candidate=S{first_asphere.surface_index}:c{first_asphere.coefficient_index}",
                    f"power=r^{first_asphere.asphere_power}",
                    (
                        f"sag={first_asphere.edge_sag_delta_um:.2f}um "
                        f"slope={first_asphere.edge_slope_delta_mrad:.2f}mrad"
                        if first_asphere.edge_sag_delta_um is not None
                        and first_asphere.edge_slope_delta_mrad is not None
                        else "sag/slope guard unavailable"
                    ),
                    f"status={first_asphere.manufacturability_status}",
                ]
            )
        return OptimizationTaskRun(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            status="diagnostic",
            summary=(
                "guarded asphere perturbations were replayed in audit-only mode"
                if asphere_trials
                else "guarded asphere candidates are available for audit-only perturbation replay"
            ),
            metric_updates=[],
            unlocked_tasks=[],
            next_action=(
                "run audit-only asphere perturbation replay before allowing coefficient optimization"
            ),
            evidence=_clean_evidence(evidence, limit=12),
        )

    def _append_second_pass_replay_run(
        runs: list[OptimizationTaskRun],
        merit_run: OptimizationTaskRun,
    ) -> None:
        if "replay-second-pass-recovery-candidate" not in merit_run.unlocked_tasks:
            return
        second_pass_task = _find_task("replay-second-pass-recovery-candidate")
        if second_pass_task is not None:
            runs.append(_second_pass_recovery_replay_run(second_pass_task))

    def _append_recovery_replay_run(
        runs: list[OptimizationTaskRun],
        recovery_run: OptimizationTaskRun,
    ) -> None:
        if "replay-floor-gap-recovery-candidate" not in recovery_run.unlocked_tasks:
            return
        replay_task = _find_task("replay-floor-gap-recovery-candidate")
        if replay_task is not None:
            replay_run = _replay_floor_gap_recovery_candidate_run(replay_task)
            runs.append(replay_run)
            if "remediate-recovery-replay-gate" in replay_run.unlocked_tasks:
                remediation_task = _find_task("remediate-recovery-replay-gate")
                if remediation_task is not None:
                    remediation_run = _recovery_replay_remediation_run(remediation_task)
                    runs.append(remediation_run)
                    if "local-merit-tuning" in remediation_run.unlocked_tasks:
                        merit_task = _find_task("local-merit-tuning")
                        if merit_task is not None:
                            merit_run = _local_merit_tuning_run(merit_task)
                            runs.append(merit_run)
                            _append_second_pass_replay_run(runs, merit_run)
                            if "asphere-guarded-audit" in merit_run.unlocked_tasks:
                                asphere_task = _find_task("asphere-guarded-audit")
                                if asphere_task is not None:
                                    runs.append(_asphere_guarded_audit_run(asphere_task))
                    if "resolve-remediation-policy-block" in remediation_run.unlocked_tasks:
                        followup_task = _find_task("resolve-remediation-policy-block")
                        if followup_task is not None:
                            runs.append(_remediation_policy_followup_run(followup_task))

    def _optimization_task_runs() -> list[OptimizationTaskRun]:
        if not optimization_task_queue:
            return []

        first_ready = next(
            (task for task in optimization_task_queue if task.status == "ready"),
            optimization_task_queue[0],
        )
        gate = optimization_attempt.verification
        gate_status = gate.status if gate is not None else "not_run"

        if first_ready.task_id == "resolve-design-strategy":
            decision = design_strategy_decision
            stable_sibling_task = _find_task("review-stable-sibling-branch")
            runs = [
                OptimizationTaskRun(
                    task_id=first_ready.task_id,
                    candidate_id=first_ready.candidate_id,
                    status="diagnostic",
                    summary=(
                        decision.summary
                        if decision is not None
                        else "strategy decision is required before local optimization continues"
                    ),
                    metric_updates=[],
                    unlocked_tasks=(
                        ["review-stable-sibling-branch"] if stable_sibling_task is not None else []
                    ),
                    next_action=(
                        decision.required_evidence[0]
                        if decision is not None and decision.required_evidence
                        else "select one evidence path before promoting the branch"
                    ),
                    evidence=_clean_evidence(
                        [
                            *first_ready.evidence,
                            *(decision.tradeoffs if decision is not None else []),
                        ],
                        limit=12,
                    ),
                )
            ]
            if (
                stable_sibling_task is not None
                and stable_sibling_strategy_option is not None
                and stable_sibling_strategy_option.mtf_max_field_frac is not None
            ):
                sibling_field = stable_sibling_strategy_option.mtf_max_field_frac
                runs.append(
                    OptimizationTaskRun(
                        task_id=stable_sibling_task.task_id,
                        candidate_id=stable_sibling_task.candidate_id,
                        status="diagnostic",
                        summary=(
                            "stable high-FOV sibling branch improves scanned "
                            "edge-field stability but remains partial-field only"
                        ),
                        metric_updates=[
                            OptimizationMetricUpdate(
                                metric="mtf_max_field_frac",
                                before=best.metadata.mtf_max_field_frac,
                                after=sibling_field,
                                unit="field",
                                direction=_metric_direction(
                                    best.metadata.mtf_max_field_frac,
                                    sibling_field,
                                    higher_is_better=True,
                                ),
                                interpretation=(
                                    "sibling branch edge-field evidence improves "
                                    f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}->"
                                    f"{format_mtf_field_fraction(sibling_field)} "
                                    "while full-field target remains 1.0"
                                ),
                            )
                        ],
                        unlocked_tasks=[],
                        next_action=(
                            "clone the stable sibling branch, run canonical "
                            "1.0-field preflight, and keep selected payload frozen"
                        ),
                        evidence=_clean_evidence(
                            [
                                *stable_sibling_task.evidence,
                                "partial-field sibling review does not replace missing full-field seed evidence",
                                "selected seed payload remains unchanged during sibling review",
                            ],
                            limit=12,
                        ),
                    )
                )
            return runs

        if first_ready.task_id == "resolve-candidate-proxy-branch":
            policy = branch_selection_policy
            return [
                OptimizationTaskRun(
                    task_id=first_ready.task_id,
                    candidate_id=first_ready.candidate_id,
                    status="diagnostic",
                    summary=(
                        policy.summary
                        if policy is not None
                        else "candidate proxy branch review is required before promotion"
                    ),
                    metric_updates=[],
                    unlocked_tasks=[],
                    next_action=(
                        policy.promotion_requirements[0]
                        if policy is not None and policy.promotion_requirements
                        else "compare the low-risk branch against the active branch"
                    ),
                    evidence=_clean_evidence(
                        [
                            *first_ready.evidence,
                            *(policy.rationale if policy is not None else []),
                        ],
                        limit=12,
                    ),
                )
            ]

        if first_ready.task_id == "record-spec-repair-target":
            policy = branch_selection_policy
            preview = spec_repair_preview
            decision = spec_repair_decision
            contract = decision.rerun_contract if decision is not None else None
            metric_updates = []
            if preview is not None:
                metric_updates.append(
                    OptimizationMetricUpdate(
                        metric="target_focal_length_mm",
                        before=efl_mm,
                        after=preview.repaired_target_focal_length_mm,
                        unit="mm",
                        direction="diagnostic",
                        interpretation=(
                            "default spec repair preserves image height/FOV and "
                            "records the target EFL to replay before payload promotion"
                        ),
                    )
                )
                metric_updates.append(
                    OptimizationMetricUpdate(
                        metric="remaining_spec_tradeoffs",
                        before=None,
                        after=float(len(preview.remaining_tradeoffs)),
                        unit="count",
                        direction="diagnostic",
                        interpretation=(
                            "unresolved preview items that must be waived or closed "
                            "after recording the repaired target"
                        ),
                    )
                )
            return [
                OptimizationTaskRun(
                    task_id=first_ready.task_id,
                    candidate_id=first_ready.candidate_id,
                    status="diagnostic",
                    summary=(
                        "spec repair decision gate is ready; repaired-target preview "
                        "and rerun contract must be recorded before optimizer payload promotion"
                    ),
                    metric_updates=metric_updates,
                    unlocked_tasks=[],
                    next_action=(
                        policy.promotion_requirements[0]
                        if policy is not None and policy.promotion_requirements
                        else "record the repaired target decision before promotion"
                    ),
                    evidence=_clean_evidence(
                        [
                            *first_ready.evidence,
                            decision.decision_summary if decision is not None else "",
                            contract.query_summary if contract is not None else "",
                            *(contract.validation_checks if contract is not None else []),
                            *(preview.evidence if preview is not None else []),
                            *(preview.risks if preview is not None else []),
                        ],
                        limit=24,
                    ),
                )
            ]

        if first_ready.task_id == "apply-protected-change-set":
            status = "passed" if gate_status == "passed" else "warning"
            passed = status == "passed"
            unlocked = _unlocked_tasks_after(first_ready.task_id, passed=passed)
            runs = [
                OptimizationTaskRun(
                    task_id=first_ready.task_id,
                    candidate_id=first_ready.candidate_id,
                    status=status,
                    summary=(
                        gate.summary
                        if gate is not None
                        else "protected optimizer proposal has no verification gate"
                    ),
                    metric_updates=_metric_updates_from_attempt(),
                    unlocked_tasks=unlocked,
                    next_action=(
                        f"unlock {', '.join(unlocked)} on the optimizer-proposal clone"
                        if unlocked
                        else "hold downstream tasks until the protected gate is clean"
                    ),
                    evidence=_clean_evidence(
                        [
                            *first_ready.evidence,
                            f"verification gate={gate_status}",
                            f"optimizer status={optimization_attempt.status}",
                            f"applied_to_payload={optimization_attempt.applied_to_payload}",
                        ]
                    ),
                )
            ]
            if passed and "lock-first-order" in unlocked:
                lock_task = _find_task("lock-first-order")
                if lock_task is not None:
                    lock_run = _lock_first_order_run(lock_task)
                    runs.append(lock_run)
                    if lock_run.status == "passed":
                        if "recover-image-quality-floor" in lock_run.unlocked_tasks:
                            recovery_task = _find_task("recover-image-quality-floor")
                            if recovery_task is not None:
                                recovery_run = _image_quality_floor_recovery_run(recovery_task)
                                runs.append(recovery_run)
                                _append_recovery_replay_run(runs, recovery_run)
                        if "local-merit-tuning" in lock_run.unlocked_tasks:
                            merit_task = _find_task("local-merit-tuning")
                            if merit_task is not None:
                                merit_run = _local_merit_tuning_run(merit_task)
                                runs.append(merit_run)
                                _append_second_pass_replay_run(runs, merit_run)
                                if "asphere-guarded-audit" in merit_run.unlocked_tasks:
                                    asphere_task = _find_task("asphere-guarded-audit")
                                    if asphere_task is not None:
                                        runs.append(_asphere_guarded_audit_run(asphere_task))
            return runs

        if first_ready.task_id == "package-seed-baseline-review":
            unlocked = _unlocked_tasks_after(first_ready.task_id, passed=True)
            runs = [
                OptimizationTaskRun(
                    task_id=first_ready.task_id,
                    candidate_id=first_ready.candidate_id,
                    status="passed",
                    summary=(
                        "unchanged real seed baseline is packaged as a reviewable first-pass draft"
                    ),
                    metric_updates=[
                        OptimizationMetricUpdate(
                            metric="acceptance_score",
                            before=None,
                            after=1.0,
                            unit=None,
                            direction="improved",
                            interpretation=(
                                "seed-baseline hold is accepted without optimizer application"
                            ),
                        )
                    ],
                    unlocked_tasks=unlocked,
                    next_action=(
                        f"optional refinement may continue with {', '.join(unlocked)}"
                        if unlocked
                        else "send the unchanged seed-baseline package to review"
                    ),
                    evidence=_clean_evidence(
                        [
                            *first_ready.evidence,
                            requirement_coverage_summary.summary
                            if requirement_coverage_summary is not None
                            else "",
                            manufacturability_review.summary,
                            "no optimizer proposal is required for this accepted seed-baseline hold",
                        ],
                        limit=8,
                    ),
                )
            ]
            lock_task = _find_task("lock-first-order")
            if lock_task is not None and "lock-first-order" in unlocked:
                lock_run = _lock_first_order_run(lock_task)
                runs.append(lock_run)
                if (
                    lock_run.status == "passed"
                    and "recover-image-quality-floor" in lock_run.unlocked_tasks
                ):
                    recovery_task = _find_task("recover-image-quality-floor")
                    if recovery_task is not None:
                        recovery_run = _image_quality_floor_recovery_run(recovery_task)
                        runs.append(recovery_run)
                        _append_recovery_replay_run(runs, recovery_run)
            return runs

        if first_ready.task_id == "package-optimizer-proposal-review":
            unlocked = _unlocked_tasks_after(first_ready.task_id, passed=True)
            first_change = (
                prescription_change_set.changes[0]
                if prescription_change_set is not None and prescription_change_set.changes
                else None
            )
            runs = [
                OptimizationTaskRun(
                    task_id=first_ready.task_id,
                    candidate_id=first_ready.candidate_id,
                    status="passed",
                    summary=(
                        "verified optimizer proposal is packaged as a reviewable first-pass draft"
                    ),
                    metric_updates=_metric_updates_from_attempt(),
                    unlocked_tasks=unlocked,
                    next_action=(
                        f"optional refinement may continue with {', '.join(unlocked)}"
                        if unlocked
                        else "send the verified optimizer-proposal package to review"
                    ),
                    evidence=_clean_evidence(
                        [
                            *first_ready.evidence,
                            (
                                f"{first_change.variable} S{first_change.surface_index} "
                                f"{first_change.before:.4f}->{first_change.after:.4f}"
                                if first_change is not None
                                else ""
                            ),
                            (
                                prescription_change_set.expected_effect
                                if prescription_change_set is not None
                                else ""
                            ),
                            (
                                optimization_attempt.verification.summary
                                if optimization_attempt.verification is not None
                                else ""
                            ),
                            "no seed payload mutation is applied before review",
                        ],
                        limit=10,
                    ),
                )
            ]
            lock_task = _find_task("lock-first-order")
            if lock_task is not None and "lock-first-order" in unlocked:
                lock_run = _lock_first_order_run(lock_task)
                runs.append(lock_run)
                if lock_run.status == "passed":
                    if "recover-image-quality-floor" in lock_run.unlocked_tasks:
                        recovery_task = _find_task("recover-image-quality-floor")
                        if recovery_task is not None:
                            recovery_run = _image_quality_floor_recovery_run(recovery_task)
                            runs.append(recovery_run)
                            _append_recovery_replay_run(runs, recovery_run)
                    if "local-merit-tuning" in lock_run.unlocked_tasks:
                        merit_task = _find_task("local-merit-tuning")
                        if merit_task is not None:
                            merit_run = _local_merit_tuning_run(merit_task)
                            runs.append(merit_run)
                            _append_second_pass_replay_run(runs, merit_run)
                            if "asphere-guarded-audit" in merit_run.unlocked_tasks:
                                asphere_task = _find_task("asphere-guarded-audit")
                                if asphere_task is not None:
                                    runs.append(_asphere_guarded_audit_run(asphere_task))
            return runs

        if first_ready.task_id == "recover-full-field":
            recovery_trial = _floor_clean_full_field_recovery_trial()
            replay_gate = _full_field_recovery_replay_gate(recovery_trial)
            after_field = (
                recovery_trial.mtf_max_field_frac
                if recovery_trial is not None and recovery_trial.mtf_max_field_frac is not None
                else None
            )
            if after_field is None:
                after_field = (
                    full_field_recovery_diagnostic.current_field_frac
                    if full_field_recovery_diagnostic is not None
                    and full_field_recovery_diagnostic.current_field_frac is not None
                    else None
                )
            after_field = (
                after_field
                if after_field is not None
                else (
                    gate.mtf_max_field_frac
                    if gate is not None and gate.mtf_max_field_frac is not None
                    else best.metadata.mtf_max_field_frac
                )
            )
            passed = replay_gate.promotion_allowed or (
                after_field >= 1.0 and gate_status == "passed"
            )
            status = "passed" if passed else "warning"
            unlocked = _unlocked_tasks_after(first_ready.task_id, passed=passed)
            metric_updates = [
                OptimizationMetricUpdate(
                    metric="mtf_max_field_frac",
                    before=best.metadata.mtf_max_field_frac,
                    after=after_field,
                    unit="field",
                    direction=_metric_direction(
                        best.metadata.mtf_max_field_frac,
                        after_field,
                        higher_is_better=True,
                    ),
                    interpretation=(
                        "full-field target is 1.0; current evidence reaches "
                        f"{format_mtf_field_fraction(after_field)}"
                    ),
                )
            ]
            if recovery_trial is not None:
                before_gap = _image_quality_floor_gap_score(seed_baseline_metrics)
                after_gap = recovery_trial.image_quality_floor_gap_score
                metric_updates.append(
                    OptimizationMetricUpdate(
                        metric="full_field_recovery_floor_gap_score",
                        before=before_gap,
                        after=after_gap,
                        unit=None,
                        direction=_metric_direction(
                            before_gap,
                            after_gap,
                            higher_is_better=False,
                        ),
                        interpretation=(
                            "protected full-field recovery branch floor gap; "
                            "0.0 means the first-pass MTF/RMS floor is cleared"
                        ),
                    )
                )
                if recovery_trial.metrics is not None:
                    metrics = recovery_trial.metrics
                    if metrics.max_rms_spot_radius_um is not None:
                        metric_updates.append(
                            OptimizationMetricUpdate(
                                metric="full_field_recovery_max_rms_spot_radius",
                                before=(
                                    seed_baseline_metrics.max_rms_spot_radius_um
                                    if seed_baseline_metrics is not None
                                    else None
                                ),
                                after=metrics.max_rms_spot_radius_um,
                                unit="um",
                                direction=_metric_direction(
                                    (
                                        seed_baseline_metrics.max_rms_spot_radius_um
                                        if seed_baseline_metrics is not None
                                        else None
                                    ),
                                    metrics.max_rms_spot_radius_um,
                                    higher_is_better=False,
                                ),
                                interpretation=(
                                    "max RMS after applying the protected full-field "
                                    "recovery branch on a clone"
                                ),
                            )
                        )
            diagnostic_summary = (
                (
                    "full-field recovery diagnostic: "
                    f"{full_field_recovery_diagnostic.failure_mode}; "
                    "stable evidence reaches "
                    f"{format_mtf_field_fraction(full_field_recovery_diagnostic.current_field_frac)} field"
                )
                if full_field_recovery_diagnostic is not None
                else "full-field evidence is still incomplete; keep promotion gated"
            )
            return [
                OptimizationTaskRun(
                    task_id=first_ready.task_id,
                    candidate_id=first_ready.candidate_id,
                    status=status,
                    summary=(
                        "full-field evidence recovered on the protected branch"
                        if passed
                        else diagnostic_summary
                    ),
                    metric_updates=[
                        *metric_updates,
                    ],
                    unlocked_tasks=unlocked,
                    next_action=(
                        f"unlock {', '.join(unlocked)} after full-field recovery replay"
                        if unlocked
                        else (
                            replay_gate.next_action
                            if recovery_trial is not None
                            else (
                                full_field_recovery_diagnostic.next_action
                                if full_field_recovery_diagnostic is not None
                                else "rerun robust full-field ray aiming before applying prescription changes"
                            )
                        )
                    ),
                    evidence=_clean_evidence(
                        [
                            (
                                "protected changes="
                                f"{_changes_label(recovery_trial.variable_changes)}"
                                if recovery_trial is not None and recovery_trial.variable_changes
                                else ""
                            ),
                            (
                                f"replay gate={replay_gate.status}"
                                if recovery_trial is not None
                                else ""
                            ),
                            (
                                f"promotion allowed={replay_gate.promotion_allowed}"
                                if recovery_trial is not None
                                else ""
                            ),
                            (
                                "failed replay checks="
                                f"{', '.join(replay_gate.failed_check_ids) or 'none'}"
                                if recovery_trial is not None
                                else ""
                            ),
                            *(
                                full_field_recovery_diagnostic.evidence
                                if full_field_recovery_diagnostic is not None
                                else []
                            ),
                            *first_ready.evidence,
                            f"verification gate={gate_status}",
                            *(gate.diagnostics[:2] if gate is not None else []),
                        ],
                        limit=20,
                    ),
                    replay_gate=replay_gate,
                )
            ]

        if first_ready.task_id == "lock-first-order":
            lock_run = _lock_first_order_run(first_ready)
            runs = [lock_run]
            if lock_run.status == "passed":
                if "recover-image-quality-floor" in lock_run.unlocked_tasks:
                    recovery_task = _find_task("recover-image-quality-floor")
                    if recovery_task is not None:
                        recovery_run = _image_quality_floor_recovery_run(recovery_task)
                        runs.append(recovery_run)
                        _append_recovery_replay_run(runs, recovery_run)
                if "local-merit-tuning" in lock_run.unlocked_tasks:
                    merit_task = _find_task("local-merit-tuning")
                    if merit_task is not None:
                        merit_run = _local_merit_tuning_run(merit_task)
                        runs.append(merit_run)
                        _append_second_pass_replay_run(runs, merit_run)
            return runs

        if first_ready.task_id == "stabilize-optimizer":
            return [
                OptimizationTaskRun(
                    task_id=first_ready.task_id,
                    candidate_id=first_ready.candidate_id,
                    status="diagnostic",
                    summary=optimization_attempt.summary,
                    metric_updates=_metric_updates_from_attempt(),
                    unlocked_tasks=[],
                    next_action=(
                        "rerun protected optimization with narrowed variables and "
                        "finite ray-aiming diagnostics"
                    ),
                    evidence=_clean_evidence(
                        [
                            *first_ready.evidence,
                            *optimization_attempt.diagnostics[:2],
                            *optimization_attempt.failures[:2],
                        ]
                    ),
                )
            ]

        return [
            OptimizationTaskRun(
                task_id=first_ready.task_id,
                candidate_id=first_ready.candidate_id,
                status="diagnostic",
                summary="queued task is ready but has no deterministic runner yet",
                metric_updates=[],
                unlocked_tasks=[],
                next_action="attach a protected deterministic runner before promoting this task",
                evidence=_clean_evidence(first_ready.evidence),
            )
        ]

    optimization_task_runs = _optimization_task_runs()

    def _is_informative_second_pass_hold(
        run: OptimizationTaskRun | None,
    ) -> bool:
        if (
            run is None
            or run.task_id != "replay-second-pass-recovery-candidate"
            or run.status != "warning"
            or run.replay_gate is None
            or run.replay_gate.promotion_allowed
        ):
            return False
        floor_metric = next(
            (
                metric
                for metric in run.metric_updates
                if metric.metric == "second_pass_replay_floor_gap_score"
            ),
            None,
        )
        return (
            floor_metric is not None
            and floor_metric.before is not None
            and floor_metric.after is not None
            and floor_metric.after < floor_metric.before
            and "floor_gap_cleared" in run.replay_gate.failed_check_ids
        )

    def _is_informative_floor_recovery_hold(
        runs: list[OptimizationTaskRun],
    ) -> bool:
        recovery_run = next(
            (run for run in runs if run.task_id == "recover-image-quality-floor"),
            None,
        )
        replay_run = next(
            (run for run in runs if run.task_id == "replay-floor-gap-recovery-candidate"),
            None,
        )
        if (
            recovery_run is None
            or replay_run is None
            or recovery_run.status not in {"warning", "passed", "diagnostic"}
            or replay_run.status not in {"warning", "diagnostic"}
            or replay_run.replay_gate is None
            or replay_run.replay_gate.promotion_allowed
        ):
            return False
        recovery_metric = next(
            (
                metric
                for metric in recovery_run.metric_updates
                if metric.metric == "recovery_probe_floor_gap_score"
            ),
            None,
        )
        payload_frozen = any(
            check.check_id == "payload_frozen" and check.status == "pass"
            for check in replay_run.replay_gate.checks
        )
        return (
            recovery_metric is not None
            and recovery_metric.before is not None
            and recovery_metric.after is not None
            and recovery_metric.after < recovery_metric.before
            and any("best floor-gap trial=" in item for item in recovery_run.evidence)
            and "floor_gap_cleared" in replay_run.replay_gate.failed_check_ids
            and payload_frozen
        )

    def _full_field_recovery_review_ready() -> bool:
        recovery_run = next(
            (run for run in optimization_task_runs if run.task_id == "recover-full-field"),
            None,
        )
        return (
            performance_aperture_tradeoff_resolution is not None
            and prescription_change_set is not None
            and prescription_change_set.source_candidate_id
            == "full-field-floor-clean-recovery-candidate"
            and _floor_clean_full_field_recovery_trial() is not None
            and recovery_run is not None
            and recovery_run.status == "passed"
            and recovery_run.replay_gate is not None
            and recovery_run.replay_gate.status == "pass"
            and recovery_run.replay_gate.promotion_allowed
        )

    def _draft_acceptance_gate() -> DraftAcceptanceGate:
        checks: list[DraftAcceptanceCheck] = []
        full_field_recovery_review_ready = _full_field_recovery_review_ready()

        def add_check(
            check_id: str,
            label: str,
            status: str,
            evidence: str,
            required_action: str | None = None,
        ) -> None:
            checks.append(
                DraftAcceptanceCheck(
                    check_id=check_id,
                    label=label,
                    status=status,
                    evidence=evidence,
                    required_action=required_action,
                )
            )

        coverage_status = (
            requirement_coverage_summary.status
            if requirement_coverage_summary is not None
            else "blocked"
        )
        coverage_required = next(
            (
                item.next_action
                for item in requirement_coverage
                if item.status in {"miss", "tradeoff", "unscored"} and item.next_action
            ),
            None,
        )
        add_check(
            "requirement_coverage",
            "Requirement coverage",
            (
                "pass"
                if coverage_status == "met"
                else ("blocker" if coverage_status == "blocked" else "warning")
            ),
            (
                requirement_coverage_summary.summary
                if requirement_coverage_summary is not None
                else "requirement coverage missing"
            ),
            coverage_required,
        )

        add_check(
            "manufacturability",
            "Manufacturability proxy",
            (
                "pass"
                if manufacturability_review.status == "pass"
                else ("blocker" if manufacturability_review.status == "blocked" else "warning")
            ),
            f"{manufacturability_review.summary}; score={manufacturability_review.score:.2f}",
            next(
                (
                    check.mitigation
                    for check in manufacturability_review.checks
                    if check.status in {"blocker", "warning"} and check.mitigation
                ),
                None,
            ),
        )

        if delivery_gate is None:
            add_check(
                "delivery_gate",
                "Delivery gate",
                "pass",
                "no delivery restriction beyond standard draft review",
                None,
            )
        else:
            add_check(
                "delivery_gate",
                "Delivery gate",
                "blocker" if delivery_gate.status == "blocked" else "warning",
                f"{delivery_gate.status}: {delivery_gate.summary}",
                delivery_gate.promotion_requirements[0]
                if delivery_gate.promotion_requirements
                else None,
            )

        if branch_selection_policy is not None:
            add_check(
                "branch_selection",
                "Branch selection policy",
                (
                    "warning"
                    if branch_selection_policy.status == "strategy_resolution_required"
                    else "pass"
                ),
                branch_selection_policy.summary,
                branch_selection_policy.promotion_requirements[0]
                if branch_selection_policy.promotion_requirements
                else None,
            )

        if (
            candidate_proxy_branch_resolution is not None
            and candidate_proxy_branch_resolution.status == "rejected_for_target_fit"
        ):
            add_check(
                "candidate_proxy_review",
                "Candidate proxy review",
                "pass",
                (
                    f"lower-risk branch {candidate_proxy_branch_resolution.candidate_case_id} "
                    "was compared and rejected: "
                    + "; ".join(candidate_proxy_branch_resolution.blockers[:2])
                ),
                None,
            )
        elif candidate_proxy_review_opportunity is None:
            selected_candidate = candidate_comparison[0] if candidate_comparison else None
            add_check(
                "candidate_proxy_review",
                "Candidate proxy review",
                "pass",
                (
                    "selected seed is the lowest candidate review-risk branch or within margin"
                    if selected_candidate is None
                    else (
                        f"selected seed {selected_candidate.case_id} is lowest review-risk "
                        "branch or within margin"
                    )
                ),
                None,
            )
        else:
            selected_candidate, lower_risk_candidate, selected_risk, lower_risk = (
                candidate_proxy_review_opportunity
            )
            add_check(
                "candidate_proxy_review",
                "Candidate proxy review",
                "warning",
                (
                    f"lower-risk real seed {lower_risk_candidate.case_id} "
                    f"review risk={lower_risk:.2f} vs selected "
                    f"{selected_candidate.case_id} review risk={selected_risk:.2f}"
                ),
                "compare the low-risk candidate branch before cost/yield-sensitive release claims",
            )

        if fov_alternative_branch_resolution is not None:
            fov_resolution = fov_alternative_branch_resolution
            if fov_resolution.status == "rejected_for_target_fit":
                add_check(
                    "fov_alternative_review",
                    "FOV alternative review",
                    "pass",
                    (f"{fov_resolution.summary}: " + "; ".join(fov_resolution.blockers[:2])),
                    None,
                )
            else:
                add_check(
                    "fov_alternative_review",
                    "FOV alternative review",
                    "warning",
                    fov_resolution.summary,
                    (
                        f"compare FOV alternative {fov_resolution.candidate_case_id} "
                        "against selected seed before accepting the narrower-FOV branch"
                    ),
                )

        verification = optimization_attempt.verification
        if seed_baseline_hold_reviewable:
            optimizer_status = "pass"
            optimizer_evidence = (
                "unchanged seed-baseline hold accepted; no protected optimizer change "
                "is required for this reviewable first-pass draft"
            )
            optimizer_action = None
        elif full_field_recovery_review_ready:
            optimizer_status = "pass"
            optimizer_evidence = (
                "protected full-field recovery replay passed for the primary review "
                "branch; EFL optimizer warning stays diagnostic for the unchanged seed payload"
            )
            optimizer_action = None
        elif verification is None:
            optimizer_status = "warning"
            optimizer_evidence = optimization_attempt.summary
            optimizer_action = "attach a protected verification gate before promotion"
        elif verification.status == "passed":
            optimizer_status = "pass"
            optimizer_evidence = verification.summary
            optimizer_action = None
        elif verification.status == "warning":
            optimizer_status = "warning"
            optimizer_evidence = verification.summary
            optimizer_action = "resolve optimizer verification warning before applying changes"
        else:
            optimizer_status = "blocker"
            optimizer_evidence = verification.summary
            optimizer_action = "stabilize protected optimizer before treating proposal as a draft"
        add_check(
            "optimizer_verification",
            "Optimizer verification",
            optimizer_status,
            optimizer_evidence,
            optimizer_action,
        )

        if seed_baseline_hold_reviewable:
            merit_status = "pass"
            merit_action = None
            merit_summary = (
                "image-quality probe waived for unchanged seed-baseline hold; real seed "
                "MTF evidence is used as the first-pass review payload"
            )
        elif full_field_recovery_review_ready:
            merit_status = "pass"
            merit_action = None
            merit_summary = (
                "protected full-field recovery branch clears the MTF/RMS review floor; "
                "local merit probe remains diagnostic until the cloned branch is applied"
            )
        elif merit_optimization_probe.status == "proposal":
            merit_status = "pass"
            merit_action = None
            merit_summary = merit_optimization_probe.summary
        elif merit_optimization_probe.status in {"warning", "not_attempted"}:
            merit_status = "warning"
            merit_action = "continue merit tuning or keep the seed baseline as the accepted payload"
            merit_summary = merit_optimization_probe.summary
        else:
            merit_status = "blocker"
            merit_action = "stabilize image-quality merit probe before draft acceptance"
            merit_summary = merit_optimization_probe.summary
        add_check(
            "image_quality_probe",
            "Image-quality merit probe",
            merit_status,
            merit_summary,
            merit_action,
        )

        floor = recommended_image_quality_floor
        floor_status = (
            "pass"
            if floor.status == "pass"
            else ("blocker" if floor.status == "blocker" else "warning")
        )
        add_check(
            "image_quality_floor",
            "Image-quality review floor",
            floor_status,
            "; ".join([*floor.evidence[:4], *floor.blockers[:2]]),
            floor.action,
        )

        latest_run = optimization_task_runs[-1] if optimization_task_runs else None
        informative_second_pass_hold = _is_informative_second_pass_hold(latest_run)
        informative_floor_recovery_hold = _is_informative_floor_recovery_hold(
            optimization_task_runs
        )
        if seed_baseline_hold_reviewable:
            run_status = "pass"
            run_evidence = (
                "unchanged seed-baseline hold accepted; optional optimizer diagnostics "
                "do not block first-pass review"
            )
            run_action = None
        elif latest_run is None:
            run_status = "warning"
            run_evidence = "no optimization task run evidence"
            run_action = "run at least one protected task before promotion"
        elif (
            latest_run.status == "passed"
            or informative_second_pass_hold
            or informative_floor_recovery_hold
        ):
            run_status = "pass"
            run_evidence = f"{latest_run.task_id}/{latest_run.status}: {latest_run.summary}"
            if informative_floor_recovery_hold and latest_run.status != "passed":
                run_evidence = (
                    f"floor recovery replay generated bounded non-promoted evidence; {run_evidence}"
                )
            run_action = None
        elif latest_run.status in {"diagnostic", "warning"}:
            run_status = "warning"
            run_evidence = f"{latest_run.task_id}/{latest_run.status}: {latest_run.summary}"
            run_action = latest_run.next_action
        else:
            run_status = "blocker"
            run_evidence = f"{latest_run.task_id}/{latest_run.status}: {latest_run.summary}"
            run_action = latest_run.next_action
        add_check(
            "task_run_evidence",
            "Task-run evidence",
            run_status,
            run_evidence,
            run_action,
        )

        def _is_hard_warning(check: DraftAcceptanceCheck) -> bool:
            if check.status == "blocker":
                return True
            if check.status != "warning":
                return False
            if check.check_id in {
                "delivery_gate",
                "branch_selection",
            }:
                return True
            if check.check_id == "optimizer_verification":
                return not informative_floor_recovery_hold
            if check.check_id == "requirement_coverage":
                return bool(hard_requirement_tradeoff_ids)
            if check.check_id == "image_quality_probe":
                return not (
                    (optimizer_status == "pass" and best.metadata.mtf_max_field_frac >= 1.0)
                    or informative_floor_recovery_hold
                )
            if check.check_id == "image_quality_floor":
                return True
            if check.check_id == "task_run_evidence":
                return not (
                    informative_second_pass_hold
                    or informative_floor_recovery_hold
                    or (
                        latest_run is not None
                        and latest_run.task_id == "asphere-guarded-audit"
                        and latest_run.status == "diagnostic"
                        and optimizer_status == "pass"
                        and best.metadata.mtf_max_field_frac >= 1.0
                    )
                )
            if check.check_id == "candidate_proxy_review":
                return False
            return check.check_id != "manufacturability"

        def _review_note_for_check(check: DraftAcceptanceCheck) -> str:
            note = f"{check.label}: {check.evidence}"
            if check.required_action:
                note = f"{note}; review note: {check.required_action}"
            return note

        blocker_labels = [
            f"{check.label}: {check.evidence}" for check in checks if check.status == "blocker"
        ]
        hard_warning_labels = [
            f"{check.label}: {check.evidence}"
            for check in checks
            if check.status == "warning" and _is_hard_warning(check)
        ]
        review_notes = [
            _review_note_for_check(check)
            for check in checks
            if check.status == "warning" and not _is_hard_warning(check)
        ]
        required_actions = _unique_in_order(
            [
                check.required_action
                for check in checks
                if check.required_action and (check.status == "blocker" or _is_hard_warning(check))
            ]
        )

        def _criteria_for_check(check: DraftAcceptanceCheck) -> list[str]:
            if check.check_id == "delivery_gate" and delivery_gate is not None:
                return list(delivery_gate.promotion_requirements[:4]) or [
                    "delivery gate no longer restricts the draft deliverable"
                ]
            if check.check_id == "branch_selection" and branch_selection_policy is not None:
                return [
                    *branch_selection_policy.promotion_requirements[:3],
                    "branch selection status no longer requires strategy resolution",
                ]
            if check.check_id == "requirement_coverage":
                criteria = [
                    f"{item.requirement_id} coverage becomes met or has an explicit waived tradeoff"
                    for item in requirement_coverage
                    if item.status in {"miss", "tradeoff", "unscored"}
                ][:4]
                return criteria or ["requirement coverage summary becomes met"]
            if check.check_id == "manufacturability":
                criteria = [
                    f"{item.check_id} becomes pass or has a signed manufacturing waiver"
                    for item in manufacturability_review.checks
                    if item.status in {"warning", "blocker"}
                ][:4]
                return criteria or ["manufacturability review status becomes pass"]
            if check.check_id == "candidate_proxy_review":
                return [
                    "lower-risk candidate branch is compared against selected seed",
                    "cost/yield-sensitive claims cite the accepted branch explicitly",
                    "optical target deltas are accepted or the selected seed remains primary",
                ]
            if check.check_id == "fov_alternative_review":
                return [
                    "closer-FOV real seed is compared against selected seed",
                    "alternative branch is accepted only if EFL/F-number/image-height/MTF fit remains within gates",
                    "remaining FOV tradeoff is closed by a better seed or explicitly waived",
                ]
            if check.check_id == "optimizer_verification":
                return [
                    "optimizer verification status is passed",
                    "post-change ray_trace_ok and mtf_ok remain true",
                    "proposal remains not applied to the delivered payload until reviewed",
                ]
            if check.check_id == "image_quality_probe":
                return [
                    "merit probe returns a verified proposal or an explicit accepted seed-baseline hold",
                    "RMS/MTF evidence is non-regressed against the accepted branch",
                ]
            if check.check_id == "image_quality_floor":
                return [
                    (
                        "recommended branch multiband min MTF is >= "
                        f"{_IMAGE_QUALITY_FLOOR_MIN_MTF:.2f}"
                    ),
                    (
                        "recommended branch field-weighted MTF is >= "
                        f"{_IMAGE_QUALITY_FLOOR_WEIGHTED_MTF:.2f}"
                    ),
                    (
                        "recommended branch max RMS spot radius is <= "
                        f"{_IMAGE_QUALITY_FLOOR_MAX_RMS_UM:.0f} um"
                    ),
                    "rerun draft_quality_rubric and confirm optical_evidence is no longer blocker",
                ]
            if check.check_id == "task_run_evidence":
                return [
                    "latest relevant optimization task run status is passed",
                    "the next promotion task is unlocked or explicitly blocked by external evidence",
                ]
            return [f"{check.label} check becomes pass"]

        def _expected_effect_for_check(check: DraftAcceptanceCheck) -> str:
            effects = {
                "requirement_coverage": "removes requirement tradeoff/miss pressure from the acceptance gate",
                "manufacturability": "raises first-pass manufacturing confidence before review",
                "delivery_gate": "removes or narrows delivery restrictions and moves the draft toward reviewable status",
                "branch_selection": "resolves the active/primary/deliverable branch ambiguity",
                "candidate_proxy_review": "makes the low-risk seed branch explicit before cost/yield-sensitive claims",
                "fov_alternative_review": "makes the closer-FOV branch decision explicit before waiving field angle",
                "optimizer_verification": "allows protected optimizer evidence to support the recommended branch",
                "image_quality_probe": "turns image-quality work from warning/diagnostic evidence into reviewable merit evidence",
                "image_quality_floor": "blocks reviewable acceptance until the recommended branch clears the first-pass MTF/RMS floor",
                "task_run_evidence": "advances the queued optimization workflow toward promotion evidence",
            }
            return effects.get(check.check_id, "moves the draft acceptance gate toward pass")

        def _unblocks_for_check(check: DraftAcceptanceCheck) -> list[str]:
            if check.check_id == "delivery_gate" and delivery_gate is not None:
                return list(delivery_gate.forbidden_claims[:4])
            if check.check_id == "branch_selection" and branch_selection_policy is not None:
                return list(branch_selection_policy.forbidden_claims[:4])
            return []

        action_priorities = {
            "delivery_gate": 1,
            "branch_selection": 2,
            "requirement_coverage": 3,
            "optimizer_verification": 4,
            "image_quality_floor": 5,
            "task_run_evidence": 6,
            "image_quality_probe": 7,
            "candidate_proxy_review": 8,
            "fov_alternative_review": 9,
            "manufacturability": 10,
        }
        upgrade_actions: list[DraftAcceptanceUpgradeAction] = []
        seen_actions: set[str] = set()
        for check in checks:
            if (
                check.status not in {"warning", "blocker"}
                or not check.required_action
                or (check.status == "warning" and not _is_hard_warning(check))
            ):
                continue
            if (
                check.check_id == "task_run_evidence"
                and recommended_image_quality_floor.status == "blocker"
            ):
                continue
            action = check.required_action
            if action in seen_actions:
                continue
            seen_actions.add(action)
            priority = action_priorities.get(check.check_id, len(action_priorities) + 1)
            upgrade_actions.append(
                DraftAcceptanceUpgradeAction(
                    action_id=f"{check.check_id}-{len(upgrade_actions) + 1}",
                    priority=priority,
                    source_check_id=check.check_id,
                    action=action,
                    acceptance_criteria=_criteria_for_check(check),
                    expected_effect=_expected_effect_for_check(check),
                    unblocks_claims=_unblocks_for_check(check),
                )
            )
        upgrade_actions.sort(key=lambda item: (item.priority, item.action_id))
        prioritized_required_actions = _unique_in_order(
            [action.action for action in upgrade_actions] + required_actions
        )

        blocker_count = len(blocker_labels)
        hard_warning_count = len(hard_warning_labels)
        review_note_count = len(review_notes)
        score_value = max(
            0.0,
            1.0 - blocker_count * 0.35 - hard_warning_count * 0.08 - review_note_count * 0.03,
        )
        if blocker_count:
            gate_status = "blocked"
            summary = f"{blocker_count} blocker(s) prevent draft acceptance"
        elif hard_warning_count:
            gate_status = "conditional"
            summary = (
                f"{hard_warning_count} hard warning(s) require evidence before first-pass review"
            )
        else:
            gate_status = "ready_for_review"
            summary = (
                f"ready for first-pass review with {review_note_count} non-blocking review note(s)"
                if review_note_count
                else "all current acceptance checks pass for first-pass review"
            )

        default_allowed_claims = [
            "real seed based first-pass optical draft",
            "Optiland-computed paraxial, trace, and MTF evidence",
        ]
        if full_field_recovery_review_ready:
            default_allowed_claims.append(
                "protected full-field recovery branch is available for conditional review"
            )
        default_forbidden_claims = [
            "production-ready prescription without tolerance review",
            "manufacturing yield claim without a supplier/process model",
        ]
        # E2-01 batch 1 (team-lead ruling): on the covered path the gap-path
        # delivery gate (which carried the full-field forbidden) is gone. A
        # delivered winner that only proves <1.0 field must STILL explicitly forbid
        # full-field edge-performance claims -- the audience is an expert, so keep
        # the explicit defense line, not just the composite blocked/tradeoff signals.
        if (
            library_coverage_diagnostic is not None
            and library_coverage_diagnostic.status == "covered"
            and best.metadata is not None
            and best.metadata.mtf_max_field_frac < 1.0
        ):
            default_forbidden_claims.append("full-field edge-performance claim")
        if branch_selection_policy is not None:
            default_forbidden_claims.extend(branch_selection_policy.forbidden_claims[:5])
        if performance_aperture_tradeoff_resolution is not None:
            default_forbidden_claims.extend(
                performance_aperture_tradeoff_resolution.forbidden_claims[:5]
            )

        return DraftAcceptanceGate(
            status=gate_status,
            candidate_id=recommended_candidate_id,
            deliverable_type=(
                delivery_gate.deliverable_type
                if delivery_gate is not None
                else "initial optical draft"
            ),
            score=score_value,
            summary=summary,
            checks=checks,
            blockers=blocker_labels,
            review_notes=review_notes[:6],
            required_next_actions=prioritized_required_actions[:6],
            upgrade_actions=upgrade_actions[:8],
            allowed_claims=(
                list(delivery_gate.allowed_claims[:5])
                if delivery_gate is not None
                else _unique_in_order(default_allowed_claims)[:6]
            ),
            forbidden_claims=(
                list(delivery_gate.forbidden_claims[:5])
                if delivery_gate is not None
                else _unique_in_order(default_forbidden_claims)[:8]
            ),
        )

    draft_acceptance_gate = _draft_acceptance_gate()

    def _design_intent_contract() -> DesignIntentContract:
        hard_requirement_ids = {
            "effective_focal_length",
            "f_number",
            "field_of_view",
            "fov_spec_consistency",
            "image_height",
            "element_count",
            "total_track",
            "mtf_field_evidence",
        }
        user_request_ids = {
            "effective_focal_length",
            "f_number",
            "field_of_view",
            "image_height",
            "element_count",
            "total_track",
        }

        def _negotiability(item: RequirementCoverageItem) -> str:
            if item.priority == "critical":
                return "locked" if item.status == "met" else "explicit_review_required"
            if item.priority == "important":
                return "reviewable"
            return "context"

        def _source(item: RequirementCoverageItem) -> str:
            if item.requirement_id in user_request_ids:
                return "user_request"
            if item.requirement_id in {"design_priority", "manufacturing_tier", "mass_budget"}:
                return "preference"
            return "derived_evidence"

        def _to_intent_item(item: RequirementCoverageItem) -> DesignIntentConstraintItem:
            return DesignIntentConstraintItem(
                requirement_id=item.requirement_id,
                label=item.label,
                target=item.target,
                priority=item.priority,
                status=item.status,
                negotiability=_negotiability(item),
                source=_source(item),
                evidence=item.evidence[:4],
                next_action=item.next_action,
            )

        hard_constraints = [
            _to_intent_item(item)
            for item in requirement_coverage
            if item.requirement_id in hard_requirement_ids
        ]
        soft_preferences = [
            _to_intent_item(item)
            for item in requirement_coverage
            if item.requirement_id not in hard_requirement_ids
        ][:8]

        conflict_flags: list[str] = []
        for item in hard_constraints:
            if item.status == "miss":
                conflict_flags.append(f"{item.requirement_id} misses target {item.target}")
            elif item.status == "tradeoff" and item.negotiability == "explicit_review_required":
                conflict_flags.append(
                    f"{item.requirement_id} requires explicit review before exact-brief claims"
                )
        if spec_repair_decision is not None and spec_repair_decision.status != "ready":
            conflict_flags.append(spec_repair_decision.decision_summary)
        if draft_acceptance_gate.status == "blocked":
            conflict_flags.append(draft_acceptance_gate.summary)
        conflict_flags = _unique_in_order(conflict_flags)[:8]

        inferred_assumptions = _unique_in_order(
            [
                "phone main/wide requests use the visible-light real production seed library",
                (
                    f"selected seed {best.metadata.case_id} is treated as the delivered payload "
                    "unless a reviewed branch replaces it"
                ),
                (
                    "element count is a scored preference, not a hard blocker"
                    if n_elements is not None
                    else "element count was not fixed by the brief"
                ),
                (
                    f"total track ceiling is {max_total_track_mm:.2f} mm"
                    if max_total_track_mm is not None
                    else "module total-track ceiling was not fixed by the brief"
                ),
                (
                    f"manufacturing tier is {manufacturing_tier}"
                    if manufacturing_tier is not None
                    else "manufacturing tier was not specified; proxy review stays contextual"
                ),
                (
                    f"priority mode is {priority}"
                    if priority is not None
                    else "priority mode defaults to balanced seed selection"
                ),
            ]
        )[:8]

        normalized_bits = [
            f"scenario={scenario.value}",
            f"EFL={efl_mm:.2f} mm",
            f"F/#={fnum:.2f}",
            f"FOV={fov_deg:.1f} deg",
        ]
        if image_height_mm is not None:
            normalized_bits.append(f"image_height={image_height_mm:.2f} mm")
        if n_elements is not None:
            normalized_bits.append(f"elements={n_elements}P")
        if max_total_track_mm is not None:
            normalized_bits.append(f"TTL<={max_total_track_mm:.2f} mm")
        if priority is not None:
            normalized_bits.append(f"priority={priority}")
        if manufacturing_tier is not None:
            normalized_bits.append(f"manufacturing={manufacturing_tier}")

        has_critical_miss = any(
            item.status == "miss" and item.priority == "critical" for item in hard_constraints
        )
        if has_critical_miss or draft_acceptance_gate.status == "blocked":
            status_value = "blocked"
        elif conflict_flags or draft_acceptance_gate.status == "conditional":
            status_value = "review_required"
        else:
            status_value = "ready"

        if status_value == "blocked":
            safe_interpretation = (
                "do not treat the raw brief as satisfied until the blocked hard constraint closes"
            )
        elif status_value == "review_required":
            safe_interpretation = (
                "treat the raw brief as an optical review contract with visible tradeoffs"
            )
        else:
            safe_interpretation = (
                "selected seed is a credible first-pass interpretation of the design brief"
            )

        next_action = next(
            (
                item.next_action
                for item in hard_constraints
                if item.next_action and item.status in {"miss", "tradeoff"}
            ),
            None,
        )
        if next_action is None:
            next_action = next(
                (action for action in draft_acceptance_gate.required_next_actions[:1] if action),
                "review the intent contract before changing seed or optimizer targets",
            )

        return DesignIntentContract(
            status=status_value,
            normalized_query="; ".join(normalized_bits),
            scenario_family="phone main/wide real-seed family",
            hard_constraints=hard_constraints[:10],
            soft_preferences=soft_preferences,
            inferred_assumptions=inferred_assumptions,
            conflict_flags=conflict_flags,
            safe_interpretation=safe_interpretation,
            next_action=next_action,
        )

    design_intent_contract = _design_intent_contract()

    def _acceptance_improvement_tasks() -> list[AcceptanceImprovementTask]:
        tasks: list[AcceptanceImprovementTask] = []

        def add_task(
            *,
            task_id: str,
            source_action_id: str,
            priority: int,
            status: str,
            stage: str,
            owner: str,
            objective: str,
            required_inputs: list[str],
            validation_steps: list[str],
            exit_criteria: list[str],
            depends_on: list[str] | None = None,
            blocks_claims: list[str] | None = None,
            evidence_probe: AcceptanceEvidenceProbe | None = None,
        ) -> None:
            tasks.append(
                AcceptanceImprovementTask(
                    task_id=task_id,
                    source_action_id=source_action_id,
                    priority=priority,
                    status=status,
                    stage=stage,
                    owner=owner,
                    objective=objective,
                    required_inputs=_unique_in_order(required_inputs),
                    validation_steps=_unique_in_order(validation_steps),
                    exit_criteria=_unique_in_order(exit_criteria),
                    depends_on=depends_on or [],
                    blocks_claims=_unique_in_order(blocks_claims or []),
                    evidence_probe=evidence_probe,
                )
            )

        active_resolution_packet = next(
            (
                run.resolution_packet
                for run in reversed(optimization_task_runs)
                if run.resolution_packet is not None
            ),
            None,
        ) or next(
            (
                task.resolution_packet
                for task in optimization_task_queue
                if task.resolution_packet is not None
            ),
            None,
        )

        for action in draft_acceptance_gate.upgrade_actions:
            is_high_fov_seed_action = (
                design_strategy_decision is not None
                and design_strategy_decision.seed_acquisition_brief is not None
                and action.source_check_id in {"delivery_gate", "branch_selection"}
                and (
                    "1.0 field" in action.action
                    or "full-field" in action.action
                    or "seed" in action.action
                )
            )
            if is_high_fov_seed_action:
                brief = design_strategy_decision.seed_acquisition_brief
                required_inputs = [
                    brief.source_format,
                    f"FOV >= {brief.minimum_fov_deg:.1f} deg",
                    f"EFL {brief.efl_window_mm[0]:.2f}-{brief.efl_window_mm[1]:.2f} mm",
                    f"F/# {brief.f_number_window[0]:.2f}-{brief.f_number_window[1]:.2f}",
                    f"image height {brief.image_height_window_mm[0]:.2f}-{brief.image_height_window_mm[1]:.2f} mm",
                    f"element count {brief.element_count_window[0]}-{brief.element_count_window[1]}P",
                    f"required MTF field {format_mtf_field_fraction(brief.required_mtf_field_frac)}",
                    *brief.validation_requirements[:4],
                ]
                validation_steps = [
                    "run the seed-intake audit probe for the requested high-FOV target",
                    "load candidate prescription with normalized visible-light wavelength set",
                    "resolve materials to backend refractive-index data",
                    "run case generation and confirm no MTF fallback below 1.0 field",
                    "rerun the design-agent fixed eval case high_fov_main_uses_89deg_seed",
                    *brief.rejection_filters[:3],
                ]
                known_evidence = _unique_in_order(
                    seed_intake_audit.known_evidence
                    if seed_intake_audit is not None
                    else [
                        *(
                            library_coverage_diagnostic.evidence
                            if library_coverage_diagnostic is not None
                            else []
                        ),
                        f"selected seed={best.metadata.case_id}",
                        (
                            "selected seed MTF field="
                            f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}"
                        ),
                    ]
                )
                missing_evidence = _unique_in_order(
                    seed_intake_audit.missing_evidence
                    if seed_intake_audit is not None
                    else [
                        (f"visible-light prescription with FOV >= {brief.minimum_fov_deg:.1f} deg"),
                        "finite sampled ray trace through the 1.0 field",
                        "MTF evaluates at 1.0 field without fallback",
                        "materials resolve to backend refractive-index data",
                    ]
                )
                probe_command = (
                    seed_intake_audit.next_probe_command
                    if seed_intake_audit is not None
                    else (
                        "cd lumira-backend && uv run python scripts/audit_seed_intake.py "
                        f"--target-fov {brief.target_fov_deg:.1f} "
                        f"--target-efl {brief.target_efl_mm:.2f} "
                        f"--target-fnum {brief.target_f_number:.2f} "
                        f"--min-fov {brief.minimum_fov_deg:.1f} "
                        f"--required-field {brief.required_mtf_field_frac:.1f} "
                        "--json"
                    )
                )
                evidence_probe = AcceptanceEvidenceProbe(
                    probe_id="high-fov-full-field-seed-intake",
                    status=seed_intake_audit.status if seed_intake_audit is not None else "gap",
                    summary=(
                        seed_intake_audit.summary
                        if seed_intake_audit is not None
                        else (
                            "current library has no accepted high-FOV full-field seed; "
                            "run the intake audit after adding a candidate prescription"
                        )
                    ),
                    known_evidence=known_evidence,
                    missing_evidence=missing_evidence,
                    next_probe_command=probe_command,
                )
                add_task(
                    task_id="ingest-high-fov-full-field-seed",
                    source_action_id=action.action_id,
                    priority=action.priority,
                    status="external_evidence_required",
                    stage="seed_ingestion",
                    owner="case_library",
                    objective=action.action,
                    required_inputs=required_inputs,
                    validation_steps=validation_steps,
                    exit_criteria=action.acceptance_criteria,
                    blocks_claims=action.unblocks_claims,
                    evidence_probe=evidence_probe,
                )
                continue

            stage_by_check = {
                "requirement_coverage": "requirement_resolution",
                "manufacturability": "manufacturability_review",
                "optimizer_verification": "optimizer_verification",
                "image_quality_probe": "merit_tuning",
                "image_quality_floor": "image_quality_recovery",
                "task_run_evidence": "task_execution",
                "delivery_gate": "delivery_review",
                "branch_selection": "strategy_resolution",
            }
            owner_by_check = {
                "requirement_coverage": "optical_design",
                "manufacturability": "manufacturing_review",
                "optimizer_verification": "optimizer",
                "image_quality_probe": "optimizer",
                "image_quality_floor": "optimizer",
                "task_run_evidence": "agent_runtime",
                "delivery_gate": "optical_design",
                "branch_selection": "optical_design",
            }
            required_inputs = [
                f"source check={action.source_check_id}",
                f"current candidate={draft_acceptance_gate.candidate_id or 'unresolved'}",
                *draft_acceptance_gate.required_next_actions[:2],
            ]
            validation_steps = [
                "rerun the matching request and inspect draft_acceptance_gate",
                "confirm the source check status moves to pass or has a signed waiver",
            ]
            if action.source_check_id == "task_run_evidence":
                validation_steps.append(
                    "rerun the linked optimization task and inspect task-run evidence"
                )
            task_status = "ready"
            task_stage = stage_by_check.get(action.source_check_id, "acceptance_resolution")
            task_owner = owner_by_check.get(action.source_check_id, "optical_design")
            task_exit_criteria = list(action.acceptance_criteria)
            task_evidence_probe = None
            if (
                action.source_check_id == "task_run_evidence"
                and active_resolution_packet is not None
            ):
                task_stage = "remediation_resolution"
                path_statuses = {path.status for path in active_resolution_packet.paths}
                task_status = (
                    "external_evidence_required"
                    if path_statuses & {"gap", "blocked", "manual_required"}
                    else "ready"
                )
                packet_inputs = [
                    f"resolution packet policy={active_resolution_packet.policy}",
                    f"policy action={active_resolution_packet.policy_action}",
                    *(
                        f"path {path.path_id}={path.status}"
                        for path in active_resolution_packet.paths[:4]
                    ),
                ]
                required_inputs = _unique_in_order([*required_inputs, *packet_inputs])
                validation_steps = _unique_in_order(
                    [
                        *validation_steps,
                        *(path.next_check for path in active_resolution_packet.paths[:4]),
                    ]
                )
                task_exit_criteria = _unique_in_order(
                    [
                        *task_exit_criteria,
                        *active_resolution_packet.resume_criteria,
                    ]
                )
                missing_evidence = _unique_in_order(
                    [
                        evidence
                        for path in active_resolution_packet.paths
                        for evidence in path.required_evidence[:3]
                    ]
                )
                next_probe_command = next(
                    (path.command for path in active_resolution_packet.paths if path.command),
                    "rerun the linked remediation task and fixed design-agent eval",
                )
                task_evidence_probe = AcceptanceEvidenceProbe(
                    probe_id="remediation-resolution-packet",
                    status=("gap" if task_status == "external_evidence_required" else "satisfied"),
                    summary=(
                        "typed remediation resolution packet defines the evidence "
                        "needed before task-run promotion can pass"
                    ),
                    known_evidence=active_resolution_packet.evidence[:6],
                    missing_evidence=missing_evidence[:8],
                    next_probe_command=next_probe_command,
                )
            if action.source_check_id == "optimizer_verification":
                validation_steps.append("confirm protected optimizer verification status is passed")
            if action.source_check_id == "image_quality_floor":
                floor_metrics = _recommended_candidate_metrics()
                floor_gap = _image_quality_floor_gap_score(floor_metrics)
                latest_quality_run = optimization_task_runs[-1] if optimization_task_runs else None
                validation_steps.extend(
                    [
                        "rerun the image-quality recovery task and inspect MTF/RMS floor metrics",
                        "confirm draft_quality_rubric.optical_evidence is pass or has a signed waiver",
                    ]
                )
                task_evidence_probe = AcceptanceEvidenceProbe(
                    probe_id="image-quality-floor-gap",
                    status=(
                        "satisfied" if recommended_image_quality_floor.status == "pass" else "gap"
                    ),
                    summary=(
                        "recommended branch still has a first-pass MTF/RMS floor gap"
                        if recommended_image_quality_floor.status != "pass"
                        else "recommended branch clears the first-pass MTF/RMS floor"
                    ),
                    known_evidence=_unique_in_order(
                        [
                            f"candidate={draft_acceptance_gate.candidate_id or recommended_candidate_id}",
                            f"normalized floor gap={floor_gap:.3f}"
                            if floor_gap is not None
                            else "normalized floor gap=missing",
                            *recommended_image_quality_floor.evidence[:5],
                            *recommended_image_quality_recovery_objective.evidence,
                            *(
                                [
                                    f"latest task run={latest_quality_run.task_id}/{latest_quality_run.status}",
                                    latest_quality_run.summary,
                                ]
                                if latest_quality_run is not None
                                else []
                            ),
                        ]
                    )[:10],
                    missing_evidence=_unique_in_order(
                        [
                            *recommended_image_quality_floor.blockers,
                            (f"multiband min MTF >= {_IMAGE_QUALITY_FLOOR_MIN_MTF:.2f}"),
                            (f"field-weighted MTF >= {_IMAGE_QUALITY_FLOOR_WEIGHTED_MTF:.2f}"),
                            (f"max RMS spot radius <= {_IMAGE_QUALITY_FLOOR_MAX_RMS_UM:.0f} um"),
                            "normalized MTF/RMS floor gap reaches 0.0",
                            "draft_quality_rubric.optical_evidence is no longer blocker",
                        ]
                    )[:8],
                    next_probe_command=(
                        "cd lumira-backend && uv run python "
                        "scripts/evaluate_design_agent.py --fail-on-regression --json"
                    ),
                )
            add_task(
                task_id=f"resolve-{action.action_id}",
                source_action_id=action.action_id,
                priority=action.priority,
                status=task_status,
                stage=task_stage,
                owner=task_owner,
                objective=action.action,
                required_inputs=required_inputs,
                validation_steps=validation_steps,
                exit_criteria=task_exit_criteria,
                blocks_claims=action.unblocks_claims,
                evidence_probe=task_evidence_probe,
            )

        tasks.sort(key=lambda item: (item.priority, item.task_id))
        return tasks[:8]

    acceptance_improvement_tasks = _acceptance_improvement_tasks()

    def _seed_acquisition_contract() -> SeedAcquisitionContract | None:
        brief = (
            design_strategy_decision.seed_acquisition_brief
            if design_strategy_decision is not None
            else None
        )
        if brief is None and seed_intake_audit is None:
            return None

        intake_task = next(
            (
                task
                for task in acceptance_improvement_tasks
                if task.task_id == "ingest-high-fov-full-field-seed"
            ),
            None,
        )
        target_regime = (
            brief.target_regime
            if brief is not None
            else "high-FOV visible-light full-field phone main/wide seed"
        )
        minimum_fov = (
            brief.minimum_fov_deg
            if brief is not None
            else seed_intake_audit.minimum_fov_deg
            if seed_intake_audit is not None
            else fov_deg
        )
        required_field = (
            brief.required_mtf_field_frac
            if brief is not None
            else seed_intake_audit.required_mtf_field_frac
            if seed_intake_audit is not None
            else 1.0
        )
        status = (
            "satisfied"
            if seed_intake_audit is not None and seed_intake_audit.status == "satisfied"
            else "external_evidence_required"
        )
        required_candidate_properties = [
            brief.source_format if brief is not None else "visible-light ZMX prescription",
            f"FOV >= {minimum_fov:.1f} deg",
            f"MTF evaluates at {format_mtf_field_fraction(required_field)} field without fallback",
        ]
        if brief is not None:
            required_candidate_properties.extend(
                [
                    f"EFL {brief.efl_window_mm[0]:.2f}-{brief.efl_window_mm[1]:.2f} mm",
                    f"F/# {brief.f_number_window[0]:.2f}-{brief.f_number_window[1]:.2f}",
                    f"image height {brief.image_height_window_mm[0]:.2f}-{brief.image_height_window_mm[1]:.2f} mm",
                    f"element count {brief.element_count_window[0]}-{brief.element_count_window[1]}P",
                ]
            )
            if brief.max_total_track_mm is not None:
                required_candidate_properties.append(f"TTL <= {brief.max_total_track_mm:.2f} mm")
            required_candidate_properties.extend(brief.validation_requirements[:4])

        pass_criteria = [
            "seed intake audit returns status=satisfied",
            "accepted_seed_count is greater than 0",
            "candidate appears in accepted_seed_candidates",
            (
                "rerun high_fov_main_uses_89deg_seed and remove partial-field "
                "delivery restriction only if full-field evidence passes"
            ),
        ]
        if intake_task is not None:
            pass_criteria.extend(intake_task.exit_criteria[:4])

        current_gap_evidence = []
        if seed_intake_audit is not None:
            current_gap_evidence.extend(
                [
                    seed_intake_audit.summary,
                    f"accepted high-FOV full-field seeds={seed_intake_audit.accepted_seed_count}",
                    f"high-FOV seeds={seed_intake_audit.high_fov_seed_count}",
                    f"full-field seeds={seed_intake_audit.full_field_seed_count}",
                    *(
                        (
                            f"near miss {candidate.role}={candidate.case_id}: "
                            + "; ".join(candidate.miss_reasons[:3])
                        )
                        for candidate in seed_intake_audit.nearest_candidates[:4]
                        if candidate.miss_reasons
                    ),
                    *seed_intake_audit.known_evidence[:4],
                    *seed_intake_audit.missing_evidence[:4],
                ]
            )
        elif library_coverage_diagnostic is not None:
            current_gap_evidence.extend(library_coverage_diagnostic.evidence[:6])

        fallback_paths = []
        if design_strategy_decision is not None:
            for option in design_strategy_decision.options[:5]:
                candidate_label = option.candidate_id or "new-seed"
                field_label = format_mtf_field_fraction(option.mtf_max_field_frac)
                fallback_paths.append(
                    f"{option.option_id}: {option.recommendation}; "
                    f"candidate={candidate_label}; evidence={option.evidence_status}; "
                    f"field={field_label}; {option.spec_impact}"
                )

        blocked_claims = []
        if delivery_gate is not None:
            blocked_claims.extend(delivery_gate.forbidden_claims[:5])
        if intake_task is not None:
            blocked_claims.extend(intake_task.blocks_claims[:5])
        if not blocked_claims:
            blocked_claims.append("full-field edge-performance claim")

        preflight_command = (
            seed_intake_audit.candidate_preflight_command
            if seed_intake_audit is not None
            else intake_task.evidence_probe.next_probe_command
            if intake_task is not None and intake_task.evidence_probe is not None
            else None
        )
        next_action = (
            f"run candidate preflight: {preflight_command}"
            if preflight_command is not None
            else "acquire a visible-light high-FOV full-field seed and run intake audit"
        )
        return SeedAcquisitionContract(
            status=status,
            summary=(
                f"{target_regime} requires external seed evidence before full-field "
                "or edge-performance claims can be promoted"
            ),
            source_task_id=intake_task.task_id if intake_task is not None else None,
            owner_role="case_library + optical_designer",
            target_regime=target_regime,
            acceptance_target=(
                f"visible-light seed with FOV >= {minimum_fov:.1f} deg and MTF at "
                f"{format_mtf_field_fraction(required_field)} field"
            ),
            required_candidate_properties=_unique_in_order(required_candidate_properties),
            preflight_command=preflight_command,
            pass_criteria=_unique_in_order(pass_criteria),
            rejection_filters=_unique_in_order(
                (brief.rejection_filters if brief is not None else [])[:6]
            ),
            current_gap_evidence=_prioritize_seed_gap_evidence(current_gap_evidence)[:10],
            fallback_paths=_unique_in_order(fallback_paths),
            blocked_claims=_unique_in_order(blocked_claims),
            next_action=next_action,
        )

    seed_acquisition_contract = _seed_acquisition_contract()

    def _draft_quality_rubric() -> DraftQualityRubric:
        dimensions: list[DraftQualityDimension] = []

        def clamp(value: float) -> float:
            return max(0.0, min(1.0, value))

        def add_dimension(
            dimension_id: str,
            label: str,
            score_value: float,
            status_value: str,
            evidence: list[str],
            recommended_action: str | None = None,
        ) -> None:
            dimensions.append(
                DraftQualityDimension(
                    dimension_id=dimension_id,
                    label=label,
                    score=round(clamp(score_value), 3),
                    status=status_value,
                    evidence=_clean_evidence(evidence, limit=5),
                    recommended_action=recommended_action,
                )
            )

        if requirement_coverage_summary is None:
            requirement_score = 0.0
            requirement_status = "blocker"
            requirement_action = "compute requirement coverage before quality scoring"
            requirement_evidence = ["requirement coverage missing"]
        else:
            total = max(
                1,
                requirement_coverage_summary.met_count
                + requirement_coverage_summary.tradeoff_count
                + requirement_coverage_summary.miss_count
                + requirement_coverage_summary.unscored_count,
            )
            requirement_score = clamp(
                (
                    requirement_coverage_summary.met_count
                    + 0.55 * requirement_coverage_summary.tradeoff_count
                    + 0.20 * requirement_coverage_summary.unscored_count
                )
                / total
                - 0.25 * requirement_coverage_summary.miss_count
            )
            requirement_status = (
                "blocker"
                if requirement_coverage_summary.status == "blocked"
                else ("warning" if requirement_coverage_summary.status == "tradeoff" else "pass")
            )
            requirement_action = next(
                (
                    item.next_action
                    for item in requirement_coverage
                    if item.status != "met" and item.next_action
                ),
                None,
            )
            requirement_evidence = [
                requirement_coverage_summary.summary,
                *(
                    f"{item.requirement_id}={item.status}"
                    for item in requirement_coverage
                    if item.status != "met"
                ),
            ]
        add_dimension(
            "requirement_fit",
            "Requirement fit",
            requirement_score,
            requirement_status,
            requirement_evidence,
            requirement_action,
        )

        verification = optimization_attempt.verification
        full_field_recovery_review_ready = _full_field_recovery_review_ready()
        full_field_recovery_trial = (
            _floor_clean_full_field_recovery_trial() if full_field_recovery_review_ready else None
        )
        if seed_baseline_hold_reviewable:
            optimizer_evidence_score = 0.88
            optimizer_evidence = "accepted seed-baseline hold; no optimizer change required"
            optimizer_action = None
        elif full_field_recovery_review_ready:
            optimizer_evidence_score = 0.88
            optimizer_evidence = (
                "protected full-field recovery replay passed for the primary review branch"
            )
            optimizer_action = None
        elif verification is None:
            optimizer_evidence_score = 0.45
            optimizer_evidence = "optimizer verification gate missing"
            optimizer_action = "attach a protected verification gate before quality promotion"
        elif verification.status == "passed":
            optimizer_evidence_score = 1.0
            optimizer_evidence = verification.summary
            optimizer_action = None
        elif verification.status == "warning":
            optimizer_evidence_score = 0.62
            optimizer_evidence = verification.summary
            optimizer_action = "resolve optimizer verification warning before reviewable claims"
        else:
            optimizer_evidence_score = 0.25
            optimizer_evidence = verification.summary
            optimizer_action = "stabilize protected optimizer before draft promotion"
        mtf_field_score = clamp(
            full_field_recovery_trial.mtf_max_field_frac
            if full_field_recovery_trial is not None
            and full_field_recovery_trial.mtf_max_field_frac is not None
            else best.metadata.mtf_max_field_frac
        )
        mtf_floor = (
            _evaluate_image_quality_floor(full_field_recovery_trial.metrics)
            if full_field_recovery_trial is not None
            else recommended_image_quality_floor
        )
        merit_score = (
            1.0
            if merit_optimization_probe.status == "proposal"
            else (
                0.85
                if seed_baseline_hold_reviewable
                else (0.62 if merit_optimization_probe.status == "warning" else 0.45)
            )
        )
        optical_score = clamp(
            0.30 * mtf_field_score
            + 0.25 * optimizer_evidence_score
            + 0.15 * merit_score
            + 0.30 * mtf_floor.score
        )
        if delivery_gate is not None and delivery_gate.status == "conditional_partial_field":
            optical_score = min(optical_score, 0.62)
        elif delivery_gate is not None and delivery_gate.status == "blocked":
            optical_score = min(optical_score, 0.30)
        optical_status = (
            "blocker"
            if mtf_floor.status == "blocker" or optical_score < 0.40
            else ("warning" if optical_score < 0.78 else "pass")
        )
        if mtf_floor.action is not None:
            optical_action = mtf_floor.action
        elif delivery_gate is not None and delivery_gate.promotion_requirements:
            optical_action = delivery_gate.promotion_requirements[0]
        else:
            optical_action = optimizer_action
        add_dimension(
            "optical_evidence",
            "Optical evidence",
            optical_score,
            optical_status,
            [
                (
                    "MTF field="
                    f"{format_mtf_field_fraction(full_field_recovery_trial.mtf_max_field_frac)} "
                    "on protected recovery branch"
                    if full_field_recovery_trial is not None
                    and full_field_recovery_trial.mtf_max_field_frac is not None
                    else f"MTF field={format_mtf_field_fraction(best.metadata.mtf_max_field_frac)}"
                ),
                *mtf_floor.evidence,
                f"optimizer={optimization_attempt.status}",
                optimizer_evidence,
                f"merit probe={merit_optimization_probe.status}",
            ],
            optical_action,
        )

        manufacturability_status = (
            "pass"
            if manufacturability_review.status == "pass"
            else ("blocker" if manufacturability_review.status == "blocked" else "warning")
        )
        manufacturability_action = next(
            (
                check.mitigation
                for check in manufacturability_review.checks
                if check.status in {"warning", "blocker"} and check.mitigation
            ),
            None,
        )
        add_dimension(
            "manufacturability",
            "Manufacturability proxy",
            manufacturability_review.score,
            manufacturability_status,
            [
                manufacturability_review.summary,
                f"tier={manufacturability_review.tier or 'unspecified'}",
                *(
                    f"{check.check_id}={check.status}"
                    for check in manufacturability_review.checks
                    if check.status != "pass"
                ),
            ],
            manufacturability_action,
        )

        latest_run = optimization_task_runs[-1] if optimization_task_runs else None
        informative_second_pass_hold = _is_informative_second_pass_hold(latest_run)
        optional_asphere_audit = (
            latest_run is not None
            and latest_run.task_id == "asphere-guarded-audit"
            and latest_run.status == "diagnostic"
            and draft_acceptance_gate.status == "ready_for_review"
        )
        run_score = (
            0.95
            if latest_run is not None
            and (latest_run.status == "passed" or informative_second_pass_hold)
            else (
                0.90
                if optional_asphere_audit or informative_second_pass_hold
                else (0.50 if latest_run is not None else 0.25)
            )
        )
        branch_score = (
            0.45
            if branch_selection_policy is not None
            and branch_selection_policy.status == "strategy_resolution_required"
            else 1.0
        )
        workflow_score = clamp(
            0.50 * draft_acceptance_gate.score + 0.30 * run_score + 0.20 * branch_score
        )
        workflow_status = (
            "blocker"
            if draft_acceptance_gate.status == "blocked"
            else (
                "warning"
                if draft_acceptance_gate.status == "conditional"
                or (
                    branch_selection_policy is not None
                    and branch_selection_policy.status == "strategy_resolution_required"
                )
                else "pass"
            )
        )
        latest_run_is_nonblocking_branch_review = (
            latest_run is not None and latest_run.task_id == "review-stable-sibling-branch"
        )
        workflow_action = (
            None
            if optional_asphere_audit
            else (
                latest_run.next_action
                if latest_run is not None
                and latest_run.status != "passed"
                and latest_run.next_action
                and not latest_run_is_nonblocking_branch_review
                else (
                    design_strategy_decision.required_evidence[0]
                    if design_strategy_decision is not None
                    and branch_selection_policy is not None
                    and branch_selection_policy.status == "strategy_resolution_required"
                    and design_strategy_decision.required_evidence
                    else (
                        draft_acceptance_gate.required_next_actions[0]
                        if draft_acceptance_gate.required_next_actions
                        else None
                    )
                )
            )
        )
        add_dimension(
            "workflow_closure",
            "Workflow closure",
            workflow_score,
            workflow_status,
            [
                f"acceptance={draft_acceptance_gate.status} score={draft_acceptance_gate.score:.2f}",
                (
                    f"latest run={latest_run.task_id}/{latest_run.status}"
                    if latest_run is not None
                    else "latest run=missing"
                ),
                (
                    f"branch policy={branch_selection_policy.status}"
                    if branch_selection_policy is not None
                    else "branch policy=straight-through"
                ),
            ],
            workflow_action,
        )

        allowed_claims = draft_acceptance_gate.allowed_claims
        forbidden_claims = draft_acceptance_gate.forbidden_claims
        claim_score = 0.95 if allowed_claims and forbidden_claims else 0.65
        if delivery_gate is not None and delivery_gate.status == "blocked":
            claim_score = min(claim_score, 0.65)
        claim_status = "pass" if claim_score >= 0.80 else "warning"
        claim_action = (
            "keep forbidden claims visible in exported reports until evidence is closed"
            if forbidden_claims
            else "add explicit forbidden claims before external sharing"
        )
        add_dimension(
            "claim_safety",
            "Claim safety",
            claim_score,
            claim_status,
            [
                "allowed=" + "; ".join(allowed_claims[:2]),
                "forbidden=" + "; ".join(forbidden_claims[:2]),
            ],
            claim_action,
        )

        by_id = {dimension.dimension_id: dimension for dimension in dimensions}
        quality_score = round(
            clamp(
                0.25 * by_id["requirement_fit"].score
                + 0.25 * by_id["optical_evidence"].score
                + 0.20 * by_id["manufacturability"].score
                + 0.20 * by_id["workflow_closure"].score
                + 0.10 * by_id["claim_safety"].score
            ),
            3,
        )
        if any(dimension.status == "blocker" for dimension in dimensions):
            level = "blocked"
        elif draft_acceptance_gate.status == "ready_for_review" and quality_score >= 0.72:
            level = "reviewable"
        else:
            level = "conditional"
        severity_rank = {"blocker": 0, "warning": 1, "pass": 2}
        weakest = min(
            dimensions,
            key=lambda item: (
                severity_rank.get(item.status, 3),
                item.score,
            ),
        )
        promotion_actions: list[str] = []
        if level == "reviewable":
            promotion_target = (
                "handoff for human optical review while keeping production claims behind "
                "tolerance and yield evidence"
            )
        elif level == "conditional":
            promotion_target = (
                "close conditional acceptance gates until the draft can be marked ready_for_review"
            )
        else:
            promotion_target = "resolve blocker quality dimensions before draft handoff"
        if level != "reviewable":
            action_candidates = list(draft_acceptance_gate.required_next_actions)
            action_candidates.extend(
                dimension.recommended_action
                for dimension in sorted(
                    dimensions,
                    key=lambda item: (
                        {"blocker": 0, "warning": 1, "pass": 2}.get(item.status, 3),
                        item.score,
                    ),
                )
                if dimension.status != "pass" and dimension.recommended_action
            )
            action_candidates.extend(task.objective for task in acceptance_improvement_tasks)
            seen_actions: set[str] = set()
            for action in action_candidates:
                cleaned_action = action.strip()
                if cleaned_action and cleaned_action not in seen_actions:
                    promotion_actions.append(cleaned_action)
                    seen_actions.add(cleaned_action)
                if len(promotion_actions) >= 5:
                    break
        summary = (
            f"{level} draft quality score {quality_score:.2f}; weakest dimension "
            f"{weakest.dimension_id}={weakest.score:.2f}"
        )
        return DraftQualityRubric(
            score=quality_score,
            level=level,
            summary=summary,
            weakest_dimension_id=weakest.dimension_id,
            minimum_next_action=promotion_actions[0] if promotion_actions else None,
            promotion_target=promotion_target,
            promotion_actions=promotion_actions,
            dimensions=dimensions,
        )

    draft_quality_rubric = _draft_quality_rubric()

    def _evidence_closeout_plan() -> EvidenceCloseoutPlan:
        items: list[EvidenceCloseoutItem] = []
        seen_ids: set[str] = set()

        def _slug(value: str) -> str:
            return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64] or "item"

        def _criteria_for_requirement(requirement: str) -> list[str]:
            lower = requirement.lower()
            if "1.0 field" in lower or "full-field" in lower:
                return [
                    "ingest or select a visible-light seed with finite ray trace",
                    "rerun MTF and verify finite values at 1.0 field",
                    "rerun draft_acceptance_gate and confirm delivery restrictions are removed",
                ]
            if "tolerance" in lower or "monte carlo" in lower:
                return [
                    "run first-order tolerance sensitivity or Monte Carlo replay",
                    "record pass/fail margin for the dominant sensitive surface or gap",
                ]
            if "supplier" in lower or "process" in lower or "yield" in lower:
                return [
                    "record supplier/process review outcome",
                    "confirm the current proxy risk can be treated as acceptable",
                ]
            if "asphere" in lower or "sag" in lower or "slope" in lower:
                return [
                    "keep coefficient edits audit-only",
                    "record sag/slope and tolerance replay before payload promotion",
                ]
            if "optimizer" in lower or "cloned" in lower or "verification" in lower:
                return [
                    "apply deltas only on a cloned branch",
                    "rerun paraxial, ray, MTF, and tolerance gates",
                ]
            return ["record reviewer evidence and rerun the draft acceptance gate"]

        def _owner_for_requirement(requirement: str, fallback: str = "optical_designer") -> str:
            lower = requirement.lower()
            if "seed" in lower or "reference" in lower or "library" in lower:
                return "optical_library_curator"
            if "supplier" in lower or "yield" in lower or "process" in lower:
                return "manufacturing_engineer"
            if "asphere" in lower or "tolerance" in lower or "monte carlo" in lower:
                return "optical_designer"
            return fallback

        def add_item(
            item_id: str,
            priority: int,
            source: str,
            status: str,
            owner_role: str,
            required_evidence: str,
            claim_unblocked: str,
            acceptance_criteria: list[str],
            evidence: list[str],
            next_action: str,
            *,
            blocks_review: bool,
            blocks_production_claims: bool = True,
        ) -> None:
            if item_id in seen_ids:
                return
            seen_ids.add(item_id)
            items.append(
                EvidenceCloseoutItem(
                    item_id=item_id,
                    priority=priority,
                    source=source,
                    status=status,
                    owner_role=owner_role,
                    required_evidence=required_evidence,
                    claim_unblocked=claim_unblocked,
                    acceptance_criteria=_unique_in_order(acceptance_criteria)[:5],
                    evidence=_unique_in_order([item for item in evidence if item])[:6],
                    next_action=next_action,
                    blocks_review=blocks_review,
                    blocks_production_claims=blocks_production_claims,
                )
            )

        if delivery_gate is not None:
            claim_unblocked = (
                delivery_gate.allowed_claims[0]
                if delivery_gate.allowed_claims
                else "delivery claim restrictions"
            )
            for index, requirement in enumerate(delivery_gate.promotion_requirements[:4], 1):
                status = (
                    "blocked" if delivery_gate.status == "blocked" else "external_evidence_required"
                )
                add_item(
                    f"delivery-gate-{index}-{_slug(requirement)}",
                    1,
                    "delivery_gate",
                    status,
                    _owner_for_requirement(requirement),
                    requirement,
                    claim_unblocked,
                    _criteria_for_requirement(requirement),
                    [
                        delivery_gate.summary,
                        *delivery_gate.forbidden_claims[:3],
                        *delivery_gate.allowed_claims[:2],
                    ],
                    requirement,
                    blocks_review=True,
                )

        if reference_influence_audit is not None:
            for index, gap in enumerate(reference_influence_audit.data_gaps[:4], 1):
                add_item(
                    f"reference-gap-{index}-{_slug(gap)}",
                    1 if "high-fov" in gap.lower() or "1.0 field" in gap.lower() else 2,
                    "reference_influence_audit",
                    "external_evidence_required",
                    _owner_for_requirement(gap),
                    gap,
                    "reference-supported design claims",
                    _criteria_for_requirement(gap),
                    [
                        reference_influence_audit.summary,
                        *reference_influence_audit.influence_notes[:3],
                    ],
                    reference_influence_audit.safe_next_action,
                    blocks_review=reference_influence_audit.status != "supported",
                )

        if manufacturing_sensitivity_audit is not None:
            source_factor = manufacturing_sensitivity_audit.dominant_factor_id or "general"
            for index, evidence_item in enumerate(
                manufacturing_sensitivity_audit.required_evidence[:5],
                1,
            ):
                factor = next(
                    (
                        item
                        for item in manufacturing_sensitivity_audit.factors
                        if item.factor_id in evidence_item
                        or item.next_action == evidence_item
                        or item.factor_id == source_factor
                    ),
                    None,
                )
                add_item(
                    f"manufacturing-sensitivity-{index}-{_slug(evidence_item)}",
                    2,
                    f"manufacturing_sensitivity_audit.{factor.factor_id if factor else source_factor}",
                    ("blocked" if manufacturing_sensitivity_audit.status == "blocked" else "ready"),
                    _owner_for_requirement(evidence_item, "manufacturing_engineer"),
                    evidence_item,
                    "production manufacturability and yield claims",
                    _criteria_for_requirement(evidence_item),
                    [
                        manufacturing_sensitivity_audit.summary,
                        factor.metric if factor else "",
                        *(factor.evidence[:3] if factor else []),
                    ],
                    evidence_item,
                    blocks_review=manufacturing_sensitivity_audit.status == "blocked",
                )

        for action in draft_acceptance_gate.upgrade_actions[:4]:
            is_external = action.source_check_id in {"delivery_gate", "branch_selection"}
            add_item(
                f"acceptance-upgrade-{action.action_id}",
                action.priority,
                f"draft_acceptance_gate.{action.source_check_id}",
                "external_evidence_required" if is_external else "ready",
                _owner_for_requirement(action.action),
                action.action,
                action.unblocks_claims[0] if action.unblocks_claims else "draft acceptance",
                action.acceptance_criteria,
                [
                    draft_acceptance_gate.summary,
                    f"source check={action.source_check_id}",
                    action.expected_effect,
                ],
                action.action,
                blocks_review=draft_acceptance_gate.status == "blocked",
            )

        for task in acceptance_improvement_tasks[:5]:
            evidence_bits = [
                f"stage={task.stage}",
                task.evidence_probe.summary if task.evidence_probe else "",
                *(task.evidence_probe.missing_evidence[:3] if task.evidence_probe else []),
            ]
            add_item(
                f"acceptance-task-{task.task_id}",
                task.priority,
                f"acceptance_improvement_task.{task.source_action_id}",
                task.status,
                task.owner,
                task.objective,
                task.blocks_claims[0] if task.blocks_claims else "draft acceptance",
                task.exit_criteria,
                evidence_bits,
                task.validation_steps[0] if task.validation_steps else task.objective,
                blocks_review=draft_acceptance_gate.status == "blocked",
            )

        if draft_quality_rubric.level != "reviewable" and draft_quality_rubric.minimum_next_action:
            action = draft_quality_rubric.minimum_next_action
            add_item(
                f"draft-quality-{_slug(action)}",
                1,
                f"draft_quality_rubric.{draft_quality_rubric.weakest_dimension_id or 'unknown'}",
                "ready",
                _owner_for_requirement(action),
                action,
                "reviewable draft quality",
                _criteria_for_requirement(action),
                [
                    draft_quality_rubric.summary,
                    draft_quality_rubric.promotion_target or "",
                ],
                action,
                blocks_review=draft_quality_rubric.level == "blocked",
            )

        if not items and draft_acceptance_gate.status == "ready_for_review":
            add_item(
                "production-evidence-signoff",
                3,
                "production_claim_safety",
                "reminder",
                "optical_designer + manufacturing_engineer",
                "run tolerance, process/yield, and supplier sign-off before production claims",
                "production-ready optical-module claims",
                [
                    "record tolerance sensitivity or Monte Carlo evidence",
                    "record supplier/process/yield acceptance",
                    "rerun draft_acceptance_gate if any production assumption changes",
                ],
                [
                    draft_acceptance_gate.summary,
                    "reviewable does not mean production-ready",
                ],
                "carry the reviewable draft into human review and schedule production evidence sign-off",
                blocks_review=False,
            )

        items.sort(key=lambda item: (item.priority, item.item_id))
        visible_items = items[:8]
        review_blocking_count = sum(item.blocks_review for item in visible_items)
        production_blocking_count = sum(item.blocks_production_claims for item in visible_items)
        external_dependency_count = sum(
            item.status == "external_evidence_required" for item in visible_items
        )
        if review_blocking_count:
            plan_status = "blocked"
        elif production_blocking_count:
            plan_status = "production_evidence_required"
        else:
            plan_status = "clear"
        highest_priority_item = visible_items[0] if visible_items else None
        if plan_status == "clear":
            summary = "all evidence obligations are closed for the current draft scope"
            safe_next_action = "handoff the draft packet for review"
        elif plan_status == "blocked":
            summary = (
                f"{review_blocking_count} evidence item(s) block review; "
                f"{external_dependency_count} external dependency item(s)"
            )
            safe_next_action = highest_priority_item.next_action if highest_priority_item else ""
        else:
            summary = (
                f"{production_blocking_count} production-claim evidence item(s) remain; "
                "draft can be reviewed with restrictions"
            )
            safe_next_action = highest_priority_item.next_action if highest_priority_item else ""

        forbidden_claims = _unique_in_order(
            [
                *draft_acceptance_gate.forbidden_claims[:5],
                *(delivery_gate.forbidden_claims[:5] if delivery_gate is not None else []),
                "do not claim production readiness until evidence closeout items are closed",
            ]
        )

        return EvidenceCloseoutPlan(
            status=plan_status,
            summary=summary,
            highest_priority_item_id=highest_priority_item.item_id
            if highest_priority_item
            else None,
            items=visible_items,
            review_blocking_count=review_blocking_count,
            production_blocking_count=production_blocking_count,
            external_dependency_count=external_dependency_count,
            safe_next_action=safe_next_action,
            forbidden_claims=forbidden_claims[:6],
        )

    evidence_closeout_plan = _evidence_closeout_plan()

    def _design_handoff_packet() -> DesignHandoffPacket:
        candidate_id = (
            draft_acceptance_gate.candidate_id or recommended_candidate_id or "seed-baseline"
        )
        if draft_acceptance_gate.status == "ready_for_review":
            handoff_status = "ready_for_review"
        elif draft_acceptance_gate.status == "blocked":
            handoff_status = "blocked"
        else:
            handoff_status = "conditional"
        if evidence_closeout_plan.review_blocking_count and handoff_status == "ready_for_review":
            handoff_status = "conditional"
        if delivery_gate is not None and delivery_gate.status == "blocked":
            handoff_status = "blocked"

        if candidate_id == "optimizer-proposal" and prescription_change_set is not None:
            prescription_source = (
                f"{best.metadata.case_id} real seed plus protected optimizer proposal"
            )
            payload_policy = (
                "delivered payload remains the selected real seed; optimizer deltas stay in a "
                "protected change set until replayed"
            )
        elif candidate_id == "seed-baseline":
            prescription_source = f"{best.metadata.case_id} real seed baseline"
            payload_policy = "delivered payload is the unchanged selected real seed"
        elif design_strategy_decision is not None:
            prescription_source = (
                f"{best.metadata.case_id} selected seed with strategy branch "
                f"{design_strategy_decision.selected_strategy}"
            )
            payload_policy = (
                "strategy branch is a review path; delivered payload is not silently mutated"
            )
        else:
            prescription_source = f"{best.metadata.case_id} selected real seed"
            payload_policy = "delivered payload is the selected real seed"

        coverage_by_id = {item.requirement_id: item for item in requirement_coverage}

        def _coverage_metric(
            metric_id: str,
            label: str,
            value: str,
            fallback_status: str = "context",
        ) -> DesignHandoffMetric:
            item = coverage_by_id.get(metric_id)
            return DesignHandoffMetric(
                metric_id=metric_id,
                label=label,
                value=value,
                target=item.target if item is not None else None,
                status=item.status if item is not None else fallback_status,
            )

        headline_metrics = [
            _coverage_metric(
                "effective_focal_length",
                "Effective focal length",
                f"{best.metadata.computed_efl_mm:.2f} mm",
            ),
            _coverage_metric("f_number", "F-number", f"F/{best.paraxial.f_number:.2f}"),
            _coverage_metric("field_of_view", "Field of view", f"{best.metadata.fov_deg:.1f} deg"),
            _coverage_metric("image_height", "Image height", f"{imh:.2f} mm"),
            _coverage_metric("element_count", "Element count", f"{best.metadata.n_pieces}P"),
            _coverage_metric(
                "total_track",
                "Total track",
                f"{best.paraxial.total_track_mm:.2f} mm",
            ),
            _coverage_metric(
                "mtf_field_evidence",
                "MTF field evidence",
                f"{format_mtf_field_fraction(best.metadata.mtf_max_field_frac)} field",
            ),
        ]

        accepted_tradeoffs: list[str] = []
        for item in requirement_coverage:
            if item.status == "tradeoff":
                accepted_tradeoffs.append(
                    f"{item.label}: {item.actual}; next={item.next_action or 'review note'}"
                )
        if spec_repair_auto_closure is not None:
            accepted_tradeoffs.append(spec_repair_auto_closure.summary)
        if branch_selection_policy is not None:
            accepted_tradeoffs.append(branch_selection_policy.summary)
        if evidence_closeout_plan.status == "production_evidence_required":
            accepted_tradeoffs.append(evidence_closeout_plan.summary)
        accepted_tradeoffs = _unique_in_order(accepted_tradeoffs)[:6]

        review_focus = _unique_in_order(
            [
                evidence_closeout_plan.safe_next_action,
                *draft_acceptance_gate.required_next_actions[:3],
                *[item.required_evidence for item in evidence_closeout_plan.items[:3]],
                manufacturing_sensitivity_audit.safe_next_action
                if manufacturing_sensitivity_audit is not None
                else "",
                draft_quality_rubric.minimum_next_action or "",
            ]
        )[:6]

        forbidden_claims = _unique_in_order(
            [
                *draft_acceptance_gate.forbidden_claims[:4],
                *evidence_closeout_plan.forbidden_claims[:4],
                *(
                    reference_influence_audit.forbidden_claims[:3]
                    if reference_influence_audit is not None
                    else []
                ),
                "do not claim production readiness from this initial handoff packet",
            ]
        )[:7]

        if handoff_status == "ready_for_review":
            summary = (
                f"handoff {candidate_id} as a reviewable first-pass optical draft; "
                f"production evidence remains {evidence_closeout_plan.status}"
            )
        elif handoff_status == "conditional":
            summary = (
                f"handoff {candidate_id} as a conditional draft; close review-blocking "
                "evidence before stronger claims"
                if evidence_closeout_plan.review_blocking_count
                else (
                    f"handoff {candidate_id} as a conditional draft; waiver and "
                    "replay evidence block stronger claims, not human review"
                )
            )
        else:
            summary = f"do not hand off {candidate_id} as a reviewable draft until blockers close"

        next_decision = next(
            (
                item
                for item in [
                    evidence_closeout_plan.safe_next_action,
                    draft_quality_rubric.minimum_next_action or "",
                    *draft_acceptance_gate.required_next_actions[:1],
                ]
                if item
            ),
            "handoff the draft packet for human optical review",
        )

        return DesignHandoffPacket(
            status=handoff_status,
            candidate_id=candidate_id,
            prescription_source=prescription_source,
            payload_policy=payload_policy,
            summary=summary,
            headline_metrics=headline_metrics,
            accepted_tradeoffs=accepted_tradeoffs,
            review_focus=review_focus,
            forbidden_claims=forbidden_claims,
            next_decision=next_decision,
        )

    design_handoff_packet = _design_handoff_packet()

    def _design_traceability_manifest() -> DesignTraceabilityManifest:
        delivered_candidate_id = design_handoff_packet.candidate_id
        delivered_payload = (
            "selected_real_seed"
            if delivered_candidate_id == "seed-baseline"
            else "selected_real_seed_with_protected_change_set"
            if delivered_candidate_id == "optimizer-proposal"
            and prescription_change_set is not None
            else "selected_real_seed_with_review_branch"
        )
        validation_evidence = _unique_in_order(
            [
                f"real case metadata: {best.metadata.case_id}",
                f"paraxial EFL {best.metadata.computed_efl_mm:.2f} mm",
                f"MTF evidence reaches {format_mtf_field_fraction(best.metadata.mtf_max_field_frac)} field",
                f"surface descriptors serialized: {len(best.surfaces)}",
                f"materials resolved: {len(best.metadata.materials)}",
                *(
                    [f"acceptance gate: {draft_acceptance_gate.status}"]
                    if draft_acceptance_gate is not None
                    else []
                ),
                *([f"delivery gate: {delivery_gate.status}"] if delivery_gate is not None else []),
                f"constraint ledger: {design_constraint_ledger.status}",
            ]
        )
        replay_commands = [
            (
                "cd lumira-backend && uv run python scripts/evaluate_design_agent.py "
                "--fail-on-regression"
            ),
            seed_intake_audit.next_probe_command
            if seed_intake_audit is not None
            else "cd lumira-backend && uv run pytest tests/test_optical_match.py -q",
        ]
        if seed_intake_audit is not None:
            replay_commands.append(seed_intake_audit.candidate_preflight_command)
        if prescription_change_set is not None:
            replay_commands.append(
                "replay protected prescription change set only after its verification checklist passes"
            )

        forbidden_mutations = _unique_in_order(
            [
                "do not edit selected seed payload in-place",
                "do not apply protected optimizer deltas without replay verification",
                "do not replace source ZMX without rerunning generated case + fixed eval",
                *design_handoff_packet.forbidden_claims[:4],
            ]
        )
        return DesignTraceabilityManifest(
            status=design_handoff_packet.status,
            source_case_id=best.metadata.case_id,
            source_zmx=best.metadata.source_zmx,
            source_zmx_path=f"data/zmx/{best.metadata.source_zmx}",
            generated_case_path=f"app/data/optical_cases/{best.metadata.case_id}.json",
            delivered_candidate_id=delivered_candidate_id,
            delivered_payload=delivered_payload,
            payload_policy=design_handoff_packet.payload_policy,
            surface_count=len(best.surfaces),
            material_count=len(best.metadata.materials),
            material_families=best.metadata.materials[:8],
            mtf_field_evidence=format_mtf_field_fraction(best.metadata.mtf_max_field_frac),
            change_set_applied=False,
            change_set_policy=(
                prescription_change_set.application_policy
                if prescription_change_set is not None
                else "no protected change set is attached"
            ),
            report_sections=[
                "paraxial_summary",
                "surface_table",
                "ray_trace",
                "mtf_chart",
                "layout_svg",
                "design_assessment",
                "pdf_report",
            ],
            validation_evidence=validation_evidence[:10],
            replay_commands=_unique_in_order(replay_commands)[:5],
            forbidden_mutations=forbidden_mutations[:8],
            next_replay_action=design_handoff_packet.next_decision,
        )

    def _design_constraint_ledger() -> DesignConstraintLedger:
        accepted_tradeoff_ids = set(
            spec_repair_auto_closure.accepted_tradeoff_ids
            if spec_repair_auto_closure is not None
            else []
        )

        def _constraint_status(item: RequirementCoverageItem) -> str:
            if item.status == "met":
                return "locked"
            if item.status == "tradeoff":
                if (
                    item.requirement_id in accepted_tradeoff_ids
                    or draft_acceptance_gate.status == "ready_for_review"
                ):
                    return "accepted_tradeoff"
                return "unresolved"
            if item.status == "miss":
                return "unresolved"
            return "context"

        def _constraint_policy(status: str) -> str:
            if status == "locked":
                return "preserve this requirement during any local optimization"
            if status == "accepted_tradeoff":
                return (
                    "keep the tradeoff visible as a review note; do not silently relabel it as met"
                )
            if status == "unresolved":
                return (
                    "requires explicit design decision or external evidence before stronger claims"
                )
            return "track as contextual evidence; do not use it as a release claim"

        constraints = [
            DesignConstraintItem(
                requirement_id=item.requirement_id,
                label=item.label,
                status=_constraint_status(item),
                target=item.target,
                current=item.actual,
                policy=_constraint_policy(_constraint_status(item)),
                evidence=item.evidence[:4],
                next_action=item.next_action,
            )
            for item in requirement_coverage
        ]
        locked_count = sum(item.status == "locked" for item in constraints)
        accepted_tradeoff_count = sum(item.status == "accepted_tradeoff" for item in constraints)
        unresolved_count = sum(item.status == "unresolved" for item in constraints)

        tasks_by_id = {task.task_id: task for task in optimization_task_queue}

        def _task_guardrails(task_id: str) -> list[str]:
            task = tasks_by_id.get(task_id)
            if task is None:
                return []
            return _unique_in_order([task.stop_condition, task.verification, *task.evidence[:3]])

        def _task_next_action(task_id: str, fallback: str) -> str:
            task = tasks_by_id.get(task_id)
            return task.objective if task is not None else fallback

        variables: list[DesignVariableGovernanceItem] = [
            DesignVariableGovernanceItem(
                variable_id="first_order_lock",
                label="First-order optical requirements",
                status="frozen",
                scope="EFL, F-number, image height, FOV, and total track",
                allowed_action="compare after every solve; reject changes that drift outside review tolerances",
                guardrails=_task_guardrails("lock-first-order")
                or [
                    f"dEFL={delta_efl:+.3f} mm",
                    f"dF#={delta_fnum:+.3f}",
                    f"dFOV={delta_fov:+.2f} deg",
                ],
                evidence=[
                    f"candidate={design_handoff_packet.candidate_id}",
                    requirement_coverage_summary.summary
                    if requirement_coverage_summary is not None
                    else "requirement coverage unavailable",
                ],
                next_action=_task_next_action(
                    "lock-first-order",
                    "preserve first-order requirements during local optimization",
                ),
            ),
            DesignVariableGovernanceItem(
                variable_id="seed_payload",
                label="Delivered seed payload",
                status="frozen",
                scope=best.metadata.case_id,
                allowed_action="deliver the selected real seed unchanged until a reviewed branch replaces it",
                guardrails=[
                    "no hidden prescription mutation",
                    "all claim upgrades must go through acceptance gates",
                ],
                evidence=[design_handoff_packet.payload_policy],
                next_action="package or review the unchanged selected seed payload",
            ),
        ]

        if prescription_change_set is not None:
            variables.append(
                DesignVariableGovernanceItem(
                    variable_id="protected_change_set",
                    label="Protected prescription change set",
                    status="guarded",
                    scope=prescription_change_set.source_candidate_id,
                    allowed_action=prescription_change_set.application_policy,
                    guardrails=_unique_in_order(
                        [
                            *prescription_change_set.verification_checklist,
                            *_task_guardrails("apply-protected-change-set"),
                        ]
                    )[:6],
                    evidence=[
                        f"{change.variable} S{change.surface_index} {change.before:.4f}->{change.after:.4f}"
                        for change in prescription_change_set.changes[:4]
                    ],
                    next_action=_task_next_action(
                        "apply-protected-change-set",
                        "replay protected deltas only on a cloned prescription",
                    ),
                )
            )

        full_field_task = tasks_by_id.get("recover-full-field")
        if full_field_task is not None:
            variables.append(
                DesignVariableGovernanceItem(
                    variable_id="full_field_recovery",
                    label="Full-field recovery variables",
                    status="blocked" if full_field_task.status == "blocked" else "guarded",
                    scope=", ".join(full_field_task.variables),
                    allowed_action=full_field_task.entry_condition,
                    guardrails=_task_guardrails("recover-full-field")[:6],
                    evidence=full_field_task.evidence[:5],
                    next_action=full_field_task.objective,
                )
            )

        packaging_task = tasks_by_id.get("protect-packaging-budget")
        packaging_guardrails = _task_guardrails("protect-packaging-budget")
        if not packaging_guardrails:
            packaging_guardrails = (
                [f"max total track={max_total_track_mm:.2f} mm"]
                if max_total_track_mm is not None
                else ["preserve the current packaging envelope"]
            )
        if packaging_task is not None or max_total_track_mm is not None:
            variables.append(
                DesignVariableGovernanceItem(
                    variable_id="packaging_budget",
                    label="Packaging and total-track variables",
                    status="guarded",
                    scope="air gaps, center thickness, filter stack, and total track",
                    allowed_action="preserve module envelope before merit tuning",
                    guardrails=packaging_guardrails,
                    evidence=[
                        (
                            f"TTL delta={delta_ttl:+.3f} mm"
                            if delta_ttl is not None
                            else "TTL target present"
                        )
                    ],
                    next_action=_task_next_action(
                        "protect-packaging-budget",
                        "verify total track after every structural edit",
                    ),
                )
            )

        asphere_task = tasks_by_id.get("asphere-guarded-audit")
        if asphere_task is not None:
            variables.append(
                DesignVariableGovernanceItem(
                    variable_id="asphere_coefficients",
                    label="Asphere coefficients",
                    status="guarded",
                    scope=", ".join(asphere_task.variables),
                    allowed_action="audit-only perturbation replay until sag/slope and MTF evidence pass",
                    guardrails=_task_guardrails("asphere-guarded-audit")[:6],
                    evidence=asphere_task.evidence[:5],
                    next_action=asphere_task.objective,
                )
            )

        forbidden_actions = _unique_in_order(
            [
                "do not silently mutate the delivered seed payload",
                "do not promote protected optimizer deltas into a final prescription without replay",
                "do not relax first-order EFL/F-number/FOV/image-height constraints without a recorded decision",
                "do not claim production readiness from the constraint ledger",
                *design_handoff_packet.forbidden_claims[:3],
            ]
        )[:7]

        variable_blocked = any(item.status == "blocked" for item in variables)
        if (
            evidence_closeout_plan.review_blocking_count
            or draft_acceptance_gate.status == "blocked"
            or variable_blocked
        ):
            ledger_status = "blocked"
        elif draft_acceptance_gate.status == "ready_for_review" and unresolved_count == 0:
            ledger_status = "ready_for_review"
        else:
            ledger_status = "needs_review"

        if ledger_status == "ready_for_review":
            summary = (
                f"{locked_count} locked constraint(s), {accepted_tradeoff_count} accepted "
                "tradeoff(s), and no unresolved review blockers"
            )
        elif ledger_status == "blocked":
            summary = (
                f"{unresolved_count} unresolved constraint(s) or review-blocking variable "
                "policy item(s) must close before handoff claims strengthen"
            )
        else:
            summary = (
                f"{locked_count} locked constraint(s) with {unresolved_count} item(s) needing "
                "review before stronger claims"
            )

        if prescription_change_set is not None:
            variable_policy_summary = (
                "selected real seed is the delivered payload; protected optimizer deltas remain "
                "guarded until cloned replay and acceptance review"
            )
        else:
            variable_policy_summary = (
                "selected real seed remains frozen unless a reviewed branch replaces it"
            )

        return DesignConstraintLedger(
            status=ledger_status,
            summary=summary,
            locked_count=locked_count,
            accepted_tradeoff_count=accepted_tradeoff_count,
            unresolved_count=unresolved_count,
            variable_policy_summary=variable_policy_summary,
            constraints=constraints,
            variables=variables,
            forbidden_actions=forbidden_actions,
            next_action=next(
                (
                    item
                    for item in [
                        evidence_closeout_plan.safe_next_action,
                        design_handoff_packet.next_decision,
                    ]
                    if item
                ),
                "review the constraint ledger before local optimization",
            ),
        )

    design_constraint_ledger = _design_constraint_ledger()
    design_traceability_manifest = _design_traceability_manifest()

    def _designer_readiness_rubric() -> DesignerReadinessRubric:
        dimensions: list[DesignerReadinessDimension] = []

        def clamp(value: float) -> float:
            return max(0.0, min(1.0, value))

        def add_dimension(
            dimension_id: str,
            label: str,
            score_value: float,
            status_value: str,
            evidence: list[str],
            next_action: str | None = None,
        ) -> None:
            dimensions.append(
                DesignerReadinessDimension(
                    dimension_id=dimension_id,
                    label=label,
                    score=round(clamp(score_value), 3),
                    status=status_value,
                    evidence=_clean_evidence(evidence, limit=5),
                    next_action=next_action,
                )
            )

        intent_conflict_count = (
            len(design_intent_contract.conflict_flags) if design_intent_contract is not None else 0
        )
        if design_intent_contract is None:
            brief_score = 0.20
            brief_status = "blocker"
            brief_evidence = ["design intent contract missing"]
            brief_action = "build the design intent contract before assessing readiness"
        elif design_intent_contract.status == "ready":
            brief_score = 0.95
            brief_status = "pass"
            brief_evidence = [
                design_intent_contract.normalized_query,
                design_intent_contract.safe_interpretation,
            ]
            brief_action = None
        elif design_intent_contract.status == "review_required":
            brief_score = max(0.55, 0.78 - 0.04 * intent_conflict_count)
            brief_status = "warning"
            brief_evidence = [
                design_intent_contract.normalized_query,
                *design_intent_contract.conflict_flags[:3],
            ]
            brief_action = design_intent_contract.next_action
        else:
            brief_score = 0.25
            brief_status = "blocker"
            brief_evidence = [
                design_intent_contract.normalized_query,
                *design_intent_contract.conflict_flags[:3],
            ]
            brief_action = design_intent_contract.next_action
        add_dimension(
            "brief_interpretation",
            "Brief interpretation",
            brief_score,
            brief_status,
            brief_evidence,
            brief_action,
        )

        high_fov_seed_gap = seed_intake_audit is not None and seed_intake_audit.status == "gap"
        if high_fov_seed_gap:
            seed_score = 0.36
            seed_status = "blocker"
            seed_evidence = [
                seed_intake_audit.summary,
                f"accepted high-FOV full-field seeds={seed_intake_audit.accepted_seed_count}",
                *seed_intake_audit.missing_evidence[:3],
            ]
            seed_action = (
                "ingest at least one visible-light high-FOV full-field seed; "
                f"preflight with {seed_intake_audit.candidate_preflight_command}"
            )
        elif design_traceability_manifest.status == "ready_for_review":
            seed_score = 0.92
            seed_status = "pass"
            seed_evidence = [
                f"source={design_traceability_manifest.source_case_id}",
                f"payload={design_traceability_manifest.delivered_payload}",
                seed_selection_scorecard.summary
                if seed_selection_scorecard is not None
                else "seed scorecard unavailable",
            ]
            seed_action = None
        elif design_traceability_manifest.status == "conditional":
            seed_score = 0.64
            seed_status = "warning"
            seed_evidence = [
                f"source={design_traceability_manifest.source_case_id}",
                design_traceability_manifest.payload_policy,
                seed_selection_scorecard.summary
                if seed_selection_scorecard is not None
                else "seed scorecard unavailable",
            ]
            seed_action = design_traceability_manifest.next_replay_action
        else:
            seed_score = 0.30
            seed_status = "blocker"
            seed_evidence = [
                f"traceability={design_traceability_manifest.status}",
                design_traceability_manifest.payload_policy,
            ]
            seed_action = design_traceability_manifest.next_replay_action
        add_dimension(
            "seed_evidence",
            "Seed evidence",
            seed_score,
            seed_status,
            seed_evidence,
            seed_action,
        )

        quality_dimensions = {
            dimension.dimension_id: dimension for dimension in draft_quality_rubric.dimensions
        }
        requirement_dimension = quality_dimensions.get("requirement_fit")
        optical_dimension = quality_dimensions.get("optical_evidence")
        optical_fit_score = clamp(
            0.45 * (requirement_dimension.score if requirement_dimension else 0.0)
            + 0.55 * (optical_dimension.score if optical_dimension else 0.0)
        )
        optical_statuses = {
            item.status for item in [requirement_dimension, optical_dimension] if item is not None
        }
        optical_fit_status = (
            "blocker"
            if "blocker" in optical_statuses
            else ("warning" if "warning" in optical_statuses else "pass")
        )
        optical_fit_action = next(
            (
                item.recommended_action
                for item in [optical_dimension, requirement_dimension]
                if item is not None and item.recommended_action
            ),
            draft_quality_rubric.minimum_next_action,
        )
        add_dimension(
            "optical_fit",
            "Optical fit",
            optical_fit_score,
            optical_fit_status,
            [
                draft_quality_rubric.summary,
                requirement_dimension.evidence[0] if requirement_dimension else "",
                optical_dimension.evidence[0] if optical_dimension else "",
            ],
            optical_fit_action,
        )

        verification = (
            optimization_attempt.verification if optimization_attempt is not None else None
        )
        if (
            draft_acceptance_gate.status == "ready_for_review"
            and recommended_candidate_id == "seed-baseline"
        ):
            optimizer_score = 0.90
            optimizer_status = "pass"
            optimizer_evidence = [
                "seed-baseline accepted without protected optimizer deltas",
                draft_acceptance_gate.summary,
            ]
            optimizer_action = None
        elif verification is not None and verification.status == "passed":
            optimizer_score = 0.88
            optimizer_status = "pass"
            optimizer_evidence = [
                verification.summary,
                f"candidate={recommended_candidate_id or 'unresolved'}",
            ]
            optimizer_action = None
        elif draft_acceptance_gate.status == "conditional" or (
            verification is not None and verification.status == "warning"
        ):
            optimizer_score = 0.56
            optimizer_status = "warning"
            optimizer_evidence = [
                verification.summary if verification is not None else draft_acceptance_gate.summary,
                f"acceptance={draft_acceptance_gate.status}",
            ]
            optimizer_action = next(
                iter(draft_acceptance_gate.required_next_actions),
                "resolve optimizer verification warning before draft promotion",
            )
        else:
            optimizer_score = 0.34
            optimizer_status = "blocker"
            optimizer_evidence = [
                f"optimizer={optimization_attempt.status if optimization_attempt is not None else 'missing'}",
                f"acceptance={draft_acceptance_gate.status}",
            ]
            optimizer_action = next(
                iter(draft_acceptance_gate.required_next_actions),
                "stabilize optimizer evidence before claiming draft readiness",
            )
        add_dimension(
            "optimization_evidence",
            "Optimization evidence",
            optimizer_score,
            optimizer_status,
            optimizer_evidence,
            optimizer_action,
        )

        sensitivity_score = 0.92
        sensitivity_status = "pass"
        sensitivity_evidence = "manufacturing sensitivity clear"
        sensitivity_action: str | None = None
        if manufacturing_sensitivity_audit is not None:
            sensitivity_evidence = manufacturing_sensitivity_audit.summary
            sensitivity_action = manufacturing_sensitivity_audit.safe_next_action
            if manufacturing_sensitivity_audit.status == "blocked":
                sensitivity_score = 0.28
                sensitivity_status = "blocker"
            elif manufacturing_sensitivity_audit.status == "risk":
                sensitivity_score = 0.58
                sensitivity_status = "warning"
            elif manufacturing_sensitivity_audit.status == "watch":
                sensitivity_score = 0.74
                sensitivity_status = "warning"
        manufacturing_score = clamp(
            0.55 * manufacturability_review.score + 0.45 * sensitivity_score
        )
        manufacturing_status = (
            "blocker"
            if manufacturability_review.status == "blocked" or sensitivity_status == "blocker"
            else (
                "warning"
                if manufacturability_review.status == "warning" or sensitivity_status == "warning"
                else "pass"
            )
        )
        manufacturing_action = next(
            (
                check.mitigation
                for check in manufacturability_review.checks
                if check.status in {"warning", "blocker"} and check.mitigation
            ),
            sensitivity_action,
        )
        add_dimension(
            "manufacturing_review",
            "Manufacturing review",
            manufacturing_score,
            manufacturing_status,
            [
                manufacturability_review.summary,
                sensitivity_evidence,
                f"manufacturing clearance={manufacturing_clearance_checklist.status}",
                f"evidence closeout={evidence_closeout_plan.status}",
            ],
            manufacturing_action or manufacturing_clearance_checklist.next_clearance_action,
        )

        if (
            design_handoff_packet.status == "blocked"
            or design_constraint_ledger.status == "blocked"
            or design_traceability_manifest.status == "blocked"
        ):
            handoff_score = 0.32
            handoff_status = "blocker"
        elif (
            design_handoff_packet.status == "conditional"
            or design_constraint_ledger.status == "needs_review"
            or design_traceability_manifest.status == "conditional"
        ):
            handoff_score = 0.64
            handoff_status = "warning"
        else:
            handoff_score = 0.94
            handoff_status = "pass"
        add_dimension(
            "handoff_completeness",
            "Handoff completeness",
            handoff_score,
            handoff_status,
            [
                design_handoff_packet.summary,
                design_constraint_ledger.summary,
                design_traceability_manifest.payload_policy,
            ],
            design_handoff_packet.next_decision,
        )

        by_id = {dimension.dimension_id: dimension for dimension in dimensions}
        readiness_score = round(
            clamp(
                0.18 * by_id["brief_interpretation"].score
                + 0.20 * by_id["seed_evidence"].score
                + 0.20 * by_id["optical_fit"].score
                + 0.15 * by_id["optimization_evidence"].score
                + 0.12 * by_id["manufacturing_review"].score
                + 0.15 * by_id["handoff_completeness"].score
            ),
            3,
        )
        blockers = _unique_in_order(
            [
                f"{dimension.label}: {dimension.next_action or dimension.evidence[0]}"
                for dimension in dimensions
                if dimension.status == "blocker"
            ]
        )
        weakest = min(dimensions, key=lambda item: item.score)
        if blockers:
            readiness_status = "blocked"
            claim_boundary = (
                "not replacement-ready for this brief; use as a diagnostic or strategy packet only"
            )
        elif readiness_score >= 0.76 and draft_acceptance_gate.status == "ready_for_review":
            readiness_status = "draft_ready"
            claim_boundary = (
                "junior first-pass draft handoff only; production sign-off still requires "
                "tolerance, supplier, and yield evidence"
            )
        else:
            readiness_status = "conditional"
            claim_boundary = (
                "conditional draft aid; human optical review is required before treating it as "
                "a junior-designer replacement"
            )
        next_improvement_action = next(
            (
                item
                for item in [
                    *draft_acceptance_gate.required_next_actions,
                    *(
                        dimension.next_action
                        for dimension in dimensions
                        if dimension.status == "blocker"
                    ),
                    *(
                        dimension.next_action
                        for dimension in dimensions
                        if dimension.status == "warning"
                    ),
                    evidence_closeout_plan.safe_next_action,
                    draft_quality_rubric.minimum_next_action,
                ]
                if item
            ),
            "continue fixed-eval optimization on the weakest readiness dimension",
        )
        forbidden_claims = _unique_in_order(
            [
                *draft_acceptance_gate.forbidden_claims[:4],
                *design_handoff_packet.forbidden_claims[:4],
                *evidence_closeout_plan.forbidden_claims[:4],
                "do not claim autonomous replacement beyond first-pass draft scope",
            ]
        )[:8]
        summary = (
            f"{readiness_status} designer-readiness score {readiness_score:.2f}; "
            f"weakest dimension {weakest.dimension_id}={weakest.score:.2f}"
        )
        return DesignerReadinessRubric(
            status=readiness_status,
            score=readiness_score,
            summary=summary,
            weakest_dimension_id=weakest.dimension_id,
            claim_boundary=claim_boundary,
            blockers=blockers,
            forbidden_claims=forbidden_claims,
            next_improvement_action=next_improvement_action,
            dimensions=dimensions,
        )

    designer_readiness_rubric = _designer_readiness_rubric()

    assessment = DesignAssessment(
        matched_case_id=best.metadata.case_id,
        score=score,
        normalized_distance=distance,
        seed_selection_scorecard=seed_selection_scorecard,
        target_focal_length_mm=efl_mm,
        target_f_number=fnum,
        target_fov_deg=fov_deg,
        target_image_height_mm=image_height_mm,
        target_n_elements=n_elements,
        target_total_track_mm=max_total_track_mm,
        priority=priority,
        manufacturing_tier=manufacturing_tier,
        delta_efl_mm=delta_efl,
        delta_f_number=delta_fnum,
        delta_fov_deg=delta_fov,
        delta_image_height_mm=delta_imh,
        delta_n_elements=delta_n,
        delta_total_track_mm=delta_ttl,
        warnings=warnings_out,
        rationale=rationale,
        candidate_comparison=candidate_comparison,
        requirement_coverage_summary=requirement_coverage_summary,
        requirement_coverage=requirement_coverage,
        design_intent_contract=design_intent_contract,
        manufacturability_review=manufacturability_review,
        manufacturing_sensitivity_audit=manufacturing_sensitivity_audit,
        manufacturing_clearance_checklist=manufacturing_clearance_checklist,
        tolerance_sensitivity_audit=tolerance_sensitivity_audit,
        next_steps=_next_steps(),
        readiness=readiness,
        risk_register=risk_register,
        optimization_plan=optimization_plan,
        optimization_attempt=optimization_attempt,
        merit_optimization_probe=merit_optimization_probe,
        full_field_recovery_diagnostic=full_field_recovery_diagnostic,
        library_coverage_diagnostic=library_coverage_diagnostic,
        reference_influence_audit=reference_influence_audit,
        design_strategy_decision=design_strategy_decision,
        designer_readiness_rubric=designer_readiness_rubric,
        seed_intake_audit=seed_intake_audit,
        seed_acquisition_contract=seed_acquisition_contract,
        delivery_gate=delivery_gate,
        draft_quality_rubric=draft_quality_rubric,
        draft_candidates=draft_candidates,
        recommended_candidate_id=recommended_candidate_id,
        branch_selection_policy=branch_selection_policy,
        strategy_tradeoff_matrix=strategy_tradeoff_matrix,
        spec_repair_preview=spec_repair_preview,
        spec_repair_decision=spec_repair_decision,
        spec_repair_auto_closure=spec_repair_auto_closure,
        draft_acceptance_gate=draft_acceptance_gate,
        acceptance_improvement_tasks=acceptance_improvement_tasks,
        evidence_closeout_plan=evidence_closeout_plan,
        design_handoff_packet=design_handoff_packet,
        design_traceability_manifest=design_traceability_manifest,
        design_constraint_ledger=design_constraint_ledger,
        prescription_change_set=prescription_change_set,
        optimization_task_queue=optimization_task_queue,
        optimization_task_runs=optimization_task_runs,
    )
    return best.model_copy(update={"design_assessment": assessment}, deep=True)
