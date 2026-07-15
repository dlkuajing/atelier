from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from pathlib import Path

import pytest

from app.core.engines.zmx_writer import write_zmx_from_codev_readout
from app.core.zmx_ingest import load_normalized_zmx
from scripts import patent_to_zmx
from scripts.patent_to_zmx import (
    PatentParseError,
    build_readout_from_prescription,
    parse_patent_prescription,
    parse_patent_prescriptions,
    prescription_fingerprint,
    write_patent_zmx,
)


def test_load_patent_pool_filters_only_patents_with_normalized_ids(tmp_path: Path) -> None:
    pool_path = tmp_path / "uspto-smartphone-batch1.jsonl"
    records = [
        {"id": "US-10101561-B2", "title": "selected"},
        {"id": "US-11099361-B2", "title": "not selected"},
    ]
    pool_path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    candidates = patent_to_zmx.load_patent_pool(tmp_path, only_patents={"us10101561b2"})

    assert [candidate.patent_id for candidate in candidates] == ["US-10101561-B2"]


def test_load_patent_pool_without_filter_keeps_existing_behavior(tmp_path: Path) -> None:
    pool_path = tmp_path / "uspto-smartphone-batch1.jsonl"
    pool_path.write_text(
        json.dumps({"id": "US-10101561-B2", "title": "candidate"}) + "\n",
        encoding="utf-8",
    )

    candidates = patent_to_zmx.load_patent_pool(tmp_path)

    assert [candidate.patent_id for candidate in candidates] == ["US-10101561-B2"]


PRESCRIPTION_TEXT = """
TABLE-US-00001 TABLE 1A 1st Embodiment f = 12.99 mm, Fno = 1.71,
HFOV = 20.0 deg. Surface # Curvature Radius Thickness Material Index Abbe #
Focal Length 0 Object Infinity Infinity 1 Ape. Stop Plano 0.890
2 Lens 1 43.6006 (SPH) 2.486 Glass 1.835 42.7 55.43
3 Lens 2 17.6926 (ASP) 1.752 Plastic 1.541 47.2 -55.65
4 10.7541 (ASP) 0.668 5 Image Plano -- Note: Reference wavelength is
587.6 nm (d-line). TABLE-US-00002 TABLE 1B Aspheric Coefficients
Surface # 3 4 k= -2.80433E+01 -1.30575E+00
A4= -5.6789E-05 -3.8862E-04 A6= -2.7992E-05 -2.0211E-05
A16= 1.0E-10 -- [0141] In Table 1B, k represents the conic coefficient.
"""

SECOND_PRESCRIPTION_TEXT = PRESCRIPTION_TEXT.replace(
    "1st Embodiment f = 12.99 mm, Fno = 1.71,\nHFOV = 20.0 deg.",
    "EXAMPLE 2: effective focal length = 13.50 mm; F/# = 1.80; Half Angle of View = 21.0 degrees.",
).replace("-5.6789E-05", "-6.6789E-05", 1)

MULTI_EMBODIMENT_TEXT = PRESCRIPTION_TEXT + "\n" + SECOND_PRESCRIPTION_TEXT

PREFERRED_EMBODIMENT_TEXT = PRESCRIPTION_TEXT.replace(
    "1st Embodiment",
    "Optical data of this preferred embodiment",
)
OUTER_SIDE_OBJECT_TEXT = PRESCRIPTION_TEXT.replace(
    "0 Object Infinity Infinity",
    "0 Outer-Side Plano Infinity Conjugate Surface",
)
M_SIDE_OBJECT_TEXT = PRESCRIPTION_TEXT.replace(
    "0 Object Infinity Infinity",
    "0 m-side surface Plano Infinity",
)

XASPHERE_TEXT = PRESCRIPTION_TEXT.replace(
    "A16= 1.0E-10 --",
    "A16= 1.0E-10 -- A18= 2.5E-12 -3.5E-12 "
    "A20= 4.5E-14 -5.5E-14 A22= 6.5E-12 -7.5E-12 "
    "A24= 8.5E-12 -9.5E-12 A26= 1.5E-12 -2.5E-12 "
    "A28= 3.5E-12 -4.5E-12 A30= 5.5E-12 -6.5E-12",
)

THREE_COLUMN_MATERIAL_TEXT = PRESCRIPTION_TEXT.replace(
    "Glass 1.835 42.7 55.43",
    "Plastic 1.634 1.660 20.4",
    1,
).replace(
    "Plastic 1.541 47.2 -55.65",
    "Glass 1.508 1.517 64.2",
    1,
)

LARGAN_COMPONENT_TEXT = """
TABLE-US-00001 TABLE 1 1st Embodiment f = 2.89 mm, Fno = 2.30,
HFOV = 38.0 deg. Surface # Curvature Radius Thickness Material Index Abbe #
Focal Length 0 Object Plano Infinity 1 Ape. Plano -0.075 Stop
2 Lens 1 1.741 ASP 0.334 Plastic 1.536 58.3 7.92
3 2.758 ASP 0.105 4 Lens 2 1.865 ASP 0.295 Plastic 1.639
18,4 5.61 5 IR-cut Piano 0.110 Glass 1.517 64.2 -- filter
6 Prism Plano 0.365 Glass 1.517 64.2 -- 7 Image Plano --
TABLE-US-00002 TABLE 2 Aspheric Coefficients Surface # 2 3 4
k= -1.0 2.0 -3.0 A4= -1.0E-02 -2.0E-02 -3.0E-02
A22= 1.0E-12 -2.0E-12 3.0E-12 A30= 4.0E-15 -5.0E-15 6.0E-15
-- [0001] In Table 2, k represents the conic coefficient.
"""

FUJIFILM_TABLE_TEXT = """
TABLE-US-00001 TABLE 1 Example 1 Sn R D Nd νd θgF SG
1 10.0000 1.0000 1.50000 50.00 0.54000 2.50
2 -20.0000 0.5000
3(St) Infinity 0.2000
4 30.0000 1.1000 1.60000 40.00 0.56000 3.00
5 -40.0000 2.0000
TABLE-US-00002 TABLE 2 Example 1 f 8.00 Bf 2.00 FNo. 2.80 2ω[°] 50.00
TABLE-US-00003 TABLE 3 Example 2 Sn R D Nd νd θgF SG ED
1 9.0000 1.1000 1.51000 52.00 0.54000 2.50
*2 -18.0000 0.6000 1.61000 42.00 0.56000 3.00 4.20
*3 25.0000 2.1000 4.30
TABLE-US-00004 TABLE 4 Example 2 f 9.00 Bf 2.10 FNo. 3.10 2ω[°] 40.00
TABLE-US-00005 TABLE 5 Example 2 Sn 2 3 KA 1.0000000E+00 -1.0000000E+00
A4 1.0000000E-06 2.0000000E-06 A6 -3.0000000E-09 -4.0000000E-09
A8 5.0000000E-12 6.0000000E-12 A10 -7.0000000E-15 -8.0000000E-15
[0001] trailing narrative.
"""

FUJIFILM_INLINE_ODD_ASPHERE_TEXT = """
TABLE-US-00001 TABLE 1 Example 1 Basic Lens Data f = 14.47, BF = 13.30,
2ω = 89.0, FNo. = 2.88 Si Ri Di Ndj νdj
1 45.470 1.28 1.57135 53.0
2 13.366 5.87
*3 34.115 2.50 1.58312 59.4
*4 8.652 4.36
5 Infinity 0.00
TABLE-US-00002 TABLE 2 Example 1 Aspherical Surface Coefficient Si 3 4
K 0.0000000E+00 0.0000000E+00
A3 1.0465349E-03 -2.0064589E-04
A4 -1.4397107E-03 8.7627361E-04
[0001] trailing narrative.
"""

FOLDED_ZOOM_TEXT = """
TABLE-US-00001 TABLE 1 Optical lens system 600 Aperture Curvature Radius Focal
Surface # Comment Type Radius Thickness (D/2) Material Index Abbe # Length
1 Lens 1 ASP 10.000 1.000 2.000 Plastic 1.54 55.93 8.00
2 -10.000 See Table 2 1.900
3 Lens 2 - Stop ASP 8.000 0.800 1.800 Plastic 1.64 23.52 -6.00
4 -8.000 See Table 2 1.700
5 Image Plano Infinity -- -- EFL = see Table 2, F number = see Table 2,
HFOV = see Table 2.
TABLE-US-00002 TABLE 2 EFL = 9.61 EFL = 24.03
Surface 2 0.911 4.599 Surface 4 4.251 0.563
F/# 2.36 4.64 HFOV [deg] 13.97 6.06
TABLE-US-00003 TABLE 3 Aspheric Coefficients Surface # Conic A4 A6
1 0 -3.70E-04 -5.26E-06
2 0 -2.58E-03 4.80E-04
3 0 -2.11E-03 4.44E-04
4 0 4.81E-04 -2.21E-05
[0001] trailing narrative.
"""

FOLDED_ZOOM_DAMAGED_QTYP_TEXT = """
TABLE-US-00001 TABLE 1 Optical lens system 800 Group Lens Surface Type
R [mm] T [mm] D [mm] Nd Vd Focal Length [mm]
Object S0 Flat Infinity Infinity G1 L1
S.sub.1 QTYP 5.000 1.000 2.000 1.54 55.93 8.00
L2 S.sub.1 QTYP -5.000 0.500 1.900
L3 S.sub.3 QTYP 8.000 See Table 2 1.800
Image sensor S4
TABLE-US-00002 TABLE 2 Configuration 1 Configuration 2
EFL = 10 [mm] EFL = 20 [mm] T [mm]
S.sub.3 1.000 2.000 F/# 3.00 4.00 HFOV 15.00 7.50
"""

APPLE_EXEMPLARY_TEXT = """
TABLE-US-00001 TABLE 1A Optical data for a first exemplary embodiment shown in
FIG. 1 f = 0.5639 mm, Fno = 2.2, HFOV = 37.5 deg, TTL = 1.059 mm
S.sub.i Component R.sub.i Shape D.sub.i Material N.sub.d V.sub.d f.sub.l
0 Object plane INF FLT INF
1 L.sub.1 INF FLT 0.079548 Plastic 1.535 56.1 2.896
2 -1.55332 ASP 0.100000
3 L.sub.2 -0.52395 ASP 0.244898 Plastic 1.535 56.1 2.305
4 -0.42801 ASP 0.100000
5 L.sub.3 0.30738 ASP 0.322474 Plastic 1.535 56.1 1.135
6 0.39315 ASP 0.101956
7 IR filter INF FLT 0.110000 Glass 1.517 64.2
8 INF FLT 0.100000
9 Image plane INF FLT
TABLE-US-00002 TABLE 1B Aspheric coefficients for the first exemplary embodiment
S.sub.i K A B C
2 -95.705155 0.311858E+01 -0.162181E+02 0.852881E+03
3 5.577920 0.706073E+01 -0.113314E+03 -0.796803E+02
4 1.226938 -0.707465E+01 0.492155E+02 -0.121150E+03
5 -2.839956 0.103387E+01 -0.475271E+01 -0.221756E+02
6 -0.713670 -0.642737E-03 -0.364121E+02 -0.142529E+02
S.sub.i D E F
2 0.399015E+04 0.484899E+04 -0.310112E+04
3 0.809371E+04 0.478545E+04
4 -0.229816E+04 -0.809035E+03
5 0.386713E+02 0.211717E+02
6 0.242787E+02 0.114039E+04
"""

