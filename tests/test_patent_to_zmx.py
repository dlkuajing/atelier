from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from pathlib import Path
from types import SimpleNamespace

import cv2
import httpx
import numpy as np
import pytest

from app.core.engines.zmx_writer import write_zmx_from_codev_readout
from app.core.zmx_ingest import load_normalized_zmx
from scripts import patent_pdf_recovery, patent_to_zmx
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


def _samsung_ten_lens_undefined_high_order_fixture(
    *,
    publish_high_order_definition: bool = False,
) -> str:
    definition = (
        "c is a reciprocal of a radius of curvature of the corresponding lens, "
        "k is a conic constant, r is a distance from a certain point on an "
        "aspherical surface to an optical axis, A to H and J are aspherical "
        "surface constants"
    )
    if publish_high_order_definition:
        definition += ", and L to P are aspherical surface constants"
    parts = [
        "IMAGING LENS SYSTEM",
        "Family ID: 91269360",
        "FOV is a field of view of the imaging lens system",
        definition,
    ]
    labels = (
        "K",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "J",
        "L",
        "M",
        "N",
        "O",
        "P",
    )
    for embodiment_number in range(1, 11):
        surface_table = embodiment_number * 2 - 1
        asphere_table = embodiment_number * 2
        parts.append(
            f"Tables {surface_table} and {asphere_table} illustrate lens characteristics "
            "and aspherical surface values of the imaging lens system according to the "
            "present embodiment."
        )
        surface_rows = " ".join(
            f"S{surface_index} "
            + (
                f"Lens {surface_index} 1.0 0.1 1.55 55.0"
                if surface_index % 2 == 1 and surface_index <= 19
                else "1.0 0.1"
            )
            for surface_index in range(1, 24)
        )
        parts.append(
            f"TABLE-US-{surface_table:05d} TABLE {surface_table} Surface Radius of "
            "Thickness/ Refractive Abbe No. Components curvature distance index number "
            f"{surface_rows}"
        )
        coefficient_sections = []
        for group in (range(1, 8), range(8, 15), range(15, 21)):
            group_values = tuple(group)
            rows = []
            for label in labels:
                values = ["0.0"] * len(group_values)
                if label == "L":
                    values[0] = "1.0E-9"
                rows.append(f"{label} " + " ".join(values))
            coefficient_sections.append(
                "Surface No. "
                + " ".join(f"S{surface_index}" for surface_index in group_values)
                + " "
                + " ".join(rows)
            )
        parts.append(
            f"TABLE-US-{asphere_table:05d} TABLE {asphere_table} "
            + " ".join(coefficient_sections)
        )
    parts.extend(
        (
            "TABLE-US-00021 TABLE 21 First Second Third Fourth Fifth Reference "
            "embodiment embodiment embodiment embodiment embodiment "
            "f 6.1 6.2 6.3 6.4 6.5 f number 1.5 1.6 1.7 1.8 1.9 "
            "FOV 78.0 78.1 78.2 78.3 78.4",
            "TABLE-US-00022 TABLE 22 Sixth Seventh Eighth Ninth Tenth Reference "
            "embodiment embodiment embodiment embodiment embodiment "
            "f 6.6 6.7 6.8 6.9 7.0 f number 1.5 1.6 1.7 1.8 1.9 "
            "FOV 78.5 78.6 78.7 78.8 78.9",
            "TABLE-US-00023 TABLE 23 conditional values",
            "TABLE-US-00024 TABLE 24 conditional values",
        )
    )
    return " ".join(parts)


def _install_samsung_ten_lens_undefined_high_order_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-SAMSUNG-TEN-LENS-HIGH-ORDER-GAP-A1"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._SAMSUNG_TEN_LENS_UNDEFINED_HIGH_ORDER_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        },
    )
    return patent_id


def _samsung_even_order_fixture(
    *,
    damaged_first_asphere_header: bool = False,
    omit_half_field_definition: bool = False,
) -> str:
    surface_headers = {
        5: (
            "Sur- face Radius of Refractive Abbe Effective No. Components "
            "curvature index number Radius"
        ),
        6: (
            "Sur- Thick- Re- face Com- Radius of ness/ fractive Abbe Effective No. "
            "ponents curvature Distance index number Radius"
        ),
        7: (
            "Radius of Thickness/ Refractive Abbe Effective Surface No. Components "
            "curvature Distance index number Radius"
        ),
    }
    default_header = (
        "Surface Radius of Thickness/ Refractive Abbe Effective No. Components "
        "curvature Distance index number Radius"
    )
    late_header = (
        "Surface Radius of Refractive Abbe Effective No. Components curvature "
        "Thickness/Distance index number Radius"
    )
    labels = {
        1: "First lens",
        3: "Second lens",
        4: "Stop",
        5: "Third lens",
        7: "Fourth lens",
        9: "Fifth lens",
        11: "Sixth lens",
        13: "Seventh lens",
        15: "Eighth lens",
        17: "Filter",
        19: "Imaging plane",
    }
    material_surfaces = {1, 3, 5, 7, 9, 11, 13, 15, 17}

    def surface_rows() -> str:
        rows = []
        for surface_index in range(1, 20):
            radius = "Infinity" if surface_index >= 17 else f"{surface_index + 1}.0"
            values = [radius, "0.1"]
            if surface_index in material_surfaces:
                values.extend(("1.55", "55.0"))
            values.append(f"{surface_index + 2}.0")
            rows.append(
                " ".join(
                    [f"S{surface_index}", labels.get(surface_index, ""), *values]
                ).strip()
            )
        return " ".join(rows)

    def asphere_rows(surface_start: int, *, terms_before_values: bool) -> str:
        rows = ["K " + " ".join(["0.0"] * 8)]
        for order in range(4, 31, 2):
            suffix = "nd" if order == 22 else "th"
            values = ["0.0"] * 8
            if order == 30:
                values[-1] = "1.0E-15"
            value_text = " ".join(values)
            label = f"{order}{suffix}"
            if terms_before_values:
                rows.append(f"{label} order {value_text} term")
            else:
                rows.append(f"{label} {value_text} order term")
        return " ".join(rows)

    definition = (
        "HFOV values are listed."
        if omit_half_field_definition
        else "HFOV is the half field of view of the imaging lens system."
    )
    parts = [
        "IMAGING LENS SYSTEM. "
        + definition
        + " c is the reciprocal of the radius of curvature of the corresponding lens, "
        "k is the conic constant, A to H and J are aspherical constants."
    ]
    for embodiment_number in range(1, 11):
        surface_table = embodiment_number * 2 - 1
        asphere_table = embodiment_number * 2
        parts.append(
            f"Tables {surface_table} and {asphere_table} list lens characteristics "
            "and aspheric values of the imaging lens system according to the present "
            "embodiment."
        )
        header = surface_headers.get(
            embodiment_number,
            late_header if embodiment_number >= 8 else default_header,
        )
        parts.append(
            f"TABLE-US-{surface_table:05d} TABLE {surface_table} {header} {surface_rows()}"
        )
        continuation = "S9 S10 S11 S12 S13 S14 S15 S16"
        if damaged_first_asphere_header and embodiment_number == 1:
            continuation = "S9 S10 S1 S12 S13 S14 S15 S16"
        parts.append(
            f"TABLE-US-{asphere_table:05d} TABLE {asphere_table} "
            "Surface No. S1 S2 S3 S4 S5 S6 S7 S8 "
            f"{asphere_rows(1, terms_before_values=True)} "
            f"Surface No{'.' if embodiment_number != 6 else ''} {continuation} "
            f"{asphere_rows(9, terms_before_values=False)} "
            f"[{1100 + embodiment_number}]"
        )
    parts.append(
        "TABLE-US-00021 TABLE 21 First Second Third Fourth Fifth Elements "
        "embodiment embodiment embodiment embodiment embodiment "
        "f 6.1 6.2 6.3 6.4 6.5 f-number 1.5 1.6 1.7 1.8 1.9 "
        "HFOV(°) 41.1 42.2 43.3 44.4 45.5 "
        "Sixth Seventh Eighth Ninth Tenth Elements embodiment embodiment embodiment "
        "embodiment embodiment f 7.1 7.2 7.3 7.4 7.5 "
        "f-number 2.1 2.2 2.3 2.4 2.5 HFOV(°) 85.1 85.2 85.3 85.4 85.5"
    )
    parts.append("TABLE-US-00022 TABLE 22 conditional values")
    parts.append("TABLE-US-00023 TABLE 23 conditional values")
    return " ".join(parts)


def _samsung_eight_lens_missing_stop_fixture(*, extra_stop_binding: bool = False) -> str:
    parts = ['"A to J" are aspheric constants.']
    for example_number in range(1, 6):
        system = example_number * 100
        surface_table = example_number * 2 - 1
        asphere_table = example_number * 2
        parts.append(
            f"The imaging lens system {system} may further include a stop ST. "
            f"The stop ST may be disposed between the second lens {system + 20} "
            f"and the third lens {system + 30}. "
            f"Tables {surface_table} and {asphere_table} list lens characteristics "
            f"and aspherical values of the imaging lens system {system}."
        )
        surface_rows = " ".join(f"S{index} {index}.0 0.1" for index in range(1, 20))
        parts.append(
            f"TABLE-US-{surface_table:05d} TABLE {surface_table} "
            "Surface Radius of Thickness/ Refractive Abbe No. Note Curvature "
            f"Distance Index Number {surface_rows}"
        )
        first_rows = " ".join(
            f"S{index} 0 0 0 0 0 0" if not (example_number == 3 and index == 12) else
            "S12 0 0 0 |0 0 0"
            for index in range(1, 17)
        )
        second_rows = " ".join(f"S{index} 0 0 0 0" for index in range(1, 17))
        parts.append(
            f"TABLE-US-{asphere_table:05d} TABLE {asphere_table} "
            f"Surface No. K A B C D E {first_rows} Surface No. F G H J {second_rows}"
        )
    parts.append(
        "TABLE-US-00011 TABLE 11 First Second Third Fourth Fifth Note Example Example "
        "Example Example Example TTL 7 7 7 7 7 BFL 1 1 1 1 1 f number 1.6 1.6 1.6 "
        "1.6 1.6 FOV 82 82 82 82 82 f 6 6 6 6 6"
    )
    parts.append("TABLE-US-00012 TABLE 12 Conditional First Second Third Fourth Fifth")
    if extra_stop_binding:
        parts.append("The stop ST has a published axial coordinate of 0.2 mm.")
    return " ".join(parts)


def _ir_filter_coating_only_fixture(*, prescription_marker: bool = False) -> str:
    parts = [
        "OPTICAL LENS ASSEMBLY AND IMAGING LENS WITH INFRARED RAY FILTERING. "
        "Light enters through an aperture stop 60 and reaches an image sensor."
    ]
    for table_number in range(1, 79):
        marker = " Curvature 1.0" if prescription_marker and table_number == 78 else ""
        parts.append(
            f"TABLE-US-{table_number:05d} TABLE {table_number} "
            f"Wavelength (nm) 850 Transmittance (%) 1.0{marker}"
        )
    return " ".join(parts)


def _surface_texture_acquisition_only_fixture(
    *,
    prescription_marker: bool = False,
) -> str:
    parts = [
        "SYSTEM AND METHOD FOR ACQUIRING IMAGES OF SURFACE TEXTURE.",
        "vision system camera assembly " * 7,
        "105-millimeter focal length",
        "spaced apart axially by approximately 1 millimeter",
        "semi-reflecting mirror " * 4,
        "structured illumination " * 2,
        "FIG. 10 is a schematic diagram of an alternate arrangement",
    ]
    if prescription_marker:
        parts.append("Surface # Curvature Radius")
    return " ".join(parts)


def _lens_driving_mechanical_only_fixture(*, prescription_marker: bool = False) -> str:
    parts = [
        "IMAGING LENS DRIVING MODULE, IMAGE CAPTURING APPARATUS AND ELECTRONIC DEVICE",
        "driving mechanism",
        "carrier carrier",
        "magnet",
        "coil",
    ]
    if prescription_marker:
        parts.append("Surface No. Curvature Radius")
    return " ".join(parts)


def _install_lens_driving_fixture_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-LENS-DRIVING-FIXTURE-A1"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._LENS_DRIVING_MECHANICAL_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "mechanical_phrase_counts": {
                "imaging lens driving module": 1,
                "image capturing apparatus": 1,
                "electronic device": 1,
                "driving mechanism": 1,
                "carrier": 2,
                "magnet": 1,
                "coil": 1,
            },
        },
    )
    return patent_id


def _non_optical_zone_stray_light_only_fixture(
    *,
    prescription_marker: bool = False,
) -> str:
    parts = [
        "IMAGING LENS ASSEMBLY AND OPTICAL VERIFICATION SYSTEM",
        "Family ID: 79907355",
        "field of view (FOV) greater than 120 degrees " * 2,
        "first connection portion " * 2,
        "non-optical zone " * 3,
        "stray light " * 2,
        "three-piece optical lens assembly",
        "curvature radius " * 2,
    ]
    if prescription_marker:
        parts.append("Surface # Radius Thickness Abbe #")
    return " ".join(parts)


def _install_non_optical_zone_fixture_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-NON-OPTICAL-ZONE-FIXTURE-A1"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._NON_OPTICAL_ZONE_STRAY_LIGHT_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "architecture_phrase_counts": {
                "Family ID: 79907355": 1,
                "field of view (FOV) greater than 120 degrees": 2,
                "first connection portion": 2,
                "non-optical zone": 3,
                "stray light": 2,
                "three-piece optical lens assembly": 1,
                "curvature radius": 2,
            },
        },
    )
    return patent_id


def _barcode_scanner_architecture_only_fixture(
    *,
    prescription_marker: bool = False,
) -> str:
    parts = [
        "SYSTEMS AND METHODS TO IDENTIFY BARCODES OF INTEREST USING A "
        "NON-INTERNET CONNECTED BARCODE SCANNER",
        "Family ID: 98700212",
        "barcode " * 5,
        "non-internet-connected barcode " * 2,
        "imaging lens assembly " * 2,
        "image sensor " * 3,
        "field of view " * 2,
        "return light " * 5,
        "illumination assembly",
        "aiming light " * 3,
    ]
    if prescription_marker:
        parts.append("Surface # Curvature Radius")
    return " ".join(parts)


def _install_barcode_scanner_fixture_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-BARCODE-SCANNER-FIXTURE-A1"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._BARCODE_SCANNER_ARCHITECTURE_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "architecture_phrase_counts": {
                "Family ID: 98700212": 1,
                "barcode": 9,
                "non-internet-connected barcode": 2,
                "imaging lens assembly": 2,
                "image sensor": 3,
                "field of view": 2,
                "return light": 5,
                "illumination assembly": 1,
                "aiming light": 3,
            },
        },
    )
    return patent_id


def _imaging_lens_system_architecture_only_fixture(
    *,
    prescription_marker: bool = False,
) -> str:
    parts = [
        "IMAGING LENS SYSTEM, IMAGE CAPTURING MODULE AND ELECTRONIC DEVICE",
        "Family ID: 79321029",
        "imaging lens system " * 3,
        "image capturing module " * 2,
        "electronic device " * 2,
        "optical path " * 3,
        "lens element " * 4,
        "aperture element " * 3,
        "field of view " * 2,
        "focal length " * 3,
        "equivalent focal length " * 2,
        "thermal expansion coefficients",
    ]
    if prescription_marker:
        parts.append("Surface # Radius")
    return " ".join(parts)


def _install_imaging_lens_system_fixture_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-IMAGING-LENS-SYSTEM-FIXTURE-B2"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._IMAGING_LENS_SYSTEM_ARCHITECTURE_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "architecture_phrase_counts": {
                "Family ID: 79321029": 1,
                "imaging lens system": 4,
                "image capturing module": 3,
                "electronic device": 3,
                "optical path": 3,
                "lens element": 4,
                "aperture element": 3,
                "field of view": 2,
                "focal length": 5,
                "equivalent focal length": 2,
                "thermal expansion coefficients": 1,
            },
        },
    )
    return patent_id


def _extended_depth_of_focus_architecture_only_fixture(
    *,
    prescription_marker: bool = False,
    table_header_drift: bool = False,
) -> str:
    table_2_header = (
        "Changed clinical endpoint."
        if table_header_drift
        else "Summary of the effect of the invented element on far vision."
    )
    parts = [
        "OPTICAL METHOD AND SYSTEM FOR EXTENDED DEPTH OF FOCUS",
        "Family ID: 46327306",
        "extended depth of focus " * 2,
        "phase mask " * 2,
        "phase-affecting " * 2,
        "non-diffractive " * 2,
        "focal length " * 2,
        "field of view " * 2,
        "FIG. 1A is a schematic illustration",
        "TABLE-US-00001 TABLE 1 Summary of the reading test.",
        f"TABLE-US-00002 TABLE 2 {table_2_header}",
    ]
    if prescription_marker:
        parts.append("Surface # Radius Thickness Abbe number")
    return " ".join(parts)


def _install_extended_depth_of_focus_fixture_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-EDOF-PHASE-ELEMENT-FIXTURE-A1"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._EXTENDED_DEPTH_OF_FOCUS_ARCHITECTURE_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "architecture_phrase_counts": {
                "Family ID: 46327306": 1,
                "extended depth of focus": 3,
                "phase mask": 2,
                "phase-affecting": 2,
                "non-diffractive": 2,
                "focal length": 2,
                "field of view": 2,
            },
            "drawing_anchor_counts": {
                "FIG. 1A is a schematic illustration": 1,
            },
        },
    )
    return patent_id


def _light_blocking_geometry_only_fixture(
    *,
    prescription_marker: bool = False,
) -> str:
    parts = [
        "IMAGING LENS ASSEMBLY MODULE, CAMERA MODULE AND ELECTRONIC DEVICE",
        "Family ID: 78608859",
        "imaging lens assembly module " * 3,
        "light blocking structure " * 3,
        "light blocking opening " * 4,
        "first curvature radius " * 2,
        "second curvature radius " * 2,
        "lens element " * 3,
        "field of view " * 2,
        "TABLE-US-00001 TABLE 1 D (mm) 5.66 FOV (degree) 10.1 N 3",
    ]
    if prescription_marker:
        parts.append("Surface # Radius Thickness Abbe #")
    return " ".join(parts)


def _install_light_blocking_geometry_fixture_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-LIGHT-BLOCKING-GEOMETRY-FIXTURE-A1"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._LIGHT_BLOCKING_GEOMETRY_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "table_count": 1,
            "geometry_phrase_counts": {
                "Family ID: 78608859": 1,
                "imaging lens assembly module": 4,
                "light blocking structure": 3,
                "light blocking opening": 4,
                "first curvature radius": 2,
                "second curvature radius": 2,
                "lens element": 3,
                "field of view": 2,
                "FOV (degree)": 1,
            },
        },
    )
    return patent_id


def _folded_tele_missing_f_number_fixture(
    *,
    publish_hfov: bool = False,
    split_conic_header: bool = False,
) -> str:
    parts = [
        "ZOOM DUAL-APERTURE CAMERA WITH FOLDED LENS",
        "Family ID: 55268405",
        "Detailed optical data and aspheric surface data is given in Tables 2 and 3 "
        "for lens module 220 a, in Tables 4 and 5 for lens module 220 b, and in "
        "Tables 6 and 7 for lens module 220 c.",
        "lens module 220 a lens module 220 b lens module 220 c",
        "EFL.sub.T of 12 mm",
        "Wide F-number Tele F-number",
        "TABLE-US-00001 TABLE 1 FIG W L H",
    ]
    for surface_number, asphere_number in ((2, 3), (4, 5), (6, 7)):
        surface_header = (
            "Radius Conic # (R) Distance N.sub.d/V.sub.d Diameter coefficient k"
            if split_conic_header
            else "Conic coefficient # Radius (R) Distance N.sub.d/V.sub.d Diameter k"
        )
        parts.append(
            f"TABLE-US-{surface_number:05d} TABLE {surface_number} {surface_header}"
        )
        parts.append(
            f"TABLE-US-{asphere_number:05d} TABLE {asphere_number} "
            "# α.sub.1 α.sub.2 α.sub.3"
        )
    if publish_hfov:
        parts.append("HFOV = 12.5 degrees")
    return " ".join(parts)


def _install_folded_tele_missing_f_number_fixture_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-FOLDED-TELE-MISSING-FNO-FIXTURE-A1"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._FOLDED_TELE_MISSING_F_NUMBER_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "lens_module_220_c_count": 2,
        },
    )
    return patent_id


def _barrel_spacer_geometry_only_fixture(
    *,
    prescription_marker: bool = False,
) -> str:
    parts = [
        "IMAGING LENS ASSEMBLY, CAMERA MODULE AND ELECTRONIC DEVICE",
        "Family ID: 63640526",
        "imaging lens assembly " * 3,
        "plastic barrel " * 3,
        "spacer " * 3,
        "lens element " * 3,
        "stray light " * 2,
    ]
    for number in range(1, 4):
        parts.append(
            f"TABLE-US-{number:05d} TABLE {number} d (mm) 0.42 "
            "ΦN1i (mm) 2.9 w1 (mm) 0.21 w2 (mm) 0.77 w2/w1 3.67"
        )
    if prescription_marker:
        parts.append("Surface # Radius Thickness Abbe #")
    return " ".join(parts)


def _install_barrel_spacer_geometry_fixture_profile(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> str:
    patent_id = "US-BARREL-SPACER-GEOMETRY-FIXTURE-A1"
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._BARREL_SPACER_GEOMETRY_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "geometry_phrase_counts": {
                "Family ID: 63640526": 1,
                "imaging lens assembly": 4,
                "plastic barrel": 3,
                "spacer": 3,
                "lens element": 3,
                "stray light": 2,
                "d (mm)": 3,
            },
        },
    )
    return patent_id


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


