"""Optical Engine — Optiland integration.

Wave 2 of Phase 2. Bridges OpticalSpecRequest → Optiland → RayTraceResult.

Strategy
========
Each scenario maps to an Optiland sample reference design. We scale the
reference to the user's target EFL (preserving relative geometry) and resize
the aperture to honour the target f-number. The frontend visualization then
consumes the surface positions, radii, and traced ray paths.

CRITICAL — never let LLM numerics enter without parameter_guards. That gate
lives upstream in `app/api/optical.py::_validate_or_400`.
"""

from __future__ import annotations

import logging
import warnings

import numpy as np
from pydantic import BaseModel

# Optiland prints deprecation noise on import paths we know about; suppress.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from optiland.optic import Optic
    from optiland.samples.objectives import (
        CookeTriplet,
        DoubleGauss,
        Telephoto,
        WideAngle100FOV,
    )

from app.core.lens_system import RayPath, RayTraceResult, Scenario
from app.core.provenance import ProvenanceSource


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scenario → Optiland reference design
# ---------------------------------------------------------------------------
# Telephoto      — multi-element retrofocus, good base for smartphone tele
# CookeTriplet   — classic 3-element wide, good base for smartphone wide
# WideAngle100   — wide-FOV reference, base for ultrawide
# DoubleGauss    — symmetric prime, base for DSLR primes
# AR_NEAR_EYE + MICROSCOPE_OBJECTIVE re-use DoubleGauss as a placeholder; future
# work adds scenario-native references (e.g. magnifier eyepiece for AR).
# ---------------------------------------------------------------------------

_SCENARIO_REFERENCE: dict[Scenario, type[Optic]] = {
    Scenario.SMARTPHONE_TELEPHOTO: Telephoto,
    Scenario.SMARTPHONE_WIDE: CookeTriplet,
    Scenario.SMARTPHONE_ULTRAWIDE: WideAngle100FOV,
    Scenario.DSLR_PRIME: DoubleGauss,
    Scenario.AR_NEAR_EYE: DoubleGauss,
    Scenario.MICROSCOPE_OBJECTIVE: DoubleGauss,
}


# ---------------------------------------------------------------------------
# Build / scale
# ---------------------------------------------------------------------------