SAMSUNG_WIDE_FOV_SURFACE_ROWS = """Surface Radius of Thickness/ Refractive Abbe Effective
No. Component Curvature Distance Index Number Radius
S1 First Lens 27.2287 0.6000 1.777 49.6 4.692
S2 4.5548 4.9502 3.542
S3 Second Lens -3.3431 1.6907 1.601 30.4 3.003
S4 -6.6665 0.1000 3.269
S5 Third Lens 6.2933 2.1939 1.618 26.3 3.423
S6 -36.9517 0.1906 3.208
S7 Fourth Lens -24.3693 1.3176 1.623 60.3 3.186
S8 -12.5741 0.0000 3.024
S9 Stop Infinity 0.3000 2.865
S10 Fifth Lens 8.2508 2.8899 1.618 60.6 3.025
S11 Sixth Lens -3.9900 0.6000 1.749 28.1 2.984
S12 6.6444 0.1000 3.105
S13 Seventh Lens 7.7338 1.6902 1.650 55.5 3.132
S14 -10.2819 2.7218 3.186
S15 Filter Infinity 0.4000 1.519 64.2 3.432
S16 Infinity 0.5500 3.454
S17 Cover Glass Infinity 0.4000 1.519 64.2 3.498
S18 Infinity 3.8036 3.519
S19 Imaging Plane Infinity 0.0015 3.827"""

SAMSUNG_WIDE_FOV_COEFFICIENT_ROWS = """Surface No. S3 S4 S5 S6 S13 S14
k -1.26022E+00 -2.71647E+00 -2.04937E-01 -5.87526E+01 0.00000E+00 0.00000E+00
A 2.59351E-03 2.46173E-03 -1.65008E-05 -1.57045E-04 2.44654E-04 1.10893E-03
B -1.10782E-04 -2.47393E-05 2.58956E-05 6.35081E-05 2.80354E-05 3.28342E-05
C 5.54083E-07 -6.16987E-07 7.87004E-08 -1.02142E-06 -7.33986E-07 2.71772E-07
D 0 0 0 0 4.00308E-08 4.64438E-08
E 0 0 0 0 0 0
F 0 0 0 0 0 0
G 0 0 0 0 0 0
H 0 0 0 0 0 0
J 0 0 0 0 0 0"""

SAMSUNG_WIDE_FOV_METADATA = """TABLE-US-00021 TABLE 21
Optical First Second Third Fourth Fifth Property
Embodiment Embodiment Embodiment Embodiment Embodiment
f 4.5301 4.5625 4.5030 4.4610 4.4950
f-number 1.8718 1.8714 1.8000 1.8000 1.8000
HFOV 82.0000 82.0000 82.0000 82.0000 81.9900
Optical Sixth Seventh Eighth Ninth Tenth Property
Embodiment Embodiment Embodiment Embodiment Embodiment
f 4.4764 4.4741 4.4642 4.4856 4.5171
f-number 1.8122 1.7800 1.7690 1.7690 1.6944
HFOV 82.0000 82.0000 82.0000 82.0000 82.0000"""


def _samsung_wide_fov_fixture() -> str:
    ordinals = (
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
    )
    parts = [
        "HFOV is a field of view of the imaging plane in a horizontal direction "
        "expressed in degrees. A, B, C, D, E, F, G, H, and J are aspherical constants."
    ]
    for embodiment_number, ordinal in enumerate(ordinals, start=1):
        surface_table = embodiment_number * 2 - 1
        coefficient_table = embodiment_number * 2
        parts.append(
            f"[{embodiment_number:04d}] Tables {surface_table} and {coefficient_table} "
            "below list the lens properties and aspherical values of the "
            f"{ordinal} embodiment of the imaging lens system. "
            f"TABLE-US-{surface_table:05d} TABLE {surface_table} "
            f"{SAMSUNG_WIDE_FOV_SURFACE_ROWS} "
            f"TABLE-US-{coefficient_table:05d} TABLE {coefficient_table} "
            f"{SAMSUNG_WIDE_FOV_COEFFICIENT_ROWS}"
        )
    parts.append(SAMSUNG_WIDE_FOV_METADATA)
    return " ".join(parts)


SAMSUNG_WIDE_FOV_TEXT = _samsung_wide_fov_fixture()


MOBILE_IMAGING_LENS_EARLY_SURFACES = """Infinity Infinity
L1 1* 4.500 1.200 1.5348 55.7 f1 = 7.100 2* -22.000 0.050
ST 3 Infinity -0.020
L2 4* 3.900 0.350 1.6608 20.4 f2 = -12.300 5* 2.500 0.340
L3 6* 35.000 0.820 1.5348 55.7 f3 = 13.500 7* -9.000 0.050
L4 8* 4.600 0.520 1.5348 55.7 f4 = -47.000 9* 3.700 0.830
L5 10* -60.000 0.590 1.5348 55.7 f5 = -27.000 11* 19.000 0.260
L6 12* -32.000 0.720 1.5348 55.7 f6 = 6.900 13* -3.300 0.100
L7 14* -29.000 0.970 1.6392 23.5 f7 = -36.000 15* 116.000 0.480
L8 16* 100.000 0.830 1.5348 55.7 f8 = -6.700 17* 3.400 0.500
18 Infinity 0.210 1.5168 64.2 19 Infinity 0.800 (IM) Infinity"""

MOBILE_IMAGING_LENS_LATE_SURFACES = """Infinity Infinity
ST 1 Infinity -0.380
L1 2* 2.800 0.740 1.5445 56.4 f1 = 5.900 3* 20.000 0.030
L2 4* 4.100 0.370 1.6707 19.2 f2 = -12.900 5* 2.600 0.110
L3 6* 5.400 0.560 1.5445 56.4 f3 = 16.700 7* 12.900 0.560
L4 8* -16.000 0.420 1.5445 56.4 f4 = -69.000 9* -28.000 0.300
L5 10* -7.200 0.400 1.6707 19.2 f5 = -14.400 11* -29.000 0.250
L6 12* -12.300 0.620 1.5880 28.8 f6 = 12.400 13* -4.600 0.030
L7 14* 4.700 0.650 1.5348 55.7 f7 = -89.000 15* 4.000 0.340
L8 16* 4.200 1.040 1.5348 55.7 f8 = -14.200 17* 2.400 1.000
18 Infinity 0.210 1.5168 64.2 19 Infinity 0.470 (IM) Infinity"""


def _mobile_imaging_lens_fixture() -> str:
    parts = ["ω represents a half field of view."]
    for example_number in range(1, 13):
        surface_table = example_number * 2 - 1
        coefficient_table = example_number * 2
        late = example_number >= 7
        surface_rows = (
            MOBILE_IMAGING_LENS_LATE_SURFACES if late else MOBILE_IMAGING_LENS_EARLY_SURFACES
        )
        f, fno, hfov = (7.05, 2.1, 35.2) if late else (7.71, 1.5, 33.4)
        parts.append(
            f"TABLE-US-{surface_table:05d} TABLE {surface_table} "
            f"f = {f:.2f} mm Fno = {fno:.1f} ω = {hfov:.1f}° "
            f"i r d n d νd [mm] {surface_rows}"
        )
        if late:
            first_rows = " ".join(
                f"{surface} 0.000E+00 1.000E-03 -2.000E-04 3.000E-05 -4.000E-06"
                for surface in range(2, 18)
            )
            second_rows = " ".join(
                f"{surface} 5.000E-07 -6.000E-08 7.000E-09 -8.000E-10 9.000E-11"
                for surface in range(2, 18)
            )
            coefficient_body = f"i k A4 A6 A8 A10 {first_rows} i A12 A14 A16 A18 A20 {second_rows}"
        else:
            surface_indices = (1, 2, *range(4, 18))
            rows = " ".join(
                f"{surface} 0.000E+00 1.000E-03 -2.000E-04 1.000E-04 "
                "-4.000E-05 5.000E-06 -6.000E-07 7.000E-08"
                for surface in surface_indices
            )
            index_header = "" if example_number == 5 else "i "
            coefficient_body = f"{index_header}k A4 A6 A8 A10 A12 A14 A16 {rows}"
        parts.append(
            f"TABLE-US-{coefficient_table:05d} TABLE {coefficient_table} "
            f"Aspheric Surface Data: {coefficient_body}"
        )
    return " ".join(parts)


MOBILE_IMAGING_LENS_TEXT = _mobile_imaging_lens_fixture()


KANTATSU_NINE_LENS_SURFACES = """L1 1*(ST) 2.400 0.500 1.5443 55.9 f1 = 40.000
2* 2.300 0.080 L2 3* 2.500 0.600 1.5443 55.9 f2 = 4.600 4* 200.000 0.030
L3 5* 8.000 0.250 1.6707 19.2 f3 = -9.800 6* 3.500 0.400
L4 7* 13.000 0.420 1.5443 55.9 f4 = 70.000 8* 20.000 0.040
L5 9* 25.000 0.320 1.5443 55.9 f5 = 24.000 10* -30.000 0.390
L6 11* -4.500 0.250 1.5443 55.9 f6 = 90.000 12* -4.200 0.050
L7 13* -20.000 0.600 1.5443 55.9 f7 = -100.000 14* -30.000 0.030
L8 15* 6.000 0.600 1.6707 19.2 f8 = 100.000 16* 6.000 0.350
L9 17* 3.500 0.830 1.5443 55.9 f9 = -10.000 18* 2.000 0.350
19 Infinity 0.210 1.5168 64.2 20 Infinity 0.660 (IM) Infinity"""


def _kantatsu_nine_lens_fixture() -> str:
    parts = [
        "f represents a focal length of the whole lens system, Fno represents an F-number, "
        "and ω represents a half angle of view."
    ]
    for example_number in range(1, 14):
        surface_table = example_number * 2 - 1
        coefficient_table = example_number * 2
        surface_rows = KANTATSU_NINE_LENS_SURFACES
        if example_number == 4:
            surface_rows = surface_rows.replace(
                "L9 17* 3.500 0.830",
                "L9 17* 3.500 0 830",
                1,
            )
        meta = "f = 6.71 mm Fno = 1.9 ω = 39.5°"
        if example_number <= 6:
            surface_body = (
                f"Basic Lens Data r d i Infinity Infinity n d ν d [mm] {surface_rows} {meta}"
            )
        else:
            surface_body = (
                f"Basic Lens Data {meta} i r d nd νd [nm] Infinity Infinity {surface_rows}"
            )
        parts.append(
            f"Numerical Data Example {example_number} [{example_number:04d}] "
            f"TABLE-US-{surface_table:05d} TABLE {surface_table} {surface_body}"
        )
        rows = " ".join(
            f"{surface} 0.000E+00 1.000E-03 -2.000E-04 3.000E-05 "
            "-4.000E-06 5.000E-07 -6.000E-08 7.000E-09"
            for surface in range(1, 19)
        )
        parts.append(
            f"TABLE-US-{coefficient_table:05d} TABLE {coefficient_table} "
            "Aspherical surface data i k A4 A6 A8 A10 A12 A14 A16 "
            f"{rows}"
        )
    return " ".join(parts)