def test_kantatsu_damaged_metadata_never_binds_unlabeled_values() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "9b970512355845fe"
        / "US-20210396957-A1.html"
    )
    raw = source.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        "9b970512355845fe334608f7850c37c952153e6600f2775493f858cf1477f71a"
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        raw.decode("utf-8"),
        patent_id="US-20210396957-A1",
    )

    assert len(attempts) == 4
    assert all(attempt.prescription is None for attempt in attempts)
    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 5))
    assert all(
        "published ih/Fno/half-field labels are absent from the table header" in str(attempt.error)
        for attempt in attempts
    )


def test_kantatsu_damaged_metadata_requires_published_definition() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "9b970512355845fe"
        / "US-20210396957-A1.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "denotes a half field of view",
        "is not defined here",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-20210396957-NO-DEFINITION-A1",
    )

    assert len(attempts) == 4
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "published half-field definition not found" in str(attempt.error) for attempt in attempts
    )


def test_kantatsu_five_lens_same_application_grant_parses_all_examples() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "9563226c2a8ee53f"
        / "US-11947087-B2.html"
    )
    raw = source.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        "9563226c2a8ee53f7b532892296df7f358c63516f248e89924654740541cfc95"
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        raw.decode("utf-8"),
        patent_id="US-20210373295-A1",
    )

    assert len(attempts) == 4
    assert all(attempt.error is None for attempt in attempts)
    assert [
        patent_to_zmx.prescription_fingerprint(attempt.prescription)
        for attempt in attempts
        if attempt.prescription is not None
    ] == [
        "77bceb9d329ad812",
        "b301b599a38b7f59",
        "d2a74b19658a9e56",
        "790e42851dd0715d",
    ]
    first = attempts[0].prescription
    assert first is not None
    assert (first.focal_length_mm, first.f_number, first.hfov_deg) == pytest.approx(
        (3.63, 1.80, 38.5)
    )
    assert [surface.index for surface in first.surfaces] == list(range(1, 15))
    assert first.surfaces[0].label == "Stop"
    assert first.surfaces[1].asphere_coefficients["K"] == pytest.approx(1.094850e-1)
    assert first.surfaces[1].asphere_coefficients["J"] == pytest.approx(-7.714514e-1)
    assert first.surfaces[11].label == "Filter"
    assert (first.surfaces[11].nd, first.surfaces[11].vd) == pytest.approx((1.517, 64.20))
    assert first.surfaces[-1].label == "Image"


def test_kantatsu_five_lens_same_application_grant_requires_half_field_definition() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "9563226c2a8ee53f"
        / "US-11947087-B2.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "denotes a half field of view",
        "is listed in degrees",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-20210373295-NO-DEFINITION-A1",
    )

    assert len(attempts) == 4
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "published half-field definition not found" in str(attempt.error) for attempt in attempts
    )


def test_same_application_grant_recovery_requires_exact_official_linkage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    primary = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "371d425dcf416125"
        / "US-20210373295-A1.html"
    ).read_text(encoding="utf-8")
    grant = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "9563226c2a8ee53f"
        / "US-11947087-B2.html"
    ).read_text(encoding="utf-8")

    async def fake_search(*_args: object) -> list[dict[str, str]]:
        return [{"documentId": "US-11947087-B2", "type": "USPAT"}]

    async def fake_grant_fetch(
        _client: object,
        _token: str,
        publication_id: str,
        source_bucket: str,
    ) -> str:
        assert (publication_id, source_bucket) == ("US-11947087-B2", "USPAT")
        return grant

    monkeypatch.setattr(patent_to_zmx, "_ppubs_search_docs", fake_search)
    monkeypatch.setattr(patent_to_zmx, "_ppubs_patent_html", fake_grant_fetch)
    recovered = asyncio.run(
        patent_to_zmx._recover_same_application_grant_html(
            object(),
            "not-recorded",
            primary_publication_id="US-20210373295-A1",
            primary_fetched=patent_to_zmx.FetchedPatentHtml(
                html=primary,
                source_bucket="US-PGPUB",
            ),
        )
    )

    assert recovered is not None
    assert recovered.publication_id == "US-11947087-B2"
    assert recovered.application_number == "17/391819"
    assert recovered.primary_embedded_tiff_count == 5
    assert recovered.primary_text_table_count == 1
    assert recovered.recovered_text_table_count == 5


def test_ability_grant_prior_publication_binding_is_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    grant = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "b54234c78c881767"
        / "US-11768354-B2.html"
    ).read_text(encoding="utf-8")
    publication = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "8321e4c6f37bd824"
        / "US-20200201001-A1.html"
    ).read_text(encoding="utf-8")

    assert patent_to_zmx._grant_prior_publication_ids(grant) == ("US-20200201001-A1",)
    assert patent_to_zmx._grant_binds_prior_publication(grant, "US-20200201001-A1")
    assert patent_to_zmx._ppubs_application_number(grant) == "16/683826"
    assert patent_to_zmx._ppubs_application_number(publication) == "16/683826"


def test_convert_candidate_retains_primary_recovered_input_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    primary = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "371d425dcf416125"
        / "US-20210373295-A1.html"
    ).read_text(encoding="utf-8")
    grant = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "9563226c2a8ee53f"
        / "US-11947087-B2.html"
    ).read_text(encoding="utf-8")
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-20210373295-A1",
        source_bucket="US-PGPUB",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html=primary,
            source_bucket="US-PGPUB",
            attempts=(source_attempt,),
        )

    async def fake_search(*_args: object) -> list[dict[str, str]]:
        return [{"documentId": "US-11947087-B2", "type": "USPAT"}]

    async def fake_grant_fetch(*_args: object) -> str:
        return grant

    clock = iter((0.0, 2.0, 2.0, 2.0, 2.0))
    monkeypatch.setattr(patent_to_zmx, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_primary_fetch)
    monkeypatch.setattr(patent_to_zmx, "_ppubs_search_docs", fake_search)
    monkeypatch.setattr(patent_to_zmx, "_ppubs_patent_html", fake_grant_fetch)

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-20210373295-A1",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
            patent_budget_seconds=1.0,
        )
    )

    assert len(attempts) == 4
    assert all(attempt.status == "conversion_retry_required" for attempt in attempts)
    assert {attempt.raw_document_sha256 for attempt in attempts} == {
        "371d425dcf4161259f4f6373c5597b9069e99641100d1f7f781a6dbb106a9f8d"
    }
    assert {attempt.parser_input_document_sha256 for attempt in attempts} == {
        "9563226c2a8ee53f7b532892296df7f358c63516f248e89924654740541cfc95"
    }
    assert {attempt.parser_input_publication_id for attempt in attempts} == {
        "US-11947087-B2"
    }
    manifest_paths = {attempt.fulltext_recovery_manifest_path for attempt in attempts}
    assert len(manifest_paths) == 1
    manifest = json.loads(Path(manifest_paths.pop()).read_text(encoding="utf-8"))
    assert manifest["application_number"] == "17/391819"
    assert manifest["primary"]["publication_id"] == "US-20210373295-A1"
    assert manifest["parser_input"]["publication_id"] == "US-11947087-B2"
    assert all(manifest["checks"].values())


def _ability_ocr_token(
    text: str,
    x: float,
    y: float,
    *,
    confidence: float = 0.999,
) -> dict[str, object]:
    return {
        "box": [
            [x - 5.0, y - 5.0],
            [x + 5.0, y - 5.0],
            [x + 5.0, y + 5.0],
            [x - 5.0, y + 5.0],
        ],
        "text": text,
        "confidence": confidence,
    }


