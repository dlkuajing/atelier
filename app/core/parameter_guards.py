"""Parameter guards — refuse physically impossible or scenario-mismatched inputs
*before* the LLM or Optical Engine ever sees them.

Why: LLMs will sometimes propose plausible-sounding nonsense (e.g. an EFL of
0.5mm for a smartphone telephoto). These guards encode domain knowledge that
catches such proposals at the API boundary.

Scenario bounds come from real-world reference designs (Largan Precision /
Sunny Optical / Genius Electronic Optical published patents).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.lens_system import Scenario


@dataclass(frozen=True)
class ScenarioBounds:
    """Physically reasonable bounds for a scenario."""

    efl_mm_min: float
    efl_mm_max: float
    f_number_min: float
    f_number_max: float
    fov_deg_min: float
    fov_deg_max: float
    image_height_mm_min: float
    image_height_mm_max: float
    n_elements_min: int
    n_elements_max: int
    description: str


# Reference bounds — derived from public smartphone-camera teardowns and
# Largan / Sunny Optical patent dossiers (2020-2026 vintage).
SCENARIO_BOUNDS: dict[Scenario, ScenarioBounds] = {
    Scenario.SMARTPHONE_TELEPHOTO: ScenarioBounds(
        efl_mm_min=5.0,
        efl_mm_max=18.0,
        f_number_min=1.8,
        f_number_max=4.0,
        fov_deg_min=15.0,
        fov_deg_max=45.0,
        image_height_mm_min=2.5,
        image_height_mm_max=8.0,
        n_elements_min=5,
        n_elements_max=9,
        description="Folded or upright telephoto module for smartphones, ~3x optical zoom",
    ),
    Scenario.SMARTPHONE_WIDE: ScenarioBounds(
        # Calibrated from v2-02's 15 real wide designs (manifest nominals, see
        # scripts/compute_bounds_stats.py): EFL[2.50,3.90] F#[1.80,2.50]
        # FOV[60.0,84.1] IMH[1.80,3.30], elements 3-5; ~5% engineering margin.
        # Replaces the earlier hand-typed teardown estimate.
        efl_mm_min=2.4,
        efl_mm_max=4.1,
        f_number_min=1.7,
        f_number_max=2.6,
        fov_deg_min=57.0,
        fov_deg_max=88.0,
        image_height_mm_min=1.7,
        image_height_mm_max=3.5,
        n_elements_min=3,
        n_elements_max=6,
        description="Main wide camera, smartphone primary (calibrated to 15 real designs)",
    ),
    Scenario.SMARTPHONE_ULTRAWIDE: ScenarioBounds(
        # Calibrated from v2-02's real wide-FOV designs. HONEST CAVEAT: this phase's
        # ammo tops out at ~89.5° (only 2 designs: 2.8mm / F1.9 / 5-elem) — we have
        # NO true 100°+ ultrawide data. Bounds center on those real samples with
        # engineering margin across the wide→ultrawide transition. The previous
        # 100–130° range was a hand-typed guess with zero backing data — removed.
        # Revisit when real 100°+ ultrawide prescriptions are added.
        efl_mm_min=2.6,
        efl_mm_max=3.0,
        f_number_min=1.7,
        f_number_max=2.1,
        fov_deg_min=85.0,
        fov_deg_max=95.0,
        image_height_mm_min=2.7,
        image_height_mm_max=3.1,
        n_elements_min=4,
        n_elements_max=6,
        description="Wide-FOV auxiliary, smartphone (limited ammo ~89.5°, no true 100°+ ultrawide yet)",
    ),
    Scenario.AR_NEAR_EYE: ScenarioBounds(
        efl_mm_min=12.0,
        efl_mm_max=30.0,
        f_number_min=1.2,
        f_number_max=2.5,
        fov_deg_min=25.0,
        fov_deg_max=60.0,
        image_height_mm_min=4.0,
        image_height_mm_max=15.0,
        n_elements_min=3,
        n_elements_max=8,
        description="Near-eye display optics, AR / VR headset",
    ),
    Scenario.DSLR_PRIME: ScenarioBounds(
        efl_mm_min=24.0,
        efl_mm_max=300.0,
        f_number_min=1.2,
        f_number_max=5.6,
        fov_deg_min=6.0,
        fov_deg_max=85.0,
        image_height_mm_min=21.0,
        image_height_mm_max=22.0,  # Full-frame diagonal ~43.3mm → half is ~21.6mm
        n_elements_min=4,
        n_elements_max=18,
        description="Full-frame prime lens for DSLR / mirrorless",
    ),
    Scenario.MICROSCOPE_OBJECTIVE: ScenarioBounds(
        efl_mm_min=2.0,
        efl_mm_max=50.0,
        f_number_min=0.5,  # Microscope objectives can have very low effective f/# (high NA)
        f_number_max=4.0,
        fov_deg_min=0.5,
        fov_deg_max=15.0,
        image_height_mm_min=1.0,
        image_height_mm_max=15.0,
        n_elements_min=4,
        n_elements_max=15,
        description="Microscope objective, high NA",
    ),
}


class ParameterGuardError(ValueError):
    """Raised when input parameters fail scenario-specific bounds."""

    def __init__(self, message: str, scenario: Scenario, violations: list[str]) -> None:
        self.scenario = scenario
        self.violations = violations
        super().__init__(message)


def validate_scenario_params(
    scenario: Scenario,
    *,
    efl_mm: float,
    f_number: float,
    fov_deg: float,
    image_height_mm: float,
    n_elements: int | None = None,
) -> None:
    """Validate top-level paraxial params against scenario bounds.

    Raises ParameterGuardError listing every violation found.
    """
    bounds = SCENARIO_BOUNDS.get(scenario)
    if bounds is None:
        raise ParameterGuardError(
            f"Unknown scenario: {scenario}",
            scenario=scenario,
            violations=[f"scenario {scenario} not in SCENARIO_BOUNDS"],
        )

    violations: list[str] = []

    if not bounds.efl_mm_min <= efl_mm <= bounds.efl_mm_max:
        violations.append(
            f"EFL {efl_mm}mm out of [{bounds.efl_mm_min}, {bounds.efl_mm_max}]mm for {scenario}"
        )
    if not bounds.f_number_min <= f_number <= bounds.f_number_max:
        violations.append(
            f"f/# {f_number} out of [{bounds.f_number_min}, {bounds.f_number_max}] for {scenario}"
        )
    if not bounds.fov_deg_min <= fov_deg <= bounds.fov_deg_max:
        violations.append(
            f"FOV {fov_deg}° out of [{bounds.fov_deg_min}, {bounds.fov_deg_max}]° for {scenario}"
        )
    if not bounds.image_height_mm_min <= image_height_mm <= bounds.image_height_mm_max:
        violations.append(
            f"image_height {image_height_mm}mm out of "
            f"[{bounds.image_height_mm_min}, {bounds.image_height_mm_max}]mm "
            f"for {scenario}"
        )
    if n_elements is not None and not (
        bounds.n_elements_min <= n_elements <= bounds.n_elements_max
    ):
        violations.append(
            f"n_elements {n_elements} out of "
            f"[{bounds.n_elements_min}, {bounds.n_elements_max}] for {scenario}"
        )

    if violations:
        raise ParameterGuardError(
            message=(
                f"{len(violations)} parameter violation(s) for scenario {scenario}:\n"
                + "\n".join(f"  - {v}" for v in violations)
                + f"\n\nScenario bounds: {bounds.description}"
            ),
            scenario=scenario,
            violations=violations,
        )


def suggest_efl_range(scenario: Scenario) -> tuple[float, float]:
    """Return (min, max) EFL in mm for a scenario, for Wizard suggestions."""
    b = SCENARIO_BOUNDS[scenario]
    return (b.efl_mm_min, b.efl_mm_max)


def suggest_f_number_range(scenario: Scenario) -> tuple[float, float]:
    b = SCENARIO_BOUNDS[scenario]
    return (b.f_number_min, b.f_number_max)