KANTATSU_NINE_LENS_TEXT = _kantatsu_nine_lens_fixture()


def _kantatsu_nine_lens_pretable_fixture() -> str:
    parts = [
        "f represents a focal length of the whole lens system, Fno represents an F-number, "
        "and ω represents a half angle of view."
    ]
    surface_rows = KANTATSU_NINE_LENS_SURFACES.replace("1*(ST)", "1 * (ST)", 1).replace(
        "(IM)", "(1M)", 1
    )
    for example_number in range(1, 11):
        surface_table = example_number * 2 - 1
        coefficient_table = example_number * 2
        parts.append(
            f"Numerical Data Example {example_number} Basic Lens Data "
            f"[{example_number:04d}] TABLE-US-{surface_table:05d} TABLE {surface_table} "
            "f = 5.69 mm Fno = 1.9 ω = 39.3° i r d n d ν d [mm] "
            f"{surface_rows}"
        )
        rows = " ".join(
            f"{surface} 0.000E+00 1.000E-03 -2.000E-04 3.000E-05 "
            "-4.000E-06 5.000E-07 -6.000E-08 7.000E-09"
            for surface in range(1, 19)
        )
        parts.append(
            f"TABLE-US-{coefficient_table:05d} TABLE {coefficient_table} "
            "Aspherical surface data i k A4 A6 A8 A10 A12 A14 A16 "
            f"{rows}"
        )
    return " ".join(parts)


KANTATSU_NINE_LENS_PRETABLE_TEXT = _kantatsu_nine_lens_pretable_fixture()


def _folded_macro_tele_surface_table(
    system: int,
    *,
    table_number: int,
    lens_count: int,
    focal_label: str,
) -> str:
    rows = ["1 A.S plano Infinity -0.500 1.500"]
    for lens_number in range(1, lens_count + 1):
        first_surface = lens_number * 2
        rows.extend(
            [
                f"{first_surface} Lens {lens_number} ASP "
                f"{5.0 + lens_number:.3f} 0.700 2.000 Plastic 1.5443 55.9 5.000",
                f"{first_surface + 1} {-6.0 - lens_number:.3f} 0.100 2.000",
            ]
        )
    filter_front = lens_count * 2 + 2
    rows.extend(
        [
            f"{filter_front} Filter plano Infinity 0.210 -- Glass 1.5168 64.2",
            f"{filter_front + 1} Infinity 0.500 --",
            f"{filter_front + 2} Image plano Infinity 0.000 -- ({table_number})",
        ]
    )
    system_label = "Lens system" if system != 290 else "Embodiment"
    return (
        f"TABLE-US-{table_number:05d} TABLE {table_number} {system_label} {system} "
        f"{focal_label} = {12.0 + system / 100:.2f} mm, F number = 2.0, "
        "Half FOV = 10.0 deg. Aperture Curvature Radius Focal Surface # Comment "
        "Type Radius Thickness (D/2) Material Index Abbe # Length " + " ".join(rows)
    )


def _folded_macro_tele_coefficient_table(
    *,
    table_number: int,
    lens_count: int,
) -> str:
    rows = " ".join(
        f"{surface} 0.0 1.0E-03 -2.0E-04 3.0E-05 -4.0E-06"
        for surface in range(2, lens_count * 2 + 2)
    )
    return (
        f"TABLE-US-{table_number:05d} TABLE {table_number} "
        f"Aspheric Coefficients Surface # Conic A4 A6 A8 A10 {rows}"
    )


def _folded_macro_tele_object_state_table(
    system: int,
    *,
    table_number: int,
    count: int,
) -> str:
    rows = ["Infinity 0.500 10.0 0.0"]
    rows.extend(
        f"{1000 - index * 50} {0.5 + index / 100:.2f} {10.0 - index / 2:.1f} {-index / 100:.2f}"
        for index in range(1, count)
    )
    system_label = "Lens system" if system != 290 else "Embodiment"
    return (
        f"TABLE-US-{table_number:05d} TABLE {table_number} {system_label} {system} "
        "Variation of lens properties with object distance Object Distance BFL HFOV "
        "[mm] [mm] [deg] Magnification " + " ".join(rows) + f" ({table_number})"
    )


def _folded_macro_tele_fixture() -> str:
    tables: dict[int, str] = {}
    for system, surface_table, coefficient_table, state_table, lens_count, count in (
        (200, 1, 2, 3, 6, 8),
        (220, 5, 6, 7, 7, 8),
        (230, 9, 10, 11, 8, 9),
        (290, 19, 20, 21, 8, 9),
    ):
        focal_label = "EFL" if system != 290 else "F"
        tables[surface_table] = _folded_macro_tele_surface_table(
            system,
            table_number=surface_table,
            lens_count=lens_count,
            focal_label=focal_label,
        )
        tables[coefficient_table] = _folded_macro_tele_coefficient_table(
            table_number=coefficient_table,
            lens_count=lens_count,
        )
        tables[state_table] = _folded_macro_tele_object_state_table(
            system,
            table_number=state_table,
            count=count,
        )
    tables[13] = _folded_macro_tele_surface_table(
        240,
        table_number=13,
        lens_count=6,
        focal_label="EFL",
    )
    tables[14] = _folded_macro_tele_coefficient_table(table_number=14, lens_count=6)
    tables[15] = (
        "TABLE-US-00015 TABLE 15 Lens system 240 Variation of surface thicknesses "
        "Surface # Config. A Config. B Config. C 0 10000000000 1000 100 "
        "5 0.100 0.200 0.300 13 0.400 0.500 0.600 (15)"
    )
    tables[16] = (
        "TABLE-US-00016 TABLE 16 Lens system 240 Config. # HFOV Magnification "
        "A 10.0 deg 0.0 B 8.0 deg -0.01 C 6.0 deg -0.02 (16)"
    )
    for table_number in (4, 8, 12, 17, 18, 22):
        tables[table_number] = (
            f"TABLE-US-{table_number:05d} TABLE {table_number} "
            f"Non-prescription auxiliary data ({table_number})"
        )
    return "Half FOV (HFOV) are given. " + " ".join(
        tables[table_number] for table_number in range(1, 23)
    )


FOLDED_MACRO_TELE_TEXT = _folded_macro_tele_fixture()


SUNNY_OBJ_STO_TEXT = """
TABLE-US-00001 TABLE 1 Material Surface Radius of Refractive Conic
number Surface type curvature Thickness index Abbe number coefficient
OBJ spherical infinite infinite STO spherical infinite -0.3784
S1 aspheric 2.0348 0.6638 1.55 56.1 -0.1992
S2 aspheric 9.8057 0.1729 17.3022
S3 aspheric 13.4651 0.2785 1.67 19.2 83.5117
S4 aspheric 4.2040 0.4639 8.1278
S5 spherical infinite 0.2963 1.52 64.2
S6 spherical infinite 0.3417 S7 spherical infinite (61) narrative follows.
TABLE-US-00002 TABLE 2 Surface number A4 A6 A8
S1 4.3347E-03 1.0409E-03 9.0835E-03
S2 -2.9093E-02 2.3320E-02 -4.1072E-02
Surface number A10 A12
S1 -3.4351E-02 6.4565E-02
S2 1.1577E-01 -2.3430E-01 (63) narrative follows.
TABLE-US-00003 TABLE 3 f1(mm) 4.57 f(mm) 5.04 f2(mm) -9.13 TTL(mm) 6.14
f3(mm) 16.02 ImgH(mm) 4.75 f4(mm) 6.17 Semi-FOV(°) 42.2 f5(mm) -3.45
f/EPD 2.02 (67) FIG. 2 A illustrates a longitudinal aberration curve.
TABLE-US-00004 TABLE 4 Material Surface Radius of Refractive Conic
number Surface type curvature Thickness index Abbe number coefficient
OBJ spherical infinite infinite STO spherical infinite -0.4000
S1 aspheric 2.1000 0.7000 1.55 56.1 -0.2000
S2 aspheric 9.9000 0.1800 17.0000
S3 aspheric 13.5000 0.2800 1.67 19.2 83.0000
S4 aspheric 4.3000 0.4700 8.0000
S5 spherical infinite 0.3000 1.52 64.2
S6 spherical infinite 0.3500 S7 spherical infinite (71) narrative follows.
TABLE-US-00005 TABLE 5 Surface number A4 A6 A8
S1 4.4000E-03 1.1000E-03 9.1000E-03
S2 -3.0000E-02 2.4000E-02 -4.2000E-02 (72) narrative follows.
TABLE-US-00006 TABLE 6 f1(mm) 4.60 f(mm) 5.08 f2(mm) -9.20 TTL(mm) 6.20
f3(mm) 16.10 ImgH(mm) 4.75 f4(mm) 6.20 Semi-FOV(°) 41.9 f5(mm) -3.50
f/EPD 2.03 (73) trailing narrative.
"""

SUNNY_NARRATIVE_META_TEXT = """
TABLE-US-00001 TABLE 1 Material Surface Surface Radius of Thickness/
Refractive Abbe Focal Conic number type curvature Distance index number
length coefficient OBJ Spherical Infinite Infinite STO Spherical Infinite
-0.6200 S1 Aspheric 1.9014 0.7452 1.56 58.4 4.96 0.2654
S2 Aspheric 5.1228 0.1082 -0.8412
S3 Aspheric 12.1489 0.2500 1.67 20.4 -11.13 6.2245
S4 Aspheric 4.5711 0.1070 0.6997
S5 Spherical Infinite 0.2100 1.52 64.2
S6 Spherical Infinite 0.1638 S7 Spherical Infinite (52) In this example,
a total effective focal length f of the optical imaging lens assembly
satisfies f=4.26 mm, half of a maximal field-of-view Semi-FOV of the
optical imaging lens assembly satisfies Semi-FOV=43.7°, and an aperture
value Fno of the optical imaging lens assembly satisfies Fno=1.48.
(53) In example 1, the object-side surface and the image-side surface of
any one of the lenses are aspheric. Table 2 below shows coefficients.
TABLE-US-00002 TABLE 2 Surface number A4 A6
S1 4.3347E-03 1.0409E-03
S2 -2.9093E-02 2.3320E-02 (54) trailing narrative.
"""