def test_pdf_page_identity_ignores_lossless_container_encoding() -> None:
    raster = np.zeros((16, 16), dtype=np.uint8)
    raster[2:14, 7:9] = 255
    ok_fast, fast = cv2.imencode(".png", raster, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    ok_small, small = cv2.imencode(".png", raster, [cv2.IMWRITE_PNG_COMPRESSION, 9])

    assert ok_fast and ok_small
    assert fast.tobytes() != small.tobytes()
    assert patent_pdf_recovery._canonical_raster_sha256(
        fast.tobytes()
    ) == patent_pdf_recovery._canonical_raster_sha256(small.tobytes())


def _ability_pdf_ocr_parser_input(*, low_confidence_radius: bool = False) -> bytes:
    surface_tokens = [
        _ability_ocr_token("Surface", 100.0, 100.0),
        _ability_ocr_token("Curvature", 200.0, 100.0),
        _ability_ocr_token("Thickness", 300.0, 100.0),
        _ability_ocr_token("Refractive", 400.0, 100.0),
        _ability_ocr_token("Abbe", 500.0, 100.0),
    ]
    rows = [
        ("S1", "11.104", "0.724", "1.83", "40.7"),
        ("S2", "5.088", "2.150", None, None),
        ("S3", "10.224", "0.481", "1.75", "53.3"),
        ("S4", "3.473", "2.926", None, None),
        ("S15", "19.027", "1.791", "1.50", "77.6"),
        ("S16", "2.769", "0.398", None, None),
        ("S5", "4.281", "1.915", "2.00", "17.3"),
        ("S6", "-47.168", "0.013", None, None),
        ("St", "8", "0.412", None, None),
        ("S10", "-17.119", "1.353", "1.96", "18.5"),
        ("S11", "4.061", "1.680", "1.62", "64.5"),
        ("S12", "-4.061", "0.355", None, None),
        ("S7", "9.773", "1.841", "1.62", "64.5"),
        ("S8", "-9.773", "3.940", None, None),
        ("Sf1", "8", "0.30", "1.51", "52.1"),
        ("Sf2", "8", "0.60", None, None),
        ("Sc1", "8", "0.50", "1.49", "68.4"),
        ("Sc2", "8", "0.549", None, None),
    ]
    for index, (label, radius, thickness, nd, vd) in enumerate(rows):
        y = 200.0 + index * 40.0
        surface_tokens.extend(
            [
                _ability_ocr_token(label, 100.0, y),
                _ability_ocr_token(
                    radius,
                    200.0,
                    y,
                    confidence=(0.98 if low_confidence_radius and label == "S1" else 0.999),
                ),
                _ability_ocr_token(thickness, 300.0, y),
            ]
        )
        if nd is not None and vd is not None:
            surface_tokens.extend(
                [
                    _ability_ocr_token(nd, 400.0, y),
                    _ability_ocr_token(vd, 500.0, y),
                ]
            )
    final_y = 200.0 + len(rows) * 40.0
    surface_tokens.extend(
        [
            _ability_ocr_token("8", 200.0, final_y),
            _ability_ocr_token("0.00", 300.0, final_y),
            _ability_ocr_token("FIG. 5", 300.0, final_y + 60.0),
        ]
    )
    meta_tokens = []
    for y, label, left, right in (
        (200.0, "F", "2.48", "2.32"),
        (240.0, "FOV", "170", "170"),
        (280.0, "FNO", "2.84", "2.82"),
    ):
        meta_tokens.extend(
            [
                _ability_ocr_token(label, 100.0, y),
                _ability_ocr_token(left, 300.0, y),
                _ability_ocr_token(right, 400.0, y),
            ]
        )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "publication_id": "US-10684452-B2",
        "page_count": 16,
        "pages": [
            {
                "page_number": 4,
                "role": "surface_ol1",
                "official_image_sha256": "1" * 64,
                "mirror_text": "FIG. 2A",
                "rapidocr_tokens": [_ability_ocr_token("FIG. 2A", 1.0, 1.0)],
            },
            {
                "page_number": 5,
                "role": "asphere_ol1",
                "official_image_sha256": "2" * 64,
                "mirror_text": "FIG. 2B",
                "rapidocr_tokens": [_ability_ocr_token("FIG. 2B", 1.0, 1.0)],
            },
            {
                "page_number": 8,
                "role": "surface_ol2",
                "official_image_sha256": "3" * 64,
                "mirror_text": "FIG. 5",
                "rapidocr_tokens": surface_tokens,
            },
            {
                "page_number": 10,
                "role": "system_meta",
                "official_image_sha256": "4" * 64,
                "mirror_text": "FIG. 7",
                "rapidocr_tokens": meta_tokens,
            },
        ],
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _ability_eight_lens_pdf_ocr_parser_input() -> bytes:
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "ability_eight_lens_metadata_unpublished_v1",
        "publication_id": "US-11231565-B2",
        "page_count": 11,
        "source_facts": {
            "primary_html_sha256": "8" * 64,
            "surface_figure_binding_count": 2,
            "asphere_figure_binding_count": 2,
            "fno_definition_count": 1,
            "fov_definition_count": 4,
            "numeric_system_value_assignment_counts": {"F": 0, "FNO": 0, "FOV": 0},
        },
        "pages": [
            {
                "page_number": 4,
                "role": "surface_single",
                "official_image_sha256": "4" * 64,
                "mirror_text": (
                    "Sheet 2 of 4 FIG . 2 Surface Curvature Thickness Abbe Conic"
                ),
                "rapidocr_tokens": [_ability_ocr_token("Surface", 1.0, 1.0)],
            },
            {
                "page_number": 5,
                "role": "asphere_single",
                "official_image_sha256": "5" * 64,
                "mirror_text": "Sheet 3 of 4 FIG . 3 Aspheric coefficient A4 A16",
                "rapidocr_tokens": [_ability_ocr_token("Aspheric", 1.0, 1.0)],
            },
        ],
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _ability_two_nine_lens_pdf_ocr_parser_input() -> bytes:
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "ability_two_nine_lens_f_number_unpublished_v1",
        "publication_id": "US-10690884-B2",
        "page_count": 13,
        "source_facts": {
            "primary_html_sha256": "d" * 64,
            "figure_binding_counts": {
                "FIG. 4A": 1,
                "FIG. 4B": 1,
                "FIG. 5A": 1,
                "FIG. 5B": 1,
                "FIG. 6": 2,
            },
            "f_number_label_counts": {"FNO": 0, "F-number": 0, "F/#": 0},
        },
        "pages": [
            {
                "page_number": 5,
                "role": "prescription_nine_ol1",
                "official_image_sha256": "5" * 64,
                "mirror_text": (
                    "Sheet 4 of 6 FIG . 4A FIG . 4B Surface Curvature Thickness Abbe K A12"
                ),
                "rapidocr_tokens": [_ability_ocr_token("Surface", 1.0, 1.0)],
            },
            {
                "page_number": 6,
                "role": "prescription_nine_ol2",
                "official_image_sha256": "6" * 64,
                "mirror_text": (
                    "Sheet 5 of 6 FIG . 5A FIG . 5B Surface Curvature Thickness Abbe K A12"
                ),
                "rapidocr_tokens": [_ability_ocr_token("Surface", 1.0, 1.0)],
            },
            {
                "page_number": 7,
                "role": "system_meta_nine",
                "official_image_sha256": "7" * 64,
                "mirror_text": "Sheet 6 of 6 FIG . 6 Optical lens OL1 Optical lens OL2 TTL FOV",
                "rapidocr_tokens": [_ability_ocr_token("FOV", 1.0, 1.0)],
            },
        ],
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _ability_four_eight_lens_pdf_ocr_parser_input() -> bytes:
    page_specs = (
        (3, "prescription_eight_ol1", "FIG . 2A FIG . 2B", "A12"),
        (4, "prescription_eight_ol2", "FIG . 4A FIG . 4B", "A12"),
        (6, "prescription_eight_ol3", "FIG . 6A FIG . 6B", "A12"),
        (7, "prescription_eight_ol4", "FIG . 8", ""),
    )
    pages = [
        {
            "page_number": page_number,
            "role": role,
            "official_image_sha256": str(page_number) * 64,
            "mirror_text": (
                f"Sheet {page_number} {figures} Surface Curvature Thickness Abbe {a12}"
            ),
            "rapidocr_tokens": [_ability_ocr_token("Surface", 1.0, 1.0)],
        }
        for page_number, role, figures, a12 in page_specs
    ]
    pages.append(
        {
            "page_number": 8,
            "role": "system_meta_four_eight",
            "official_image_sha256": "8" * 64,
            "mirror_text": (
                "Sheet 7 of 7 FIG . 9 Optical lens OL1 Optical lens OL2 "
                "Optical lens OL3 Optical lens OL4 F1 R1"
            ),
            "rapidocr_tokens": [_ability_ocr_token("F1", 1.0, 1.0)],
        }
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "ability_four_eight_lens_f_number_unpublished_v1",
        "publication_id": "US-10809497-B2",
        "page_count": 14,
        "source_facts": {
            "primary_html_sha256": "a" * 64,
            "figure_binding_counts": {
                "FIG. 2A": 1,
                "FIG. 2B": 1,
                "FIG. 4A": 1,
                "FIG. 4B": 1,
                "FIG. 6A": 1,
                "FIG. 6B": 1,
                "FIG. 8": 1,
                "FIG. 9": 2,
            },
            "f_number_label_counts": {"FNO": 0, "F-number": 0, "F/#": 0},
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _largan_surface_page(
    *,
    embodiment_number: int,
    page_number: int,
    figure_number: int,
    focal_length: float,
) -> dict[str, object]:
    tokens = [
        _ability_ocr_token("Surface #", 100.0, 100.0),
        _ability_ocr_token("Curvature Radius", 200.0, 100.0),
        _ability_ocr_token("Thickness", 300.0, 100.0),
        _ability_ocr_token("Material", 400.0, 100.0),
        _ability_ocr_token("Index", 500.0, 100.0),
        _ability_ocr_token("Abbe #", 600.0, 100.0),
        _ability_ocr_token("0", 100.0, 130.0),
    ]
    for surface_number in range(1, 15):
        y = 130.0 + 30.0 * surface_number
        tokens.append(_ability_ocr_token(str(surface_number), 100.0, y))
        radius = (
            "Plano"
            if surface_number in {1, 12, 13, 14}
            else f"{10.0 + surface_number:.5f} (ASP)"
        )
        tokens.append(_ability_ocr_token(radius, 200.0, y))
        if surface_number != 14:
            tokens.append(_ability_ocr_token("0.100", 300.0, y))
        if surface_number in {2, 4, 6, 8, 10}:
            tokens.extend(
                (
                    _ability_ocr_token("Plastic", 400.0, y),
                    _ability_ocr_token("1.544", 500.0, y),
                    _ability_ocr_token("55.9", 600.0, y),
                )
            )
        elif surface_number == 12:
            tokens.extend(
                (
                    _ability_ocr_token("Glass", 400.0, y),
                    _ability_ocr_token("1.517", 500.0, y),
                    _ability_ocr_token("64.2", 600.0, y),
                )
            )
    table_number = 2 * embodiment_number - 1
    return {
        "page_number": page_number,
        "role": f"largan_surface_{embodiment_number}",
        "official_image_sha256": format(page_number % 16, "x") * 64,
        "mirror_text": (
            f"TABLE {table_number} ( Embodiment {embodiment_number} ) "
            f"f = {focal_length:.2f} mm , Fno = 2.9 , HFOV = 33.0 deg . "
            f"Surface # Curvature Radius Thickness Fig . {figure_number}"
        ),
        "rapidocr_tokens": tokens,
    }


def _largan_asphere_page(
    *,
    embodiment_number: int,
    page_number: int,
    figure_number: int,
) -> dict[str, object]:
    tokens: list[dict[str, object]] = []
    scientific_values: list[str] = []
    row_labels = ("K", "A4", "A6", "A8", "A10", "A12", "A14", "A16")
    for group_index, surfaces in enumerate(((2, 3, 4, 5, 6), (7, 8, 9, 10, 11))):
        header_y = 100.0 + group_index * 400.0
        tokens.append(_ability_ocr_token("Surface #", 100.0, header_y))
        column_xs = [200.0 + 100.0 * index for index in range(5)]
        tokens.extend(
            _ability_ocr_token(str(surface), x, header_y)
            for surface, x in zip(surfaces, column_xs, strict=True)
        )
        for row_index, label in enumerate(row_labels, start=1):
            row_y = header_y + 30.0 * row_index
            tokens.append(_ability_ocr_token(label, 100.0, row_y))
            for column_x in column_xs:
                value = "-1.00000E+00" if label == "K" else "0.00000E+00"
                tokens.append(_ability_ocr_token(value, column_x, row_y))
                scientific_values.append(value)
    table_number = 2 * embodiment_number
    return {
        "page_number": page_number,
        "role": f"largan_asphere_{embodiment_number}",
        "official_image_sha256": format(page_number % 16, "x") * 64,
        "mirror_text": (
            f"TABLE {table_number} Aspheric Coefficients Surface # "
            + " ".join(scientific_values)
            + f" Fig . {figure_number}"
        ),
        "rapidocr_tokens": tokens,
    }


def _largan_three_five_lens_pdf_ocr_parser_input() -> bytes:
    focal_lengths = (5.44, 5.46, 5.47)
    pages: list[dict[str, object]] = []
    for embodiment_number, (surface_page, asphere_page, surface_figure) in enumerate(
        ((8, 9, 7), (10, 11, 9), (12, 13, 11)),
        start=1,
    ):
        pages.extend(
            (
                _largan_surface_page(
                    embodiment_number=embodiment_number,
                    page_number=surface_page,
                    figure_number=surface_figure,
                    focal_length=focal_lengths[embodiment_number - 1],
                ),
                _largan_asphere_page(
                    embodiment_number=embodiment_number,
                    page_number=asphere_page,
                    figure_number=surface_figure + 1,
                ),
            )
        )
    meta_tokens = [
        _ability_ocr_token("Embodiment Embodiment Embodiment", 100.0, 100.0),
        *(
            _ability_ocr_token(str(index), 100.0 + index * 100.0, 130.0)
            for index in range(1, 4)
        ),
    ]
    for label, y, values in (
        ("f", 160.0, focal_lengths),
        ("Fno", 190.0, (2.9, 2.9, 2.9)),
        ("HFOV", 220.0, (33.0, 33.0, 33.0)),
    ):
        meta_tokens.append(_ability_ocr_token(label, 100.0, y))
        meta_tokens.extend(
            _ability_ocr_token(str(value), 100.0 + index * 100.0, y)
            for index, value in enumerate(values, start=1)
        )
    pages.append(
        {
            "page_number": 14,
            "role": "largan_system_meta",
            "official_image_sha256": "e" * 64,
            "mirror_text": "TABLE 7 Embodiment f Fno HFOV TTL ImgH Fig . 13",
            "rapidocr_tokens": meta_tokens,
        }
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "largan_three_five_lens_prescriptions_v1",
        "publication_id": "US-12449639-B2",
        "page_count": 21,
        "source_facts": {
            "primary_html_sha256": "e" * 64,
            "figure_binding_counts": {
                f"FIG. {number}": 1 for number in range(7, 14)
            },
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _ability_zoom_two_state_pdf_ocr_parser_input() -> bytes:
    pages = []
    for role, page_number, figure in (
        ("ability_zoom_telescopic", 4, 3),
        ("ability_zoom_wide", 5, 4),
    ):
        tokens = [
            _ability_ocr_token("Surface", 100.0, 100.0),
            _ability_ocr_token("Curvature", 200.0, 100.0),
            _ability_ocr_token("index", 400.0, 100.0),
            _ability_ocr_token("Abbe", 500.0, 100.0),
            _ability_ocr_token("S1", 100.0, 150.0),
            _ability_ocr_token("S2", 100.0, 200.0, confidence=0.94),
            _ability_ocr_token("STO", 100.0, 250.0),
            _ability_ocr_token("S3", 100.0, 300.0),
            _ability_ocr_token("S4", 100.0, 350.0),
            _ability_ocr_token("IMA", 100.0, 400.0),
        ]
        pages.append(
            {
                "page_number": page_number,
                "role": role,
                "official_image_sha256": str(page_number) * 64,
                "mirror_text": (
                    f"FIG . {figure} Surface Curvature Thickness Refractive Abbe"
                ),
                "rapidocr_tokens": tokens,
            }
        )
    pages.extend(
        (
            {
                "page_number": 6,
                "role": "ability_zoom_asphere",
                "official_image_sha256": "6" * 64,
                "mirror_text": "FIG . 5 S24 S23 K A2 A4",
                "rapidocr_tokens": [_ability_ocr_token("S24", 1.0, 1.0)],
            },
            {
                "page_number": 7,
                "role": "ability_zoom_meta",
                "official_image_sha256": "7" * 64,
                "mirror_text": "FIG . 6 Fw Ft TTL Fno FOVt FOVw",
                "rapidocr_tokens": [_ability_ocr_token("Fw", 1.0, 1.0)],
            },
        )
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "ability_zoom_two_state_census_v1",
        "publication_id": "US-20210373301-A1",
        "page_count": 14,
        "source_facts": {
            "primary_html_sha256": "c" * 64,
            "figure_binding_counts": {
                "FIG. 3": 1,
                "FIG. 4": 1,
                "FIG. 5": 1,
                "FIG. 6": 2,
            },
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _circle_optics_seven_lens_pdf_ocr_parser_input() -> bytes:
    pages = []
    for prefix, role, page_number, figure in (
        ("a", "circle_optics_surface_table", 17, "FIG.8C-1"),
        ("b", "circle_optics_asphere_table", 18, "FIG.8C-2"),
    ):
        tokens = [
            _ability_ocr_token(figure, 500.0, 500.0),
        ]
        if role == "circle_optics_surface_table":
            tokens.append(_ability_ocr_token("Lens Prescription", 800.0, 500.0))
            tokens.append(_ability_ocr_token("1.42", 500.0, 800.0, confidence=0.995))
        pages.append(
            {
                "page_number": page_number,
                "role": role,
                "official_image_sha256": prefix * 64,
                "mirror_text": "",
                "rapidocr_rotation": "clockwise_90",
                "rapidocr_tokens": tokens,
            }
        )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "circle_optics_seven_lens_ocr_review_v1",
        "publication_id": "US-12313825-B2",
        "page_count": 66,
        "source_facts": {
            "primary_html_sha256": (
                "f39a32f7a1eb5004447f43fc12e3bd60c06a55f4f4c50d26e4375e61b17bd154"
            ),
            "family_id": "74060373",
            "application_number": "17/622463",
            "required_text_counts": dict.fromkeys(
                patent_pdf_recovery._CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT,
                1,
            ),
            "lens_element_count": 7,
            "aspheric_lens_element_count": 3,
            "f_number": 2.0,
            "nominal_focal_length_mm": 2.57,
            "aperture_stop_diameter_mm": 1.42,
            "track_length_mm": 50.0,
            "image_width_mm": 3.9,
            "design_wavelengths_nm": [450, 587, 656],
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _kodak_low_stress_pdf_ocr_parser_input() -> bytes:
    pages = []
    page_specs = (
        (
            "c",
            "kodak_projection_prescription",
            36,
            (
                "FIG. 14A",
                "Surface",
                "RADIUS",
                "THICKNESS",
                "APERTURE",
                "GLASS",
                "OBJECT (SCREEN)",
                "STOP",
                "IMAGE (INT IMG)",
            ),
        ),
        (
            "d",
            "kodak_relay_prescription",
            37,
            (
                "FIG. 14B",
                "Surface",
                "RADIUS",
                "THICKNESS",
                "APERTURE",
                "GLASS",
                "OBJECT (DLP)",
                "APERTURE STOP",
                "INT IMAGE",
            ),
        ),
    )
    for prefix, role, page_number, labels in page_specs:
        pages.append(
            {
                "page_number": page_number,
                "role": role,
                "official_image_sha256": prefix * 64,
                "mirror_text": "",
                "rapidocr_rotation": "counterclockwise_90",
                "rapidocr_tokens": [
                    _ability_ocr_token(label, 100.0 + index * 20.0, 100.0)
                    for index, label in enumerate(labels)
                ],
            }
        )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "kodak_low_stress_two_lens_metadata_unpublished_v1",
        "publication_id": "US-20140036377-A1",
        "page_count": 61,
        "source_facts": {
            "primary_html_sha256": (
                "2efe34e5641c40bcb2c93d330d9288271b19f2d851f1bba26e03aef85d269819"
            ),
            "normalized_text_sha256": (
                "8affd3aaf0079a69bd7d4a8e68fb31a653b857f6bcbd352b9666d696cd2be572"
            ),
            "family_id": "44121309",
            "application_number": "14/042755",
            "required_text_counts": dict.fromkeys(
                patent_pdf_recovery._KODAK_LOW_STRESS_REQUIRED_TEXT,
                1,
            ),
            "f_number_context_counts": dict.fromkeys(
                patent_pdf_recovery._KODAK_LOW_STRESS_F_NUMBER_CONTEXTS,
                1,
            ),
            "numeric_system_value_assignment_counts": {
                "F": 0,
                "FNO": 0,
                "FOV": 0,
                "HFOV": 0,
                "EFL": 0,
            },
            "effective_focal_length_count": 0,
            "focal_length_count": 3,
            "field_of_view_count": 1,
            "prescription_count": 2,
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_four_lens_eleven_pdf_ocr_parser_input() -> bytes:
    pages = []
    figure_counts = {}
    for embodiment_number in range(1, 12):
        optical_figure = 2 if embodiment_number == 1 else 4 * embodiment_number - 1
        asphere_figure = 4 * embodiment_number
        figure_counts[f"FIG. {optical_figure}"] = 1
        figure_counts[f"FIG. {asphere_figure}"] = 1
        prefix = str(embodiment_number)
        optical_tokens = [
            _ability_ocr_token(f"Sheet {optical_figure} of 48", 700.0, 50.0),
            _ability_ocr_token("Surface#", 100.0, 100.0),
            _ability_ocr_token("Radius", 200.0, 100.0),
        ]
        for row, suffix in enumerate(
            ("00", "11", "12", "21", "22", "31", "32", "41", "42", "51", "52", "60"),
            start=1,
        ):
            optical_tokens.append(
                _ability_ocr_token(f"{prefix}{suffix}", 100.0, 140.0 + row * 40.0)
            )
        pages.append(
            {
                "page_number": optical_figure + 1,
                "role": f"genius_optical_{embodiment_number}",
                "official_image_sha256": f"{embodiment_number % 10}" * 64,
                "mirror_text": f"Sheet {optical_figure} of 48",
                "rapidocr_tokens": optical_tokens,
            }
        )

        asphere_tokens = [
            _ability_ocr_token(f"Sheet {asphere_figure} of 48", 700.0, 50.0),
            _ability_ocr_token("Surface#", 100.0, 100.0),
            _ability_ocr_token("Surface#", 100.0, 500.0),
        ]
        for column, suffix in enumerate(("11", "12", "21", "22", "31", "32", "41", "42")):
            asphere_tokens.append(
                _ability_ocr_token(f"{prefix}{suffix}", 200.0 + column * 50.0, 100.0)
            )
        for block_y in (150.0, 550.0):
            for row, label in enumerate(("K", "a4", "a6", "a8", "a10", "a12", "a14", "a16")):
                asphere_tokens.append(
                    _ability_ocr_token(label, 100.0, block_y + row * 35.0)
                )
        pages.append(
            {
                "page_number": asphere_figure + 1,
                "role": f"genius_asphere_{embodiment_number}",
                "official_image_sha256": f"{(embodiment_number + 1) % 10}" * 64,
                "mirror_text": f"Sheet {asphere_figure} of 48",
                "rapidocr_tokens": asphere_tokens,
            }
        )

    comparison_tokens = [_ability_ocr_token("Sheet 46 of 48", 700.0, 50.0)]
    for panel, value_count in enumerate((4, 4, 3), start=1):
        y = 100.0 + panel * 100.0
        comparison_tokens.append(_ability_ocr_token("Fno", 100.0, y))
        for column in range(value_count):
            comparison_tokens.append(
                _ability_ocr_token(f"{2.5 + column / 10:.1f}", 200.0 + column * 100.0, y)
            )
    pages.append(
        {
            "page_number": 47,
            "role": "genius_comparison",
            "official_image_sha256": "f" * 64,
            "mirror_text": "Sheet 46 of 48 FIG. 46 Fno",
            "rapidocr_tokens": comparison_tokens,
        }
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_four_lens_eleven_embodiment_census_v1",
        "publication_id": "US-20170097490-A1",
        "page_count": 66,
        "source_facts": {
            "primary_html_sha256": (
                "0211f3fe1bdd3152ab6c57c25e4991603504980b37398c9ae5cbcb9812c43dea"
            ),
            "figure_binding_counts": figure_counts,
            "comparison_binding_counts": {
                "FIG. 46 shows a comparison table": 1,
                "all 11 example embodiments shown in FIGS. 1": 1,
            },
            "fno_label_count": 1,
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_nine_lens_eleven_pdf_ocr_parser_input() -> bytes:
    pages = []
    for embodiment_number in range(1, 12):
        optical_page_number = 7 + (embodiment_number - 1) * 4
        asphere_page_number = optical_page_number + 1
        optical_tokens = [
            _ability_ocr_token(
                f"Sheet {optical_page_number - 2} of 48",
                700.0,
                50.0,
            ),
            _ability_ocr_token(
                "EFL = 1 ; HFOV = 2 ; TTL = 3 ; Fno = 4 ; Image Height = 5",
                100.0,
                100.0,
            ),
            *(
                _ability_ocr_token(label, 100.0 + index * 100.0, 150.0)
                for index, label in enumerate(
                    ("Surface #", "curvature", "Thickness", "Material", "index", "number")
                )
            ),
        ]
        pages.append(
            {
                "page_number": optical_page_number,
                "role": f"genius_nine_eleven_optical_{embodiment_number}",
                "official_image_sha256": str(embodiment_number % 10) * 64,
                "mirror_text": "",
                "rapidocr_tokens": optical_tokens,
            }
        )
        pages.append(
            {
                "page_number": asphere_page_number,
                "role": f"genius_nine_eleven_asphere_{embodiment_number}",
                "official_image_sha256": str((embodiment_number + 1) % 10) * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(
                        f"Sheet {asphere_page_number - 2} of 48",
                        700.0,
                        50.0,
                    ),
                    *(
                        _ability_ocr_token(label, 100.0 + index * 80.0, 100.0)
                        for index, label in enumerate(
                            ("Surface", "K", "a4", "a6", "a8", "a10", "a12", "a14", "a16")
                        )
                    ),
                ],
            }
        )
    for comparison, (page_number, sheet_number) in enumerate(((49, 47), (50, 48)), start=1):
        pages.append(
            {
                "page_number": page_number,
                "role": f"genius_nine_eleven_comparison_{comparison}",
                "official_image_sha256": "f" * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(f"Sheet {sheet_number} of 48", 700.0, 50.0)
                ],
            }
        )
    markers = patent_pdf_recovery._GENIUS_NINE_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_NINE_LENS_ELEVEN_COMPARISON_MARKERS
    source = " ".join(
        (*markers, *comparisons, *("Genius Electronic Optical (Xiamen) Co., Ltd.",) * 2)
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_nine_lens_eleven_embodiment_census_v1",
        "publication_id": "US-12625349-B2",
        "page_count": 65,
        "source_facts": patent_pdf_recovery._genius_nine_lens_eleven_source_facts(source),
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_eight_lens_fourteen_pdf_ocr_parser_input() -> bytes:
    pages = []
    for embodiment_number in range(1, 15):
        optical_page_number = 5 + (embodiment_number - 1) * 3
        asphere_page_number = optical_page_number + 1
        optical_tokens = [
            _ability_ocr_token(
                f"Sheet {optical_page_number - 1} of 46",
                700.0,
                50.0,
            ),
            *(
                _ability_ocr_token(f"{label}=1.0", 100.0 + index * 100.0, 100.0)
                for index, label in enumerate(("EFL", "HFOV", "TTL", "Fno", "Image height"))
            ),
            *(
                _ability_ocr_token(label, 100.0 + index * 100.0, 150.0)
                for index, label in enumerate(
                    ("Surface", "Radius", "Thickness", "Material", "index", "number")
                )
            ),
        ]
        pages.append(
            {
                "page_number": optical_page_number,
                "role": f"genius_eight_fourteen_optical_{embodiment_number}",
                "official_image_sha256": str(embodiment_number % 10) * 64,
                "mirror_text": "",
                "rapidocr_tokens": optical_tokens,
            }
        )
        asphere_tokens = [
            _ability_ocr_token(
                f"Sheet {asphere_page_number - 1} of 46",
                700.0,
                50.0,
            ),
            _ability_ocr_token("Surface", 900.0, 100.0),
            *(
                _ability_ocr_token(label, 100.0 + index * 80.0, 100.0)
                for index, label in enumerate(
                    ("Surface", "K", "a2", "a4", "a6", "a8", "a10", "a12", "a14", "a16")
                )
            ),
        ]
        pages.append(
            {
                "page_number": asphere_page_number,
                "role": f"genius_eight_fourteen_asphere_{embodiment_number}",
                "official_image_sha256": str((embodiment_number + 1) % 10) * 64,
                "mirror_text": "",
                "rapidocr_tokens": asphere_tokens,
            }
        )
    for comparison, (page_number, sheet_number) in enumerate(((46, 45), (47, 46)), start=1):
        pages.append(
            {
                "page_number": page_number,
                "role": f"genius_eight_fourteen_comparison_{comparison}",
                "official_image_sha256": "f" * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(f"Sheet {sheet_number} of 46", 700.0, 50.0)
                ],
            }
        )
    markers = patent_pdf_recovery._GENIUS_EIGHT_LENS_FOURTEEN_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_EIGHT_LENS_FOURTEEN_COMPARISON_MARKERS
    source = " ".join(
        (*markers, *comparisons, *("Genius Electronic Optical (Xiamen) Co., Ltd.",) * 2)
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_eight_lens_fourteen_embodiment_census_v1",
        "publication_id": "US-20250020895-A1",
        "page_count": 64,
        "source_facts": patent_pdf_recovery._genius_eight_lens_fourteen_source_facts(source),
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_six_lens_ten_dual_focus_pdf_ocr_parser_input() -> bytes:
    pages = []
    for embodiment_number in range(1, 11):
        optical_page_number = 24 + (embodiment_number - 1) * 2
        asphere_page_number = optical_page_number + 1
        pages.append(
            {
                "page_number": optical_page_number,
                "role": f"genius_six_ten_dual_optical_{embodiment_number}",
                "official_image_sha256": str(embodiment_number % 10) * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(
                        f"Sheet {optical_page_number - 1} of 46",
                        700.0,
                        50.0,
                    ),
                    _ability_ocr_token(
                        "EFL=1, EFLA=2, Fno at first focusing state=3",
                        100.0,
                        100.0,
                    ),
                    _ability_ocr_token(
                        "Fno at second focusing state=4, "
                        "HFOV at first focusing state=5",
                        100.0,
                        140.0,
                    ),
                    _ability_ocr_token(
                        "HFOV at second focusing state=6, TTL=7, ImgH=8",
                        100.0,
                        180.0,
                    ),
                ],
            }
        )
        pages.append(
            {
                "page_number": asphere_page_number,
                "role": f"genius_six_ten_dual_asphere_{embodiment_number}",
                "official_image_sha256": str((embodiment_number + 1) % 10) * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(
                        f"Sheet {asphere_page_number - 1} of 46",
                        700.0,
                        50.0,
                    ),
                    *(
                        _ability_ocr_token(label, 100.0 + index * 80.0, 100.0)
                        for index, label in enumerate(
                            ("K", "a4", "a6", "a8", "a10", "a12", "a14", "a16", "a18", "a20")
                        )
                    ),
                ],
            }
        )
    for comparison in range(1, 5):
        page_number = 43 + comparison
        pages.append(
            {
                "page_number": page_number,
                "role": f"genius_six_ten_dual_comparison_{comparison}",
                "official_image_sha256": "f" * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(
                        f"Sheet {page_number - 1} of 46",
                        700.0,
                        50.0,
                    )
                ],
            }
        )
    markers = patent_pdf_recovery._GENIUS_SIX_LENS_TEN_DUAL_FOCUS_REQUIRED_FIGURE_TEXT
    comparison = (
        patent_pdf_recovery._GENIUS_SIX_LENS_TEN_DUAL_FOCUS_COMPARISON_MARKER
    )
    source = " ".join(
        (
            *markers,
            comparison,
            *("first focusing state",) * 200,
            *("second focusing state",) * 206,
            *("optical imaging lens of six lens elements",) * 2,
        )
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_six_lens_ten_dual_focus_census_v1",
        "publication_id": "US-12656578-B2",
        "page_count": 64,
        "source_facts": patent_pdf_recovery._genius_six_lens_ten_dual_focus_source_facts(
            source
        ),
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_six_lens_five_pdf_ocr_parser_input() -> bytes:
    pages = []
    for embodiment_number in range(1, 6):
        optical_page_number = 6 + (embodiment_number - 1) * 3
        asphere_page_number = optical_page_number + 1
        optical_sheet = optical_page_number - 1
        asphere_sheet = asphere_page_number - 1
        optical_tokens = [
            _ability_ocr_token(f"Sheet {optical_sheet} of 20", 700.0, 50.0),
            *(
                _ability_ocr_token(f"{label}=1.0", 100.0 + index * 100.0, 100.0)
                for index, label in enumerate(("EFL", "HFOV", "TTL", "Fno", "LCR"))
            ),
            *(
                _ability_ocr_token(label, 100.0 + index * 100.0, 150.0)
                for index, label in enumerate(("surface", "radius", "thickness", "Abbe"))
            ),
        ]
        pages.append(
            {
                "page_number": optical_page_number,
                "role": f"genius_six_optical_{embodiment_number}",
                "official_image_sha256": str(embodiment_number) * 64,
                "mirror_text": "",
                "rapidocr_tokens": optical_tokens,
            }
        )
        asphere_tokens = [
            _ability_ocr_token(f"Sheet {asphere_sheet} of 20", 700.0, 50.0),
            _ability_ocr_token("surface", 900.0, 100.0),
            *(
                _ability_ocr_token(label, 100.0 + index * 80.0, 100.0)
                for index, label in enumerate(
                    ("surface", "K", "a2", "a4", "a6", "a8", "a10", "a12", "a14", "a16")
                )
            ),
        ]
        pages.append(
            {
                "page_number": asphere_page_number,
                "role": f"genius_six_asphere_{embodiment_number}",
                "official_image_sha256": str(embodiment_number + 1) * 64,
                "mirror_text": "",
                "rapidocr_tokens": asphere_tokens,
            }
        )

    for index, (page_number, sheet_number) in enumerate(((20, 19), (21, 20)), start=1):
        pages.append(
            {
                "page_number": page_number,
                "role": f"genius_six_comparison_{index}",
                "official_image_sha256": "f" * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(f"Sheet {sheet_number} of 20", 700.0, 50.0)
                ],
            }
        )

    figure_counts = {
        marker.split(" shows", maxsplit=1)[0]: 1
        for marker in patent_pdf_recovery._GENIUS_SIX_LENS_FIVE_REQUIRED_FIGURE_TEXT
    }
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_six_lens_five_embodiment_census_v1",
        "publication_id": "US-20240369810-A1",
        "page_count": 34,
        "source_facts": {
            "primary_html_sha256": "d" * 64,
            "figure_binding_counts": figure_counts,
            "comparison_binding_count": 1,
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_four_lens_nine_pdf_ocr_parser_input() -> bytes:
    pages = []
    for embodiment_number in range(1, 10):
        optical_page_number = 5 + (embodiment_number - 1) * 3
        asphere_page_number = optical_page_number + 1
        pages.append(
            {
                "page_number": optical_page_number,
                "role": f"genius_four_nine_optical_{embodiment_number}",
                "official_image_sha256": str(embodiment_number) * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(
                        f"Sheet {optical_page_number - 1} of 33", 700.0, 50.0
                    ),
                    _ability_ocr_token(
                        "System length=1, EFL=2, HFOV=3, Fno=4", 100.0, 100.0
                    ),
                    *(
                        _ability_ocr_token(label, 100.0 + index * 100.0, 150.0)
                        for index, label in enumerate(
                            ("Surface", "curvature", "Material", "index", "number")
                        )
                    ),
                ],
            }
        )
        pages.append(
            {
                "page_number": asphere_page_number,
                "role": f"genius_four_nine_asphere_{embodiment_number}",
                "official_image_sha256": str((embodiment_number + 1) % 10) * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(
                        f"Sheet {asphere_page_number - 1} of 33", 700.0, 50.0
                    ),
                    _ability_ocr_token("Surface", 900.0, 100.0),
                    *(
                        _ability_ocr_token(label, 100.0 + index * 80.0, 100.0)
                        for index, label in enumerate(
                            ("Surface", "K", "a4", "a6", "a8", "a10", "a12", "a14", "a16")
                        )
                    ),
                ],
            }
        )
    for comparison in range(1, 5):
        page_number = 30 + comparison
        pages.append(
            {
                "page_number": page_number,
                "role": f"genius_four_nine_comparison_{comparison}",
                "official_image_sha256": "f" * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(f"Sheet {page_number - 1} of 33", 700.0, 50.0)
                ],
            }
        )
    markers = patent_pdf_recovery._GENIUS_FOUR_LENS_NINE_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_FOUR_LENS_NINE_COMPARISON_MARKERS
    source = " ".join((*markers, *comparisons))
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_four_lens_nine_embodiment_census_v1",
        "publication_id": "US-20260186247-A1",
        "page_count": 47,
        "source_facts": patent_pdf_recovery._genius_four_lens_nine_source_facts(source),
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_six_lens_nine_pdf_ocr_parser_input() -> bytes:
    pages = []
    for embodiment_number in range(1, 10):
        optical_page_number = 6 + (embodiment_number - 1) * 3
        asphere_page_number = optical_page_number + 1
        optical_tokens = [
            _ability_ocr_token(f"Sheet {optical_page_number - 1} of 32", 700.0, 50.0),
            _ability_ocr_token(
                "Effective focal length (EFL) = 1, Half field of view (HFOV) = 2, "
                "System length (TTL) = 3, F-number (Fno) = 4, "
                "Light circle radius (LCR) = 5",
                100.0,
                100.0,
            ),
            *(
                _ability_ocr_token(label, 100.0 + index * 100.0, 150.0)
                for index, label in enumerate(("surface", "radius", "thickness", "Abbe"))
            ),
        ]
        pages.append(
            {
                "page_number": optical_page_number,
                "role": f"genius_six_optical_{embodiment_number}",
                "official_image_sha256": str(embodiment_number) * 64,
                "mirror_text": "",
                "rapidocr_tokens": optical_tokens,
            }
        )
        asphere_tokens = [
            _ability_ocr_token(f"Sheet {asphere_page_number - 1} of 32", 700.0, 50.0),
            _ability_ocr_token("surface", 900.0, 100.0),
            *(
                _ability_ocr_token(label, 100.0 + index * 80.0, 100.0)
                for index, label in enumerate(
                    ("surface", "K", "a2", "a4", "a6", "a8", "a10", "a12", "a14", "a16")
                )
            ),
        ]
        pages.append(
            {
                "page_number": asphere_page_number,
                "role": f"genius_six_asphere_{embodiment_number}",
                "official_image_sha256": str((embodiment_number + 1) % 10) * 64,
                "mirror_text": "",
                "rapidocr_tokens": asphere_tokens,
            }
        )

    for index, (page_number, sheet_number) in enumerate(((32, 31), (33, 32)), start=1):
        pages.append(
            {
                "page_number": page_number,
                "role": f"genius_six_comparison_{index}",
                "official_image_sha256": "f" * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(f"Sheet {sheet_number} of 32", 700.0, 50.0)
                ],
            }
        )

    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_six_lens_nine_embodiment_census_v1",
        "publication_id": "US-20260036791-A1",
        "page_count": 51,
        "source_facts": {
            "primary_html_sha256": "e" * 64,
            "figure_binding_counts": {
                marker.split(" shows", maxsplit=1)[0]: 1
                for marker in patent_pdf_recovery._GENIUS_SIX_LENS_NINE_REQUIRED_FIGURE_TEXT
            },
            "comparison_binding_counts": {
                marker.split(" shows", maxsplit=1)[0]: 1
                for marker in patent_pdf_recovery._GENIUS_SIX_LENS_NINE_COMPARISON_MARKERS
            },
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_six_lens_nine_variant_pdf_ocr_parser_input(
    *,
    profile: str,
    publication_id: str,
    page_count: int,
    sheet_count: int,
    comparison_count: int,
    source_facts: dict[str, object],
) -> bytes:
    payload = json.loads(_genius_six_lens_nine_pdf_ocr_parser_input())
    payload["profile"] = profile
    payload["publication_id"] = publication_id
    payload["page_count"] = page_count
    payload["source_facts"] = source_facts
    pages = [
        page
        for page in payload["pages"]
        if not page["role"].startswith("genius_six_comparison_")
    ]
    for page in pages:
        for token in page["rapidocr_tokens"]:
            token["text"] = re.sub(r"of 32\b", f"of {sheet_count}", token["text"])
    for comparison in range(1, comparison_count + 1):
        page_number = 31 + comparison
        pages.append(
            {
                "page_number": page_number,
                "role": f"genius_six_comparison_{comparison}",
                "official_image_sha256": "f" * 64,
                "mirror_text": "",
                "rapidocr_tokens": [
                    _ability_ocr_token(
                        f"Sheet {page_number - 1} of {sheet_count}",
                        700.0,
                        50.0,
                    )
                ],
            }
        )
    payload["pages"] = pages
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_six_lens_nine_three_comparison_pdf_ocr_parser_input() -> bytes:
    markers = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_THREE_COMPARISON_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_THREE_COMPARISON_MARKERS
    source = " ".join((*markers, *comparisons))
    return _genius_six_lens_nine_variant_pdf_ocr_parser_input(
        profile="genius_six_lens_nine_three_comparison_census_v1",
        publication_id="US-20260186249-A1",
        page_count=48,
        sheet_count=33,
        comparison_count=3,
        source_facts=patent_pdf_recovery._genius_six_lens_nine_three_comparison_source_facts(
            source
        ),
    )


def _genius_six_lens_nine_four_comparison_pdf_ocr_parser_input() -> bytes:
    markers = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_MARKERS
    expected = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_EXPECTED_COUNTS
    source_parts = list(markers)
    for marker, count in zip(comparisons, expected, strict=True):
        source_parts.extend([marker] * count)
    source = " ".join(source_parts)
    return _genius_six_lens_nine_variant_pdf_ocr_parser_input(
        profile="genius_six_lens_nine_four_comparison_census_v1",
        publication_id="US-20260186250-A1",
        page_count=50,
        sheet_count=34,
        comparison_count=4,
        source_facts=patent_pdf_recovery._genius_six_lens_nine_four_comparison_source_facts(
            source
        ),
    )


def _ability_three_lens_prescription_page(
    *,
    optical_lens: int,
    page_number: int,
    role: str,
    surface_figure: str,
    asphere_figure: str,
) -> dict[str, object]:
    surface_labels = [*(f"S{i}" for i in range(1, 7)), "St"]
    surface_labels.extend(
        f"S{i}" for i in range(7, 19 if optical_lens == 3 else 17)
    )
    asphere_labels = (
        ["S5", "S6", "S7", "S8", "S9", "S11", "S12", "S13", "S14"]
        if optical_lens == 3
        else ["S3", "S4", "S7", "S8", "S9", "S10", "S11", "S12", "S13", "S14"]
    )
    tokens = [
        _ability_ocr_token("surface", 100.0, 100.0),
        _ability_ocr_token("curvature", 200.0, 100.0),
        _ability_ocr_token("(mm)", 300.0, 120.0),
        _ability_ocr_token("index", 400.0, 100.0),
        _ability_ocr_token("number", 500.0, 100.0),
        _ability_ocr_token("constant", 700.0, 100.0),
    ]
    for index, label in enumerate(surface_labels):
        y = 200.0 + index * 30.0
        tokens.extend(
            (
                _ability_ocr_token(label, 100.0, y),
                _ability_ocr_token("8" if label == "St" else "10.0", 200.0, y),
                _ability_ocr_token("0.2", 300.0, y),
                _ability_ocr_token("0", 700.0, y),
            )
        )
        if label[1:].isdigit() and int(label[1:]) % 2 == 1:
            tokens.extend(
                (
                    _ability_ocr_token("1.5", 400.0, y),
                    _ability_ocr_token("55", 500.0, y),
                )
            )
    image_y = 200.0 + len(surface_labels) * 30.0
    tokens.extend(
        (
            _ability_ocr_token("I", 100.0, image_y),
            _ability_ocr_token("8", 200.0, image_y),
        )
    )
    surface_figure_y = image_y + 50.0
    tokens.append(_ability_ocr_token(f"Fig. {surface_figure}", 400.0, surface_figure_y))
    asphere_header_y = surface_figure_y + 100.0
    coefficient_labels = ("A2", "A4", "A6", "A8", "A10", "A12", "A14", "A16")
    coefficient_xs = tuple(200.0 + index * 100.0 for index in range(8))
    tokens.extend(
        _ability_ocr_token(label, x, asphere_header_y)
        for label, x in zip(coefficient_labels, coefficient_xs, strict=True)
    )
    overlay_rows = []
    for index, label in enumerate(asphere_labels):
        y = asphere_header_y + 50.0 + index * 30.0
        tokens.append(_ability_ocr_token(label, 100.0, y))
        tokens.extend(_ability_ocr_token("0", x, y) for x in coefficient_xs)
        overlay_rows.append(f"{label} " + " ".join("0" for _ in coefficient_labels))
    asphere_figure_y = asphere_header_y + 100.0 + len(asphere_labels) * 30.0
    tokens.append(_ability_ocr_token(f"Fig. {asphere_figure}", 400.0, asphere_figure_y))
    return {
        "page_number": page_number,
        "role": role,
        "official_image_sha256": str(page_number) * 64,
        "mirror_text": (
            f"Sheet {page_number - 2} of 7 surface curvature A16 "
            f"Fig . {surface_figure} "
            + " ".join(overlay_rows)
            + f" Fig . {asphere_figure}"
        ),
        "rapidocr_tokens": tokens,
    }


def _ability_three_lens_pdf_ocr_parser_input(
    *,
    complete_prescriptions: bool = False,
) -> bytes:
    pages = []
    for optical_lens, page_number, role, surface_figure, asphere_figure in (
        (1, 6, "prescription_ol1", "4A", "4B"),
        (2, 7, "prescription_ol2", "5A", "5B"),
        (3, 8, "prescription_ol3", "6A", "6B"),
    ):
        if complete_prescriptions:
            pages.append(
                _ability_three_lens_prescription_page(
                    optical_lens=optical_lens,
                    page_number=page_number,
                    role=role,
                    surface_figure=surface_figure,
                    asphere_figure=asphere_figure,
                )
            )
        else:
            pages.append(
                {
                    "page_number": page_number,
                    "role": role,
                    "official_image_sha256": str(page_number) * 64,
                    "mirror_text": (
                        f"Sheet {page_number - 2} of 7 surface curvature A16 "
                        f"Fig . {surface_figure} Fig . {asphere_figure}"
                    ),
                    "rapidocr_tokens": [_ability_ocr_token("fixture", 1.0, 1.0)],
                }
            )
    meta_tokens = [
        _ability_ocr_token("OL1", 300.0, 100.0),
        _ability_ocr_token("OL2", 500.0, 100.0),
        _ability_ocr_token("OL3", 700.0, 100.0),
    ]
    for y, label, values in (
        (200.0, "F (mm)", (3.0, 3.0, 4.04)),
        (240.0, "FNO (mm)", (2.6, 2.6, 2.8)),
        (280.0, "FOV (degree)", (90.0, 90.0, 90.0)),
    ):
        meta_tokens.append(_ability_ocr_token(label, 100.0, y))
        meta_tokens.extend(
            _ability_ocr_token(str(value), x, y)
            for x, value in zip((300.0, 500.0, 700.0), values, strict=True)
        )
    pages.append(
        {
            "page_number": 9,
            "role": "system_meta_three",
            "official_image_sha256": "9" * 64,
            "mirror_text": "Sheet 7 of 7 Fig . 7 OL1 OL2 OL3 F FNO FOV",
            "rapidocr_tokens": meta_tokens,
        }
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "ability_three_lens_prescriptions_v1",
        "publication_id": "US-11175479-B2",
        "page_count": 15,
        "source_facts": {
            "primary_html_sha256": "7" * 64,
            "figure_binding_counts": {
                "FIG. 4A": 1,
                "FIG. 4B": 1,
                "FIG. 5A": 1,
                "FIG. 5B": 1,
                "FIG. 6A": 1,
                "FIG. 6B": 2,
                "FIG. 7": 2,
            },
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _ability_two_five_lens_prescription_page(
    *,
    optical_lens: int,
    page_number: int,
    surface_figure: str,
    asphere_figure: str,
) -> dict[str, object]:
    surface_labels = [*(f"S{i}" for i in range(1, 5)), "St"]
    surface_labels.extend(f"S{i}" for i in range(5, 15))
    tokens = [
        _ability_ocr_token("Surface", 100.0, 100.0),
        _ability_ocr_token("curvature", 200.0, 100.0),
        _ability_ocr_token("Thickness", 300.0, 100.0),
        _ability_ocr_token("Refractive", 400.0, 100.0),
        _ability_ocr_token("Abbe", 500.0, 100.0),
    ]
    for index, label in enumerate(surface_labels):
        y = 200.0 + index * 30.0
        tokens.extend(
            (
                _ability_ocr_token(label, 100.0, y),
                _ability_ocr_token("8" if label == "St" else "10", 200.0, y),
                _ability_ocr_token("0.2", 300.0, y),
            )
        )
        if label != "St" and int(label[1:]) % 2 == 1:
            tokens.extend(
                (
                    _ability_ocr_token("1.5", 400.0, y),
                    _ability_ocr_token("55", 500.0, y),
                )
            )
    image_y = 200.0 + len(surface_labels) * 30.0
    tokens.append(_ability_ocr_token("8", 200.0, image_y))
    surface_figure_y = image_y + 60.0
    tokens.append(_ability_ocr_token(f"FIG. {surface_figure}", 350.0, surface_figure_y))

    asphere_header_y = surface_figure_y + 100.0
    asphere_labels = ("S3", "S4", "S7", "S8", "S9", "S10")
    column_xs = tuple(200.0 + index * 100.0 for index in range(len(asphere_labels)))
    tokens.append(_ability_ocr_token("Surface", 100.0, asphere_header_y))
    tokens.extend(
        _ability_ocr_token(label, x, asphere_header_y)
        for label, x in zip(asphere_labels, column_xs, strict=True)
    )
    row_labels = ("K", "A2", "A4", "A6", "A8", "A10", "A12")
    overlay_rows = []
    for index, label in enumerate(row_labels):
        y = asphere_header_y + 50.0 + index * 30.0
        tokens.append(_ability_ocr_token(label, 100.0, y))
        tokens.extend(_ability_ocr_token("0", x, y) for x in column_xs)
        overlay_rows.append(f"{label} " + " ".join("0" for _ in column_xs))
    asphere_figure_y = asphere_header_y + 100.0 + len(row_labels) * 30.0
    tokens.append(_ability_ocr_token(f"FIG. {asphere_figure}", 350.0, asphere_figure_y))
    return {
        "page_number": page_number,
        "role": f"prescription_five_ol{optical_lens}",
        "official_image_sha256": str(page_number) * 64,
        "mirror_text": (
            f"Sheet {page_number - 1} of 5 Surface Radius A12 FIG . {surface_figure} "
            + "Surface number "
            + " ".join(asphere_labels)
            + " "
            + " ".join(overlay_rows)
            + f" FIG . {asphere_figure}"
        ),
        "rapidocr_tokens": tokens,
    }


def _ability_two_five_lens_pdf_ocr_parser_input(
    *,
    complete_prescriptions: bool = False,
) -> bytes:
    pages = []
    for optical_lens, page_number, surface_figure, asphere_figure in (
        (1, 4, "3A", "3B"),
        (2, 5, "4A", "4B"),
    ):
        if complete_prescriptions:
            pages.append(
                _ability_two_five_lens_prescription_page(
                    optical_lens=optical_lens,
                    page_number=page_number,
                    surface_figure=surface_figure,
                    asphere_figure=asphere_figure,
                )
            )
        else:
            pages.append(
                {
                    "page_number": page_number,
                    "role": f"prescription_five_ol{optical_lens}",
                    "official_image_sha256": str(page_number) * 64,
                    "mirror_text": (
                        f"Sheet {page_number - 1} of 5 Surface Radius A12 "
                        f"FIG . {surface_figure} FIG . {asphere_figure}"
                    ),
                    "rapidocr_tokens": [_ability_ocr_token("fixture", 1.0, 1.0)],
                }
            )
    meta_tokens = [
        _ability_ocr_token("OL1", 300.0, 100.0),
        _ability_ocr_token("OL2", 500.0, 100.0),
    ]
    for y, label, values in (
        (200.0, "f (mm)", (2.1, 2.5)),
        (240.0, "Fno", (2.0, 2.0)),
        (280.0, "FOV (°)", (140.0, 110.0)),
    ):
        meta_tokens.append(_ability_ocr_token(label, 100.0, y))
        meta_tokens.extend(
            _ability_ocr_token(str(value), x, y)
            for x, value in zip((300.0, 500.0), values, strict=True)
        )
    pages.append(
        {
            "page_number": 6,
            "role": "system_meta_five",
            "official_image_sha256": "6" * 64,
            "mirror_text": "Sheet 5 of 5 FIG . 5 OL1 OL2 Fno FOV",
            "rapidocr_tokens": meta_tokens,
        }
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "ability_two_five_lens_prescriptions_v1",
        "publication_id": "US-20200201001-A1",
        "page_count": 12,
        "source_facts": {
            "primary_html_sha256": "8" * 64,
            "figure_binding_counts": {
                "FIG. 3A": 1,
                "FIG. 3B": 1,
                "FIG. 4A": 1,
                "FIG. 4B": 1,
                "FIG. 5": 2,
            },
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_ability_eight_lens_source_facts_detect_published_system_value() -> None:
    figure_text = (
        "FIG. 2 shows each lens parameter of the optical lens "
        "FIG. 3 lists aspheric coefficients of the mathematic equation "
        "of the aspheric lenses of the optical lens "
    )
    source = (
        figure_text * 2
        + "FNO is F-number of the stop STO "
        + "FOV is a field of view of the optical lens " * 4
        + "FNO = 2.8"
    )

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._ability_eight_lens_source_facts(source)
    assert facts["surface_figure_binding_count"] == 2
    assert facts["asphere_figure_binding_count"] == 2
    assert facts["numeric_system_value_assignment_counts"] == {"F": 0, "FNO": 1, "FOV": 0}


def test_ability_two_five_lens_source_facts_bind_every_published_figure() -> None:
    markers = patent_pdf_recovery._ABILITY_TWO_FIVE_LENS_REQUIRED_FIGURE_TEXT
    source = " ".join((*markers, markers[-1]))

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    assert patent_pdf_recovery._ability_two_five_lens_source_facts(source)[
        "figure_binding_counts"
    ] == {
        "FIG. 3A": 1,
        "FIG. 3B": 1,
        "FIG. 4A": 1,
        "FIG. 4B": 1,
        "FIG. 5": 2,
    }


def test_ability_two_nine_lens_source_facts_prove_f_number_absence() -> None:
    markers = patent_pdf_recovery._ABILITY_TWO_NINE_LENS_REQUIRED_FIGURE_TEXT
    source = " ".join((*markers, markers[-1]))

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._ability_two_nine_lens_source_facts(source)
    assert facts["figure_binding_counts"] == {
        "FIG. 4A": 1,
        "FIG. 4B": 1,
        "FIG. 5A": 1,
        "FIG. 5B": 1,
        "FIG. 6": 2,
    }
    assert facts["f_number_label_counts"] == {"FNO": 0, "F-number": 0, "F/#": 0}


def test_ability_four_eight_lens_source_facts_prove_f_number_absence() -> None:
    markers = patent_pdf_recovery._ABILITY_FOUR_EIGHT_LENS_REQUIRED_FIGURE_TEXT
    source = " ".join((*markers, markers[-1]))

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._ability_four_eight_lens_source_facts(source)
    assert facts["figure_binding_counts"] == {
        "FIG. 2A": 1,
        "FIG. 2B": 1,
        "FIG. 4A": 1,
        "FIG. 4B": 1,
        "FIG. 6A": 1,
        "FIG. 6B": 1,
        "FIG. 8": 1,
        "FIG. 9": 2,
    }
    assert facts["f_number_label_counts"] == {"FNO": 0, "F-number": 0, "F/#": 0}


def test_largan_three_five_lens_source_facts_bind_every_table() -> None:
    markers = patent_pdf_recovery._LARGAN_THREE_FIVE_LENS_REQUIRED_FIGURE_TEXT
    source = " ".join(markers)

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._largan_three_five_lens_source_facts(source)
    assert facts["figure_binding_counts"] == {
        f"FIG. {number}": 1 for number in range(7, 14)
    }


def test_ability_zoom_two_state_source_facts_bind_all_four_figures() -> None:
    markers = patent_pdf_recovery._ABILITY_ZOOM_TWO_STATE_REQUIRED_FIGURE_TEXT
    source = " ".join((*markers, markers[-1]))

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._ability_zoom_two_state_source_facts(source)
    assert facts["figure_binding_counts"] == {
        "FIG. 3": 1,
        "FIG. 4": 1,
        "FIG. 5": 1,
        "FIG. 6": 2,
    }


def test_circle_optics_source_facts_bind_layout_and_disclosure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = patent_pdf_recovery._CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT
    source = " ".join(markers)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    layout = {
        "application_number": "17/622463",
        "page_count": 66,
        "role_pages": {
            "circle_optics_surface_table": 16,
            "circle_optics_asphere_table": 17,
        },
    }
    monkeypatch.setitem(
        patent_pdf_recovery._CIRCLE_OPTICS_SEVEN_LENS_SOURCE_LAYOUTS,
        digest,
        layout,
    )

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    assert (
        patent_pdf_recovery.circle_optics_seven_lens_source_layout_for_sha256(digest)
        == layout
    )
    facts = patent_pdf_recovery._circle_optics_seven_lens_source_facts(source)
    assert facts["application_number"] == "17/622463"
    assert facts["required_text_counts"] == dict.fromkeys(markers, 1)
    assert facts["design_wavelengths_nm"] == [450, 587, 656]


def test_kodak_low_stress_source_facts_bind_layout_and_metadata_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = " ".join(
        (
            *patent_pdf_recovery._KODAK_LOW_STRESS_REQUIRED_TEXT,
            *patent_pdf_recovery._KODAK_LOW_STRESS_F_NUMBER_CONTEXTS,
            "focal length focal length focal length field of view",
        )
    )
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    normalized_digest = hashlib.sha256(
        patent_pdf_recovery._normalized_html_text(source).encode("utf-8")
    ).hexdigest()
    layout = {
        "application_number": "14/042755",
        "normalized_text_sha256": normalized_digest,
        "page_count": 61,
        "blank_mirror_pages": frozenset({7, 37}),
        "role_pages": {
            "kodak_projection_prescription": 35,
            "kodak_relay_prescription": 36,
        },
    }
    monkeypatch.setitem(
        patent_pdf_recovery._KODAK_LOW_STRESS_SOURCE_LAYOUTS,
        digest,
        layout,
    )

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    assert (
        patent_pdf_recovery.kodak_low_stress_source_layout_for_sha256(digest)
        == layout
    )
    facts = patent_pdf_recovery._kodak_low_stress_source_facts(source)
    assert facts["required_text_counts"] == dict.fromkeys(
        patent_pdf_recovery._KODAK_LOW_STRESS_REQUIRED_TEXT,
        1,
    )
    assert facts["f_number_context_counts"] == dict.fromkeys(
        patent_pdf_recovery._KODAK_LOW_STRESS_F_NUMBER_CONTEXTS,
        1,
    )
    assert facts["numeric_system_value_assignment_counts"] == dict.fromkeys(
        ("F", "FNO", "FOV", "HFOV", "EFL"),
        0,
    )
    assert facts["effective_focal_length_count"] == 0
    assert facts["focal_length_count"] == 3
    assert facts["field_of_view_count"] == 1
    assert facts["prescription_count"] == 2


def test_canonical_parser_input_records_explicit_rapidocr_rotation() -> None:
    payload = json.loads(
        patent_pdf_recovery._canonical_parser_input(
            publication_id="US-12313825-B2",
            page_count=66,
            key_pages=[(17, "surface", "a" * 64, "", [])],
            rapidocr_rotation="clockwise_90",
        )
    )

    assert payload["pages"][0]["rapidocr_rotation"] == "clockwise_90"


def test_rapidocr_supports_counterclockwise_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = np.zeros((2, 3, 3), dtype=np.uint8)
    observed: dict[str, object] = {}

    monkeypatch.setattr(patent_pdf_recovery.cv2, "imdecode", lambda *_args: image)

    def fake_rotate(candidate: np.ndarray, code: int) -> np.ndarray:
        observed["candidate"] = candidate
        observed["code"] = code
        return candidate

    monkeypatch.setattr(patent_pdf_recovery.cv2, "rotate", fake_rotate)

    class FakeRapidOcr:
        def __call__(self, candidate: np.ndarray) -> tuple[list[object], None]:
            observed["ocr_image"] = candidate
            return [], None

    monkeypatch.setattr(patent_pdf_recovery, "RapidOCR", FakeRapidOcr)

    assert (
        patent_pdf_recovery._rapidocr_tokens(
            b"fixture",
            rotation="counterclockwise_90",
        )
        == []
    )
    assert observed["candidate"] is image
    assert observed["code"] == cv2.ROTATE_90_COUNTERCLOCKWISE
    assert observed["ocr_image"] is image


def test_genius_four_lens_eleven_source_facts_bind_every_figure() -> None:
    markers = patent_pdf_recovery._GENIUS_FOUR_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
    comparison = patent_pdf_recovery._GENIUS_FOUR_LENS_ELEVEN_COMPARISON_MARKERS
    source = " ".join((*markers, *comparison, "Fno"))

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_four_lens_eleven_source_facts(source)
    assert len(facts["figure_binding_counts"]) == 22
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert facts["comparison_binding_counts"] == dict.fromkeys(comparison, 1)
    assert facts["fno_label_count"] == 1


@pytest.mark.parametrize(
    ("source_sha256", "page_count", "drawing_page_offset", "blank_pages"),
    (
        (
            "0211f3fe1bdd3152ab6c57c25e4991603504980b37398c9ae5cbcb9812c43dea",
            66,
            1,
            frozenset({6, 17, 21, 33, 45}),
        ),
        (
            "3b6a1046e050f84cd85e6e04efeee1a2ca96ff2450b1b810816733d7a3d03a73",
            65,
            1,
            frozenset({48}),
        ),
        (
            "bdc8b8babf2e783d5c8bb49be17a1c79ff143aba871d0ac217edc6e63e8def6a",
            66,
            2,
            frozenset({6, 7, 11, 19, 23, 27, 32, 50}),
        ),
        (
            "8b17a79c47cb8c9b589e62cba4097197485d1827ea7ed7147ba57da9f4ccd873",
            65,
            1,
            frozenset({6, 10, 17, 30, 41, 42, 48}),
        ),
    ),
)
def test_genius_four_lens_eleven_source_layout_is_exact(
    source_sha256: str,
    page_count: int,
    drawing_page_offset: int,
    blank_pages: frozenset[int],
) -> None:
    layout = (
        patent_pdf_recovery.genius_four_lens_eleven_source_layout_for_sha256(
            source_sha256
        )
    )

    assert layout["page_count"] == page_count
    assert layout["drawing_page_offset"] == drawing_page_offset
    assert layout["blank_mirror_pages"] == blank_pages


def test_genius_four_lens_eleven_source_layout_rejects_changed_html() -> None:
    with pytest.raises(
        patent_pdf_recovery.PatentPdfRecoveryError,
        match="official HTML is not source-locked",
    ):
        patent_pdf_recovery.genius_four_lens_eleven_source_layout_for_sha256(
            "0" * 64
        )


def test_genius_nine_lens_eleven_source_facts_bind_every_figure() -> None:
    markers = patent_pdf_recovery._GENIUS_NINE_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_NINE_LENS_ELEVEN_COMPARISON_MARKERS
    source = " ".join(
        (*markers, *comparisons, *("Genius Electronic Optical (Xiamen) Co., Ltd.",) * 2)
    )

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_nine_lens_eleven_source_facts(source)
    assert len(facts["figure_binding_counts"]) == 22
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert facts["comparison_binding_counts"] == dict.fromkeys(comparisons, 1)
    assert facts["genius_applicant_assignee_count"] == 2


def test_genius_eight_lens_fourteen_source_facts_bind_every_figure() -> None:
    markers = patent_pdf_recovery._GENIUS_EIGHT_LENS_FOURTEEN_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_EIGHT_LENS_FOURTEEN_COMPARISON_MARKERS
    source = " ".join(
        (*markers, *comparisons, *("Genius Electronic Optical (Xiamen) Co., Ltd.",) * 2)
    )

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_eight_lens_fourteen_source_facts(source)
    assert len(facts["figure_binding_counts"]) == 28
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert facts["comparison_binding_counts"] == dict.fromkeys(comparisons, 1)
    assert facts["genius_applicant_assignee_count"] == 2


def test_genius_four_lens_nine_source_facts_bind_every_figure() -> None:
    markers = patent_pdf_recovery._GENIUS_FOUR_LENS_NINE_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_FOUR_LENS_NINE_COMPARISON_MARKERS
    source = " ".join((*markers, *comparisons))

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_four_lens_nine_source_facts(source)
    assert len(facts["figure_binding_counts"]) == 18
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert len(facts["comparison_binding_counts"]) == 2
    assert set(facts["comparison_binding_counts"].values()) == {1}


def test_genius_six_lens_five_source_facts_bind_every_figure() -> None:
    markers = patent_pdf_recovery._GENIUS_SIX_LENS_FIVE_REQUIRED_FIGURE_TEXT
    comparison = patent_pdf_recovery._GENIUS_SIX_LENS_FIVE_COMPARISON_MARKER
    source = " ".join((*markers, comparison))

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_six_lens_five_source_facts(source)
    assert len(facts["figure_binding_counts"]) == 10
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert facts["comparison_binding_count"] == 1


def test_genius_six_lens_nine_source_facts_bind_every_figure() -> None:
    markers = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_REQUIRED_FIGURE_TEXT
    comparisons = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_COMPARISON_MARKERS
    source = " ".join((*markers, *comparisons))

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_six_lens_nine_source_facts(source)
    assert len(facts["figure_binding_counts"]) == 18
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert facts["comparison_binding_counts"] == {"FIG. 43": 1, "FIG. 44": 1}


def test_genius_six_lens_ten_dual_focus_source_facts_are_exact() -> None:
    markers = patent_pdf_recovery._GENIUS_SIX_LENS_TEN_DUAL_FOCUS_REQUIRED_FIGURE_TEXT
    comparison = (
        patent_pdf_recovery._GENIUS_SIX_LENS_TEN_DUAL_FOCUS_COMPARISON_MARKER
    )
    source = " ".join(
        (
            *markers,
            comparison,
            *("first focusing state",) * 200,
            *("second focusing state",) * 206,
            *("optical imaging lens of six lens elements",) * 2,
        )
    )

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_six_lens_ten_dual_focus_source_facts(source)
    assert len(facts["figure_binding_counts"]) == 10
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert facts["comparison_binding_count"] == 1
    assert facts["first_focusing_state_count"] == 201
    assert facts["second_focusing_state_count"] == 207
    assert facts["six_lens_element_claim_count"] == 2


def test_genius_six_lens_nine_comparison_variant_source_facts_are_exact() -> None:
    three_markers = (
        patent_pdf_recovery._GENIUS_SIX_LENS_NINE_THREE_COMPARISON_REQUIRED_FIGURE_TEXT
    )
    three_comparisons = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_THREE_COMPARISON_MARKERS
    three_source = " ".join((*three_markers, *three_comparisons))
    assert patent_pdf_recovery.ability_drawing_tables_declared(three_source)
    three_facts = (
        patent_pdf_recovery._genius_six_lens_nine_three_comparison_source_facts(
            three_source
        )
    )
    assert len(three_facts["figure_binding_counts"]) == 18
    assert set(three_facts["figure_binding_counts"].values()) == {1}
    assert three_facts["comparison_binding_counts"] == {
        "FIG. 43": 1,
        "FIG. 44": 1,
        "FIG. 45": 1,
    }

    four_markers = (
        patent_pdf_recovery._GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_REQUIRED_FIGURE_TEXT
    )
    four_comparisons = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_MARKERS
    expected = patent_pdf_recovery._GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_EXPECTED_COUNTS
    four_parts = list(four_markers)
    for marker, count in zip(four_comparisons, expected, strict=True):
        four_parts.extend([marker] * count)
    four_source = " ".join(four_parts)
    assert patent_pdf_recovery.ability_drawing_tables_declared(four_source)
    four_facts = patent_pdf_recovery._genius_six_lens_nine_four_comparison_source_facts(
        four_source
    )
    assert len(four_facts["figure_binding_counts"]) == 18
    assert set(four_facts["figure_binding_counts"].values()) == {1}
    assert four_facts["comparison_binding_counts"] == dict(
        zip(four_comparisons, expected, strict=True)
    )


def test_google_404_is_allowed_only_for_proven_official_only_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def missing_page(*_args: object, **_kwargs: object) -> object:
        request = httpx.Request("GET", "https://patents.google.com/missing")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("missing", request=request, response=response)

    monkeypatch.setattr(patent_pdf_recovery, "_get_with_retries", missing_page)
    urls = asyncio.run(
        patent_pdf_recovery._google_citation_pdf_urls(
            object(),
            "https://patents.google.com/missing",
            profile="genius_six_lens_nine_three_comparison_census_v1",
        )
    )
    assert urls == set()
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(
            patent_pdf_recovery._google_citation_pdf_urls(
                object(),
                "https://patents.google.com/missing",
                profile="ability_eight_lens_metadata_unpublished_v1",
            )
        )


def test_ability_eight_lens_pdf_ocr_parser_records_metadata_terminal() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_eight_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-11231565-B2",
    )

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert attempts[0].error.status == "metadata_unpublished"
    assert (
        attempts[0].error.reason_code
        == "metadata_unpublished.system_f_fno_fov_values_absent"
    )


def test_ability_eight_lens_pdf_ocr_parser_rejects_possible_published_system_value() -> None:
    payload = json.loads(_ability_eight_lens_pdf_ocr_parser_input())
    payload["source_facts"]["numeric_system_value_assignment_counts"]["F"] = 1

    with pytest.raises(PatentParseError, match="may publish system values"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-11231565-B2",
        )


def test_ability_two_nine_lens_profile_records_both_metadata_terminals() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_two_nine_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-10690884-B2",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert all(isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError) for attempt in attempts)
    assert all(attempt.error.status == "metadata_unpublished" for attempt in attempts)
    assert all(
        attempt.error.reason_code == "metadata_unpublished.system_f_number_absent"
        for attempt in attempts
    )


def test_ability_two_nine_lens_profile_rejects_ocr_f_number_label() -> None:
    payload = json.loads(_ability_two_nine_lens_pdf_ocr_parser_input())
    payload["pages"][2]["rapidocr_tokens"].append(_ability_ocr_token("FNO", 2.0, 2.0))

    with pytest.raises(PatentParseError, match="OCR may publish an F-number"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-10690884-B2",
        )


def test_ability_four_eight_lens_profile_records_four_metadata_terminals() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_four_eight_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-10809497-B2",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )
    assert all(attempt.error.status == "metadata_unpublished" for attempt in attempts)
    assert all(
        attempt.error.reason_code == "metadata_unpublished.system_f_number_absent"
        for attempt in attempts
    )


def test_ability_four_eight_lens_profile_rejects_ocr_f_number_label() -> None:
    payload = json.loads(_ability_four_eight_lens_pdf_ocr_parser_input())
    payload["pages"][4]["rapidocr_tokens"].append(_ability_ocr_token("FNO", 2.0, 2.0))

    with pytest.raises(PatentParseError, match="OCR may publish an F-number"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-10809497-B2",
        )


def test_largan_three_five_lens_profile_parses_complete_cross_checked_cells() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _largan_three_five_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-12449639-B2",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3]
    prescriptions = [attempt.prescription for attempt in attempts]
    assert all(prescription is not None for prescription in prescriptions)
    assert [prescription.focal_length_mm for prescription in prescriptions if prescription] == [
        5.44,
        5.46,
        5.47,
    ]
    assert all(prescription.f_number == 2.9 for prescription in prescriptions if prescription)
    assert all(prescription.hfov_deg == 33.0 for prescription in prescriptions if prescription)
    assert all(len(prescription.surfaces) == 14 for prescription in prescriptions if prescription)


def test_largan_three_five_lens_profile_retains_low_confidence_by_embodiment() -> None:
    payload = json.loads(_largan_three_five_lens_pdf_ocr_parser_input())
    first_asphere = next(page for page in payload["pages"] if page["role"] == "largan_asphere_1")
    coefficient = next(
        token
        for token in first_asphere["rapidocr_tokens"]
        if token["text"] == "-1.00000E+00"
    )
    coefficient["confidence"] = 0.98

    attempts = patent_to_zmx._parse_prescription_attempts(
        json.dumps(payload),
        patent_id="US-12449639-B2",
    )

    assert attempts[0].prescription is None
    assert "coefficient OCR views disagree" in str(attempts[0].error)
    assert all(attempt.prescription is not None for attempt in attempts[1:])


def test_circle_optics_seven_lens_profile_retains_source_specific_review() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _circle_optics_seven_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-12313825-B2",
    )

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert "only 1 table-region numeric OCR tokens" in str(attempts[0].error)
    assert "retained for parser review" in str(attempts[0].error)


def test_circle_optics_seven_lens_profile_fails_closed_on_source_drift() -> None:
    payload = json.loads(_circle_optics_seven_lens_pdf_ocr_parser_input())
    marker = next(iter(payload["source_facts"]["required_text_counts"]))
    payload["source_facts"]["required_text_counts"][marker] = 2

    attempts = patent_to_zmx._parse_prescription_attempts(
        json.dumps(payload),
        patent_id="US-12313825-B2",
    )

    assert len(attempts) == 1
    assert "required source-text bindings changed" in str(attempts[0].error)


def test_kodak_low_stress_profile_retains_two_metadata_terminals() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _kodak_low_stress_pdf_ocr_parser_input().decode(),
        patent_id="US-20140036377-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )
    assert all(attempt.error.status == "metadata_unpublished" for attempt in attempts)
    assert {
        attempt.error.reason_code for attempt in attempts
    } == {"metadata_unpublished.prescription_specific_efl_and_field_absent"}


def test_kodak_low_stress_profile_fails_closed_on_source_drift() -> None:
    payload = json.loads(_kodak_low_stress_pdf_ocr_parser_input())
    payload["source_facts"]["focal_length_count"] = 4

    attempts = patent_to_zmx._parse_prescription_attempts(
        json.dumps(payload),
        patent_id="US-20140036377-A1",
    )

    assert len(attempts) == 2
    assert all(not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError) for attempt in attempts)
    assert all("source fact 'focal_length_count' changed" in str(attempt.error) for attempt in attempts)


def test_kodak_low_stress_profile_fails_closed_when_ocr_exposes_system_label() -> None:
    payload = json.loads(_kodak_low_stress_pdf_ocr_parser_input())
    payload["pages"][0]["rapidocr_tokens"].append(
        _ability_ocr_token("EFL", 500.0, 500.0)
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        json.dumps(payload),
        patent_id="US-20140036377-A1",
    )

    assert len(attempts) == 2
    assert all(not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError) for attempt in attempts)
    assert all("OCR may publish system metadata: EFL" in str(attempt.error) for attempt in attempts)


def test_ability_zoom_two_state_profile_retains_each_state_failure() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_zoom_two_state_pdf_ocr_parser_input().decode(),
        patent_id="US-20210373301-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert [attempt.embodiment for attempt in attempts] == [
        "Ability zoom telescopic state",
        "Ability zoom wide-angle state",
    ]
    assert all(attempt.prescription is None for attempt in attempts)
    assert all("surface label 'S2' confidence 0.940000" in str(attempt.error) for attempt in attempts)


def test_ability_zoom_surface_census_accepts_complete_variable_grid() -> None:
    page = {
        "rapidocr_tokens": [
            _ability_ocr_token("Surface", 100.0, 100.0),
            _ability_ocr_token("Curvature", 200.0, 100.0),
            _ability_ocr_token("index", 400.0, 100.0),
            _ability_ocr_token("Abbe", 500.0, 100.0),
            _ability_ocr_token("S1", 100.0, 150.0),
            _ability_ocr_token("10", 200.0, 150.0),
            _ability_ocr_token("1", 300.0, 150.0),
            _ability_ocr_token("1.5", 400.0, 150.0),
            _ability_ocr_token("60", 500.0, 150.0),
            _ability_ocr_token("STO", 100.0, 200.0),
            _ability_ocr_token("8", 200.0, 200.0),
            _ability_ocr_token("0.5", 300.0, 200.0),
            _ability_ocr_token("S2", 100.0, 250.0),
            _ability_ocr_token("-10", 200.0, 250.0),
            _ability_ocr_token("2", 300.0, 250.0),
            _ability_ocr_token("IMA", 100.0, 300.0),
        ]
    }

    patent_to_zmx._ability_zoom_surface_census(page)


def test_genius_four_lens_eleven_profile_retains_every_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_four_lens_eleven_pdf_ocr_parser_input().decode(),
        patent_id="US-20170097490-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 12))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "optical/asphere/Fno census passed; numeric cell parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


@pytest.mark.parametrize(
    ("publication_id", "primary_html_sha256", "page_count", "page_shift"),
    (
        (
            "US-20150077867-A1",
            "3b6a1046e050f84cd85e6e04efeee1a2ca96ff2450b1b810816733d7a3d03a73",
            65,
            0,
        ),
        (
            "US-8929000-B2",
            "bdc8b8babf2e783d5c8bb49be17a1c79ff143aba871d0ac217edc6e63e8def6a",
            66,
            1,
        ),
        (
            "US-9341816-B2",
            "8b17a79c47cb8c9b589e62cba4097197485d1827ea7ed7147ba57da9f4ccd873",
            65,
            0,
        ),
    ),
)
def test_genius_four_lens_eleven_profile_uses_source_locked_page_offset(
    publication_id: str,
    primary_html_sha256: str,
    page_count: int,
    page_shift: int,
) -> None:
    payload = json.loads(_genius_four_lens_eleven_pdf_ocr_parser_input())
    payload["publication_id"] = publication_id
    payload["page_count"] = page_count
    payload["source_facts"]["primary_html_sha256"] = primary_html_sha256
    for page in payload["pages"]:
        page["page_number"] += page_shift

    attempts = patent_to_zmx._parse_prescription_attempts(
        json.dumps(payload),
        patent_id=publication_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 12))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "optical/asphere/Fno census passed; numeric cell parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


def test_genius_nine_lens_eleven_profile_retains_every_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_nine_lens_eleven_pdf_ocr_parser_input().decode(),
        patent_id="US-12625349-B2",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 12))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "nine-lens eleven-embodiment census passed; numeric parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


def test_genius_eight_lens_fourteen_profile_retains_every_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_eight_lens_fourteen_pdf_ocr_parser_input().decode(),
        patent_id="US-20250020895-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 15))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "eight-lens fourteen-embodiment census passed; numeric parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


def test_genius_eight_lens_fourteen_profile_refuses_source_binding_drift() -> None:
    payload = json.loads(_genius_eight_lens_fourteen_pdf_ocr_parser_input())
    payload["source_facts"]["genius_applicant_assignee_count"] = 1

    with pytest.raises(PatentParseError, match="official figure/source bindings changed"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-20250020895-A1",
        )


def test_genius_six_lens_ten_dual_focus_profile_retains_every_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_six_lens_ten_dual_focus_pdf_ocr_parser_input().decode(),
        patent_id="US-12656578-B2",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 11))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "ten-embodiment dual-focus census passed; numeric parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


