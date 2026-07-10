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

import json
from pathlib import Path

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
    # --- E2-01 batch 1: 22 gate-passing IDMxS patent seeds (main/wide + ultrawide) ---
    # 25 curated candidates -> 22 ingested. Each seed passed a full-embodiment
    # cross-validation gate (zmx-computed vs patent-declared across ALL embodiments,
    # not just embodiment 1; tol EFL<=5%, FOV<=3deg, TTL<=10%). See PATENT_PROVENANCE
    # below for the per-seed verdict + matched embodiment. Two seeds carry real
    # >=85deg full-field(1.0) evidence: US20170003482A1 (91deg 7P, emb 3, EFL 0.0%)
    # and US8908290B1 (91.2deg 6P, emb 3, EFL 2.3%).
    # generated by scripts/e2_intake.py; n_pieces = backend n_imaging (filter-excluded);
    # nominal_* are backend-computed. Deferred / gate-failed (NOT ingested):
    #   US10007086B2 (11P) - anomalous 18.9mm track pending ZMX geometry check;
    #   US11347030B2 - FOV >3deg off every embodiment (gate FAIL, todo batch 2);
    #   US8736979B2, US9348117B1 - element-count mismatch vs all embodiments (gate FAIL).
    {
        "filename": "US20170045714A1.zmx",  # US20170045714A1
        "n_pieces": 8,
        "nominal_fnum": 1.75,
        "nominal_fov_deg": 70.4,
        "nominal_efl_mm": 3.97,
        "nominal_imh_mm": 2.801,
        "nominal_ttl_mm": 4.981,
    },
    {
        "filename": "US20170003482A1.zmx",  # US20170003482A1
        "n_pieces": 7,
        "nominal_fnum": 2.32,
        "nominal_fov_deg": 91.0,
        "nominal_efl_mm": 3.621,
        "nominal_imh_mm": 3.685,
        "nominal_ttl_mm": 5.395,
    },
    {
        "filename": "US20180143405A1.zmx",  # US20180143405A1
        "n_pieces": 6,
        "nominal_fnum": 1.86,
        "nominal_fov_deg": 95.0,
        "nominal_efl_mm": 3.073,
        "nominal_imh_mm": 3.354,
        "nominal_ttl_mm": 4.503,
    },
    {
        "filename": "US9239447B1.zmx",  # US9239447B1
        "n_pieces": 6,
        "nominal_fnum": 2.2,
        "nominal_fov_deg": 90.0,
        "nominal_efl_mm": 3.035,
        "nominal_imh_mm": 3.035,
        "nominal_ttl_mm": 4.404,
    },
    {
        "filename": "US8908290B1.zmx",  # US8908290B1
        "n_pieces": 6,
        "nominal_fnum": 2.0,
        "nominal_fov_deg": 91.2,
        "nominal_efl_mm": 3.95,
        "nominal_imh_mm": 4.034,
        "nominal_ttl_mm": 6.352,
    },
    {
        "filename": "US10330891B2.zmx",  # US10330891B2
        "n_pieces": 6,
        "nominal_fnum": 2.08,
        "nominal_fov_deg": 100.0,
        "nominal_efl_mm": 2.416,
        "nominal_imh_mm": 2.88,
        "nominal_ttl_mm": 4.5,
    },
    {
        "filename": "US10310222B2.zmx",  # US10310222B2
        "n_pieces": 6,
        "nominal_fnum": 1.8,
        "nominal_fov_deg": 76.2,
        "nominal_efl_mm": 4.609,
        "nominal_imh_mm": 3.614,
        "nominal_ttl_mm": 5.77,
    },
    {
        "filename": "US10281683B2.zmx",  # US10281683B2
        "n_pieces": 6,
        "nominal_fnum": 1.68,
        "nominal_fov_deg": 81.0,
        "nominal_efl_mm": 4.706,
        "nominal_imh_mm": 4.019,
        "nominal_ttl_mm": 6.0,
    },
    {
        "filename": "US20150338607A1.zmx",  # US20150338607A1
        "n_pieces": 6,
        "nominal_fnum": 1.6,
        "nominal_fov_deg": 72.0,
        "nominal_efl_mm": 4.156,
        "nominal_imh_mm": 3.02,
        "nominal_ttl_mm": 5.19,
    },
    {
        "filename": "US9651759B2.zmx",  # US9651759B2
        "n_pieces": 6,
        "nominal_fnum": 2.2,
        "nominal_fov_deg": 82.0,
        "nominal_efl_mm": 3.277,
        "nominal_imh_mm": 2.848,
        "nominal_ttl_mm": 4.887,
    },
    {
        "filename": "US9201216B2.zmx",  # US9201216B2
        "n_pieces": 6,
        "nominal_fnum": 2.1,
        "nominal_fov_deg": 84.0,
        "nominal_efl_mm": 3.267,
        "nominal_imh_mm": 2.942,
        "nominal_ttl_mm": 4.363,
    },
    {
        "filename": "US20140118844A1.zmx",  # US20140118844A1
        "n_pieces": 6,
        "nominal_fnum": 2.4,
        "nominal_fov_deg": 79.2,
        "nominal_efl_mm": 3.483,
        "nominal_imh_mm": 2.881,
        "nominal_ttl_mm": 4.889,
    },
    {
        "filename": "US9304295B2.zmx",  # US9304295B2
        "n_pieces": 6,
        "nominal_fnum": 2.5,
        "nominal_fov_deg": 78.6,
        "nominal_efl_mm": 3.559,
        "nominal_imh_mm": 2.913,
        "nominal_ttl_mm": 5.22,
    },
    {
        "filename": "US8310767B2.zmx",  # US8310767B2
        "n_pieces": 6,
        "nominal_fnum": 2.9,
        "nominal_fov_deg": 74.4,
        "nominal_efl_mm": 2.939,
        "nominal_imh_mm": 2.231,
        "nominal_ttl_mm": 4.102,
    },
    {
        "filename": "US20210165194A1.zmx",  # US20210165194A1
        "n_pieces": 5,
        "nominal_fnum": 2.0,
        "nominal_fov_deg": 95.0,
        "nominal_efl_mm": 2.409,
        "nominal_imh_mm": 2.629,
        "nominal_ttl_mm": 4.802,
    },
    {
        "filename": "US9810880B2.zmx",  # US9810880B2
        "n_pieces": 6,
        "nominal_fnum": 2.25,
        "nominal_fov_deg": 83.4,
        "nominal_efl_mm": 4.994,
        "nominal_imh_mm": 4.449,
        "nominal_ttl_mm": 5.799,
    },
    {
        "filename": "US9557532B2.zmx",  # US9557532B2
        "n_pieces": 6,
        "nominal_fnum": 2.3,
        "nominal_fov_deg": 70.0,
        "nominal_efl_mm": 4.148,
        "nominal_imh_mm": 2.904,
        "nominal_ttl_mm": 4.901,
    },
    {
        "filename": "US10031318B2.zmx",  # US10031318B2
        "n_pieces": 6,
        "nominal_fnum": 2.05,
        "nominal_fov_deg": 78.4,
        "nominal_efl_mm": 4.814,
        "nominal_imh_mm": 3.926,
        "nominal_ttl_mm": 5.333,
    },
    {
        "filename": "US9063319B1.zmx",  # US9063319B1
        "n_pieces": 6,
        "nominal_fnum": 2.25,
        "nominal_fov_deg": 78.0,
        "nominal_efl_mm": 4.756,
        "nominal_imh_mm": 3.851,
        "nominal_ttl_mm": 5.299,
    },
    {
        "filename": "US20140111876A1.zmx",  # US20140111876A1
        "n_pieces": 6,
        "nominal_fnum": 2.07,
        "nominal_fov_deg": 75.2,
        "nominal_efl_mm": 4.185,
        "nominal_imh_mm": 3.223,
        "nominal_ttl_mm": 5.488,
    },
    {
        "filename": "US9316811B2.zmx",  # US9316811B2
        "n_pieces": 6,
        "nominal_fnum": 2.2,
        "nominal_fov_deg": 76.2,
        "nominal_efl_mm": 4.841,
        "nominal_imh_mm": 3.795,
        "nominal_ttl_mm": 5.613,
    },
    {
        "filename": "US9195030B2.zmx",  # US9195030B2
        "n_pieces": 6,
        "nominal_fnum": 2.24,
        "nominal_fov_deg": 77.4,
        "nominal_efl_mm": 4.213,
        "nominal_imh_mm": 3.375,
        "nominal_ttl_mm": 5.252,
    },
]