ABILITY_OPTO_TEXT = """
first embodiment of the invention. The parameters of the lenses of the
first embodiment are listed in Table 1 and Table 2.
TABLE-US-00001 TABLE 1 f = 3.03968 mm; f/HEP = 1.6; HAF = 50.0010 deg
Focal Thickness Refractive Abbe length Surface Radius of curvature (mm)
(mm) Material index number (mm) 0 Object plane infinity
1 1.sup.st lens 4.01438621 0.750 plastic 1.514 56.80 -9.24529
2 2.040696375 3.602 3 Aperture plane -0.412
4 2.sup.nd lens 2.45222384 0.895 plastic 1.565 58.00 6.33819
5 6.705898264 0.561
6 3 .sup.rd lens 16.39663088 0.932 plastic 1.565 58.00 7.93877
7 -6.073735083 0.656
8 Infrared rays 1E+18 0.200 BK7_SCH 1.517 64.20 filter
9 1E+18 0.412 10 Image plane 1E+18 0 Reference wavelength: 555 nm.
TABLE-US-00002 TABLE 2 Coefficients of the aspheric surfaces
Surface 1 2 4 k -1.882119E-01 -1.927558E+00 -6.483417E+00
A4 7.686381E-04 3.070422E-02 5.439775E-02
A6 4.630306E-04 -3.565153E-03 -7.980567E-03
Surface 5 6 7 k 1.766123E+01 -5.000000E+01 -3.544648E+01
A4 7.241691E-03 -2.985209E-02 -6.315366E-02
A6 -8.359563E-03 -7.175713E-03 6.038040E-03
(111) The detail parameters of the first embodiment are listed in Table 1.
"""

ABILITY_CORRUPT_EXPONENT_TEXT = ABILITY_OPTO_TEXT.replace(
    "A6 4.630306E-04 -3.565153E-03 -7.980567E-03",
    "A6 4.630306 IE-04 -3.565153E-03 -7.980567E-03",
)

AAC_RAYTECH_COMPACT_TEXT = """
TABLE-US-00001 TABLE 1 R d nd νd S1 Infinity d0= -0.460
R1 5.316 d1= 1.600 nd1 1.4959 ν1 81.65
R2 -24.225 d2= 0.030
R3 626.915 d3= 0.412 nd2 1.6700 ν2 19.39
R4 34.369 d4= 0.092
R5 3.324 d5= 0.853 nd3 1.5444 ν3 55.82
R6 2.183 d6= 1.500
R7 Infinity d7= 6.982 nd4 1.5891 ν4 61.25
R8 Infinity d8= 6.500
R9 Infinity d9= 0.210 ndg 1.5168 νg 64.17
R10 Infinity d10= 0.807 [0076] narrative definitions follow.
TABLE-US-00002 TABLE 2 Conic constant Aspheric coefficient k A4 A6 A8 A10 A12
R1 -9.5839E-01 3.0795E-03 -5.0356E-04 8.2246E-04 -8.7499E-04 5.7935E-04
R2 5.5038E+00 2.5011E-02 -7.0471E-03 -1.4091E-02 2.3707E-02 -1.7833E-02
Conic constant Aspheric coefficient k A14 A16 A18 A20 A22
R1 -9.5839E-01 -2.6080E-04 8.2927E-05 -1.8914E-05 3.1033E-06 -3.6308E-07
R2 5.5038E+00 8.1728E-03 -2.5055E-03 5.3547E-04 -8.1113E-05 8.6956E-06
TABLE-US-00003 TABLE 3 R d nd vd S1 Infinity d0= -1.012
R1 3.982 d1= 1.297 nd1 1.4959 vd1 81.64
R2 36.568 d2= 0.036
TABLE-US-00004 TABLE 4 Conic constant Aspheric coefficient k A4 A6
R1 -5.3865E-01 3.3646E-03 -9.3315E-04
TABLE-US-00005 TABLE 5 Parameters 1.sup.st 2.sup.nd and conditions
D/TTL 0.16 0.12
f 18.269 16.282
Fno 2.871 2.871
TTL 18.986 17.746
IH 3.575 3.575
FOV 21.79° 24.47°
[0146] trailing narrative.
"""


def test_parse_patent_prescription_extracts_surface_and_asphere_fields() -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-EXAMPLE-A1")

    assert prescription.embodiment == "1st Embodiment"
    assert prescription.focal_length_mm == pytest.approx(12.99)
    assert prescription.f_number == pytest.approx(1.71)
    assert prescription.hfov_deg == pytest.approx(20.0)
    assert len(prescription.surfaces) == 5

    stop = prescription.surfaces[0]
    assert stop.index == 1
    assert stop.label == "Ape. Stop"
    assert stop.radius_mm == 0.0
    assert stop.thickness_mm == pytest.approx(0.890)

    first_lens = prescription.surfaces[1]
    assert first_lens.label == "Lens 1"
    assert first_lens.radius_mm == pytest.approx(43.6006)
    assert first_lens.nd == pytest.approx(1.835)
    assert first_lens.vd == pytest.approx(42.7)
    assert first_lens.surface_type == "SPH"

    asphere = prescription.surfaces[2]
    assert asphere.surface_type == "ASP"
    assert asphere.asphere_coefficients["K"] == pytest.approx(-28.0433)
    assert asphere.asphere_coefficients["A"] == pytest.approx(-5.6789e-5)
    assert asphere.asphere_coefficients["B"] == pytest.approx(-2.7992e-5)
    assert asphere.asphere_coefficients["G"] == pytest.approx(1.0e-10)

    image = prescription.surfaces[-1]
    assert image.label == "Image"
    assert image.thickness_mm == 0.0
    assert prescription.image_height_mm == pytest.approx(12.99 * math.tan(math.radians(20.0)))


def test_parse_patent_prescription_uses_d_line_columns_when_material_table_has_reference_index() -> (
    None
):
    prescription = parse_patent_prescription(
        THREE_COLUMN_MATERIAL_TEXT,
        patent_id="US-THREE-COLUMN-A1",
    )

    first_lens = prescription.surfaces[1]
    assert first_lens.nd == pytest.approx(1.660)
    assert first_lens.vd == pytest.approx(20.4)

    filter_surface = prescription.surfaces[2]
    assert filter_surface.nd == pytest.approx(1.517)
    assert filter_surface.vd == pytest.approx(64.2)


def test_parse_patent_prescription_rejects_unphysical_material_indices() -> None:
    text = PRESCRIPTION_TEXT.replace("Glass 1.835 42.7 55.43", "Glass 1.835 1.66", 1)

    with pytest.raises(PatentParseError, match="outside physical bounds"):
        parse_patent_prescription(text, patent_id="US-BAD-MATERIAL-A1")


def test_parse_patent_prescriptions_extracts_all_embodiments() -> None:
    prescriptions = parse_patent_prescriptions(
        MULTI_EMBODIMENT_TEXT,
        patent_id="US-MULTI-A1",
    )

    assert [prescription.embodiment for prescription in prescriptions] == [
        "1st Embodiment",
        "EXAMPLE 2",
    ]
    assert [prescription.focal_length_mm for prescription in prescriptions] == pytest.approx(
        [12.99, 13.50]
    )
    assert prescriptions[1].f_number == pytest.approx(1.80)
    assert prescriptions[1].hfov_deg == pytest.approx(21.0)
    assert prescriptions[0].surfaces[2].asphere_coefficients["A"] == pytest.approx(-5.6789e-5)
    assert prescriptions[1].surfaces[2].asphere_coefficients["A"] == pytest.approx(-6.6789e-5)


@pytest.mark.parametrize(
    "raw_text",
    (PREFERRED_EMBODIMENT_TEXT, OUTER_SIDE_OBJECT_TEXT, M_SIDE_OBJECT_TEXT),
)
def test_parse_primary_tables_accepts_published_label_and_object_row_variants(
    raw_text: str,
) -> None:
    prescription = parse_patent_prescription(raw_text, patent_id="US-PRIMARY-VARIANT-A1")

    assert prescription.focal_length_mm == pytest.approx(12.99)
    assert prescription.f_number == pytest.approx(1.71)
    assert prescription.hfov_deg == pytest.approx(20.0)
    assert len(prescription.surfaces) == 5


@pytest.mark.parametrize(
    ("published_label", "expected_label"),
    (
        ("IR-filter", "IR-filter"),
        ("RCS", "Image"),
        ("Inner-Side", "Image"),
    ),
)
def test_parse_primary_tables_accepts_published_filter_and_conjugate_labels(
    published_label: str,
    expected_label: str,
) -> None:
    raw_text = PRESCRIPTION_TEXT.replace("5 Image Plano --", f"5 {published_label} Plano --")

    prescription = parse_patent_prescription(raw_text, patent_id="US-PRIMARY-END-A1")

    assert prescription.surfaces[-1].label == expected_label


def test_parse_patent_prescriptions_skips_narrative_embodiment_references() -> None:
    text = (
        "The image capturing unit according to the 1st embodiment has f = 1.00 mm, "
        "Fno = 2.00, HFOV = 30.0 deg. The detailed optical data follow. " + PRESCRIPTION_TEXT
    )

    prescriptions = parse_patent_prescriptions(text, patent_id="US-NARRATIVE-A1")

    assert len(prescriptions) == 1
    assert prescriptions[0].embodiment == "1st Embodiment"
    assert prescriptions[0].focal_length_mm == pytest.approx(12.99)


@pytest.mark.parametrize(
    "meta_line",
    [
        "Embodiment 1 f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "First Embodiment f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "EXAMPLE 1 f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "Example No. 1: effective focal length: 12.99 mm; F/#: 1.71; Half Angle of View: 20.0 degrees.",
        "Ｅｍｂｏｄｉｍｅｎｔ １ ｆ = １２．９９ ｍｍ, Ｆｎｏ = １．７１, ＨＦＯＶ = ２０．０ ｄｅｇ.",
    ],
)
def test_parse_patent_prescription_accepts_nfkc_and_meta_variants(meta_line: str) -> None:
    text = re.sub(
        r"1st Embodiment f = 12\.99 mm, Fno = 1\.71,\s+HFOV = 20\.0 deg\.",
        meta_line,
        PRESCRIPTION_TEXT,
    )

    prescription = parse_patent_prescription(text, patent_id="US-VARIANT-A1")

    assert prescription.focal_length_mm == pytest.approx(12.99)
    assert prescription.f_number == pytest.approx(1.71)
    assert prescription.hfov_deg == pytest.approx(20.0)
    assert len(prescription.surfaces) == 5


def test_build_readout_from_patent_prescription_roundtrips_through_zmx_ingest(
    tmp_path: Path,
) -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-EXAMPLE-A1")
    readout = build_readout_from_prescription(prescription)

    output_path = write_zmx_from_codev_readout(readout, tmp_path / "patent.zmx")
    optic = load_normalized_zmx(output_path)
    efl = float(optic.paraxial.f2())

    assert math.isfinite(efl)
    assert abs(efl) > 1.0


def test_build_readout_does_not_use_ftan_image_height_for_surface_diameters() -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-EXAMPLE-A1")
    readout = build_readout_from_prescription(prescription)
    forbidden_global = prescription.image_height_mm * 1.1

    assert readout.surfaces
    assert all(
        surface.semi_diameter_mm != pytest.approx(forbidden_global) for surface in readout.surfaces
    )