def test_genius_six_lens_ten_dual_focus_profile_refuses_source_drift() -> None:
    payload = json.loads(_genius_six_lens_ten_dual_focus_pdf_ocr_parser_input())
    payload["source_facts"]["second_focusing_state_count"] = 206

    with pytest.raises(PatentParseError, match="official figure/source bindings changed"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-12656578-B2",
        )


def test_genius_nine_lens_eleven_profile_refuses_source_binding_drift() -> None:
    payload = json.loads(_genius_nine_lens_eleven_pdf_ocr_parser_input())
    payload["source_facts"]["genius_applicant_assignee_count"] = 1

    with pytest.raises(PatentParseError, match="figure/source bindings changed"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-12625349-B2",
        )


def test_genius_four_lens_nine_profile_retains_every_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_four_lens_nine_pdf_ocr_parser_input().decode(),
        patent_id="US-20260186247-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 10))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "four-lens nine-embodiment census passed; numeric parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


def test_genius_six_lens_five_profile_retains_every_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_six_lens_five_pdf_ocr_parser_input().decode(),
        patent_id="US-20240369810-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 6))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "six-lens optical/asphere census passed; numeric cell parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


def test_genius_six_lens_nine_profile_retains_every_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_six_lens_nine_pdf_ocr_parser_input().decode(),
        patent_id="US-20260036791-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 10))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "six-lens optical/asphere census passed; numeric cell parser remains"
        in str(attempt.error)
        for attempt in attempts
    )

    grant_payload = json.loads(_genius_six_lens_nine_pdf_ocr_parser_input())
    grant_payload["page_count"] = 50
    grant_payload["publication_id"] = "US-12461345-B2"
    grant_attempts = patent_to_zmx._parse_prescription_attempts(
        json.dumps(grant_payload),
        patent_id="US-12461345-B2",
    )
    assert [attempt.embodiment_number for attempt in grant_attempts] == list(range(1, 10))