DATA06_MANIFEST_NAMES = (
    "data06c_manifest.json",
    "data06f_manifest.json",
    "data06f_b11_manifest.json",
    "data06i_rescan2_manifest.json",
)
DATA09_MANIFEST_NAMES = ("data09d1_manifest.json",)
DATA10_MANIFEST_NAMES = ("data10a_manifest.json", "data10b_manifest.json")
P12_MANIFEST_NAMES = ("p12_intake_manifest.json",)
DATA06_ZMX_AMMO: list[dict] = []
for manifest_name in DATA06_MANIFEST_NAMES:
    manifest_path = Path(__file__).with_name(manifest_name)
    if manifest_path.exists():
        DATA06_ZMX_AMMO.extend(json.loads(manifest_path.read_text(encoding="utf-8")))
DATA09_ZMX_AMMO: list[dict] = []
for manifest_name in DATA09_MANIFEST_NAMES:
    manifest_path = Path(__file__).with_name(manifest_name)
    if manifest_path.exists():
        DATA09_ZMX_AMMO.extend(json.loads(manifest_path.read_text(encoding="utf-8")))
DATA10_ZMX_AMMO: list[dict] = []
for manifest_name in DATA10_MANIFEST_NAMES:
    manifest_path = Path(__file__).with_name(manifest_name)
    if manifest_path.exists():
        DATA10_ZMX_AMMO.extend(json.loads(manifest_path.read_text(encoding="utf-8")))
