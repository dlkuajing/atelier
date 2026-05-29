"""Manifest of the 17 phase-v2-02 smartphone main/wide ammunition zmx designs.

Sourcing: the GGG dataset has 33 real Zemax designs. We filtered to the
smartphone main/wide visible-imaging domain (EFL 2.3-4.0mm, FOV 55-95deg),
which gave 21 candidates. During ingest verification 4 were dropped:
- 3 **near-infrared lenses** (design wavelengths 930-960nm — ToF / structured-
  light / IR sensing optics, not visible main/wide cameras). Forcing them into
  the visible F/d/C band drifts EFL 2.6-4.9% and their MTF would be the IR
  design at the wrong band. Future IR/ToF subclass candidates.
- 1 **malformed variant** (3P_F2.4...TTL3.51x.ZMX): its stop surface has a None
  semi-aperture and an array-shaped EPD, crashing ray-aiming for MTF/SVG on
  every field. The trailing "x" marks it a draft variant.
Net: 17 healthy visible main/wide designs.

Excluded (kept out of data/zmx):
  4P_F1.5_FOV90.8_EFL2.6_IMH2.2_TTL4.08.ZMX   (IR, wl 930-960nm)
  4P_F2.0_FOV83.5_EFL2.6_IMH2.3_TTL4.02.ZMX   (IR, wl 930-960nm)
  4P_F2.0_FOV91.4_EFL2.5_IMH2.6_TTL4.30.ZMX   (IR, wl 930-960nm)
  3P_F2.4_FOV78.0_EFL2.8_IMH2.3_TTL3.51x.ZMX  (malformed: None stop semi-aperture)

Nominal values are hard-coded from each filename
(NP_F{fnum}_FOV{fov}_EFL{efl}_IMH{imh}_TTL{ttl}{suffix}) — the trailing-x /
case-difference suffixes make runtime regex fragile. These are the design
*intent* values (most authoritative for bounds + EFL checks).

Shared by tests (test_zmx_ingest, test_case_library, test_parameter_guards) and
the offline scripts (generate_cases, compute_bounds_stats).
"""

from __future__ import annotations