def test_corephotonics_555_nm_convention_publishes_nd_vd_material_columns() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "b1257f70d0725069"
        / "US-12560777-B2.html"
    )
    raw = source.read_bytes()
    text = patent_to_zmx.normalize_patent_text(raw.decode("utf-8"))

    assert hashlib.sha256(raw).hexdigest() == (
        "b1257f70d07250690e5306488b26c607e6970051b4f43ab6efbee8841a0bd9e2"
    )
    assert "Corephotonics Ltd." in text
    assert text.count("The reference wavelength is 555.0 nm") == 1
    assert "R [mm] T [mm] D [mm] Nd Vd Focal Length [mm]" in text


@pytest.mark.parametrize(
    ("parser_input", "patent_id"),
    (
        (
            _genius_six_lens_nine_three_comparison_pdf_ocr_parser_input,
            "US-20260186249-A1",
        ),
        (
            _genius_six_lens_nine_four_comparison_pdf_ocr_parser_input,
            "US-20260186250-A1",
        ),
    ),
)
def test_genius_six_lens_nine_comparison_variants_retain_every_embodiment(
    parser_input: object,
    patent_id: str,
) -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        parser_input().decode(),
        patent_id=patent_id,
    )
    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 10))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "six-lens optical/asphere census passed; numeric cell parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