def test_write_patent_zmx_persists_real_imh_and_real_ray_surface_diameters(
    tmp_path: Path,
) -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-EXAMPLE-A1")
    output_path = tmp_path / "patent.zmx"

    trace_audit = write_patent_zmx(prescription, output_path)
    zmx_text = output_path.read_text(encoding="ascii")
    optic = load_normalized_zmx(output_path)

    assert math.isfinite(float(optic.paraxial.f2()))
    assert trace_audit.real_image_height_mm > 0.0
    assert trace_audit.real_image_height_mm != pytest.approx(prescription.image_height_mm)
    assert "! ATELIER_REAL_IMH_MM" in zmx_text
    assert "! ATELIER_FTAN_IMH_SANITY_MM" in zmx_text
    assert "ATELIER_APERTURE_INTERPOLATED_SURFACES none" in zmx_text
    assert f"DIAM {prescription.image_height_mm * 1.1:.15g}" not in zmx_text


def test_write_patent_zmx_emits_xasphere_xdat_for_a18_a20(tmp_path: Path) -> None:
    prescription = parse_patent_prescription(XASPHERE_TEXT, patent_id="US-XASPHERE-A1")

    asphere = prescription.surfaces[2]
    assert asphere.asphere_coefficients["H"] == pytest.approx(2.5e-12)
    assert asphere.asphere_coefficients["J"] == pytest.approx(4.5e-14)
    assert asphere.asphere_coefficients["A22"] == pytest.approx(6.5e-12)
    assert asphere.asphere_coefficients["A30"] == pytest.approx(5.5e-12)

    output_path = tmp_path / "xasphere.zmx"
    write_patent_zmx(prescription, output_path)
    zmx_text = output_path.read_text(encoding="ascii")
    optic = load_normalized_zmx(output_path)

    assert math.isfinite(float(optic.paraxial.f2()))
    assert "TYPE XASPHERE" in zmx_text
    assert "XDAT 11 2.5e-12 0 0 1 0 0" in zmx_text
    assert "XDAT 12 4.5e-14 0 0 1 0 0" in zmx_text
    assert "XDAT 13 6.5e-12 0 0 1 0 0" in zmx_text
    assert "XDAT 17 5.5e-12 0 0 1 0 0" in zmx_text


def test_parse_patent_prescription_accepts_largan_component_rows() -> None:
    prescription = parse_patent_prescription(
        LARGAN_COMPONENT_TEXT,
        patent_id="US-LARGAN-FIXTURE-A1",
    )

    assert len(prescription.surfaces) == 7
    assert prescription.surfaces[0].label == "Ape."
    assert prescription.surfaces[0].radius_mm == 0.0
    assert prescription.surfaces[3].vd == pytest.approx(18.4)

    ir_cut = prescription.surfaces[4]
    assert ir_cut.label == "IR-cut"
    assert ir_cut.radius_mm == 0.0
    assert ir_cut.nd == pytest.approx(1.517)
    assert ir_cut.vd == pytest.approx(64.2)

    prism = prescription.surfaces[5]
    assert prism.label == "Prism"
    assert prism.radius_mm == 0.0
    assert prism.nd == pytest.approx(1.517)
    assert prism.vd == pytest.approx(64.2)

    assert prescription.surfaces[1].asphere_coefficients["A22"] == pytest.approx(1.0e-12)
    assert prescription.surfaces[1].asphere_coefficients["A30"] == pytest.approx(4.0e-15)


def test_parse_patent_prescriptions_accepts_fujifilm_table_pairs() -> None:
    prescriptions = parse_patent_prescriptions(
        FUJIFILM_TABLE_TEXT,
        patent_id="US-FUJIFILM-FIXTURE-A1",
    )

    assert [prescription.embodiment for prescription in prescriptions] == [
        "Example 1",
        "Example 2",
    ]

    first = prescriptions[0]
    assert first.focal_length_mm == pytest.approx(8.0)
    assert first.f_number == pytest.approx(2.8)
    assert first.hfov_deg == pytest.approx(25.0)
    assert len(first.surfaces) == 6
    assert first.surfaces[2].label == "Stop"
    assert first.surfaces[2].radius_mm == math.inf
    assert first.surfaces[-1].label == "Image"

    second = prescriptions[1]
    assert second.hfov_deg == pytest.approx(20.0)
    assert second.surfaces[1].surface_type == "ASP"
    assert second.surfaces[1].nd == pytest.approx(1.61)
    assert second.surfaces[1].vd == pytest.approx(42.0)
    assert second.surfaces[1].asphere_coefficients["K"] == pytest.approx(1.0)
    assert second.surfaces[1].asphere_coefficients["A"] == pytest.approx(1.0e-6)
    assert second.surfaces[1].asphere_coefficients["B"] == pytest.approx(-3.0e-9)
    assert second.surfaces[1].asphere_coefficients["D"] == pytest.approx(-7.0e-15)
    assert second.surfaces[2].asphere_coefficients["K"] == pytest.approx(-1.0)
    assert second.surfaces[2].asphere_coefficients["A"] == pytest.approx(2.0e-6)


def test_fujifilm_inline_tables_fail_loud_on_odd_asphere_terms() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        FUJIFILM_INLINE_ODD_ASPHERE_TEXT,
        patent_id="US-FUJIFILM-ODD-A1",
    )

    assert len(attempts) == 1
    assert attempts[0].embodiment == "Example 1"
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, PatentParseError)
    assert "unsupported nonzero Fujifilm asphere terms" in str(attempts[0].error)


def test_parse_folded_zoom_discrete_configurations() -> None:
    prescriptions = parse_patent_prescriptions(
        FOLDED_ZOOM_TEXT,
        patent_id="US-FOLDED-ZOOM-FIXTURE-A1",
    )

    assert [prescription.embodiment for prescription in prescriptions] == [
        "Folded zoom system 600 configuration 1",
        "Folded zoom system 600 configuration 2",
    ]
    first, second = prescriptions
    assert (first.focal_length_mm, first.f_number, first.hfov_deg) == pytest.approx(
        (9.61, 2.36, 13.97)
    )
    assert (second.focal_length_mm, second.f_number, second.hfov_deg) == pytest.approx(
        (24.03, 4.64, 6.06)
    )
    assert first.surfaces[1].thickness_mm == pytest.approx(0.911)
    assert second.surfaces[1].thickness_mm == pytest.approx(4.599)
    assert first.surfaces[3].thickness_mm == pytest.approx(4.251)
    assert second.surfaces[3].thickness_mm == pytest.approx(0.563)
    assert first.surfaces[2].label == "Stop"
    assert first.surfaces[0].nd == pytest.approx(1.54)
    assert first.surfaces[0].vd == pytest.approx(55.93)
    assert first.surfaces[0].asphere_coefficients["A"] == pytest.approx(-3.70e-4)
    assert first.surfaces[2].asphere_coefficients["B"] == pytest.approx(4.44e-4)
    assert first.surfaces[-1].label == "Image"


def test_parse_apple_suffixed_exemplary_table_pair() -> None:
    prescriptions = parse_patent_prescriptions(
        APPLE_EXEMPLARY_TEXT,
        patent_id="US-APPLE-EXEMPLARY-A1",
    )

    assert len(prescriptions) == 1
    prescription = prescriptions[0]
    assert prescription.embodiment == "Apple exemplary embodiment 1"
    assert (
        prescription.focal_length_mm,
        prescription.f_number,
        prescription.hfov_deg,
    ) == pytest.approx((0.5639, 2.2, 37.5))
    assert len(prescription.surfaces) == 9
    first_lens = prescription.surfaces[0]
    assert first_lens.index == 1
    assert first_lens.radius_mm == math.inf
    assert first_lens.nd == pytest.approx(1.535)
    asphere = prescription.surfaces[1]
    assert asphere.index == 2
    assert asphere.surface_type == "ASP"
    assert asphere.asphere_coefficients["K"] == pytest.approx(-95.705155)
    assert asphere.asphere_coefficients["A"] == pytest.approx(3.11858)
    assert asphere.asphere_coefficients["D"] == pytest.approx(3990.15)
    assert asphere.asphere_coefficients["F"] == pytest.approx(-3101.12)
    assert "F" not in prescription.surfaces[2].asphere_coefficients
    assert prescription.surfaces[6].label == "IR filter"
    assert prescription.surfaces[-1].label == "Image"


def test_parse_apple_exemplary_table_rejects_cross_bound_ordinal() -> None:
    text = APPLE_EXEMPLARY_TEXT.replace(
        "Optical data for a first exemplary embodiment",
        "Optical data for a second exemplary embodiment",
        1,
    )

    with pytest.raises(PatentParseError, match="ordinal does not match"):
        parse_patent_prescriptions(text, patent_id="US-APPLE-CROSS-BOUND-A1")


def test_parse_mobile_imaging_lens_single_and_split_coefficient_layouts() -> None:
    prescriptions = parse_patent_prescriptions(
        MOBILE_IMAGING_LENS_TEXT,
        patent_id="US-MOBILE-IMAGING-LENS-A1",
    )

    assert len(prescriptions) == 12
    early = prescriptions[0]
    assert early.embodiment == "Mobile imaging-lens example 1"
    assert (early.focal_length_mm, early.f_number, early.hfov_deg) == pytest.approx(
        (7.71, 1.5, 33.4)
    )
    assert len(early.surfaces) == 20
    assert early.surfaces[0].label == "Lens 1"
    assert early.surfaces[2].label == "Stop"
    assert early.surfaces[0].asphere_coefficients["A"] == pytest.approx(1.0e-3)
    assert early.surfaces[0].asphere_coefficients["G"] == pytest.approx(7.0e-8)
    assert prescriptions[4].surfaces[0].surface_type == "ASP"

    late = prescriptions[6]
    assert (late.focal_length_mm, late.f_number, late.hfov_deg) == pytest.approx((7.05, 2.1, 35.2))
    assert late.surfaces[0].label == "Stop"
    assert late.surfaces[1].label == "Lens 1"
    assert late.surfaces[1].asphere_coefficients["H"] == pytest.approx(-8.0e-10)
    assert late.surfaces[1].asphere_coefficients["J"] == pytest.approx(9.0e-11)
    assert late.surfaces[-1].label == "Image"


def test_mobile_imaging_lens_split_exponent_fails_only_its_example() -> None:
    text = MOBILE_IMAGING_LENS_TEXT.replace("1.000E-04", "1.000 E-04", 1)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-MOBILE-IMAGING-LENS-OCR-A1",
    )

    assert len(attempts) == 12
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, PatentParseError)
    assert "coefficient A10 is malformed: E-04" in str(attempts[0].error)
    assert sum(attempt.error is None for attempt in attempts) == 11


def test_mobile_imaging_lens_requires_published_half_field_definition() -> None:
    text = MOBILE_IMAGING_LENS_TEXT.replace(
        "ω represents a half field of view.",
        "ω is listed in degrees.",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-MOBILE-IMAGING-LENS-MISSING-DEFINITION-A1",
    )

    assert len(attempts) == 12
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "published half-field definition not found" in str(attempt.error) for attempt in attempts
    )