P12_ZMX_AMMO: list[dict] = []
for manifest_name in P12_MANIFEST_NAMES:
    manifest_path = Path(__file__).with_name(manifest_name)
    if manifest_path.exists():
        P12_ZMX_AMMO.extend(json.loads(manifest_path.read_text(encoding="utf-8")))
ZMX_AMMO.extend(DATA06_ZMX_AMMO)
ZMX_AMMO.extend(DATA09_ZMX_AMMO)
ZMX_AMMO.extend(DATA10_ZMX_AMMO)
ZMX_AMMO.extend(P12_ZMX_AMMO)

ZMX_AMMO_FILENAMES: list[str] = [a["filename"] for a in ZMX_AMMO]

assert len(DATA06_ZMX_AMMO) == 128, (
    f"expected 128 converted DATA-06 designs "
    f"(67 DATA-06c + 39 DATA-06f + 12 B11 + 10 DATA-06i rescan2), "
    f"got {len(DATA06_ZMX_AMMO)}"
)
assert len(DATA09_ZMX_AMMO) == 186, (
    f"expected 186 converted DATA-09d1 designs, got {len(DATA09_ZMX_AMMO)}"
)
assert len(DATA10_ZMX_AMMO) == 83, (
    f"expected 83 converted DATA-10 designs (8 DATA-10a live mining + 75 DATA-10b "
    f"Sunny/Ability parser-family expansion), got {len(DATA10_ZMX_AMMO)}"
)
assert len(P12_ZMX_AMMO) == 6, (
    f"expected 6 accepted Phase 12 NEWMAX designs, got {len(P12_ZMX_AMMO)}"
)
assert len(ZMX_AMMO) == 442, (
    f"expected 442 ammo designs (17 GGG + 22 patent + 128 DATA-06 + 186 DATA-09d1 "
    f"+ 8 DATA-10a + 75 DATA-10b + 6 Phase 12 NEWMAX), got {len(ZMX_AMMO)}"
)