def test_ability_three_lens_pdf_profile_retains_each_disclosed_ocr_failure() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_three_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-11175479-B2",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3]
    assert [attempt.embodiment for attempt in attempts] == [
        "Ability optical lens OL1",
        "Ability optical lens OL2",
        "Ability optical lens OL3",
    ]
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(isinstance(attempt.error, PatentParseError) for attempt in attempts)
    assert all("token 'surface'" in str(attempt.error) for attempt in attempts)


def test_ability_three_lens_pdf_profile_parses_complete_cross_checked_cells() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_three_lens_pdf_ocr_parser_input(complete_prescriptions=True).decode(),
        patent_id="US-11175479-B2",
    )

    assert all(attempt.error is None for attempt in attempts)
    prescriptions = [attempt.prescription for attempt in attempts]
    assert all(prescription is not None for prescription in prescriptions)
    assert [
        (prescription.focal_length_mm, prescription.f_number, prescription.hfov_deg)
        for prescription in prescriptions
        if prescription is not None
    ] == pytest.approx([(3.0, 2.6, 45.0), (3.0, 2.6, 45.0), (4.04, 2.8, 45.0)])
    assert [len(prescription.surfaces) for prescription in prescriptions if prescription] == [
        18,
        18,
        20,
    ]


def test_ability_three_lens_pdf_profile_rejects_source_binding_drift() -> None:
    payload = json.loads(_ability_three_lens_pdf_ocr_parser_input())
    payload["source_facts"]["figure_binding_counts"]["FIG. 6B"] = 1

    with pytest.raises(PatentParseError, match="official figure bindings changed"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-11175479-B2",
        )


def test_ability_two_five_lens_profile_retains_each_disclosed_ocr_failure() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_two_five_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-20200201001-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert [attempt.embodiment for attempt in attempts] == [
        "Ability optical lens OL1",
        "Ability optical lens OL2",
    ]
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(isinstance(attempt.error, PatentParseError) for attempt in attempts)
    assert all("token 'FIG." in str(attempt.error) for attempt in attempts)


def test_ability_two_five_lens_profile_parses_complete_cross_checked_cells() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_two_five_lens_pdf_ocr_parser_input(complete_prescriptions=True).decode(),
        patent_id="US-20200201001-A1",
    )

    assert all(attempt.error is None for attempt in attempts)
    prescriptions = [attempt.prescription for attempt in attempts]
    assert all(prescription is not None for prescription in prescriptions)
    assert [
        (prescription.focal_length_mm, prescription.f_number, prescription.hfov_deg)
        for prescription in prescriptions
        if prescription is not None
    ] == pytest.approx([(2.1, 2.0, 70.0), (2.5, 2.0, 55.0)])
    assert [len(prescription.surfaces) for prescription in prescriptions if prescription] == [
        16,
        16,
    ]
    assert all(
        prescription.surfaces[4].label == "Stop"
        for prescription in prescriptions
        if prescription is not None
    )


def test_ability_two_five_lens_profile_rejects_source_binding_drift() -> None:
    payload = json.loads(_ability_two_five_lens_pdf_ocr_parser_input())
    payload["source_facts"]["figure_binding_counts"]["FIG. 5"] = 1

    with pytest.raises(PatentParseError, match="official figure bindings changed"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-20200201001-A1",
        )


def test_ability_two_five_lens_profile_rejects_unproven_prior_publication() -> None:
    payload = json.loads(_ability_two_five_lens_pdf_ocr_parser_input())
    payload["publication_id"] = "US-11768354-B2"
    payload["source_publication_id"] = "US-20200201001-A1"
    payload["source_linkage"] = {
        "application_number": "16/683826",
        "exact_application_number_match": True,
        "grant_prior_publication_binding": False,
        "kind": "uspto_prior_publication_data_same_application_v1",
        "primary_html_sha256": "b" * 64,
        "source_html_sha256": "8" * 64,
    }

    with pytest.raises(PatentParseError, match="prior-publication binding is absent"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-11768354-B2",
        )


def test_ability_pdf_ocr_parser_recovers_only_independently_classified_ol2() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_pdf_ocr_parser_input().decode(),
        patent_id="US-10684452-B2",
    )

    assert len(attempts) == 2
    assert attempts[0].prescription is None
    assert "fail closed" in str(attempts[0].error)
    second = attempts[1].prescription
    assert second is not None
    assert (second.focal_length_mm, second.f_number, second.hfov_deg) == pytest.approx(
        (2.32, 2.82, 85.0)
    )
    assert len(second.surfaces) == 19
    assert [surface.label for surface in second.surfaces[8:]] == [
        "Stop",
        "S10",
        "S11",
        "S12",
        "S7",
        "S8",
        "Filter",
        "Filter",
        "Cover",
        "Cover",
        "Image",
    ]
    assert second.surfaces[8].radius_mm is None
    assert (second.surfaces[14].nd, second.surfaces[14].vd) == pytest.approx((1.51, 52.1))


def test_ability_pdf_ocr_parser_rejects_low_confidence_optical_number() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_pdf_ocr_parser_input(low_confidence_radius=True).decode(),
        patent_id="US-10684452-B2",
    )

    assert attempts[1].prescription is None
    assert "numeric cell" in str(attempts[1].error)


def test_convert_candidate_retains_official_pdf_ocr_linkage_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser_input = _ability_pdf_ocr_parser_input()
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-10684452-B2",
        source_bucket="USPAT",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="official HTML without tables",
            source_bucket="USPAT",
            attempts=(source_attempt,),
        )

    async def fake_pdf_recovery(*_args: object, **_kwargs: object) -> object:
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id="US-10684452-B2",
            official_pdf=b"%PDF-official",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10684452"
            ),
            mirror_pdf=b"%PDF-mirror",
            mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US10684452.pdf",
            parser_input=parser_input,
            page_count=16,
            page_image_sha256=("a" * 64,),
            key_page_numbers=(4, 5, 8, 10),
            pypdf_version="fixture",
            rapidocr_version="fixture",
        )

    clock = iter((0.0, 2.0))
    monkeypatch.setattr(patent_to_zmx, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_primary_fetch)
    monkeypatch.setattr(patent_to_zmx, "recover_ability_official_pdf_ocr", fake_pdf_recovery)

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-10684452-B2",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
            patent_budget_seconds=1.0,
        )
    )

    assert [attempt.status for attempt in attempts] == ["failed", "conversion_retry_required"]
    assert {attempt.parser_input_source_bucket for attempt in attempts} == {
        "USPTO-PDF-OCR-JSON"
    }
    manifest_paths = {attempt.fulltext_recovery_manifest_path for attempt in attempts}
    assert len(manifest_paths) == 1
    manifest = json.loads(Path(manifest_paths.pop()).read_text(encoding="utf-8"))
    assert manifest["recovery_type"] == "uspto_official_pdf_exact_image_ocr_overlay"
    assert manifest["official_pdf"]["source_bucket"] == "USPTO-PDF"
    assert manifest["ocr_overlay_pdf"]["source_bucket"] == "GOOGLE-OCR-PDF"
    assert manifest["source_pin"]["source_bucket"] == "USPTO-PDF-OCR-SOURCE-PIN"
    assert manifest["parser_input"]["key_page_numbers"] == [4, 5, 8, 10]
    assert manifest["page_identity"] == "decoded_page_raster_pixels_v1"
    assert manifest["checks"]["all_decoded_page_rasters_pixel_identical"] is True
    assert all(manifest["checks"].values())
    cached_sources = patent_to_zmx._load_pdf_ocr_source_pin(
        tmp_path / "raw",
        publication_id="US-10684452-B2",
    )
    assert cached_sources is not None
    assert cached_sources.official_pdf == b"%PDF-official"
    assert cached_sources.mirror_pdf == b"%PDF-mirror"


def test_convert_candidate_retains_pdf_terminal_evidence_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-11231565-B2",
        source_bucket="USPAT",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="official HTML whose image tables require PDF recovery",
            source_bucket="USPAT",
            attempts=(source_attempt,),
        )

    async def fake_pdf_recovery(*_args: object, **_kwargs: object) -> object:
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id="US-11231565-B2",
            official_pdf=b"%PDF-official-eight-lens",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11231565"
            ),
            mirror_pdf=b"%PDF-mirror-eight-lens",
            mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US11231565.pdf",
            parser_input=_ability_eight_lens_pdf_ocr_parser_input(),
            page_count=11,
            page_image_sha256=("a" * 64, "b" * 64),
            key_page_numbers=(4, 5),
            pypdf_version="fixture",
            rapidocr_version="fixture",
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("metadata-terminal PDF recovery must not launch a trace worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_primary_fetch)
    monkeypatch.setattr(patent_to_zmx, "recover_ability_official_pdf_ocr", fake_pdf_recovery)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-11231565-B2",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
        )
    )

    assert [attempt.status for attempt in attempts] == ["metadata_unpublished"]
    assert attempts[0].reason_code == "metadata_unpublished.system_f_fno_fov_values_absent"
    assert attempts[0].parser_input_source_bucket == "USPTO-PDF-OCR-JSON"
    assert attempts[0].fulltext_recovery_manifest_path
    assert not (tmp_path / "staging").exists()


def test_convert_candidate_retains_two_nine_lens_terminals_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-10690884-B2",
        source_bucket="USPAT",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="official HTML whose two nine-lens tables require PDF recovery",
            source_bucket="USPAT",
            attempts=(source_attempt,),
        )

    async def fake_pdf_recovery(*_args: object, **_kwargs: object) -> object:
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id="US-10690884-B2",
            official_pdf=b"%PDF-official-two-nine-lens",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10690884"
            ),
            mirror_pdf=b"%PDF-mirror-two-nine-lens",
            mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US10690884.pdf",
            parser_input=_ability_two_nine_lens_pdf_ocr_parser_input(),
            page_count=13,
            page_image_sha256=tuple(str(index) * 64 for index in range(1, 4)),
            key_page_numbers=(5, 6, 7),
            pypdf_version="fixture",
            rapidocr_version="fixture",
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("metadata-terminal PDF recovery must not launch a trace worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_primary_fetch)
    monkeypatch.setattr(patent_to_zmx, "recover_ability_official_pdf_ocr", fake_pdf_recovery)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-10690884-B2",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
        )
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert all(attempt.status == "metadata_unpublished" for attempt in attempts)
    assert all(
        attempt.reason_code == "metadata_unpublished.system_f_number_absent"
        for attempt in attempts
    )
    assert all(attempt.parser_input_source_bucket == "USPTO-PDF-OCR-JSON" for attempt in attempts)
    assert not (tmp_path / "staging").exists()


def test_convert_candidate_retains_four_eight_lens_terminals_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-10809497-B2",
        source_bucket="USPAT",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="official HTML whose four eight-lens tables require PDF recovery",
            source_bucket="USPAT",
            attempts=(source_attempt,),
        )

    async def fake_pdf_recovery(*_args: object, **_kwargs: object) -> object:
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id="US-10809497-B2",
            official_pdf=b"%PDF-official-four-eight-lens",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10809497"
            ),
            mirror_pdf=b"%PDF-mirror-four-eight-lens",
            mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US10809497.pdf",
            parser_input=_ability_four_eight_lens_pdf_ocr_parser_input(),
            page_count=14,
            page_image_sha256=tuple(str(index) * 64 for index in range(1, 6)),
            key_page_numbers=(3, 4, 6, 7, 8),
            pypdf_version="fixture",
            rapidocr_version="fixture",
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("metadata-terminal PDF recovery must not launch a trace worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_primary_fetch)
    monkeypatch.setattr(
        patent_to_zmx,
        "recover_ability_official_pdf_ocr",
        fake_pdf_recovery,
    )
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-10809497-B2",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
        )
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4]
    assert all(attempt.status == "metadata_unpublished" for attempt in attempts)
    assert all(
        attempt.reason_code == "metadata_unpublished.system_f_number_absent"
        for attempt in attempts
    )
    assert all(
        attempt.parser_input_source_bucket == "USPTO-PDF-OCR-JSON"
        for attempt in attempts
    )
    assert not (tmp_path / "staging").exists()


def test_convert_candidate_retains_three_lens_pdf_ocr_failures_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-11175479-B2",
        source_bucket="USPAT",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="official HTML whose three image tables require PDF recovery",
            source_bucket="USPAT",
            attempts=(source_attempt,),
        )

    async def fake_pdf_recovery(*_args: object, **_kwargs: object) -> object:
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id="US-11175479-B2",
            official_pdf=b"%PDF-official-three-lens",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11175479"
            ),
            mirror_pdf=b"%PDF-mirror-three-lens",
            mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US11175479.pdf",
            parser_input=_ability_three_lens_pdf_ocr_parser_input(),
            page_count=15,
            page_image_sha256=tuple(str(index) * 64 for index in range(1, 6)),
            key_page_numbers=(6, 7, 8, 9),
            pypdf_version="fixture",
            rapidocr_version="fixture",
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("rejected PDF OCR cells must not launch a trace worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_primary_fetch)
    monkeypatch.setattr(patent_to_zmx, "recover_ability_official_pdf_ocr", fake_pdf_recovery)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-11175479-B2",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
        )
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3]
    assert all(attempt.status == "failed" for attempt in attempts)
    assert all(attempt.parser_input_source_bucket == "USPTO-PDF-OCR-JSON" for attempt in attempts)
    assert len({attempt.fulltext_recovery_manifest_sha256 for attempt in attempts}) == 1
    assert not (tmp_path / "staging").exists()


def test_convert_candidate_retains_two_five_lens_pdf_failures_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-20200201001-A1",
        source_bucket="US-PGPUB",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="official HTML whose two five-lens tables require PDF recovery",
            source_bucket="US-PGPUB",
            attempts=(source_attempt,),
        )

    async def fake_pdf_recovery(*_args: object, **_kwargs: object) -> object:
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id="US-20200201001-A1",
            official_pdf=b"%PDF-official-two-five-lens",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20200201001"
            ),
            mirror_pdf=b"%PDF-mirror-two-five-lens",
            mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US20200201001.pdf",
            parser_input=_ability_two_five_lens_pdf_ocr_parser_input(),
            page_count=12,
            page_image_sha256=tuple(str(index) * 64 for index in range(1, 4)),
            key_page_numbers=(4, 5, 6),
            pypdf_version="fixture",
            rapidocr_version="fixture",
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("rejected PDF OCR cells must not launch a trace worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_primary_fetch)
    monkeypatch.setattr(patent_to_zmx, "recover_ability_official_pdf_ocr", fake_pdf_recovery)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-20200201001-A1",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
        )
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert all(attempt.status == "failed" for attempt in attempts)
    assert all(attempt.parser_input_source_bucket == "USPTO-PDF-OCR-JSON" for attempt in attempts)
    assert len({attempt.fulltext_recovery_manifest_sha256 for attempt in attempts}) == 1
    assert not (tmp_path / "staging").exists()


def test_convert_candidate_recovers_linked_prior_publication_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    grant = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "b54234c78c881767"
        / "US-11768354-B2.html"
    ).read_text(encoding="utf-8")
    publication = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "8321e4c6f37bd824"
        / "US-20200201001-A1.html"
    ).read_text(encoding="utf-8")
    source_parser_payload = json.loads(_ability_two_five_lens_pdf_ocr_parser_input())
    source_parser_payload["source_facts"]["primary_html_sha256"] = hashlib.sha256(
        publication.encode("utf-8")
    ).hexdigest()
    source_parser_input = (
        json.dumps(source_parser_payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-11768354-B2",
        source_bucket="USPAT",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html=grant,
            source_bucket="USPAT",
            attempts=(source_attempt,),
        )

    async def fake_prior_fetch(
        _client: object,
        _token: str,
        publication_id: str,
        source_bucket: str,
    ) -> str:
        assert (publication_id, source_bucket) == ("US-20200201001-A1", "US-PGPUB")
        return publication

    async def fake_pdf_recovery(
        *_args: object,
        publication_id: str,
        **_kwargs: object,
    ) -> object:
        if publication_id == "US-11768354-B2":
            raise patent_to_zmx.PatentPdfRecoveryError(
                "grant citation PDF unavailable; use prior publication"
            )
        assert publication_id == "US-20200201001-A1"
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id=publication_id,
            official_pdf=b"%PDF-official-prior-publication",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20200201001"
            ),
            mirror_pdf=b"%PDF-mirror-prior-publication",
            mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US20200201001.pdf",
            parser_input=source_parser_input,
            page_count=12,
            page_image_sha256=tuple(str(index) * 64 for index in range(1, 4)),
            key_page_numbers=(4, 5, 6),
            pypdf_version="fixture",
            rapidocr_version="fixture",
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("rejected linked PDF OCR cells must not launch a trace worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_primary_fetch)
    monkeypatch.setattr(patent_to_zmx, "_ppubs_patent_html", fake_prior_fetch)
    monkeypatch.setattr(patent_to_zmx, "recover_ability_official_pdf_ocr", fake_pdf_recovery)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-11768354-B2",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
        )
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert all(attempt.status == "failed" for attempt in attempts)
    assert len({attempt.fulltext_recovery_manifest_sha256 for attempt in attempts}) == 1
    manifest = json.loads(
        Path(attempts[0].fulltext_recovery_manifest_path).read_text(encoding="utf-8")
    )
    assert manifest["pdf_source_publication"]["publication_id"] == "US-20200201001-A1"
    assert manifest["pdf_source_publication"]["application_number"] == "16/683826"
    assert manifest["checks"]["prior_publication_linkage_matches_parser_input"] is True
    linked_parser = json.loads(Path(attempts[0].parser_input_document_path).read_text())
    assert linked_parser["publication_id"] == "US-11768354-B2"
    assert linked_parser["source_publication_id"] == "US-20200201001-A1"
    assert linked_parser["source_linkage"]["grant_prior_publication_binding"] is True
    assert not (tmp_path / "staging").exists()