def test_kantatsu_six_lens_retained_source_parses_only_complete_examples() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "849299ca1b87707e"
        / "US-20210382275-A1.html"
    )
    raw = source.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        "849299ca1b87707e5c62f4ebdc74777bdd7cf333cdc910baa9b768df874791d7"
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        raw.decode("utf-8"),
        patent_id="US-20210382275-A1",
    )

    assert len(attempts) == 4
    assert [attempt.embodiment_number for attempt in attempts if attempt.error is None] == [2, 3]
    assert "coefficient A14 for source surface 9 is malformed: E-01" in str(attempts[0].error)
    assert "coefficient label expected A16, found <end>" in str(attempts[3].error)
    second = attempts[1].prescription
    assert second is not None
    assert (second.focal_length_mm, second.f_number, second.hfov_deg) == pytest.approx(
        (4.22, 1.80, 39.3)
    )
    assert [surface.index for surface in second.surfaces] == list(range(1, 17))
    assert second.surfaces[0].label == "Stop"
    assert second.surfaces[1].asphere_coefficients["A"] == pytest.approx(-5.811608e-3)
    assert second.surfaces[13].label == "Filter"
    assert (second.surfaces[13].nd, second.surfaces[13].vd) == pytest.approx((1.563, 51.3))
    assert second.surfaces[-1].label == "Image"


def test_kantatsu_six_lens_requires_published_half_field_definition() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "849299ca1b87707e"
        / "US-20210382275-A1.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "denotes a half field of view",
        "is listed in degrees",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-20210382275-NO-DEFINITION-A1",
    )

    assert len(attempts) == 4
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "published half-field definition not found" in str(attempt.error) for attempt in attempts
    )


def test_kantatsu_ih_first_retains_every_official_numeric_break() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "856703de431c5c5a"
        / "US-20210364766-A1.html"
    )
    raw = source.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        "856703de431c5c5ac4338d3ea28d1dea7d7e2fa89038135cb9f4287e72075e9b"
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        raw.decode("utf-8"),
        patent_id="US-20210364766-A1",
    )

    assert len(attempts) == 4
    assert all(attempt.prescription is None for attempt in attempts)
    assert ", 10, 6, 11," in str(attempts[0].error)
    assert ", 13, 77, 14," in str(attempts[1].error)
    assert "[1, 2, 1, 544, 3" in str(attempts[2].error)
    assert "example 4 header is source-damaged" in str(attempts[3].error)


def test_kantatsu_ih_first_requires_published_half_field_definition() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "856703de431c5c5a"
        / "US-20210364766-A1.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "denotes a half field of view",
        "is listed in degrees",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-20210364766-NO-DEFINITION-A1",
    )

    assert len(attempts) == 4
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "published half-field definition not found" in str(attempt.error) for attempt in attempts
    )


def test_kantatsu_missing_half_field_never_derives_values_from_f_and_ih() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "bbba59946989737a"
        / "US-20210373296-A1.html"
    )
    raw = source.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        "bbba59946989737a279b2946eea599f4465be4a1c4bd861a3e475cad0bec527c"
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        raw.decode("utf-8"),
        patent_id="US-20210373296-A1",
    )

    assert len(attempts) == 6
    assert all(attempt.prescription is None for attempt in attempts)
    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 7))
    assert all(
        "published half-field value is absent from the table header" in str(attempt.error)
        for attempt in attempts
    )


def test_kantatsu_missing_half_field_requires_published_definition() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "bbba59946989737a"
        / "US-20210373296-A1.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "denotes a half field of view",
        "is not defined here",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-20210373296-NO-DEFINITION-A1",
    )

    assert len(attempts) == 6
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "published half-field definition not found" in str(attempt.error) for attempt in attempts
    )


def test_kantatsu_inline_retained_source_parses_only_complete_examples() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "709bf966d3087414"
        / "US-20220163773-A1.html"
    )
    raw = source.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        "709bf966d30874140c2dbae29e78a02c4ebc0f0d24ac3ff37ad10d2b5c339e64"
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        raw.decode("utf-8"),
        patent_id="US-20220163773-A1",
    )

    assert len(attempts) == 11
    assert [attempt.embodiment_number for attempt in attempts if attempt.error is None] == list(
        range(2, 12)
    )
    assert "coefficient A20 for source surface 2 is missing" in str(attempts[0].error)
    second = attempts[1].prescription
    assert second is not None
    assert (second.focal_length_mm, second.f_number, second.hfov_deg) == pytest.approx(
        (4.70, 1.60, 39.4)
    )
    assert [surface.index for surface in second.surfaces] == list(range(1, 19))
    assert second.surfaces[0].label == "Stop"
    assert second.surfaces[1].asphere_coefficients["A"] == pytest.approx(-7.200435e-3)
    assert second.surfaces[15].label == "Filter"
    assert (second.surfaces[15].nd, second.surfaces[15].vd) == pytest.approx((1.517, 64.2))
    assert second.surfaces[-1].label == "Image"


def test_kantatsu_inline_retains_official_ocr_damage_without_numeric_repair() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "1a0d11c6dc00d532"
        / "US-20210364759-A1.html"
    )
    raw = source.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        "1a0d11c6dc00d5328c68ca7c4115662f12f32334e5d4c76b71b9da43ef296651"
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        raw.decode("utf-8"),
        patent_id="US-20210364759-A1",
    )

    assert len(attempts) == 12
    assert all(attempt.prescription is None for attempt in attempts)
    assert "[1, 2, 3, 4, 5, 6, 7, 8, 5583" in str(attempts[0].error)
    assert "nd=3.671 allowed [1.3, 2.2]" in str(attempts[1].error)
    assert "stop row is malformed" in str(attempts[2].error)
    assert "coefficient label expected A4" in str(attempts[5].error)


def test_kantatsu_inline_requires_published_half_field_definition() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "709bf966d3087414"
        / "US-20220163773-A1.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "ω denotes a half field of view",
        "ω is listed in degrees",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-20220163773-NO-DEFINITION-A1",
    )

    assert len(attempts) == 11
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "published half-field definition not found" in str(attempt.error) for attempt in attempts
    )


def test_kantatsu_nine_lens_retains_damaged_rows_and_units_per_example() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        KANTATSU_NINE_LENS_TEXT,
        patent_id="US-KANTATSU-NINE-LENS-A1",
    )

    assert len(attempts) == 13
    assert [attempt.embodiment_number for attempt in attempts if attempt.error is None] == [
        1,
        2,
        3,
        5,
        6,
    ]
    first = attempts[0].prescription
    assert first is not None
    assert (first.focal_length_mm, first.f_number, first.hfov_deg) == pytest.approx(
        (6.71, 1.9, 39.5)
    )
    assert len(first.surfaces) == 21
    assert first.surfaces[0].label == "Stop"
    assert first.surfaces[0].nd == pytest.approx(1.5443)
    assert first.surfaces[0].asphere_coefficients["A"] == pytest.approx(1.0e-3)
    assert first.surfaces[0].asphere_coefficients["G"] == pytest.approx(7.0e-9)
    assert "lens 9 first-surface row is malformed" in str(attempts[3].error)
    assert all(
        "surface-table unit is [nm], not [mm]" in str(attempt.error) for attempt in attempts[6:]
    )


def test_kantatsu_nine_lens_requires_published_half_angle_definition() -> None:
    text = KANTATSU_NINE_LENS_TEXT.replace(
        "and ω represents a half angle of view.",
        "and ω is listed in degrees.",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-KANTATSU-NINE-LENS-MISSING-DEFINITION-A1",
    )

    assert len(attempts) == 13
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "published half-angle definition not found" in str(attempt.error) for attempt in attempts
    )


def test_kantatsu_nine_lens_parses_ten_pretable_bound_examples() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        KANTATSU_NINE_LENS_PRETABLE_TEXT,
        patent_id="US-KANTATSU-NINE-LENS-PRETABLE-A1",
    )

    assert len(attempts) == 10
    assert all(attempt.error is None for attempt in attempts)
    first = attempts[0].prescription
    assert first is not None
    assert (first.focal_length_mm, first.f_number, first.hfov_deg) == pytest.approx(
        (5.69, 1.9, 39.3)
    )
    assert first.surfaces[0].label == "Stop"
    assert first.surfaces[-1].label == "Image"


def test_kantatsu_nine_lens_pretable_retains_split_material_token() -> None:
    text = KANTATSU_NINE_LENS_PRETABLE_TEXT.replace("1.5443", "1 5443", 1)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-KANTATSU-NINE-LENS-PRETABLE-DAMAGED-A1",
    )

    assert len(attempts) == 10
    assert "surface sequence must be 1-20" in str(attempts[0].error)
    assert all(attempt.error is None for attempt in attempts[1:])


def test_folded_macro_tele_retains_all_states_and_only_parses_infinity_efl() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        FOLDED_MACRO_TELE_TEXT,
        patent_id="US-FOLDED-MACRO-TELE-A1",
    )

    assert len(attempts) == 37
    successful = [attempt for attempt in attempts if attempt.error is None]
    assert [attempt.embodiment_number for attempt in successful] == [1, 9, 17, 26]
    prescriptions = [attempt.prescription for attempt in successful]
    assert all(prescription is not None for prescription in prescriptions)
    assert [len(prescription.surfaces) for prescription in prescriptions if prescription] == [
        16,
        18,
        20,
        16,
    ]
    first = prescriptions[0]
    assert first is not None
    assert (first.focal_length_mm, first.f_number, first.hfov_deg) == pytest.approx(
        (14.0, 2.0, 10.0)
    )
    assert first.surfaces[0].label == "Stop"
    assert first.surfaces[1].asphere_coefficients["A"] == pytest.approx(1.0e-3)
    assert all(
        "finite-object state is published but unsupported" in str(attempt.error)
        for attempt in attempts[1:8]
    )
    assert all(
        "whole-system focal token F is not officially defined as EFL" in str(attempt.error)
        for attempt in attempts[28:]
    )


def test_folded_macro_tele_requires_official_half_field_definition() -> None:
    text = FOLDED_MACRO_TELE_TEXT.replace(
        "Half FOV (HFOV) are given.",
        "HFOV values are listed.",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-FOLDED-MACRO-TELE-NO-DEFINITION-A1",
    )

    assert len(attempts) == 37
    assert all(attempt.prescription is None for attempt in attempts)
    assert all("Half FOV/HFOV definition not found" in str(attempt.error) for attempt in attempts)