def build_optic_for_scenario(
    scenario: Scenario,
    target_efl_mm: float,
    target_f_number: float | None = None,
) -> Optic:
    """Construct + scale an Optiland Optic for the given scenario.

    EFL is set exactly via `updater.scale_system`. F-number is best-effort —
    if `optic.set_aperture` works for the design, we resize the entrance pupil;
    otherwise we accept the natural F# induced by the scale.

    Raises ValueError on unknown scenario.
    """
    ref_class = _SCENARIO_REFERENCE.get(scenario)
    if ref_class is None:
        raise ValueError(f"No reference design for scenario {scenario}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        optic = ref_class()

        current_efl = float(optic.paraxial.f2())
        if current_efl <= 0:
            raise RuntimeError(
                f"Reference {ref_class.__name__} has non-positive EFL {current_efl}"
            )

        scale_factor = target_efl_mm / current_efl
        optic.updater.scale_system(scale_factor)

        if target_f_number is not None:
            target_epd = target_efl_mm / target_f_number
            try:
                # Optiland's set_aperture accepts ApertureType + value
                optic.set_aperture(aperture_type="EPD", value=target_epd)
            except Exception as exc:
                logger.warning(
                    "aperture_resize_skipped",
                    extra={
                        "scenario": scenario,
                        "target_f_number": target_f_number,
                        "natural_f_number": float(optic.paraxial.FNO()),
                        "reason": str(exc),
                    },
                )

        # Wide-field scenarios (smartphone-ultrawide, AR near-eye) and any
        # heavily-scaled prescription can make Optiland's default "paraxial"
        # ray aimer produce NaN guesses on the first pass — we observed:
        #   ValueError: Initial ray aiming guess produced NaNs.
        #   Consider using the 'robust' method instead.
        # The "robust" aimer is iterative + bracketed, fast enough for our
        # demo workload, and a safe default for everyone. Apply universally
        # so the scenario logic stays simple.
        try:
            optic.ray_tracer.set_aiming("robust", max_iter=20, tol=1e-6)
        except Exception as exc:
            logger.warning(
                "ray_aiming_robust_skipped",
                extra={"scenario": scenario, "reason": str(exc)},
            )

    return optic


# ---------------------------------------------------------------------------
# Paraxial summary
# ---------------------------------------------------------------------------


class ParaxialSummary(BaseModel):
    provenance: ProvenanceSource = ProvenanceSource.THIN_LENS_ANALYTIC
    effective_focal_length_mm: float
    f_number: float
    entrance_pupil_diameter_mm: float
    exit_pupil_diameter_mm: float
    total_track_mm: float
    n_surfaces: int
    stop_surface_index: int


def compute_paraxial_summary(optic: Optic) -> ParaxialSummary:
    """Extract paraxial properties from Optiland."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return ParaxialSummary(
            effective_focal_length_mm=float(optic.paraxial.f2()),
            f_number=float(optic.paraxial.FNO()),
            entrance_pupil_diameter_mm=float(optic.paraxial.EPD()),
            exit_pupil_diameter_mm=float(optic.paraxial.XPD()),
            total_track_mm=float(optic.total_track),
            n_surfaces=int(optic.surfaces.num_surfaces),
            stop_surface_index=int(optic.surfaces.stop_index),
        )


# ---------------------------------------------------------------------------
# Surface descriptors (flat list for frontend rendering)
# ---------------------------------------------------------------------------


class SurfaceDescriptor(BaseModel):
    index: int
    z_mm: float                # axial position
    radius_mm: float           # surface curvature radius (inf for plane)
    is_stop: bool
    is_image: bool
    is_object: bool


def extract_surface_descriptors(optic: Optic) -> list[SurfaceDescriptor]:
    """Flatten optic.surfaces into a list the frontend can render directly."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        positions = np.asarray(optic.surfaces.positions).flatten()
        radii = np.asarray(optic.surfaces.radii).flatten()
        stop_idx = int(optic.surfaces.stop_index)
        n = int(optic.surfaces.num_surfaces)

    out: list[SurfaceDescriptor] = []
    for i in range(n):
        z = float(positions[i])
        r = float(radii[i])
        out.append(
            SurfaceDescriptor(
                index=i,
                # Filter inf object plane down to a sentinel value for serialization
                z_mm=z if np.isfinite(z) else -1e9,
                radius_mm=r if np.isfinite(r) else float("inf"),
                is_stop=(i == stop_idx),
                is_object=(i == 0),
                is_image=(i == n - 1),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Ray tracing — paraxial chief + marginal + axial sample
# ---------------------------------------------------------------------------


def _paraxial_ray_to_points(
    positions: np.ndarray, y_values: np.ndarray
) -> list[tuple[float, float]]:
    """Pair surface Z positions with paraxial ray heights y → list of (z, y).

    Filters non-finite Z (object at infinity) so the output is renderable.
    """
    points: list[tuple[float, float]] = []
    flat_pos = positions.flatten()
    flat_y = y_values.flatten()
    for z, y in zip(flat_pos, flat_y, strict=False):
        z_f, y_f = float(z), float(y)
        if np.isfinite(z_f) and np.isfinite(y_f):
            points.append((z_f, y_f))
    return points


def trace_optic(
    optic: Optic,
    assembly_name: str,
    wavelength_nm: float = 550.0,
) -> RayTraceResult:
    """Trace paraxial chief + marginal rays through the optic.

    Returns a RayTraceResult with chief ray + marginal ray sampled at each
    surface plane. This is the v1 "good enough for Demo" trace; richer
    real-ray bundles can be added in a follow-up if needed.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        positions = np.asarray(optic.surfaces.positions)
        cr_y, _cr_u = optic.paraxial.chief_ray()
        mr_y, _mr_u = optic.paraxial.marginal_ray()

    chief_points = _paraxial_ray_to_points(positions, cr_y)
    marginal_pos = _paraxial_ray_to_points(positions, mr_y)
    marginal_neg = [(z, -y) for z, y in marginal_pos]

    sampled_paths: list[RayPath] = [
        RayPath(
            ray_id="chief-axial",
            wavelength_nm=wavelength_nm,
            field_angle_deg=0.0,
            points_mm=chief_points,
            reaches_image=True,
        ),
        RayPath(
            ray_id="marginal-upper",
            wavelength_nm=wavelength_nm,
            field_angle_deg=0.0,
            points_mm=marginal_pos,
            reaches_image=True,
        ),
        RayPath(
            ray_id="marginal-lower",
            wavelength_nm=wavelength_nm,
            field_angle_deg=0.0,
            points_mm=marginal_neg,
            reaches_image=True,
        ),
    ]

    return RayTraceResult(
        assembly_name=assembly_name,
        n_rays=len(sampled_paths),
        sampled_paths=sampled_paths,
        rms_spot_radius_um={},
        has_vignetting=False,
    )


# ---------------------------------------------------------------------------
# Top-level entry — used by /api/optical/raytrace
# ---------------------------------------------------------------------------


def raytrace_from_spec(
    scenario: Scenario,
    target_efl_mm: float,
    target_f_number: float,
    wavelength_nm: float = 550.0,
) -> tuple[ParaxialSummary, list[SurfaceDescriptor], RayTraceResult]:
    """Full pipeline: build → summarize → describe surfaces → trace rays.

    Returns three artefacts in one call so the API handler can return them
    together to the frontend.
    """
    optic = build_optic_for_scenario(
        scenario, target_efl_mm, target_f_number=target_f_number
    )
    summary = compute_paraxial_summary(optic)
    surfaces = extract_surface_descriptors(optic)
    name = f"{scenario.value}-EFL{target_efl_mm}mm-F{target_f_number}"
    trace = trace_optic(optic, assembly_name=name, wavelength_nm=wavelength_nm)
    return summary, surfaces, trace