def test_pdf_ocr_source_pin_rejects_retained_source_hash_drift(tmp_path: Path) -> None:
    official = patent_to_zmx._retain_source_bytes(
        tmp_path,
        publication_id="US-10684452-B2",
        source_bucket="USPTO-PDF",
        suffix="pdf",
        content=b"%PDF-official",
    )
    mirror = patent_to_zmx._retain_source_bytes(
        tmp_path,
        publication_id="US-10684452-B2",
        source_bucket="GOOGLE-OCR-PDF",
        suffix="pdf",
        content=b"%PDF-mirror",
    )
    recovered = patent_to_zmx.PatentPdfOcrRecovery(
        publication_id="US-10684452-B2",
        official_pdf=b"%PDF-official",
        official_pdf_url=(
            "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10684452"
        ),
        mirror_pdf=b"%PDF-mirror",
        mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US10684452.pdf",
        parser_input=b"{}\n",
        page_count=1,
        page_image_sha256=("a" * 64,),
        key_page_numbers=(1,),
        pypdf_version="fixture",
        rapidocr_version="fixture",
    )
    patent_to_zmx._retain_pdf_ocr_source_pin(
        tmp_path,
        publication_id="US-10684452-B2",
        recovered=recovered,
        official_pdf_source=official,
        mirror_pdf_source=mirror,
    )
    Path(official.retained_path).write_bytes(b"%PDF-mutated")

    with pytest.raises(patent_to_zmx.PatentParseError, match="hash mismatch"):
        patent_to_zmx._load_pdf_ocr_source_pin(
            tmp_path,
            publication_id="US-10684452-B2",
        )


def test_pdf_ocr_source_pin_and_manifest_support_official_only_rapidocr(
    tmp_path: Path,
) -> None:
    official = patent_to_zmx._retain_source_bytes(
        tmp_path,
        publication_id="US-20260009980-A1",
        source_bucket="USPTO-PDF",
        suffix="pdf",
        content=b"%PDF-official",
    )
    parser_source = patent_to_zmx._retain_source_bytes(
        tmp_path,
        publication_id="US-20260009980-A1",
        source_bucket="USPTO-PDF-OCR-JSON",
        suffix="json",
        content=b"{}\n",
    )
    primary = patent_to_zmx._retain_source_bytes(
        tmp_path,
        publication_id="US-20260009980-A1",
        source_bucket="US-PGPUB",
        suffix="html",
        content=b"official html",
    )
    recovered = patent_to_zmx.PatentPdfOcrRecovery(
        publication_id="US-20260009980-A1",
        official_pdf=b"%PDF-official",
        official_pdf_url=(
            "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20260009980"
        ),
        mirror_pdf=None,
        mirror_pdf_url=None,
        parser_input=b"{}\n",
        page_count=1,
        page_image_sha256=("a" * 64,),
        key_page_numbers=(1,),
        pypdf_version="fixture",
        rapidocr_version="fixture",
    )
    pin = patent_to_zmx._retain_pdf_ocr_source_pin(
        tmp_path,
        publication_id="US-20260009980-A1",
        recovered=recovered,
        official_pdf_source=official,
        mirror_pdf_source=None,
    )
    cached = patent_to_zmx._load_pdf_ocr_source_pin(
        tmp_path,
        publication_id="US-20260009980-A1",
    )

    assert cached is not None
    assert cached.official_pdf == b"%PDF-official"
    assert cached.mirror_pdf is None
    assert cached.mirror_pdf_url is None
    manifest_evidence = patent_to_zmx._retain_pdf_ocr_recovery_manifest(
        tmp_path,
        primary_publication_id="US-20260009980-A1",
        primary_source=primary,
        recovered=recovered,
        official_pdf_source=official,
        mirror_pdf_source=None,
        parser_source=parser_source,
        source_pin=pin,
    )
    manifest = json.loads(Path(manifest_evidence.retained_path).read_text(encoding="utf-8"))
    assert manifest["recovery_type"] == "uspto_official_pdf_coordinate_rapidocr"
    assert manifest["page_identity"] == "official_decoded_page_raster_pixels_v1"
    assert "ocr_overlay_pdf" not in manifest
    assert "all_decoded_page_rasters_pixel_identical" not in manifest["checks"]


def test_pdf_ocr_source_pin_rejects_source_outside_raw_lake(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    official = patent_to_zmx._retain_source_bytes(
        raw_dir,
        publication_id="US-10684452-B2",
        source_bucket="USPTO-PDF",
        suffix="pdf",
        content=b"%PDF-official",
    )
    mirror = patent_to_zmx._retain_source_bytes(
        raw_dir,
        publication_id="US-10684452-B2",
        source_bucket="GOOGLE-OCR-PDF",
        suffix="pdf",
        content=b"%PDF-mirror",
    )
    recovered = patent_to_zmx.PatentPdfOcrRecovery(
        publication_id="US-10684452-B2",
        official_pdf=b"%PDF-official",
        official_pdf_url=(
            "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10684452"
        ),
        mirror_pdf=b"%PDF-mirror",
        mirror_pdf_url="https://patentimages.storage.googleapis.com/test/US10684452.pdf",
        parser_input=b"{}\n",
        page_count=1,
        page_image_sha256=("a" * 64,),
        key_page_numbers=(1,),
        pypdf_version="fixture",
        rapidocr_version="fixture",
    )
    pin = patent_to_zmx._retain_pdf_ocr_source_pin(
        raw_dir,
        publication_id="US-10684452-B2",
        recovered=recovered,
        official_pdf_source=official,
        mirror_pdf_source=mirror,
    )
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-official")
    pin_path = Path(pin.retained_path)
    payload = json.loads(pin_path.read_text(encoding="utf-8"))
    payload["official_pdf"]["path"] = outside.as_posix()
    pin_path.write_bytes(
        (
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    )

    with pytest.raises(patent_to_zmx.PatentParseError, match="outside the raw document lake"):
        patent_to_zmx._load_pdf_ocr_source_pin(
            raw_dir,
            publication_id="US-10684452-B2",
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


@pytest.mark.parametrize(
    ("publication_id", "source_parts", "example_1100_surface_2_g"),
    (
        (
            "US-12216259-B2",
            ("USPAT", "86d554b9602ba6d6", "US-12216259-B2.html"),
            -1.34e-10,
        ),
        (
            "US-12411321-B1",
            ("USPAT", "9084f2c33d964572", "US-12411321-B1.html"),
            1.34e-10,
        ),
        (
            "US-20250271645-A1",
            ("US-PGPUB", "6cee6f58f05c7c78", "US-20250271645-A1.html"),
            -1.34e-10,
        ),
    ),
)
def test_large_aperture_scanning_tele_official_family_parses_exactly(
    publication_id: str,
    source_parts: tuple[str, str, str],
    example_1100_surface_2_g: float,
) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / Path(*source_parts)
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        source.read_text(encoding="utf-8"),
        patent_id=publication_id,
    )

    assert len(attempts) == 4
    assert all(attempt.error is None for attempt in attempts)
    prescriptions = [attempt.prescription for attempt in attempts]
    assert all(prescription is not None for prescription in prescriptions)
    complete = [prescription for prescription in prescriptions if prescription is not None]
    assert all(
        prescription.reference_wavelength_um == pytest.approx(0.555)
        for prescription in complete
    )
    observed_metadata = [
        (prescription.focal_length_mm, prescription.f_number, prescription.hfov_deg)
        for prescription in complete
    ]
    assert observed_metadata == [
        pytest.approx(values)
        for values in (
            (17.37, 2.35, 12.8),
            (14.10, 2.45, 11.5),
            (14.10, 2.45, 15.7),
            (14.10, 2.43, 13.7),
        )
    ]
    assert all(
        [surface.index for surface in prescription.surfaces] == list(range(1, 17))
        for prescription in complete
    )
    first = complete[0]
    assert first.surfaces[0].label == "Stop"
    assert first.surfaces[1].material == "Glass"
    assert first.surfaces[3].material == "Plastic"
    assert first.surfaces[-1].label == "Image"
    assert set(first.surfaces[1].asphere_coefficients) == {
        "K",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
    }
    example_900 = complete[1]
    assert example_900.surfaces[1].asphere_coefficients["G"] == pytest.approx(-1.79e-10)
    assert example_900.surfaces[12].asphere_coefficients["G"] == pytest.approx(-3.87e-8)
    example_1100 = complete[3]
    assert example_1100.surfaces[1].asphere_coefficients["G"] == pytest.approx(
        example_1100_surface_2_g
    )
    assert example_1100.surfaces[13].label == "IR Filter"
    readout = build_readout_from_prescription(first)
    assert [wavelength.wavelength_um for wavelength in readout.wavelengths] == pytest.approx(
        [0.4861, 0.555, 0.5876, 0.6563]
    )
    assert readout.reference_wavelength_index == 2


def test_large_aperture_scanning_tele_rejects_changed_official_hash() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "86d554b9602ba6d6"
        / "US-12216259-B2.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "HFOV = 12.8",
        "HFOV = 12.9",
        1,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-12216259-B2",
    )

    assert len(attempts) == 4
    assert all(attempt.prescription is None for attempt in attempts)
    assert all("official raw text hash changed" in str(attempt.error) for attempt in attempts)


def test_large_aperture_scanning_tele_requires_native_fov_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "86d554b9602ba6d6"
        / "US-12216259-B2.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "n-FOV.sub.T 25.6°",
        "n-FOV.sub.T 24.0°",
        1,
    )
    normalized = patent_to_zmx.normalize_patent_text(text)
    monkeypatch.setitem(
        patent_to_zmx._LARGE_APERTURE_SCANNING_TELE_SOURCE_PROFILES,
        "US-12216259-B2",
        {
            "raw_document_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-12216259-B2",
    )

    assert len(attempts) == 4
    assert all(attempt.prescription is None for attempt in attempts)
    assert all("TABLE 14 field bindings changed" in str(attempt.error) for attempt in attempts)


@pytest.mark.parametrize(
    ("publication_id", "source_parts"),
    (
        (
            "US-11947247-B2",
            ("USPAT", "738f12facf7092f2", "US-11947247-B2.html"),
        ),
        (
            "US-12572060-B2",
            ("USPAT", "3a888161b1902f85", "US-12572060-B2.html"),
        ),
        (
            "US-20230288783-A1",
            ("US-PGPUB", "a0b7015cb421fac8", "US-20230288783-A1.html"),
        ),
    ),
)
def test_folded_adaptive_zoom_configurations_are_source_terminal(
    publication_id: str,
    source_parts: tuple[str, str, str],
) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / Path(*source_parts)
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        source.read_text(encoding="utf-8"),
        patent_id=publication_id,
    )

    assert [attempt.embodiment for attempt in attempts] == [
        "Folded adaptive zoom configuration 1",
        "Folded adaptive zoom configuration 2",
        "Folded adaptive zoom configuration 3",
    ]
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "metadata_unpublished"
        and attempt.error.reason_code
        == "metadata_unpublished.configuration_hfov_and_qcon_q6_definition_absent"
        for attempt in attempts
    )


def test_folded_adaptive_zoom_rejects_changed_official_hash() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "738f12facf7092f2"
        / "US-11947247-B2.html"
    )
    attempts = patent_to_zmx._parse_prescription_attempts(
        source.read_text(encoding="utf-8") + " publication revision",
        patent_id="US-11947247-B2",
    )

    assert len(attempts) == 3
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "official raw text hash changed" in str(attempt.error)
        for attempt in attempts
    )


def test_folded_adaptive_zoom_refuses_new_numeric_hfov(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "738f12facf7092f2"
        / "US-11947247-B2.html"
    )
    text = source.read_text(encoding="utf-8").replace(
        "f/# 2.34 3.52 4.69",
        "f/# 2.34 3.52 4.69 HFOV = 20",
        1,
    )
    monkeypatch.setitem(
        patent_to_zmx._FOLDED_ADAPTIVE_ZOOM_SOURCE_PROFILES,
        "US-11947247-B2",
        {
            **patent_to_zmx._FOLDED_ADAPTIVE_ZOOM_SOURCE_PROFILES["US-11947247-B2"],
            "raw_document_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                patent_to_zmx.normalize_patent_text(text).encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        text,
        patent_id="US-11947247-B2",
    )

    assert len(attempts) == 3
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "now publishes numeric HFOV" in str(attempt.error)
        for attempt in attempts
    )


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


def test_samsung_ten_lens_undefined_high_order_terms_are_source_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _samsung_ten_lens_undefined_high_order_fixture()
    patent_id = _install_samsung_ten_lens_undefined_high_order_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 11))
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )
    assert {
        (attempt.error.status, attempt.error.reason_code)
        for attempt in attempts
        if isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
    } == {
        (
            "metadata_unpublished",
            "metadata_unpublished.high_order_asphere_term_definition_absent",
        )
    }


def test_samsung_ten_lens_published_high_order_definition_refuses_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _samsung_ten_lens_undefined_high_order_fixture(
        publish_high_order_definition=True
    )
    patent_id = _install_samsung_ten_lens_undefined_high_order_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 10
    assert all(isinstance(attempt.error, PatentParseError) for attempt in attempts)
    assert all(
        not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )
    assert all("now have a published definition" in str(attempt.error) for attempt in attempts)


def test_parse_samsung_even_order_pairs_preserves_published_half_field() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _samsung_even_order_fixture(),
        patent_id="US-SAMSUNG-EVEN-ORDER-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 11))
    assert all(attempt.error is None for attempt in attempts)
    prescriptions = [attempt.prescription for attempt in attempts]
    assert all(prescription is not None for prescription in prescriptions)
    first = prescriptions[0]
    sixth = prescriptions[5]
    assert first is not None and sixth is not None
    assert (first.focal_length_mm, first.f_number, first.hfov_deg) == pytest.approx(
        (6.1, 1.5, 41.1)
    )
    assert sixth.hfov_deg == pytest.approx(85.1)
    surfaces = {surface.index: surface for surface in first.surfaces}
    assert len(surfaces) == 19
    assert surfaces[4].label == "Stop"
    assert surfaces[4].surface_type == "ASP"
    assert surfaces[1].nd == pytest.approx(1.55)
    assert surfaces[16].asphere_coefficients["A30"] == pytest.approx(1.0e-15)


def test_samsung_even_order_damaged_header_fails_only_affected_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _samsung_even_order_fixture(damaged_first_asphere_header=True),
        patent_id="US-SAMSUNG-EVEN-ORDER-DAMAGED-A1",
    )

    assert len(attempts) == 10
    assert isinstance(attempts[0].error, PatentParseError)
    assert "asphere headers must be S1-S8 and S9-S16" in str(attempts[0].error)
    assert all(attempt.prescription is not None for attempt in attempts[1:])


def test_samsung_even_order_requires_published_half_field_definition() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _samsung_even_order_fixture(omit_half_field_definition=True),
        patent_id="US-SAMSUNG-EVEN-ORDER-NO-HALF-FIELD-A1",
    )

    assert len(attempts) == 10
    assert all(attempt.prescription is None for attempt in attempts)
    assert all("half-field HFOV definition not found" in str(attempt.error) for attempt in attempts)


def test_samsung_eight_lens_missing_stop_is_source_terminal_per_example() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _samsung_eight_lens_missing_stop_fixture(),
        patent_id="US-SAMSUNG-EIGHT-LENS-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4, 5]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )
    assert {
        (attempt.error.status, attempt.error.reason_code)
        for attempt in attempts
        if isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
    } == {
        (
            "metadata_unpublished",
            "metadata_unpublished.stop_axial_coordinate_absent",
        )
    }


def test_samsung_eight_lens_extra_stop_disclosure_refuses_terminal_classification() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _samsung_eight_lens_missing_stop_fixture(extra_stop_binding=True),
        patent_id="US-SAMSUNG-EIGHT-LENS-EXTRA-A1",
    )

    assert len(attempts) == 5
    assert all(isinstance(attempt.error, PatentParseError) for attempt in attempts)
    assert all(
        not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )
    assert all("extra binding" in str(attempt.error) for attempt in attempts)


def test_ir_filter_coating_only_document_is_confirmed_no_prescription() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ir_filter_coating_only_fixture(),
        patent_id="US-IR-FILTER-A1",
    )

    assert len(attempts) == 1
    assert attempts[0].embodiment_number is None
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == "confirmed_no_prescription.ir_filter_coating_tables_only"


def test_ir_filter_coating_only_classifier_refuses_prescription_marker() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ir_filter_coating_only_fixture(prescription_marker=True),
        patent_id="US-IR-FILTER-DAMAGED-A1",
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "prescription-table markers" in str(attempts[0].error)


def test_surface_texture_acquisition_only_is_confirmed_no_prescription() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _surface_texture_acquisition_only_fixture(),
        patent_id="US-20160305871-A1",
    )

    assert len(attempts) == 1
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription.surface_texture_acquisition_architecture_only"
    )


def test_surface_texture_acquisition_classifier_refuses_prescription_marker() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _surface_texture_acquisition_only_fixture(prescription_marker=True),
        patent_id="US-20160305871-A1",
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert "contains a prescription marker" in str(attempts[0].error)


def test_lens_driving_mechanical_only_is_confirmed_no_prescription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _lens_driving_mechanical_only_fixture()
    patent_id = _install_lens_driving_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription.lens_driving_mechanical_architecture_only"
    )


def test_lens_driving_mechanical_classifier_refuses_prescription_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _lens_driving_mechanical_only_fixture(prescription_marker=True)
    patent_id = _install_lens_driving_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "contains a prescription marker" in str(attempts[0].error)


def test_lens_driving_mechanical_classifier_refuses_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _lens_driving_mechanical_only_fixture()
    patent_id = _install_lens_driving_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "official text hash changed" in str(attempts[0].error)


def test_non_optical_zone_stray_light_only_is_confirmed_no_prescription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _non_optical_zone_stray_light_only_fixture()
    patent_id = _install_non_optical_zone_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription.non_optical_zone_stray_light_architecture_only"
    )


def test_non_optical_zone_classifier_refuses_prescription_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _non_optical_zone_stray_light_only_fixture(prescription_marker=True)
    patent_id = _install_non_optical_zone_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "contains a prescription marker" in str(attempts[0].error)


def test_non_optical_zone_classifier_refuses_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _non_optical_zone_stray_light_only_fixture()
    patent_id = _install_non_optical_zone_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "official text hash changed" in str(attempts[0].error)


def test_barcode_scanner_architecture_only_is_confirmed_no_prescription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _barcode_scanner_architecture_only_fixture()
    patent_id = _install_barcode_scanner_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription.barcode_scanner_architecture_only"
    )


def test_barcode_scanner_classifier_refuses_prescription_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _barcode_scanner_architecture_only_fixture(prescription_marker=True)
    patent_id = _install_barcode_scanner_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "contains a prescription marker" in str(attempts[0].error)


def test_barcode_scanner_classifier_refuses_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _barcode_scanner_architecture_only_fixture()
    patent_id = _install_barcode_scanner_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "official text hash changed" in str(attempts[0].error)


def test_imaging_lens_system_architecture_only_is_confirmed_no_prescription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _imaging_lens_system_architecture_only_fixture()
    patent_id = _install_imaging_lens_system_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription.imaging_lens_system_architecture_only"
    )


def test_imaging_lens_system_classifier_refuses_prescription_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _imaging_lens_system_architecture_only_fixture(prescription_marker=True)
    patent_id = _install_imaging_lens_system_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "contains a prescription marker" in str(attempts[0].error)


def test_imaging_lens_system_classifier_refuses_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _imaging_lens_system_architecture_only_fixture()
    patent_id = _install_imaging_lens_system_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "official text hash changed" in str(attempts[0].error)


def test_extended_depth_of_focus_architecture_only_is_confirmed_no_prescription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _extended_depth_of_focus_architecture_only_fixture()
    patent_id = _install_extended_depth_of_focus_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription."
        "extended_depth_of_focus_phase_element_architecture_only"
    )


def test_extended_depth_of_focus_classifier_refuses_prescription_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _extended_depth_of_focus_architecture_only_fixture(
        prescription_marker=True
    )
    patent_id = _install_extended_depth_of_focus_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "contains a prescription marker" in str(attempts[0].error)


def test_extended_depth_of_focus_classifier_refuses_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _extended_depth_of_focus_architecture_only_fixture()
    patent_id = _install_extended_depth_of_focus_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "official text hash changed" in str(attempts[0].error)


def test_extended_depth_of_focus_classifier_refuses_clinical_table_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _extended_depth_of_focus_architecture_only_fixture(table_header_drift=True)
    patent_id = _install_extended_depth_of_focus_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "clinical table 2 header changed" in str(attempts[0].error)


def test_light_blocking_geometry_only_is_confirmed_no_prescription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _light_blocking_geometry_only_fixture()
    patent_id = _install_light_blocking_geometry_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == "confirmed_no_prescription.light_blocking_geometry_only"


def test_light_blocking_geometry_classifier_refuses_prescription_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _light_blocking_geometry_only_fixture(prescription_marker=True)
    patent_id = _install_light_blocking_geometry_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "contains a prescription marker" in str(attempts[0].error)