def test_parse_samsung_wide_fov_embodiment_pairs_and_full_field() -> None:
    prescriptions = parse_patent_prescriptions(
        SAMSUNG_WIDE_FOV_TEXT,
        patent_id="US-SAMSUNG-WIDE-FOV-A1",
    )

    assert len(prescriptions) == 10
    first = prescriptions[0]
    assert first.embodiment == "Samsung wide-FOV embodiment 1"
    assert (
        first.focal_length_mm,
        first.f_number,
        first.hfov_deg,
    ) == pytest.approx((4.5301, 1.8718, 41.0))
    assert len(first.surfaces) == 19
    surfaces = {surface.index: surface for surface in first.surfaces}
    assert surfaces[1].nd == pytest.approx(1.777)
    assert surfaces[9].label == "Stop"
    assert surfaces[19].label == "Imaging Plane"
    assert surfaces[3].surface_type == "ASP"
    assert surfaces[3].asphere_coefficients["K"] == pytest.approx(-1.26022)
    assert surfaces[3].asphere_coefficients["A"] == pytest.approx(2.59351e-3)
    assert surfaces[14].asphere_coefficients["D"] == pytest.approx(4.64438e-8)
    assert prescriptions[4].hfov_deg == pytest.approx(40.995)


def test_parse_samsung_wide_fov_requires_published_full_field_definition() -> None:
    text = SAMSUNG_WIDE_FOV_TEXT.replace(
        "HFOV is a field of view of the imaging plane in a horizontal direction "
        "expressed in degrees.",
        "HFOV is listed in degrees.",
        1,
    )

    with pytest.raises(PatentParseError, match="full-field HFOV definition not found"):
        parse_patent_prescriptions(text, patent_id="US-SAMSUNG-WIDE-FOV-MISSING-A1")


def test_parse_folded_zoom_accepts_reordered_multiline_surface_header() -> None:
    text = FOLDED_ZOOM_TEXT.replace(
        "Surface # Comment Type Radius Thickness (D/2) Material Index Abbe # Length",
        "Surface Curvature Aperture Radius Abbe Focal # Comment Type Radius "
        "Thickness (D/2) Material Index # Length",
    )

    prescriptions = parse_patent_prescriptions(
        text,
        patent_id="US-FOLDED-ZOOM-REORDERED-A1",
    )

    assert len(prescriptions) == 2
    assert prescriptions[1].surfaces[3].thickness_mm == pytest.approx(0.563)


def test_folded_zoom_qtyp_index_damage_is_retained_per_configuration() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        FOLDED_ZOOM_DAMAGED_QTYP_TEXT,
        patent_id="US-FOLDED-ZOOM-QTYP-A1",
    )

    assert len(attempts) == 2
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(isinstance(attempt.error, PatentParseError) for attempt in attempts)
    assert all(
        "surface index break: expected S2, found S1" in str(attempt.error) for attempt in attempts
    )


def test_folded_zoom_qtyp_is_rejected_when_surface_indices_are_intact() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        FOLDED_ZOOM_DAMAGED_QTYP_TEXT.replace("L2 S.sub.1", "L2 S.sub.2"),
        patent_id="US-FOLDED-ZOOM-QTYP-INTACT-A1",
    )

    assert len(attempts) == 2
    assert all(
        "unsupported published QTYP/NR/A0-A6 surfaces" in str(attempt.error) for attempt in attempts
    )


def test_folded_zoom_fallback_does_not_claim_static_qtyp_table() -> None:
    text = patent_to_zmx.normalize_patent_text(
        """
        TABLE-US-00001 TABLE 1 Optical lens system 800 Group Lens Surface Type
        R [mm] T [mm] D [mm] Nd Vd Object S0 Flat Infinity Infinity
        S.sub.1 QTYP 5.0 1.0 2.0 1.54 55.93 S.sub.2 QTYP -5.0 0.5 1.9
        TABLE-US-00002 TABLE 2 Conic Surface (k) NR A.sub.0 A.sub.1
        S.sub.1 0 3.0 1.0E-03 -1.0E-04
        """
    )

    assert patent_to_zmx._parse_folded_zoom_table_attempts(text, patent_id="STATIC") == []


def test_parse_patent_prescriptions_accepts_aac_raytech_compact_tables() -> None:
    prescriptions = parse_patent_prescriptions(
        AAC_RAYTECH_COMPACT_TEXT,
        patent_id="US-AAC-RAYTECH-FIXTURE-A1",
    )

    assert [prescription.embodiment for prescription in prescriptions] == [
        "AAC Raytech example 1",
        "AAC Raytech example 2",
    ]

    first = prescriptions[0]
    assert first.focal_length_mm == pytest.approx(18.269)
    assert first.f_number == pytest.approx(2.871)
    assert first.hfov_deg == pytest.approx(21.79 / 2.0)
    assert len(first.surfaces) == 12
    assert first.surfaces[0].label == "Stop"
    assert first.surfaces[0].radius_mm == math.inf
    assert first.surfaces[0].thickness_mm == pytest.approx(-0.460)

    first_lens = first.surfaces[1]
    assert first_lens.label == "Surface R1"
    assert first_lens.nd == pytest.approx(1.4959)
    assert first_lens.vd == pytest.approx(81.65)
    assert first_lens.surface_type == "ASP"
    assert first_lens.asphere_coefficients["K"] == pytest.approx(-0.95839)
    assert first_lens.asphere_coefficients["A"] == pytest.approx(3.0795e-3)
    assert first_lens.asphere_coefficients["H"] == pytest.approx(-1.8914e-5)
    assert first_lens.asphere_coefficients["A22"] == pytest.approx(-3.6308e-7)

    second = prescriptions[1]
    assert second.focal_length_mm == pytest.approx(16.282)
    assert second.hfov_deg == pytest.approx(24.47 / 2.0)
    assert second.surfaces[1].asphere_coefficients["B"] == pytest.approx(-9.3315e-4)


def test_parse_patent_prescriptions_accepts_sunny_obj_sto_tables() -> None:
    prescriptions = parse_patent_prescriptions(
        SUNNY_OBJ_STO_TEXT,
        patent_id="US-SUNNY-FIXTURE-A1",
    )

    assert [prescription.embodiment for prescription in prescriptions] == [
        "Sunny embodiment 1",
        "Sunny embodiment 2",
    ]

    first = prescriptions[0]
    assert first.focal_length_mm == pytest.approx(5.04)
    assert first.f_number == pytest.approx(2.02)
    assert first.hfov_deg == pytest.approx(42.2)
    # OBJ row skipped; STO + S1..S7 = 8 surfaces.
    assert len(first.surfaces) == 8
    assert first.surfaces[0].label == "Stop"
    assert first.surfaces[0].radius_mm == math.inf
    assert first.surfaces[0].thickness_mm == pytest.approx(-0.3784)

    lens1 = first.surfaces[1]
    assert lens1.label == "Surface S1"
    assert lens1.radius_mm == pytest.approx(2.0348)
    assert lens1.nd == pytest.approx(1.55)
    assert lens1.vd == pytest.approx(56.1)
    assert lens1.surface_type == "ASP"
    # Conic from the surface table plus A4..A12 from the split-header
    # asphere table.
    assert lens1.asphere_coefficients["K"] == pytest.approx(-0.1992)
    assert lens1.asphere_coefficients["A"] == pytest.approx(4.3347e-3)
    assert lens1.asphere_coefficients["D"] == pytest.approx(-3.4351e-2)
    assert lens1.asphere_coefficients["E"] == pytest.approx(6.4565e-2)

    air_surface = first.surfaces[2]
    assert air_surface.nd is None
    assert air_surface.asphere_coefficients["K"] == pytest.approx(17.3022)

    ir_filter = first.surfaces[5]
    assert ir_filter.nd == pytest.approx(1.52)
    assert ir_filter.vd == pytest.approx(64.2)

    second = prescriptions[1]
    assert second.focal_length_mm == pytest.approx(5.08)
    assert second.f_number == pytest.approx(2.03)
    assert second.hfov_deg == pytest.approx(41.9)


def test_parse_sunny_narrative_meta_and_focal_length_column() -> None:
    prescriptions = parse_patent_prescriptions(
        SUNNY_NARRATIVE_META_TEXT,
        patent_id="US-SUNNY-FIXTURE-A2",
    )

    assert len(prescriptions) == 1
    first = prescriptions[0]
    # Metadata from the anchored "In this example, ..." narrative sentence.
    assert first.focal_length_mm == pytest.approx(4.26)
    assert first.f_number == pytest.approx(1.48)
    assert first.hfov_deg == pytest.approx(43.7)

    # The per-element Focal-length column (4.96) is skipped; the trailing
    # value is the conic.
    lens1 = first.surfaces[1]
    assert lens1.nd == pytest.approx(1.56)
    assert lens1.vd == pytest.approx(58.4)
    assert lens1.asphere_coefficients["K"] == pytest.approx(0.2654)


def test_sunny_group_rows_are_cardinality_bound_and_full_fov_is_halved() -> None:
    raw_text = """
    FOV is a maximum field of view of the optical imaging lens assembly.
    TABLE-US-00001 TABLE 1 Conditional Embodiment Expression 1 2 3
    f/EPD 1.37 1.28 1.19 ImgH/f 1.79 1.71 1.91
    TABLE-US-00002 TABLE 2 embodiment parameter 1 2 3
    f(mm) 3.10 3.20 3.30 FOV(deg) 120.0 122.0 124.0
    """
    text = patent_to_zmx.normalize_patent_text(raw_text)
    rows = patent_to_zmx._sunny_consolidated_meta_rows(
        patent_to_zmx._patent_table_blocks(text),
        embodiment_count=3,
        document_text=text,
    )

    assert rows == {
        "efl": [3.10, 3.20, 3.30],
        "fno": [1.37, 1.28, 1.19],
        "hfov": [60.0, 61.0, 62.0],
    }
    assert patent_to_zmx._sunny_meta_for_embodiment(
        text,
        embodiment_number=2,
        table_span=(0, 0),
        consolidated=rows,
    ) == pytest.approx((3.20, 1.28, 61.0))


def test_sunny_group_rows_reject_compound_fno_and_undefined_or_ambiguous_fov() -> None:
    raw_text = """
    TABLE-US-00001 TABLE 1 Conditional/Embodiment 1 2 3
    ImgH × f/EPD (mm) 3.10 3.20 3.30
    tan(FOV/2) × f(mm) 4.10 4.20 4.30 FOV(deg) 120.0 122.0 124.0
    TABLE-US-00002 TABLE 2 Example Condition 1 2 3
    FOV(deg) 121.0 123.0 125.0
    """
    text = patent_to_zmx.normalize_patent_text(raw_text)
    rows = patent_to_zmx._sunny_consolidated_meta_rows(
        patent_to_zmx._patent_table_blocks(text),
        embodiment_count=3,
        document_text=text,
    )

    assert "fno" not in rows
    assert "efl" not in rows
    assert "hfov" not in rows