# E2-01 batch 1 full-embodiment cross-validation provenance (patent seeds only).
# zmx-computed values recomputed by the backend from the ingested prescription;
# declared values from lens-data-staging/patent_declared_specs.json (Google
# Patents). matched_embodiment = the declared embodiment the computed design best
# matches after scanning ALL embodiments (early false-negatives came from
# comparing embodiment 1 only). verdict PASS requires EFL<=5%, FOV<=3deg vs that
# embodiment, and element-count equality. fov_declared_deg = 2 x declared HFOV.
# Regenerate with scripts/e2_intake.py --cross-validate (see that script's gate).
PATENT_PROVENANCE: dict[str, dict] = {
    "US10031318B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.75, "efl_computed_mm": 4.814, "efl_diff_pct": 0.7, "fov_computed_deg": 78.4, "fov_declared_deg": 78.4, "fov_diff_deg": 0.0},
    "US10281683B2": {"verdict": "PASS", "matched_embodiment": 1, "n_pieces": 6, "mtf_max_field_frac": 0.5, "efl_computed_mm": 4.706, "efl_diff_pct": 4.3, "fov_computed_deg": 81.0, "fov_declared_deg": 81.0, "fov_diff_deg": 0.0},
    "US10310222B2": {"verdict": "PASS", "matched_embodiment": 5, "n_pieces": 6, "mtf_max_field_frac": 0.5, "efl_computed_mm": 4.609, "efl_diff_pct": 4.8, "fov_computed_deg": 76.2, "fov_declared_deg": 76.2, "fov_diff_deg": 0.0},
    "US10330891B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.85, "efl_computed_mm": 2.416, "efl_diff_pct": 0.2, "fov_computed_deg": 100.0, "fov_declared_deg": 100.0, "fov_diff_deg": 0.0},
    "US20140111876A1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.9, "efl_computed_mm": 4.185, "efl_diff_pct": 0.4, "fov_computed_deg": 75.2, "fov_declared_deg": 75.2, "fov_diff_deg": 0.0},
    "US20140118844A1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 1.0, "efl_computed_mm": 3.483, "efl_diff_pct": 0.1, "fov_computed_deg": 79.2, "fov_declared_deg": 79.2, "fov_diff_deg": 0.0},
    "US20150338607A1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.5, "efl_computed_mm": 4.156, "efl_diff_pct": 0.1, "fov_computed_deg": 72.0, "fov_declared_deg": 72.0, "fov_diff_deg": 0.0},
    "US20170003482A1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 7, "mtf_max_field_frac": 1.0, "efl_computed_mm": 3.621, "efl_diff_pct": 0.0, "fov_computed_deg": 91.0, "fov_declared_deg": 91.0, "fov_diff_deg": 0.0},
    "US20170045714A1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 8, "mtf_max_field_frac": 0.9, "efl_computed_mm": 3.97, "efl_diff_pct": 0.0, "fov_computed_deg": 70.4, "fov_declared_deg": 70.4, "fov_diff_deg": 0.0},
    "US20180143405A1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.85, "efl_computed_mm": 3.073, "efl_diff_pct": 0.1, "fov_computed_deg": 95.0, "fov_declared_deg": 95.0, "fov_diff_deg": 0.0},
    "US20210165194A1": {"verdict": "PASS", "matched_embodiment": 1, "n_pieces": 5, "mtf_max_field_frac": 0.5, "efl_computed_mm": 2.409, "efl_diff_pct": 0.4, "fov_computed_deg": 95.0, "fov_declared_deg": 95.0, "fov_diff_deg": 0.0},
    "US8310767B2": {"verdict": "PASS", "matched_embodiment": 4, "n_pieces": 6, "mtf_max_field_frac": 1.0, "efl_computed_mm": 2.939, "efl_diff_pct": 1.1, "fov_computed_deg": 74.4, "fov_declared_deg": 74.8, "fov_diff_deg": 0.4},
    "US8908290B1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 1.0, "efl_computed_mm": 3.95, "efl_diff_pct": 2.3, "fov_computed_deg": 91.2, "fov_declared_deg": 91.2, "fov_diff_deg": 0.0},
    "US9063319B1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.75, "efl_computed_mm": 4.756, "efl_diff_pct": 1.2, "fov_computed_deg": 78.0, "fov_declared_deg": 78.0, "fov_diff_deg": 0.0},
    "US9195030B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.85, "efl_computed_mm": 4.213, "efl_diff_pct": 0.1, "fov_computed_deg": 77.4, "fov_declared_deg": 77.4, "fov_diff_deg": 0.0},
    "US9201216B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.9, "efl_computed_mm": 3.267, "efl_diff_pct": 0.1, "fov_computed_deg": 84.0, "fov_declared_deg": 84.0, "fov_diff_deg": 0.0},
    "US9239447B1": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.5, "efl_computed_mm": 3.035, "efl_diff_pct": 0.2, "fov_computed_deg": 90.0, "fov_declared_deg": 90.0, "fov_diff_deg": 0.0},
    "US9304295B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 1.0, "efl_computed_mm": 3.559, "efl_diff_pct": 0.0, "fov_computed_deg": 78.6, "fov_declared_deg": 78.6, "fov_diff_deg": 0.0},
    "US9316811B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 0.75, "efl_computed_mm": 4.841, "efl_diff_pct": 0.2, "fov_computed_deg": 76.2, "fov_declared_deg": 76.2, "fov_diff_deg": 0.0},
    "US9557532B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 1.0, "efl_computed_mm": 4.148, "efl_diff_pct": 0.2, "fov_computed_deg": 70.0, "fov_declared_deg": 70.0, "fov_diff_deg": 0.0},
    "US9651759B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 1.0, "efl_computed_mm": 3.277, "efl_diff_pct": 0.2, "fov_computed_deg": 82.0, "fov_declared_deg": 82.0, "fov_diff_deg": 0.0},
    "US9810880B2": {"verdict": "PASS", "matched_embodiment": 3, "n_pieces": 6, "mtf_max_field_frac": 1.0, "efl_computed_mm": 4.994, "efl_diff_pct": 0.1, "fov_computed_deg": 83.4, "fov_declared_deg": 83.4, "fov_diff_deg": 0.0},
}

# Every ingested patent seed must carry a passing cross-validation verdict.
_patent_ids = [
    a["filename"].removesuffix(".zmx")
    for a in ZMX_AMMO
    if a["filename"].startswith("US") and not a["filename"].startswith("US-")
]
assert set(_patent_ids) == set(PATENT_PROVENANCE), (
    f"patent seeds and provenance out of sync: "
    f"{set(_patent_ids) ^ set(PATENT_PROVENANCE)}"
)
assert all(p["verdict"] == "PASS" for p in PATENT_PROVENANCE.values()), (
    "every ingested patent seed must pass full-embodiment cross-validation"
)