def test_light_blocking_geometry_classifier_refuses_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _light_blocking_geometry_only_fixture()
    patent_id = _install_light_blocking_geometry_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "official text hash changed" in str(attempts[0].error)


def test_folded_tele_three_prescriptions_are_terminal_when_f_number_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _folded_tele_missing_f_number_fixture()
    patent_id = _install_folded_tele_missing_f_number_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert [attempt.embodiment for attempt in attempts] == [
        "Folded Tele lens module 220a",
        "Folded Tele lens module 220b",
        "Folded Tele lens module 220c",
    ]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "metadata_unpublished"
        and attempt.error.reason_code == "metadata_unpublished.system_f_number_absent"
        for attempt in attempts
    )


def test_folded_tele_accepts_published_split_conic_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _folded_tele_missing_f_number_fixture(split_conic_header=True)
    patent_id = _install_folded_tele_missing_f_number_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 3
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.reason_code == "metadata_unpublished.system_f_number_absent"
        for attempt in attempts
    )


def test_folded_tele_missing_f_number_classifier_refuses_metadata_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _folded_tele_missing_f_number_fixture(publish_hfov=True)
    patent_id = _install_folded_tele_missing_f_number_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "phrase 'HFOV' occurs 1; expected 0" in str(attempts[0].error)


def test_folded_tele_missing_f_number_classifier_refuses_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _folded_tele_missing_f_number_fixture()
    patent_id = _install_folded_tele_missing_f_number_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "official text hash changed" in str(attempts[0].error)


def test_barrel_spacer_geometry_embodiments_are_confirmed_no_prescription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _barrel_spacer_geometry_only_fixture()
    patent_id = _install_barrel_spacer_geometry_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert [attempt.embodiment for attempt in attempts] == [
        "Barrel/spacer geometry embodiment 1",
        "Barrel/spacer geometry embodiment 2",
        "Barrel/spacer geometry embodiment 3",
    ]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        and attempt.error.reason_code
        == "confirmed_no_prescription.barrel_spacer_geometry_only"
        for attempt in attempts
    )


def test_barrel_spacer_geometry_classifier_refuses_prescription_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _barrel_spacer_geometry_only_fixture(prescription_marker=True)
    patent_id = _install_barrel_spacer_geometry_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "contains a prescription marker" in str(attempts[0].error)


def test_barrel_spacer_geometry_classifier_refuses_source_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = _barrel_spacer_geometry_only_fixture()
    patent_id = _install_barrel_spacer_geometry_fixture_profile(monkeypatch, text)

    attempts = patent_to_zmx._parse_prescription_attempts(
        text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "official text hash changed" in str(attempts[0].error)


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


def _sunny_long_focus_source_fixture(patent_id: str) -> str:
    metadata = []
    focal_lengths = ("40.00", "40.00", "40", "45", "", "40", "48", "40")
    for index, focal_length in enumerate(focal_lengths, start=1):
        metadata.append(
            f"In Embodiment {index}, a total effective focal length f of the camera lens "
            f"has a value of {focal_length} mm, and an aperture number Fno of the camera "
            f"lens has a value of{'4.0' if index == 5 else ' 4.0'}."
        )

    def surface_table(number: int, *, misspelled_s7: bool = False) -> str:
        s7_type = "Sphericai" if misspelled_s7 else "Spherical"
        return f"""TABLE-US-{number:05d} TABLE {number}
        Material Surface Surface Radius of Thickness/ Refractive Dispersion Focal Conic
        No. type curvature distance index coefficient length coefficient
        OBJ Spherical Infinity Infinity STO Spherical Infinity 1.0000
        S1 Aspherical 10.0000 1.0000 1.500 50.00 20.00 0.0000
        S2 Aspherical -10.0000 1.0000 0.0000
        S3 Aspherical 11.0000 1.0000 1.600 40.00 -20.00 0.0000
        S4 Aspherical -11.0000 1.0000 0.0000
        S5 Aspherical 12.0000 1.0000 1.700 30.00 30.00 0.0000
        S6 Aspherical -12.0000 20.0000 0.0000
        S7 {s7_type} Infinity 0.2100 1.518 64.17
        S8 Spherical Infinity 0.7900 S9 Spherical Infinity"""

    def coefficient_table(number: int, coefficient_count: int) -> str:
        labels = ("A4", "A6", "A8", "A10", "A12", "A14", "A16", "A18", "A20")[
            :coefficient_count
        ]
        header = " ".join(labels)
        values = " ".join("0.0E+00" for _ in labels)
        rows = " ".join(f"S{index} {values}" for index in range(1, 7))
        return f"TABLE-US-{number:05d} TABLE {number} Surface No. {header} {rows}"

    tables = [surface_table(1, misspelled_s7=True), coefficient_table(2, 8)]
    tables.append(
        "TABLE-US-00003 TABLE 3 (P1) Spherical Infinity -10.0000 "
        "S1 Aspherical -7.4399 -3.7276 S6 Aspherical -15.8317 -13.7656 "
        "(P2) Spherical Infinity -5.0000 Spherical Infinity 5.0000 "
        "Spherical Infinity 2.3656"
    )
    for embodiment, surface_number, coefficient_number, coefficient_count in (
        (3, 4, 5, 8),
        (4, 6, 7, 8),
        (5, 8, 9, 9),
        (6, 10, 11, 8),
        (7, 12, 13, 9),
        (8, 14, 15, 9),
    ):
        assert embodiment >= 3
        tables.extend(
            [
                surface_table(surface_number),
                coefficient_table(coefficient_number, coefficient_count),
            ]
        )
    tables.append(
        "TABLE-US-00016 TABLE 16 Conditional expression Embodiment 1 2 3 4 5 6 7 8 "
        "f × tan (Semi-FOV) 5.12 ← 5.12 5.76 5.12 5.12 6.15 5.12 "
        "TL/EPD 3.71 ← 3.63 3.68 3.90 3.67 3.64 3.92"
    )
    return " ".join(
        (
            f"{patent_id} - Patent Public Search | USPTO CAMERA LENS Abstract",
            "Family ID: 77932615 Appl. No.: 17/509745",
            "Semi-FOV is the maximum semi-field of view of the camera lens.",
            *metadata,
            *tables,
        )
    )


def test_sunny_long_focus_source_locked_derivation_and_fail_closed_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-SUNNY-LONG-FOCUS-TEST-B2"
    raw_text = _sunny_long_focus_source_fixture(patent_id)
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    monkeypatch.setitem(
        patent_to_zmx._SUNNY_LONG_FOCUS_FOLDED_SOURCE_PROFILES,
        patent_id,
        {
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "table_one_label": "1",
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 9))
    converted = {
        attempt.embodiment_number: attempt.prescription
        for attempt in attempts
        if attempt.prescription is not None
    }
    assert set(converted) == {1, 3, 4, 6, 7, 8}
    assert [converted[index].image_height_mm for index in sorted(converted)] == pytest.approx(
        [5.12, 5.12, 5.76, 5.12, 6.15, 5.12]
    )
    assert all(
        sum(bool(surface.asphere_coefficients) for surface in prescription.surfaces) == 6
        for prescription in converted.values()
    )
    assert isinstance(attempts[1].error, PatentParseError)
    assert "folded-coordinate parser is required" in str(attempts[1].error)
    assert isinstance(attempts[4].error, patent_to_zmx.PatentTerminalParseError)
    assert attempts[4].error.status == "metadata_unpublished"
    assert (
        attempts[4].error.reason_code
        == "metadata_unpublished.configuration_effective_focal_length_and_numeric_semi_fov_absent"
    )


def test_sunny_long_focus_source_locked_product_drift_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-SUNNY-LONG-FOCUS-DRIFT-B2"
    raw_text = _sunny_long_focus_source_fixture(patent_id).replace(
        "5.12 ← 5.12 5.76",
        "5.13 ← 5.12 5.76",
        1,
    )
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    monkeypatch.setitem(
        patent_to_zmx._SUNNY_LONG_FOCUS_FOLDED_SOURCE_PROFILES,
        patent_id,
        {
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "table_one_label": "1",
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 8
    assert all(attempt.prescription is None for attempt in attempts)
    assert {
        str(attempt.error) for attempt in attempts
    } == {"Sunny long-focus field-product token sequence changed"}


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-12216247-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "52c7518342334430",
                "US-12216247-B2.html",
            ),
        ),
        (
            "US-20220244497-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "f19c4e1fdb2e6594",
                "US-20220244497-A1.html",
            ),
        ),
    ),
)
def test_sunny_fingerprint_wide_angle_exact_sources_recover_all_five_embodiments(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)
    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4, 5]
    assert all(attempt.error is None for attempt in attempts)
    prescriptions = [attempt.prescription for attempt in attempts]
    assert all(prescription is not None for prescription in prescriptions)
    assert [prescription.focal_length_mm for prescription in prescriptions] == pytest.approx(
        [0.26, 0.30, 0.27, 0.29, 0.29]
    )
    assert [prescription.f_number for prescription in prescriptions] == pytest.approx(
        [1.40, 1.36, 1.38, 1.48, 1.49]
    )
    assert [prescription.hfov_deg for prescription in prescriptions] == pytest.approx(
        [74.95, 72.85, 71.45, 70.70, 72.00]
    )
    assert [prescription_fingerprint(prescription) for prescription in prescriptions] == [
        "49bac5303aeebcea",
        "d8f042c1b2c3a55e",
        "64a36b2afe0001f8",
        "9b5f2449551c89d2",
        "55b063230f9e7c27",
    ]
    assert all(len(prescription.surfaces) == 12 for prescription in prescriptions)
    assert all(
        sum(surface.surface_type == "ASP" for surface in prescription.surfaces) == 6
        for prescription in prescriptions
    )
    assert all(prescription.surfaces[0].nd == pytest.approx(1.52) for prescription in prescriptions)
    assert all(prescription.surfaces[4].label == "Stop" for prescription in prescriptions)
    assert all(prescription.surfaces[-1].label == "Surface S9" for prescription in prescriptions)


def test_sunny_fingerprint_wide_angle_metadata_drift_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-12216247-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "52c7518342334430"
        / "US-12216247-B2.html"
    )
    raw_text = source_path.read_text(encoding="utf-8").replace(
        "FOV is 149.9°",
        "FOV is 149.8°",
        1,
    )
    monkeypatch.setitem(
        patent_to_zmx._SUNNY_FINGERPRINT_WIDE_ANGLE_SOURCE_PROFILES,
        patent_id,
        {
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                patent_to_zmx.normalize_patent_text(raw_text).encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 5
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "Sunny fingerprint embodiment metadata changed"
    }


def test_sunny_fingerprint_wide_angle_optical_cell_drift_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-12216247-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "52c7518342334430"
        / "US-12216247-B2.html"
    )
    original = source_path.read_text(encoding="utf-8")
    raw_text = original.replace(
        "0.2445",
        "0.2446",
        1,
    )
    assert raw_text != original
    monkeypatch.setitem(
        patent_to_zmx._SUNNY_FINGERPRINT_WIDE_ANGLE_SOURCE_PROFILES,
        patent_id,
        {
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                patent_to_zmx.normalize_patent_text(raw_text).encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 5
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "Sunny fingerprint embodiment 1 optical cells changed"
    }


def _lens_barrel_absorbing_source_fixture(patent_id: str) -> str:
    headings = " ".join(
        f"{index}{'st' if index == 1 else 'nd' if index == 2 else 'rd' if index == 3 else 'th'} "
        f"Example [{index:04d}] FIG. {index} A is a schematic view."
        for index in range(1, 9)
    )

    def geometry_table(index: int) -> str:
        suffix = "st" if index == 1 else "nd" if index == 2 else "rd" if index == 3 else "th"
        if index <= 6:
            body = (
                "EPD (mm) 1.62 ψY (mm) 1.62 ψb (mm) 1.881 ψL (mm) 3.098 "
                "EPD/ψb 0.861 ψY/ψL 0.523 ψA (mm) 1.884 ψL/ψb 1.647 "
                "EPD/ψA 0.860 CT (mm) 0.89 L (mm) 0.622 ψY/CT 1.820"
            )
        else:
            body = (
                "EPD (mm) 1.77 ψY (mm) 2.32 ψb (mm) 1.82 ψY/ψL 0.720 "
                "EPD/ψb 0.973 ψL/ψb 1.275 L (mm) 0.22 CT (mm) 0.492 "
                "ψY (mm) 1.67 ψY/CT 3.394"
            )
        return (
            f"TABLE-US-{index:05d} TABLE {index} {index}{suffix} example {body} "
            f"[{1000 + index:04d}] According to the {index}{suffix} example."
        )

    return " ".join(
        (
            f"{patent_id} - Patent Public Search | USPTO IMAGING LENS ASSEMBLY, "
            "CAMERA MODULE AND ELECTRONIC DEVICE Abstract",
            "Family ID: 72082560 Appl. No.: 16/924496",
            "minimum opening optical lens element set",
            "BRIEF DESCRIPTION OF THE DRAWINGS FIG. 1 A is a schematic view. "
            "DETAILED DESCRIPTION",
            headings,
            "The 8th example is a smart phone with an image sensor.",
            *(geometry_table(index) for index in range(1, 8)),
        )
    )


def _install_lens_barrel_absorbing_test_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    phrases = ("minimum opening", "optical lens element set", "smart phone", "image sensor")
    monkeypatch.setitem(
        patent_to_zmx._LENS_BARREL_ABSORBING_GEOMETRY_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "application_number": "16/924496",
            "table7_prefix": "7th example EPD (mm) 1.77 ψY (mm) 2.32 ψb (mm) 1.82",
            "geometry_phrase_counts": {
                phrase: len(re.findall(re.escape(phrase), normalized, re.IGNORECASE))
                for phrase in phrases
            },
        },
    )


def test_lens_barrel_absorbing_source_locked_examples_are_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-LENS-BARREL-ABSORBING-TEST-A1"
    raw_text = _lens_barrel_absorbing_source_fixture(patent_id)
    _install_lens_barrel_absorbing_test_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 9))
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        for attempt in attempts
    )
    assert {
        attempt.error.reason_code for attempt in attempts[:7]
    } == {"confirmed_no_prescription.lens_barrel_absorbing_geometry_only"}
    assert (
        attempts[7].error.reason_code
        == "confirmed_no_prescription.camera_module_device_architecture_only"
    )


def test_lens_barrel_absorbing_source_locked_prescription_marker_fails_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-LENS-BARREL-ABSORBING-DRIFT-A1"
    raw_text = _lens_barrel_absorbing_source_fixture(patent_id).replace(
        "minimum opening optical lens element set",
        "minimum opening optical lens element set radius of curvature",
        1,
    )
    _install_lens_barrel_absorbing_test_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 8
    assert all(attempt.prescription is None for attempt in attempts)
    assert {
        str(attempt.error) for attempt in attempts
    } == {"lens-barrel absorbing disclosure contains a prescription marker"}


def _folded_lens_barrel_driving_source_fixture(patent_id: str) -> str:
    return " ".join(
        (
            f"{patent_id} - Patent Public Search | USPTO IMAGING LENS ASSEMBLY MODULE, "
            "IMAGING LENS ASSEMBLY DRIVING MODULE AND ELECTRONIC DEVICE Abstract",
            "Family ID: 77725725 Appl. No.: 18/337147",
            "BRIEF DESCRIPTION OF THE DRAWINGS FIG. 1 A is an exploded view. "
            "FIG. 1 E is an optical surface schematic view. DETAILED DESCRIPTION",
            "1st Embodiment [0041] Please refer to FIG. 1 A.",
            "imaging lens assembly module imaging lens assembly driving module "
            "light path folding element first lens barrel second lens barrel "
            "rolling bearings first sensing element fourth sensing element "
            "plastic lens elements",
            "TABLE-US-00001 d1 (mm) 1.4 d2 (mm) 1.4",
            "2nd Embodiment [0066] Please refer to FIG. 2 A.",
            "The smartphone includes an image sensor and imaging lens assembly modules "
            "with different focal length.",
        )
    )


def _install_folded_lens_barrel_driving_test_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    phrases = (
        "Family ID: 77725725",
        "imaging lens assembly module",
        "imaging lens assembly driving module",
        "light path folding element",
        "first lens barrel",
        "second lens barrel",
        "rolling bearings",
        "first sensing element",
        "fourth sensing element",
        "plastic lens elements",
        "smartphone",
        "image sensor",
        "FIG. 1 E is an optical surface schematic view",
        "TABLE-US-00001",
    )
    monkeypatch.setitem(
        patent_to_zmx._FOLDED_LENS_BARREL_DRIVING_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "application_number": "18/337147",
            "heading_markers": (
                "1st Embodiment [0041]",
                "2nd Embodiment [0066]",
            ),
            "table_prefix": "TABLE-US-00001 d1 (mm) 1.4 d2 (mm) 1.4",
            "ppubs_table_count": len(
                patent_to_zmx._patent_table_blocks(normalized)
            ),
            "architecture_phrase_counts": {
                phrase: len(re.findall(re.escape(phrase), normalized, re.IGNORECASE))
                for phrase in phrases
            },
        },
    )


def test_folded_lens_barrel_driving_source_locked_examples_are_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-FOLDED-LENS-BARREL-DRIVING-TEST-A1"
    raw_text = _folded_lens_barrel_driving_source_fixture(patent_id)
    _install_folded_lens_barrel_driving_test_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        for attempt in attempts
    )
    assert attempts[0].error.reason_code == (
        "confirmed_no_prescription.lens_driving_mechanical_architecture_only"
    )
    assert attempts[1].error.reason_code == (
        "confirmed_no_prescription.camera_module_device_architecture_only"
    )


def test_folded_lens_barrel_driving_prescription_marker_fails_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-FOLDED-LENS-BARREL-DRIVING-DRIFT-A1"
    raw_text = _folded_lens_barrel_driving_source_fixture(patent_id) + (
        " radius of curvature"
    )
    _install_folded_lens_barrel_driving_test_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 2
    assert all(attempt.prescription is None for attempt in attempts)
    assert {
        str(attempt.error) for attempt in attempts
    } == {"folded lens-barrel driving disclosure contains a prescription marker"}


def _circle_optics_mechanical_source_fixture(patent_id: str) -> str:
    drawings = []
    for figure in range(1, 29):
        if figure == 8:
            description = "FIG. 8 depicts an image sensor with a sensor mount having adjustors"
        elif figure == 21:
            description = (
                "FIG. 21 depicts an alternate configuration for an improved multi-camera "
                "projection device"
            )
        else:
            description = f"FIG. {figure} is a schematic architecture view"
        drawings.append(f"({figure}) {description}.")
    return " ".join(
        (
            f"{patent_id} - Patent Public Search | USPTO OPTO-MECHANICS OF PANORAMIC "
            "CAPTURE DEVICES WITH ABUTTING CAMERAS Abstract",
            "Family ID: 74060373 Appl. No.: 17/622393",
            "BRIEF DESCRIPTION OF THE DRAWINGS",
            *drawings,
            "DETAILED DESCRIPTION outer compressor aperture stop image plane aspheric "
            "surfaces lens element thicknesses and curvatures",
        )
    )


def _install_circle_optics_mechanical_test_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    phrases = (
        "Family ID: 74060373",
        "outer compressor",
        "aperture stop",
        "image plane",
        "aspheric surfaces",
        "lens element thicknesses and curvatures",
        "FIG. 8 depicts an image sensor with a sensor mount having adjustors",
        "FIG. 21 depicts an alternate configuration for an improved multi-camera "
        "projection device",
    )
    monkeypatch.setitem(
        patent_to_zmx._CIRCLE_OPTICS_MECHANICAL_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "application_number": "17/622393",
            "drawing_description_count": 28,
            "architecture_phrase_counts": {
                phrase: len(re.findall(re.escape(phrase), normalized, re.IGNORECASE))
                for phrase in phrases
            },
        },
    )


def test_circle_optics_mechanical_source_locked_member_is_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-CIRCLE-OPTICS-MECHANICAL-TEST-B2"
    raw_text = _circle_optics_mechanical_source_fixture(patent_id)
    _install_circle_optics_mechanical_test_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert attempts[0].error.status == "confirmed_no_prescription"
    assert attempts[0].error.reason_code == (
        "confirmed_no_prescription.panoramic_opto_mechanical_architecture_only"
    )


def test_circle_optics_mechanical_prescription_marker_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-CIRCLE-OPTICS-MECHANICAL-DRIFT-B2"
    raw_text = _circle_optics_mechanical_source_fixture(patent_id) + " lens prescription"
    _install_circle_optics_mechanical_test_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 1
    assert str(attempts[0].error) == (
        "Circle Optics mechanical disclosure contains a prescription marker"
    )


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


def test_convert_candidate_preserves_source_terminal_status_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch(
        _client: object,
        _token: str,
        patent_id: str,
    ) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html=_samsung_eight_lens_missing_stop_fixture(),
            source_bucket="US-PGPUB",
            attempts=(
                patent_to_zmx.SourceFetchAttempt(
                    publication_id=patent_id,
                    source_bucket="US-PGPUB",
                    state=patent_to_zmx.SourceFetchState.RETAINED,
                    http_status=200,
                ),
            ),
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("source-terminal outcomes must not launch a trace worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "token",
            patent_to_zmx.PatentCandidate(
                patent_id="US-SAMSUNG-EIGHT-LENS-A1",
                title="fixture",
                source_url="",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "zmx",
            raw_document_dir=tmp_path / "raw",
        )
    )

    assert [attempt.status for attempt in attempts] == ["metadata_unpublished"] * 5
    assert {
        attempt.reason_code for attempt in attempts
    } == {"metadata_unpublished.stop_axial_coordinate_absent"}
    assert all(attempt.raw_document_path for attempt in attempts)
    assert not (tmp_path / "zmx").exists() or not any((tmp_path / "zmx").iterdir())


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