def test_sunny_group_rows_collapse_only_exact_duplicate_state_pairs() -> None:
    raw_text = """
    FOV is a maximum field of view.
    TABLE-US-00001 TABLE 1 Parameter 1 2 3 4 5 6
    f(mm) 1.35 1.35 1.38 1.38 1.31 1.31
    Fno 2.20 2.20 2.19 2.19 2.18 2.18
    FOV(deg) 113.08 113.08 112.06 112.06 111.85 111.85
    """
    text = patent_to_zmx.normalize_patent_text(raw_text)
    rows = patent_to_zmx._sunny_consolidated_meta_rows(
        patent_to_zmx._patent_table_blocks(text),
        embodiment_count=3,
        document_text=text,
    )

    assert rows == {
        "efl": [1.35, 1.38, 1.31],
        "fno": [2.20, 2.19, 2.18],
        "hfov": [56.54, 56.03, 55.925],
    }

    differing = text.replace("2.20 2.20", "2.20 2.21")
    differing_rows = patent_to_zmx._sunny_consolidated_meta_rows(
        patent_to_zmx._patent_table_blocks(differing),
        embodiment_count=3,
        document_text=differing,
    )
    assert "fno" not in differing_rows


def test_parse_patent_prescription_accepts_ability_opto_tables() -> None:
    prescription = parse_patent_prescription(
        ABILITY_OPTO_TEXT,
        patent_id="US-ABILITY-FIXTURE-A1",
    )

    # Meta from "f = 3.03968 mm; f/HEP = 1.6; HAF = 50.0010 deg".
    assert prescription.focal_length_mm == pytest.approx(3.03968)
    assert prescription.f_number == pytest.approx(1.6)
    assert prescription.hfov_deg == pytest.approx(50.0010)

    surfaces = {surface.index: surface for surface in prescription.surfaces}
    lens1 = surfaces[1]
    assert lens1.label == "Lens 1"
    assert lens1.nd == pytest.approx(1.514)
    assert lens1.vd == pytest.approx(56.80)
    # Ordinal marker split across tokens ("3 .sup.rd lens") still resolves.
    assert surfaces[6].label == "Lens 3"
    assert surfaces[3].label == "Ape. Stop"
    assert surfaces[3].radius_mm == 0.0
    assert surfaces[3].thickness_mm == pytest.approx(-0.412)

    ir_filter = surfaces[8]
    assert ir_filter.label == "IR-cut filter"
    # Named model glass ("BK7_SCH") with explicit nd/vd is kept.
    assert ir_filter.nd == pytest.approx(1.517)
    assert ir_filter.vd == pytest.approx(64.20)

    # "Surface 1 2 4" header without "#" still parses coefficients.
    assert lens1.asphere_coefficients["K"] == pytest.approx(-1.882119e-1)
    assert lens1.asphere_coefficients["A"] == pytest.approx(7.686381e-4)
    assert surfaces[7].asphere_coefficients["B"] == pytest.approx(6.038040e-3)


def test_ability_opto_ocr_corrupt_exponent_fails_loud() -> None:
    with pytest.raises(PatentParseError, match="OCR-corrupted exponent"):
        parse_patent_prescription(
            ABILITY_CORRUPT_EXPONENT_TEXT,
            patent_id="US-ABILITY-FIXTURE-A2",
        )


def test_convert_candidate_writes_each_embodiment_with_e_suffix_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_patent_html(_client: object, _token: str, patent_id: str) -> str:
        assert patent_id == "US-MULTI-A1"
        return MULTI_EMBODIMENT_TEXT

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch_patent_html)
    candidate = patent_to_zmx.PatentCandidate(
        patent_id="US-MULTI-A1",
        title="multi embodiment fixture",
        source_url="local-fixture",
        pool_path=tmp_path / "pool.jsonl",
        line_number=1,
    )

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(object(), "local-token", candidate, tmp_path)
    )

    assert [attempt.status for attempt in attempts] == ["success", "success"]
    assert [attempt.embodiment for attempt in attempts] == ["1st Embodiment", "EXAMPLE 2"]
    assert (tmp_path / "US-MULTI-A1-e1.zmx").is_file()
    assert (tmp_path / "US-MULTI-A1-e2.zmx").is_file()
    assert attempts[0].zmx_path.endswith("US-MULTI-A1-e1.zmx")
    assert attempts[1].zmx_path.endswith("US-MULTI-A1-e2.zmx")
    assert all(attempt.attempt_id for attempt in attempts)
    assert all(Path(attempt.receipt_path).is_file() for attempt in attempts)
    assert all(Path(attempt.raw_document_path).is_file() for attempt in attempts)
    assert attempts[0].raw_document_sha256 == attempts[1].raw_document_sha256


def test_real_worker_retry_keeps_stable_request_identity_and_append_only_attempts(
    tmp_path: Path,
) -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-RETRY-A1")
    fetched = patent_to_zmx.FetchedPatentHtml(
        html=PRESCRIPTION_TEXT,
        source_bucket="fixture",
    )
    source = patent_to_zmx._retain_fetched_patent_html(
        tmp_path / "raw",
        patent_id=prescription.patent_id,
        fetched=fetched,
    )
    request = patent_to_zmx._conversion_request(prescription, source)
    kwargs = {
        "published_zmx_path": tmp_path / "staging" / "US-RETRY-A1-e1.zmx",
        "attempts_root": tmp_path / "attempts",
        "repo_root": patent_to_zmx.ROOT,
        "timeout_seconds": 30.0,
    }

    first = patent_to_zmx.run_patent_conversion_attempt(request, **kwargs)
    second = patent_to_zmx.run_patent_conversion_attempt(request, **kwargs)

    assert first.status == second.status == "success"
    assert first.request_sha256 == second.request_sha256
    assert first.retry_number == 1
    assert second.retry_number == 2
    assert first.attempt_id != second.attempt_id
    assert Path(first.candidate_zmx_path or "").is_file()
    assert Path(second.candidate_zmx_path or "").is_file()
    assert kwargs["published_zmx_path"].is_file()


def test_convert_candidate_keeps_later_embodiments_after_parse_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken_first = PRESCRIPTION_TEXT.replace("3 Lens 2", "6 Lens 2", 1)

    async def fake_fetch_patent_html(_client: object, _token: str, patent_id: str) -> str:
        assert patent_id == "US-PARTIAL-A1"
        return broken_first + "\n" + SECOND_PRESCRIPTION_TEXT

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch_patent_html)
    candidate = patent_to_zmx.PatentCandidate(
        patent_id="US-PARTIAL-A1",
        title="partial embodiment fixture",
        source_url="local-fixture",
        pool_path=tmp_path / "pool.jsonl",
        line_number=1,
    )

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(object(), "local-token", candidate, tmp_path)
    )

    assert [attempt.status for attempt in attempts] == ["failed", "success"]
    assert "surface table index break" in attempts[0].reason
    assert attempts[0].embodiment == "1st Embodiment"
    assert attempts[1].embodiment == "EXAMPLE 2"
    assert not (tmp_path / "US-PARTIAL-A1-e1.zmx").exists()
    assert (tmp_path / "US-PARTIAL-A1-e2.zmx").is_file()
    assert attempts[1].zmx_path.endswith("US-PARTIAL-A1-e2.zmx")


def test_convert_candidate_skips_formal_index_embodiments_but_not_staging_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_patent_html(_client: object, _token: str, patent_id: str) -> str:
        assert patent_id == "US-MULTI-A1"
        return MULTI_EMBODIMENT_TEXT

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch_patent_html)
    candidate = patent_to_zmx.PatentCandidate(
        patent_id="US-MULTI-A1",
        title="multi embodiment fixture",
        source_url="local-fixture",
        pool_path=tmp_path / "pool.jsonl",
        line_number=1,
    )
    formal_index = tmp_path / "index.json"
    formal_index.write_text(
        '[{"case_id": "US-MULTI-A1-e2", "source_zmx": "US-MULTI-A1-e2.zmx"}]',
        encoding="utf-8",
    )
    (tmp_path / "US-MULTI-A1-e1.zmx").write_text("stale staging artifact", encoding="ascii")

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "local-token",
            candidate,
            tmp_path,
            formal_case_stems=patent_to_zmx.load_formal_case_stems(formal_index),
        )
    )

    assert [attempt.status for attempt in attempts] == ["success", "skipped"]
    assert attempts[1].reason == "formal case index already contains this patent embodiment"
    assert (tmp_path / "US-MULTI-A1-e1.zmx").read_text(encoding="ascii") != "stale staging artifact"
    assert not (tmp_path / "US-MULTI-A1-e2.zmx").exists()


def test_parse_patent_prescription_rejects_unsupported_high_order_asphere_terms() -> None:
    text = PRESCRIPTION_TEXT.replace("A16= 1.0E-10 --", "A32= 1.0E-10 --")

    with pytest.raises(PatentParseError, match="unsupported nonzero high-order"):
        parse_patent_prescription(text, patent_id="US-UNSUPPORTED-A1")


def test_prescription_fingerprint_uses_first_eight_radius_thickness_values() -> None:
    base = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-FP-A1")
    meta_changed = parse_patent_prescription(
        PRESCRIPTION_TEXT.replace("f = 12.99 mm", "f = 13.49 mm", 1),
        patent_id="US-FP-A2",
    )
    radius_changed = parse_patent_prescription(
        PRESCRIPTION_TEXT.replace("43.6006", "44.6006", 1),
        patent_id="US-FP-A3",
    )

    fingerprint = prescription_fingerprint(base)

    assert len(fingerprint) == 16
    assert fingerprint == prescription_fingerprint(meta_changed)
    assert fingerprint != prescription_fingerprint(radius_changed)


def test_convert_candidate_skips_duplicate_prescription_without_writing_zmx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "zmx"
    seen_prescription_fingerprints: set[str] = set()

    async def fake_fetch(_client: object, _token: str, _patent_id: str) -> str:
        return PRESCRIPTION_TEXT

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)

    first = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "token",
            patent_to_zmx.PatentCandidate(
                patent_id="US-DUP-A1",
                title="first",
                source_url="",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            output_dir,
            seen_prescription_fingerprints=seen_prescription_fingerprints,
        )
    )
    second = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "token",
            patent_to_zmx.PatentCandidate(
                patent_id="US-DUP-A2",
                title="second",
                source_url="",
                pool_path=tmp_path / "pool.jsonl",
                line_number=2,
            ),
            output_dir,
            seen_prescription_fingerprints=seen_prescription_fingerprints,
        )
    )

    assert [attempt.status for attempt in first] == ["success"]
    assert [attempt.status for attempt in second] == ["duplicate_prescription"]
    assert "prescription fingerprint" in second[0].reason
    assert (output_dir / "US-DUP-A1-e1.zmx").is_file()
    assert not (output_dir / "US-DUP-A2-e1.zmx").exists()


def test_patent_to_zmx_report_includes_failure_reason_counts(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"

    patent_to_zmx._write_report(
        report_path,
        [
            patent_to_zmx.ConversionAttempt(
                patent_id="US-FAIL-A1",
                title="parse failure",
                status="failed",
                reason="PatentParseError: no embodiment table",
            ),
            patent_to_zmx.ConversionAttempt(
                patent_id="US-DUP-A1",
                title="duplicate",
                status="duplicate_prescription",
                reason="duplicate_prescription: prescription fingerprint abc123",
            ),
        ],
        target_successes=1,
    )

    report = report_path.read_text(encoding="utf-8")

    assert "- failure_reason_counts:" in report
    assert "  - PatentParseError: 1" in report
    assert "  - duplicate_prescription: 1" in report