ZMX_AMMO: list[dict] = [
    # --- directly loadable (visible), 7 ---
    {
        "filename": "3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56.ZMX",
        "n_pieces": 3,
        "nominal_fnum": 2.5,
        "nominal_fov_deg": 78.0,
        "nominal_efl_mm": 2.7,
        "nominal_imh_mm": 2.3,
        "nominal_ttl_mm": 3.56,
    },
    {
        "filename": "3P_F2.5_FOV78.1_EFL2.8_IMH2.3_TTL4.33.ZMX",
        "n_pieces": 3,
        "nominal_fnum": 2.5,
        "nominal_fov_deg": 78.1,
        "nominal_efl_mm": 2.8,
        "nominal_imh_mm": 2.3,
        "nominal_ttl_mm": 4.33,
    },
    {
        "filename": "4P_F1.9_FOV60.0_EFL3.7_IMH2.1_TTL6.00.ZMX",
        "n_pieces": 4,
        "nominal_fnum": 1.9,
        "nominal_fov_deg": 60.0,
        "nominal_efl_mm": 3.7,
        "nominal_imh_mm": 2.1,
        "nominal_ttl_mm": 6.00,
    },
    {
        "filename": "4P_F1.9_FOV60.1_EFL3.7_IMH2.1_TTL6.00.ZMX",
        "n_pieces": 4,
        "nominal_fnum": 1.9,
        "nominal_fov_deg": 60.1,
        "nominal_efl_mm": 3.7,
        "nominal_imh_mm": 2.1,
        "nominal_ttl_mm": 6.00,
    },
    {
        "filename": "4P_F2.2_FOV67.7_EFL2.6_IMH1.8_TTL3.58.zmx",
        "n_pieces": 4,
        "nominal_fnum": 2.2,
        "nominal_fov_deg": 67.7,
        "nominal_efl_mm": 2.6,
        "nominal_imh_mm": 1.8,
        "nominal_ttl_mm": 3.58,
    },
    {
        "filename": "4P_F2.2_FOV68.0_EFL2.6_IMH1.8_TTL3.30.zmx",
        "n_pieces": 4,
        "nominal_fnum": 2.2,
        "nominal_fov_deg": 68.0,
        "nominal_efl_mm": 2.6,
        "nominal_imh_mm": 1.8,
        "nominal_ttl_mm": 3.30,
    },
    {
        "filename": "4P_F2.2_FOV74.7_EFL2.9_IMH2.2_TTL3.90.zmx",
        "n_pieces": 4,
        "nominal_fnum": 2.2,
        "nominal_fov_deg": 74.7,
        "nominal_efl_mm": 2.9,
        "nominal_imh_mm": 2.2,
        "nominal_ttl_mm": 3.90,
    },
    # --- needs xasphere preprocessing (visible), 10 ---
    {
        "filename": "4P_F2.0_FOV84.1_EFL2.5_IMH2.3_TTL3.34.ZMX",
        "n_pieces": 4,
        "nominal_fnum": 2.0,
        "nominal_fov_deg": 84.1,
        "nominal_efl_mm": 2.5,
        "nominal_imh_mm": 2.3,
        "nominal_ttl_mm": 3.34,
    },
    {
        "filename": "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15.zmx",
        "n_pieces": 5,
        "nominal_fnum": 1.8,
        "nominal_fov_deg": 74.1,
        "nominal_efl_mm": 2.9,
        "nominal_imh_mm": 2.3,
        "nominal_ttl_mm": 4.15,
    },
    {
        "filename": "5P_F1.9_FOV76.9_EFL3.6_IMH2.9_TTL4.30.zmx",
        "n_pieces": 5,
        "nominal_fnum": 1.9,
        "nominal_fov_deg": 76.9,
        "nominal_efl_mm": 3.6,
        "nominal_imh_mm": 2.9,
        "nominal_ttl_mm": 4.30,
    },
    {
        "filename": "5P_F1.9_FOV77.0_EFL3.6_IMH2.9_TTL4.30.zmx",
        "n_pieces": 5,
        "nominal_fnum": 1.9,
        "nominal_fov_deg": 77.0,
        "nominal_efl_mm": 3.6,
        "nominal_imh_mm": 2.9,
        "nominal_ttl_mm": 4.30,
    },
    {
        "filename": "5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.29.zmx",
        "n_pieces": 5,
        "nominal_fnum": 1.9,
        "nominal_fov_deg": 89.5,
        "nominal_efl_mm": 2.8,
        "nominal_imh_mm": 2.9,
        "nominal_ttl_mm": 4.29,
    },
    {
        "filename": "5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.33.zmx",
        "n_pieces": 5,
        "nominal_fnum": 1.9,
        "nominal_fov_deg": 89.5,
        "nominal_efl_mm": 2.8,
        "nominal_imh_mm": 2.9,
        "nominal_ttl_mm": 4.33,
    },
    {
        "filename": "5P_F2.0_FOV71.0_EFL2.6_IMH1.9_TTL4.26.zmx",
        "n_pieces": 5,
        "nominal_fnum": 2.0,
        "nominal_fov_deg": 71.0,
        "nominal_efl_mm": 2.6,
        "nominal_imh_mm": 1.9,
        "nominal_ttl_mm": 4.26,
    },
    {
        "filename": "5P_F2.0_FOV78.7_EFL3.8_IMH3.3_TTL4.35.zmx",
        "n_pieces": 5,
        "nominal_fnum": 2.0,
        "nominal_fov_deg": 78.7,
        "nominal_efl_mm": 3.8,
        "nominal_imh_mm": 3.3,
        "nominal_ttl_mm": 4.35,
    },
    {
        "filename": "5P_F2.0_FOV78.8_EFL3.8_IMH3.2_TTL4.30.zmx",
        "n_pieces": 5,
        "nominal_fnum": 2.0,
        "nominal_fov_deg": 78.8,
        "nominal_efl_mm": 3.8,
        "nominal_imh_mm": 3.2,
        "nominal_ttl_mm": 4.30,
    },
    {
        "filename": "5P_F2.0_FOV78.8_EFL3.9_IMH3.3_TTL4.35.zmx",
        "n_pieces": 5,
        "nominal_fnum": 2.0,
        "nominal_fov_deg": 78.8,
        "nominal_efl_mm": 3.9,
        "nominal_imh_mm": 3.3,
        "nominal_ttl_mm": 4.35,
    },
]

ZMX_AMMO_FILENAMES: list[str] = [a["filename"] for a in ZMX_AMMO]

assert len(ZMX_AMMO) == 17, f"expected 17 ammo designs, got {len(ZMX_AMMO)}"
