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


def _ability_five_three_lens_pdf_ocr_parser_input() -> bytes:
    pages = []
    for embodiment, (surface_page, surface_figure, asphere_page, asphere_figure) in enumerate(
        zip(
            (4, 8, 12, 16, 20),
            (3, 7, 11, 15, 19),
            (5, 9, 13, 17, 21),
            (4, 8, 12, 16, 20),
            strict=True,
        ),
        start=1,
    ):
        surface_tokens = [
            _ability_ocr_token(f"FIG.{surface_figure}", 100.0, 100.0),
            _ability_ocr_token("Radius of", 200.0, 100.0),
            _ability_ocr_token("Curvature", 300.0, 100.0),
            _ability_ocr_token("Thickness", 400.0, 100.0),
            _ability_ocr_token("Refractive", 500.0, 100.0),
            _ability_ocr_token("Abbe", 600.0, 100.0),
            _ability_ocr_token("Effective Focal", 700.0, 100.0),
            _ability_ocr_token("Distance fn", 800.0, 100.0),
            *(
                _ability_ocr_token(str(number), 100.0 + number * 10.0, 200.0)
                for number in range(25)
            ),
        ]
        pages.append(
            {
                "page_number": surface_page,
                "role": f"ability_five_three_surface_{embodiment}",
                "official_image_sha256": str(surface_page % 10) * 64,
                "mirror_text": f"Sheet {surface_page - 1} of 21 FIG. {surface_figure}",
                "rapidocr_tokens": surface_tokens,
            }
        )
        asphere_tokens = [
            _ability_ocr_token(f"FIG.{asphere_figure}", 100.0, 100.0),
            _ability_ocr_token("Surface", 200.0, 100.0),
            *(
                _ability_ocr_token(label, 300.0 + index * 50.0, 100.0)
                for index, label in enumerate(("B", "E", "F", "H"))
            ),
            *(
                _ability_ocr_token(str(number), 100.0 + number * 10.0, 200.0)
                for number in range(55)
            ),
        ]
        pages.append(
            {
                "page_number": asphere_page,
                "role": f"ability_five_three_asphere_{embodiment}",
                "official_image_sha256": str(asphere_page % 10) * 64,
                "mirror_text": f"Sheet {asphere_page - 1} of 21 FIG. {asphere_figure}",
                "rapidocr_tokens": asphere_tokens,
            }
        )
    meta_tokens = [
        _ability_ocr_token("FIG.21", 100.0, 100.0),
        *(
            _ability_ocr_token(ordinal, 200.0 + index * 100.0, 100.0)
            for index, ordinal in enumerate(("First", "Second", "Third", "Fourth", "Fifth"))
        ),
        _ability_ocr_token("FOV", 800.0, 100.0),
        *(
            _ability_ocr_token(str(number), 100.0 + number * 10.0, 200.0)
            for number in range(55)
        ),
    ]
    pages.append(
        {
            "page_number": 22,
            "role": "ability_five_three_meta",
            "official_image_sha256": "2" * 64,
            "mirror_text": "Sheet 21 of 21 FIG. 21 First Second Third Fourth Fifth FOV",
            "rapidocr_tokens": meta_tokens,
        }
    )
    values = {
        ordinal: {
            "entrance_pupil_diameter_mm": epd,
            "focal_length_mm": focal_length,
            "full_field_of_view_deg": fov,
        }
        for ordinal, epd, focal_length, fov in zip(
            ("first", "second", "third", "fourth", "fifth"),
            (0.666, 1.075, 1.178, 1.097, 1.124),
            (1.619, 2.408, 2.393, 2.227, 2.716),
            (84.0, 84.0, 84.0, 87.0, 77.4),
            strict=True,
        )
    }
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "ability_five_three_lens_f_number_unpublished_v1",
        "publication_id": "US-20160085051-A1",
        "page_count": 27,
        "source_facts": {
            "primary_html_sha256": (
                "a389c98016a9f5af18165a30a2041fe29a761d3d37958ffce100e8bfb81ea50d"
            ),
            "normalized_text_sha256": (
                "a7a4d8d7489ef8db8b76b64868fdcf31cfc32b37934a5c17f39484893f212b1f"
            ),
            "family_id": "55525612",
            "application_number": "14/858521",
            "figure_binding_counts": {
                f"FIG. {figure}": 1
                for figure in (3, 4, 7, 8, 11, 12, 15, 16, 19, 20, 21)
            },
            "embodiment_detail_counts": dict.fromkeys(
                ("first", "second", "third", "fourth", "fifth"),
                1,
            ),
            "embodiment_system_values": values,
            "f_number_label_counts": {"FNO": 0, "F-number": 0, "F/#": 0},
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _aac_two_three_lens_pdf_ocr_parser_input() -> bytes:
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "aac_two_three_lens_field_unpublished_v1",
        "publication_id": "US-20160161712-A1",
        "page_count": 7,
        "source_facts": {
            "primary_html_sha256": (
                "d442fce31a21057546974505b5aa3e5361304ad8525afe7455a4cb438bfb5600"
            ),
            "normalized_text_sha256": (
                "99c5ebf699ef689f6769d12e6a755c33eda8e3fac4021eccdf3f36abf693213d"
            ),
            "family_id": "53345880",
            "application_number": "14/832442",
            "figure_binding_counts": {
                "FIG. 1": 1,
                "FIG. 2": 1,
                "FIG. 3": 1,
                "FIG. 4": 1,
            },
            "table_numbers": [1, 2, 3, 4, 5],
            "table_block_sha256": [
                "e2ec3a72c80cf18601e0ee782c9550d9feffd600aea8d06081b122c0955586f5",
                "5c1f1c74edb0ba1ffd97f8b5d86808d4cae516047cf9059cd533d1d3facdb386",
                "efb81b625b9f8f04857d955c7beee11576014688f8103baf4b312950bcc836e5",
                "01ff5df296ef054c678b06fa3a1db72a3c96446e724e0fc6a60a8fec22afe39a",
                "c006d1ce1ef4a7827d844fa46e812622007675de3b8473228d817430dc0812c5",
            ],
            "embodiment_table_bindings": {
                "1": {"surface_table": 1, "asphere_table": 2},
                "2": {"surface_table": 3, "asphere_table": 4},
            },
            "embodiment_system_values": {
                "1": {
                    "focal_length_mm": 3.5246,
                    "f_number": 2.8,
                    "published_dof_deg": 33.41,
                },
                "2": {
                    "focal_length_mm": 2.3412,
                    "f_number": 2.6,
                    "published_dof_deg": 37.72,
                },
            },
            "dof_label_count": 2,
            "dof_expansion_count": 1,
            "system_field_label_counts": {
                "FOV": 0,
                "HFOV": 0,
                "field of view": 0,
                "angle of view": 0,
            },
        },
        "pages": [
            {
                "page_number": 2,
                "role": "aac_two_three_drawing_sheet_1",
                "official_image_sha256": "1" * 64,
                "mirror_text": "Patent Application Publication Sheet 1 of 2 Fig. 1 Fig. 2",
                "rapidocr_tokens": [
                    _ability_ocr_token("Fig.1", 100.0, 100.0),
                    _ability_ocr_token("Fig.2", 200.0, 100.0),
                ],
            },
            {
                "page_number": 3,
                "role": "aac_two_three_drawing_sheet_2",
                "official_image_sha256": "2" * 64,
                "mirror_text": "Patent Application Publication Sheet 2 of 2 Fig. 3 Fig. 4",
                "rapidocr_tokens": [
                    _ability_ocr_token("Fig.3", 100.0, 100.0),
                    _ability_ocr_token("Fig.4", 200.0, 100.0),
                ],
            },
        ],
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


def _ability_three_five_lens_pdf_ocr_parser_input(
    publication_id: str = "US-11719909-B2",
) -> bytes:
    source_profile = patent_to_zmx._ABILITY_THREE_FIVE_LENS_PUBLICATION_SOURCES[
        publication_id
    ]
    source_facts = {
        "primary_html_sha256": source_profile["primary_html_sha256"],
        "normalized_text_sha256": source_profile["normalized_text_sha256"],
        "family_id": "74187659",
        "application_number": "16/883126",
        "prescription_count": 3,
        "lens_element_count": 5,
        "figure_binding_counts": dict.fromkeys(
            (
                "surface_ol1",
                "asphere_ol1",
                "surface_ol2",
                "asphere_ol2",
                "surface_ol3",
                "asphere_ol3",
                "system_meta",
            ),
            2,
        ),
        "angular_field_label_counts": {
            "FOV": 0,
            "HFOV": 0,
            "field of view": 0,
            "viewing angle": 0,
            "angle of view": 0,
            "image height": 0,
        },
        "shape_coordinate_definition_counts": {"h": 1, "H": 1},
    }
    common_prescription_labels = (
        "Surface",
        "Curvature",
        "Thickness",
        "Refractive",
        "Abbe",
        "S2",
        "S3",
        "S4",
        "St",
        "S5",
        "S6",
        "S7",
        "S8",
        "S9",
        "S10",
        "S11",
        "S12",
        "K",
        "A2",
        "A4",
        "A6",
        "A8",
        "A10",
        "A12",
        "A14",
        "A16",
    )
    pages = []
    for embodiment_number in (1, 2, 3):
        role = f"ability_three_five_prescription_ol{embodiment_number}"
        page_number = patent_to_zmx._ABILITY_THREE_FIVE_LENS_ROLE_PAGE_NUMBERS[role]
        tokens = [
            _ability_ocr_token(f"FIG. {embodiment_number + 3}A", 100.0, 100.0),
            _ability_ocr_token(f"FIG. {embodiment_number + 3}B", 200.0, 100.0),
            _ability_ocr_token("S1", 100.0, 200.0),
            *(
                _ability_ocr_token(label, 300.0 + index * 10.0, 300.0)
                for index, label in enumerate(common_prescription_labels)
            ),
        ]
        if embodiment_number == 2:
            tokens.append(_ability_ocr_token("-17.90", 200.0, 200.0))
        pages.append(
            {
                "page_number": page_number,
                "role": role,
                "official_image_sha256": source_profile["key_page_image_sha256"][role],
                "mirror_text": (
                    "" if page_number in source_profile["blank_key_pages"] else "OCR text"
                ),
                "rapidocr_tokens": tokens,
            }
        )

    meta_role = "ability_three_five_system_meta"
    meta_page_number = patent_to_zmx._ABILITY_THREE_FIVE_LENS_ROLE_PAGE_NUMBERS[
        meta_role
    ]
    meta_tokens = [
        _ability_ocr_token("FIG. 7", 100.0, 500.0),
        _ability_ocr_token("OL1", 200.0, 100.0),
        _ability_ocr_token("OL2", 300.0, 100.0),
        _ability_ocr_token("OL3", 400.0, 100.0),
        _ability_ocr_token("EFL (mm)", 100.0, 150.0),
        _ability_ocr_token("Fno", 100.0, 170.0),
        _ability_ocr_token("TTL (mm)", 100.0, 190.0),
        _ability_ocr_token("F1 (mm)", 100.0, 210.0),
        _ability_ocr_token("F2 (mm)", 100.0, 230.0),
        _ability_ocr_token("F3 (mm)", 100.0, 250.0),
        _ability_ocr_token("F4 (mm)", 100.0, 270.0),
        _ability_ocr_token("F5 (mm)", 100.0, 290.0),
        _ability_ocr_token("F345 (mm)", 100.0, 310.0),
        _ability_ocr_token("F2/F345", 100.0, 330.0),
        _ability_ocr_token("TTL/EFL", 100.0, 350.0),
        _ability_ocr_token("R1 (mm)", 100.0, 400.0),
        _ability_ocr_token("R2 (mm)", 100.0, 420.0),
        _ability_ocr_token("R3 (mm)", 100.0, 440.0),
        _ability_ocr_token("R4 (mm)", 100.0, 460.0),
        _ability_ocr_token("17.90", 300.0, 400.0),
    ]
    pages.append(
        {
            "page_number": meta_page_number,
            "role": meta_role,
            "official_image_sha256": source_profile["key_page_image_sha256"][meta_role],
            "mirror_text": (
                ""
                if meta_page_number in source_profile["blank_key_pages"]
                else "OCR text"
            ),
            "rapidocr_tokens": meta_tokens,
        }
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "ability_three_five_lens_angular_field_unpublished_v1",
        "publication_id": publication_id,
        "page_count": 13,
        "source_facts": source_facts,
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_seven_lens_seven_pdf_ocr_parser_input() -> bytes:
    ordinals = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh")
    pages = []
    for example_number, ordinal in enumerate(ordinals, start=1):
        optical_page_number = 11 + (example_number - 1) * 2
        asphere_page_number = optical_page_number + 1
        optical_figure = 20 + (example_number - 1) * 2
        asphere_figure = optical_figure + 1
        optical_tokens = [
            _ability_ocr_token(
                f"Sheet {optical_page_number - 1} of 25",
                700.0,
                50.0,
            ),
            _ability_ocr_token(f"{ordinal.title()} Example", 100.0, 100.0),
            *(
                _ability_ocr_token(f"{label}=1", 100.0 + index * 100.0, 150.0)
                for index, label in enumerate(("EFL", "HFOV", "TTL", "Fno"))
            ),
            *(
                _ability_ocr_token(label, 100.0 + index * 100.0, 200.0)
                for index, label in enumerate(
                    ("Curvature", "Thickness", "Refractive", "Abbe", "Focal Length")
                )
            ),
            *(
                _ability_ocr_token(f"{name} Lens", 100.0, 250.0 + index * 30.0)
                for index, name in enumerate(
                    ("First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh")
                )
            ),
            _ability_ocr_token(f"FIG. {optical_figure}", 700.0, 600.0),
        ]
        pages.append(
            {
                "page_number": optical_page_number,
                "role": f"genius_seven_optical_{example_number}",
                "official_image_sha256": str(example_number) * 64,
                "mirror_text": "",
                "rapidocr_scale": 0.5,
                "rapidocr_tokens": optical_tokens,
            }
        )
        asphere_tokens = [_ability_ocr_token(f"FIG. {asphere_figure}", 700.0, 50.0)]
        for label in ("No.", "K", "a2", "a4", "a6", "a8", "a10", "a12", "a14", "a16"):
            asphere_tokens.extend(
                (
                    _ability_ocr_token(label, 100.0, 100.0),
                    _ability_ocr_token(label, 500.0, 100.0),
                )
            )
        pages.append(
            {
                "page_number": asphere_page_number,
                "role": f"genius_seven_asphere_{example_number}",
                "official_image_sha256": str(example_number + 1) * 64,
                "mirror_text": "",
                "rapidocr_rotation": "clockwise_90",
                "rapidocr_scale": 0.5,
                "rapidocr_tokens": asphere_tokens,
            }
        )
    pages.extend(
        (
            {
                "page_number": 25,
                "role": "genius_seven_comparison_1",
                "official_image_sha256": "e" * 64,
                "mirror_text": "",
                "rapidocr_scale": 0.5,
                "rapidocr_tokens": [
                    _ability_ocr_token("Sheet 24 of 25", 700.0, 50.0),
                    _ability_ocr_token("FIG. 34", 700.0, 100.0),
                ],
            },
            {
                "page_number": 26,
                "role": "genius_seven_comparison_2",
                "official_image_sha256": "f" * 64,
                "mirror_text": "",
                "rapidocr_rotation": "clockwise_90",
                "rapidocr_scale": 0.5,
                "rapidocr_tokens": [_ability_ocr_token("FIG. 35", 700.0, 100.0)],
            },
        )
    )
    primary_digest = "1197f4ec4bb5df4a37e2b93c1bf5292aab4b2f27fdfede1e09e0d0a896807da8"
    layout = patent_pdf_recovery.genius_seven_lens_seven_source_layout_for_sha256(
        primary_digest
    )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_seven_lens_seven_example_census_v1",
        "publication_id": "US-20240411113-A1",
        "page_count": 36,
        "source_facts": {
            "primary_html_sha256": primary_digest,
            "normalized_text_sha256": layout["normalized_text_sha256"],
            "family_id": layout["family_id"],
            "application_number": layout["application_number"],
            "figure_binding_counts": dict.fromkeys(
                patent_pdf_recovery._GENIUS_SEVEN_LENS_SEVEN_REQUIRED_FIGURE_TEXT,
                1,
            ),
            "comparison_binding_counts": dict.fromkeys(
                patent_pdf_recovery._GENIUS_SEVEN_LENS_SEVEN_COMPARISON_MARKERS,
                1,
            ),
            "example_heading_counts": dict.fromkeys(ordinals, 1),
            "system_values": list(layout["system_values"]),
            "genius_applicant_assignee_count": 2,
        },
        "pages": pages,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _genius_four_lens_six_pdf_ocr_parser_input(publication_id: str) -> bytes:
    root = Path(__file__).resolve().parents[1]
    evidence_root = (
        root
        / ".planning/quick/260716-patent-generic-family-48495278"
    )
    ocr_audit = json.loads(
        (evidence_root / "family-48495278-ocr-audit.json").read_text(
            encoding="utf-8"
        )
    )
    source_paths = {
        "US-20150138653-A1": (
            root
            / "data/patent-lake/uspto-ppubs-html/US-PGPUB/cc17913116d0dc5e/"
            "US-20150138653-A1.html"
        ),
        "US-8976467-B2": (
            root
            / "data/patent-lake/uspto-ppubs-html/USPAT/dc2eefd750653fe9/"
            "US-8976467-B2.html"
        ),
    }
    source = source_paths[publication_id].read_text(encoding="utf-8")
    facts = patent_pdf_recovery._genius_four_lens_six_source_facts(source)
    layout = patent_pdf_recovery.genius_four_lens_six_source_layout_for_sha256(
        facts["primary_html_sha256"]
    )
    pages = []
    for audit_page in ocr_audit["publications"][publication_id]["pages"]:
        audit_role = audit_page["role"]
        role = (
            "genius_four_six_comparison"
            if audit_role == "comparison"
            else f"genius_four_six_{audit_role}"
        )
        page_number = audit_page["page_number"]
        pages.append(
            {
                "page_number": page_number,
                "role": role,
                "official_image_sha256": layout["page_image_sha256"][
                    page_number - 1
                ],
                "mirror_text": audit_page["mirror_text"],
                "rapidocr_tokens": audit_page["rapidocr_tokens"],
            }
        )
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "profile": "genius_four_lens_six_embodiment_census_v1",
        "publication_id": publication_id,
        "page_count": layout["page_count"],
        "source_facts": facts,
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


def test_ability_five_three_lens_sources_bind_five_prescriptions() -> None:
    root = Path(__file__).resolve().parents[1]
    source_paths = (
        root
        / "data/patent-lake/uspto-ppubs-html/US-PGPUB/a389c98016a9f5af/"
        "US-20160085051-A1.html",
        root
        / "data/patent-lake/uspto-ppubs-html/USPAT/e9fee581375c0ca2/"
        "US-9541733-B2.html",
    )
    expected_values = {
        ordinal: {
            "entrance_pupil_diameter_mm": epd,
            "focal_length_mm": focal_length,
            "full_field_of_view_deg": fov,
        }
        for ordinal, epd, focal_length, fov in zip(
            ("first", "second", "third", "fourth", "fifth"),
            (0.666, 1.075, 1.178, 1.097, 1.124),
            (1.619, 2.408, 2.393, 2.227, 2.716),
            (84.0, 84.0, 84.0, 87.0, 77.4),
            strict=True,
        )
    }

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        assert patent_pdf_recovery.ability_drawing_tables_declared(source)
        facts = patent_pdf_recovery._ability_five_three_lens_source_facts(source)
        assert facts["family_id"] == "55525612"
        assert facts["application_number"] == "14/858521"
        assert facts["figure_binding_counts"] == {
            f"FIG. {figure}": 1
            for figure in (3, 4, 7, 8, 11, 12, 15, 16, 19, 20, 21)
        }
        assert facts["embodiment_detail_counts"] == dict.fromkeys(
            ("first", "second", "third", "fourth", "fifth"),
            1,
        )
        assert facts["embodiment_system_values"] == expected_values
        assert facts["f_number_label_counts"] == {
            "FNO": 0,
            "F-number": 0,
            "F/#": 0,
        }
        assert not patent_pdf_recovery.ability_drawing_tables_declared(source + " ")


def test_ability_three_five_lens_sources_bind_full_denominator_and_field_gap() -> None:
    root = Path(__file__).resolve().parents[1]
    source_paths = (
        root
        / "data/patent-lake/uspto-ppubs-html/US-PGPUB/a94cba4e581ebdb5/"
        "US-20210026108-A1.html",
        root
        / "data/patent-lake/uspto-ppubs-html/USPAT/f43a4a419a082df6/"
        "US-11719909-B2.html",
    )

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        assert patent_pdf_recovery.ability_drawing_tables_declared(source)
        layout = patent_pdf_recovery._ability_three_five_lens_source_layout(source)
        assert layout["page_count"] == 13
        assert len(layout["page_image_sha256"]) == 13
        assert layout["role_pages"] == {
            "ability_three_five_prescription_ol1": 4,
            "ability_three_five_prescription_ol2": 5,
            "ability_three_five_prescription_ol3": 6,
            "ability_three_five_system_meta": 7,
        }
        facts = patent_pdf_recovery._ability_three_five_lens_source_facts(source)
        assert facts["family_id"] == "74187659"
        assert facts["application_number"] == "16/883126"
        assert facts["prescription_count"] == 3
        assert facts["lens_element_count"] == 5
        assert facts["figure_binding_counts"] == dict.fromkeys(
            (
                "surface_ol1",
                "asphere_ol1",
                "surface_ol2",
                "asphere_ol2",
                "surface_ol3",
                "asphere_ol3",
                "system_meta",
            ),
            2,
        )
        assert facts["angular_field_label_counts"] == {
            "FOV": 0,
            "HFOV": 0,
            "field of view": 0,
            "viewing angle": 0,
            "angle of view": 0,
            "image height": 0,
        }
        assert facts["shape_coordinate_definition_counts"] == {"h": 1, "H": 1}
        assert not patent_pdf_recovery.ability_drawing_tables_declared(source + " ")


def test_aac_two_three_lens_sources_bind_two_prescriptions_and_field_gap() -> None:
    root = Path(__file__).resolve().parents[1]
    source_paths = (
        root
        / "data/patent-lake/uspto-ppubs-html/US-PGPUB/d442fce31a210575/"
        "US-20160161712-A1.html",
        root
        / "data/patent-lake/uspto-ppubs-html/USPAT/cd5bc9f6cab04ac6/"
        "US-9810879-B2.html",
    )

    for source_path in source_paths:
        source = source_path.read_text(encoding="utf-8")
        assert patent_pdf_recovery.ability_drawing_tables_declared(source)
        facts = patent_pdf_recovery._aac_two_three_lens_source_facts(source)
        assert facts["family_id"] == "53345880"
        assert facts["application_number"] == "14/832442"
        assert facts["figure_binding_counts"] == {
            "FIG. 1": 1,
            "FIG. 2": 1,
            "FIG. 3": 1,
            "FIG. 4": 1,
        }
        assert facts["table_numbers"] == [1, 2, 3, 4, 5]
        assert facts["embodiment_table_bindings"] == {
            "1": {"surface_table": 1, "asphere_table": 2},
            "2": {"surface_table": 3, "asphere_table": 4},
        }
        assert facts["embodiment_system_values"] == {
            "1": {
                "focal_length_mm": 3.5246,
                "f_number": 2.8,
                "published_dof_deg": 33.41,
            },
            "2": {
                "focal_length_mm": 2.3412,
                "f_number": 2.6,
                "published_dof_deg": 37.72,
            },
        }
        assert facts["dof_label_count"] == 2
        assert facts["dof_expansion_count"] == 1
        assert facts["system_field_label_counts"] == {
            "FOV": 0,
            "HFOV": 0,
            "field of view": 0,
            "angle of view": 0,
        }
        assert not patent_pdf_recovery.ability_drawing_tables_declared(source + " ")


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


@pytest.mark.parametrize(
    (
        "source_path",
        "application_number",
        "page_count",
        "blank_pages",
        "owner_count",
        "relationship_counts",
    ),
    (
        (
            Path(
                "data/patent-lake/uspto-ppubs-html/US-PGPUB/cc17913116d0dc5e/"
                "US-20150138653-A1.html"
            ),
            "14/608769",
            36,
            frozenset(),
            1,
            {
                "continuation_parent_application": 1,
                "related_parent_application": 1,
                "parent_grant": 1,
                "prior_publication": 0,
            },
        ),
        (
            Path(
                "data/patent-lake/uspto-ppubs-html/USPAT/dc2eefd750653fe9/"
                "US-8976467-B2.html"
            ),
            "13/757675",
            31,
            frozenset({12}),
            2,
            {
                "continuation_parent_application": 0,
                "related_parent_application": 0,
                "parent_grant": 0,
                "prior_publication": 1,
            },
        ),
    ),
)
def test_genius_four_lens_six_sources_bind_full_denominator(
    source_path: Path,
    application_number: str,
    page_count: int,
    blank_pages: frozenset[int],
    owner_count: int,
    relationship_counts: dict[str, int],
) -> None:
    source = source_path.read_text(encoding="utf-8")

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_four_lens_six_source_facts(source)
    layout = patent_pdf_recovery.genius_four_lens_six_source_layout_for_sha256(
        facts["primary_html_sha256"]
    )
    assert layout["application_number"] == application_number
    assert layout["page_count"] == page_count
    assert layout["blank_mirror_pages"] == blank_pages
    assert len(layout["page_image_sha256"]) == page_count
    assert len(layout["role_pages"]) == 13
    assert facts["family_id"] == "48495278"
    assert facts["application_number"] == application_number
    assert facts["owner_count"] == owner_count
    assert facts["priority_binding_counts"] == {
        "CN201210328571.9": 2,
        "CN201210437198.0": 2,
    }
    assert facts["relationship_binding_counts"] == relationship_counts
    assert facts["prescription_count"] == 6
    assert facts["lens_element_count"] == 4
    assert len(facts["figure_binding_counts"]) == 12
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert facts["comparison_binding_count"] == 1
    assert set(facts["device_figure_binding_counts"].values()) == {1}
    assert facts["declared_figure_numbers"] == list(range(1, 29))
    assert facts["html_table_count"] == 0
    assert facts["html_system_label_counts"] == dict.fromkeys(
        ("FNO", "F-number", "F/#", "HFOV", "field of view"),
        0,
    )
    assert not patent_pdf_recovery.ability_drawing_tables_declared(source + " ")


def test_genius_four_lens_six_source_layout_rejects_changed_html() -> None:
    with pytest.raises(
        patent_pdf_recovery.PatentPdfRecoveryError,
        match="official HTML is not source-locked",
    ):
        patent_pdf_recovery.genius_four_lens_six_source_layout_for_sha256(
            "0" * 64
        )


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


@pytest.mark.parametrize(
    "source_path",
    (
        Path(
            "data/patent-lake/uspto-ppubs-html/USPAT/7a3936c854f9d03e/"
            "US-12298484-B2.html"
        ),
        Path(
            "data/patent-lake/uspto-ppubs-html/US-PGPUB/1197f4ec4bb5df4a/"
            "US-20240411113-A1.html"
        ),
    ),
)
def test_genius_seven_lens_seven_source_facts_are_exact(source_path: Path) -> None:
    source = source_path.read_text(encoding="utf-8")

    assert patent_pdf_recovery.ability_drawing_tables_declared(source)
    facts = patent_pdf_recovery._genius_seven_lens_seven_source_facts(source)
    assert facts["family_id"] == "59199108"
    assert facts["application_number"] == "18/743044"
    assert len(facts["figure_binding_counts"]) == 14
    assert set(facts["figure_binding_counts"].values()) == {1}
    assert len(facts["comparison_binding_counts"]) == 2
    assert set(facts["comparison_binding_counts"].values()) == {1}
    assert list(facts["example_heading_counts"].values()) == [1] * 7
    assert facts["system_values"] == list(
        patent_pdf_recovery._GENIUS_SEVEN_LENS_SEVEN_SYSTEM_VALUES
    )
    assert facts["genius_applicant_assignee_count"] == 2


def test_genius_seven_lens_seven_source_layout_rejects_changed_html() -> None:
    with pytest.raises(
        patent_pdf_recovery.PatentPdfRecoveryError,
        match="official HTML is not source-locked",
    ):
        patent_pdf_recovery.genius_seven_lens_seven_source_layout_for_sha256(
            "0" * 64
        )


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


@pytest.mark.parametrize("publication_id", ("US-11719909-B2", "US-20210026108-A1"))
def test_ability_three_five_lens_profile_records_three_field_terminals(
    publication_id: str,
) -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_three_five_lens_pdf_ocr_parser_input(publication_id).decode(),
        patent_id=publication_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "metadata_unpublished"
        for attempt in attempts
    )
    assert [attempt.error.reason_code for attempt in attempts] == [
        "metadata_unpublished.prescription_specific_angular_field_absent",
        "metadata_unpublished.prescription_specific_angular_field_"
        "absent_and_r1_sign_conflicted",
        "metadata_unpublished.prescription_specific_angular_field_absent",
    ]
    assert "FIG. 5A publishes S1/R1=-17.90 mm" in str(attempts[1].error)
    assert "FIG. 7 publishes OL2 R1=+17.90 mm" in str(attempts[1].error)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("field", "may publish angular field"),
        ("source", "source fact 'angular_field_label_counts' changed"),
        ("raster", "raster hash changed"),
        ("r1", "token '17.90' occurs 0 times"),
    ),
)
def test_ability_three_five_lens_profile_fails_closed_on_source_drift(
    mutation: str,
    message: str,
) -> None:
    payload = json.loads(_ability_three_five_lens_pdf_ocr_parser_input())
    if mutation == "field":
        payload["pages"][-1]["rapidocr_tokens"].append(
            _ability_ocr_token("FOV", 500.0, 500.0)
        )
    elif mutation == "source":
        payload["source_facts"]["angular_field_label_counts"]["FOV"] = 1
    elif mutation == "raster":
        payload["pages"][0]["official_image_sha256"] = "0" * 64
    else:
        for token in payload["pages"][-1]["rapidocr_tokens"]:
            if token["text"] == "17.90":
                token["text"] = "-17.90"

    with pytest.raises(PatentParseError, match=message):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-11719909-B2",
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


def test_ability_five_three_lens_profile_records_five_metadata_terminals() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _ability_five_three_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-20160085051-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4, 5]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )
    assert all(attempt.error.status == "metadata_unpublished" for attempt in attempts)
    assert all(
        attempt.error.reason_code == "metadata_unpublished.system_f_number_absent"
        for attempt in attempts
    )


def test_ability_five_three_lens_profile_rejects_f_number_or_incomplete_table() -> None:
    f_number_payload = json.loads(_ability_five_three_lens_pdf_ocr_parser_input())
    f_number_payload["pages"][-1]["rapidocr_tokens"].append(
        _ability_ocr_token("FNO", 900.0, 100.0)
    )
    with pytest.raises(PatentParseError, match="may publish an F-number"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(f_number_payload),
            patent_id="US-20160085051-A1",
        )

    incomplete_payload = json.loads(_ability_five_three_lens_pdf_ocr_parser_input())
    surface_page = incomplete_payload["pages"][0]
    surface_page["rapidocr_tokens"] = [
        token
        for token in surface_page["rapidocr_tokens"]
        if token["text"] != "Refractive"
    ]
    with pytest.raises(PatentParseError, match="lacks complete table evidence"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(incomplete_payload),
            patent_id="US-20160085051-A1",
        )


def test_aac_two_three_lens_profile_records_two_field_terminals() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _aac_two_three_lens_pdf_ocr_parser_input().decode(),
        patent_id="US-20160161712-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "metadata_unpublished"
        and attempt.error.reason_code
        == "metadata_unpublished.system_field_of_view_absent"
        for attempt in attempts
    )
    assert all("explicitly labeled DOF" in str(attempt.error) for attempt in attempts)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("field", "source fact 'system_field_label_counts' changed"),
        ("dof", "source fact 'dof_expansion_count' changed"),
        ("table", "source fact 'table_block_sha256' changed"),
        ("drawing", "may publish system field"),
    ),
)
def test_aac_two_three_lens_profile_fails_closed_on_source_drift(
    mutation: str,
    message: str,
) -> None:
    payload = json.loads(_aac_two_three_lens_pdf_ocr_parser_input())
    if mutation == "field":
        payload["source_facts"]["system_field_label_counts"]["FOV"] = 1
    elif mutation == "dof":
        payload["source_facts"]["dof_expansion_count"] = 0
    elif mutation == "table":
        payload["source_facts"]["table_block_sha256"][0] = "0" * 64
    else:
        payload["pages"][1]["rapidocr_tokens"].append(
            _ability_ocr_token("HFOV", 300.0, 100.0)
        )

    with pytest.raises(PatentParseError, match=message):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-20160161712-A1",
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
    "publication_id",
    ("US-20150138653-A1", "US-8976467-B2"),
)
def test_genius_four_lens_six_profile_retains_every_embodiment(
    publication_id: str,
) -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_four_lens_six_pdf_ocr_parser_input(publication_id).decode(),
        patent_id=publication_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 7))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(attempt.error is not None for attempt in attempts)
    assert all(
        "four-lens comparison label 'Fno' confidence" in str(attempt.error)
        for attempt in attempts
    )
    assert all(
        "numeric cell parser remains" not in str(attempt.error)
        for attempt in attempts
    )


def test_genius_four_lens_six_profile_rejects_changed_source_fact() -> None:
    payload = json.loads(
        _genius_four_lens_six_pdf_ocr_parser_input("US-20150138653-A1")
    )
    payload["source_facts"]["declared_figure_numbers"] = list(range(1, 28))

    with pytest.raises(
        patent_to_zmx.PatentParseError,
        match="source fact 'declared_figure_numbers' changed",
    ):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-20150138653-A1",
        )


def test_genius_four_lens_six_profile_retains_raster_drift_per_embodiment() -> None:
    payload = json.loads(
        _genius_four_lens_six_pdf_ocr_parser_input("US-8976467-B2")
    )
    optical_page = next(
        page
        for page in payload["pages"]
        if page["role"] == "genius_four_six_optical_1"
    )
    optical_page["official_image_sha256"] = "0" * 64

    attempts = patent_to_zmx._parse_prescription_attempts(
        json.dumps(payload),
        patent_id="US-8976467-B2",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 7))
    assert all(attempt.prescription is None for attempt in attempts)
    assert "genius_four_six_optical_1 official raster hash changed" in str(
        attempts[0].error
    )
    assert all(
        "genius_four_six_optical_1 official raster hash changed"
        not in str(attempt.error)
        for attempt in attempts[1:]
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


def test_genius_seven_lens_seven_profile_retains_every_example() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        _genius_seven_lens_seven_pdf_ocr_parser_input().decode(),
        patent_id="US-20240411113-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 8))
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        "seven-lens seven-example census passed; numeric cell parser remains"
        in str(attempt.error)
        for attempt in attempts
    )


def test_genius_seven_lens_seven_profile_refuses_source_drift() -> None:
    payload = json.loads(_genius_seven_lens_seven_pdf_ocr_parser_input())
    payload["source_facts"]["application_number"] = "18/000000"

    with pytest.raises(PatentParseError, match="source fact 'application_number' changed"):
        patent_to_zmx._parse_prescription_attempts(
            json.dumps(payload),
            patent_id="US-20240411113-A1",
        )


def test_genius_seven_lens_seven_profile_records_ocr_provenance_drift() -> None:
    payload = json.loads(_genius_seven_lens_seven_pdf_ocr_parser_input())
    payload["pages"][0]["rapidocr_scale"] = 1.0

    attempts = patent_to_zmx._parse_prescription_attempts(
        json.dumps(payload),
        patent_id="US-20240411113-A1",
    )

    assert "lacks its source-locked 0.5 OCR scale" in str(attempts[0].error)


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


def test_convert_candidate_retains_five_three_lens_terminals_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-20160085051-A1",
        source_bucket="US-PGPUB",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="official HTML whose five three-lens tables require PDF recovery",
            source_bucket="US-PGPUB",
            attempts=(source_attempt,),
        )

    async def fake_pdf_recovery(*_args: object, **_kwargs: object) -> object:
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id="US-20160085051-A1",
            official_pdf=b"%PDF-official-five-three-lens",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/"
                "downloadPdf/20160085051"
            ),
            mirror_pdf=b"%PDF-mirror-five-three-lens",
            mirror_pdf_url=(
                "https://patentimages.storage.googleapis.com/test/US20160085051.pdf"
            ),
            parser_input=_ability_five_three_lens_pdf_ocr_parser_input(),
            page_count=27,
            page_image_sha256=tuple(f"{index:x}" * 64 for index in range(1, 12)),
            key_page_numbers=(4, 5, 8, 9, 12, 13, 16, 17, 20, 21, 22),
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
                patent_id="US-20160085051-A1",
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

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4, 5]
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


def test_convert_candidate_retains_aac_two_three_field_terminals_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = patent_to_zmx.SourceFetchAttempt(
        publication_id="US-20160161712-A1",
        source_bucket="US-PGPUB",
        state=patent_to_zmx.SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_primary_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="official HTML whose drawing audit requires PDF recovery",
            source_bucket="US-PGPUB",
            attempts=(source_attempt,),
        )

    async def fake_pdf_recovery(*_args: object, **_kwargs: object) -> object:
        return patent_to_zmx.PatentPdfOcrRecovery(
            publication_id="US-20160161712-A1",
            official_pdf=b"%PDF-official-aac-two-three-lens",
            official_pdf_url=(
                "https://image-ppubs.uspto.gov/dirsearch-public/print/"
                "downloadPdf/20160161712"
            ),
            mirror_pdf=b"%PDF-mirror-aac-two-three-lens",
            mirror_pdf_url=(
                "https://patentimages.storage.googleapis.com/test/US20160161712A1.pdf"
            ),
            parser_input=_aac_two_three_lens_pdf_ocr_parser_input(),
            page_count=7,
            page_image_sha256=("1" * 64, "2" * 64),
            key_page_numbers=(2, 3),
            pypdf_version="fixture",
            rapidocr_version="fixture",
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("metadata-terminal PDF audit must not launch a trace worker")

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
                patent_id="US-20160161712-A1",
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
    assert {
        attempt.reason_code for attempt in attempts
    } == {"metadata_unpublished.system_field_of_view_absent"}
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
            "US-11832791-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "2ef9a1fbb3aad093",
                "US-11832791-B2.html",
            ),
        ),
        (
            "US-20230091208-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "0ba2fa9864b8a3fc",
                "US-20230091208-A1.html",
            ),
        ),
    ),
)
def test_endoscopic_three_lens_exact_sources_are_terminal_when_f_number_absent(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3]
    assert [attempt.embodiment for attempt in attempts] == [
        "Endoscopic optical imaging lens assembly embodiment 1",
        "Endoscopic optical imaging lens assembly embodiment 2",
        "Endoscopic optical imaging lens assembly embodiment 3",
    ]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "metadata_unpublished"
        and attempt.error.reason_code
        == "metadata_unpublished.system_f_number_absent"
        and attempt.prescription is None
        for attempt in attempts
    )


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-11435552-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "fc7ffce9d6d1ba62",
                "US-11435552-B2.html",
            ),
        ),
        (
            "US-20200041761-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "41a8a3a3a2183a91",
                "US-20200041761-A1.html",
            ),
        ),
    ),
)
def test_samsung_iris_exact_sources_retain_six_states_without_repairs(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 7))
    assert [attempt.embodiment for attempt in attempts] == list(
        patent_to_zmx._SAMSUNG_IRIS_MOVING_GROUP_ITEM_LABELS
    )
    visible = attempts[0].prescription
    ir = attempts[1].prescription
    assert visible is not None and ir is not None
    assert (visible.focal_length_mm, visible.f_number, visible.hfov_deg) == pytest.approx(
        (3.75, 2.08, 36.7)
    )
    assert (len(visible.surfaces), len(ir.surfaces)) == (14, 17)
    assert visible.reference_wavelength_um == pytest.approx(0.5876)
    assert ir.reference_wavelength_um == pytest.approx(0.82)
    assert prescription_fingerprint(visible) == "2f0f22ea16129b08"
    assert prescription_fingerprint(ir) == "60e6e642c0aa3840"
    assert sum(bool(surface.asphere_coefficients) for surface in visible.surfaces) == 10
    assert sum(bool(surface.asphere_coefficients) for surface in ir.surfaces) == 10
    assert visible.surfaces[0].asphere_coefficients["K"] == pytest.approx(-0.29816)
    assert ir.surfaces[10].asphere_coefficients["K"] == pytest.approx(0.0)
    assert ir.surfaces[7].nd == pytest.approx(1.50858)
    assert ir.surfaces[8].nd == pytest.approx(1.52652)

    assert all(attempt.prescription is None for attempt in attempts[2:])
    assert [str(attempt.error) for attempt in attempts[2:]] == [
        "Samsung iris embodiment 2 visible state source conflict: TABLE 6 labels "
        "asphere columns 1-10 although TABLE 4 uses ST between surfaces 4 and 6",
        "Samsung iris embodiment 2 IR state source conflict: TABLE 6 surface labels "
        "are inconsistent and TABLE 7 publishes duplicate K rows for surfaces 7-2/7-3",
        "Samsung iris embodiment 3 visible state source conflict: TABLE 8 radius "
        "1.530f377 is nonnumeric, TABLE 10 surface labels are inconsistent, and "
        "narrative/TABLE 11 system metadata disagree",
        "Samsung iris embodiment 3 IR state source conflict: TABLE 10 labels asphere "
        "columns 1-10 although TABLE 9 uses ST between surfaces 4 and 6, and "
        "narrative/TABLE 11 system metadata disagree",
    ]


def test_endoscopic_three_lens_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    audit_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-78592599"
        / "family-78592599-raster-audit.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["family_id"] == "78592599"
    assert audit["figure_declarations"] == [str(index) for index in range(1, 12)]
    for publication_id, record in audit["publications"].items():
        pdf_path = root / record["retained_pdf_path"]
        content = pdf_path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == record["retained_pdf_sha256"]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == record["page_count"] == 15
        assert sum(len(page.extract_text() or "") for page in reader.pages) == 0
        assert record["text_layer_char_count"] == 0
        page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=publication_id,
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        raster_set_sha256 = hashlib.sha256(
            json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert raster_set_sha256 == record["raster_set_sha256"]

        second_pdf_path = root / record["second_live_pdf_path"]
        second_content = second_pdf_path.read_bytes()
        assert (
            hashlib.sha256(second_content).hexdigest()
            == record["second_live_pdf_sha256"]
        )
        second_reader = patent_pdf_recovery.pypdf.PdfReader(str(second_pdf_path))
        second_page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} recheck",
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(second_reader.pages, start=1)
        ]
        assert second_page_hashes == page_hashes
        assert record["second_live_raster_set_equal"] is True
        assert len(record["drawing_page_numbers"]) == record["drawing_sheet_count"] == 7

        contact_path = root / record["contact_sheet_path"]
        assert (
            hashlib.sha256(contact_path.read_bytes()).hexdigest()
            == record["contact_sheet_sha256"]
        )


def test_samsung_iris_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    audit_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-63585563"
        / "family-63585563-raster-audit.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["family_id"] == "63585563"
    assert audit["figure_declarations"] == [str(index) for index in range(1, 19)]
    for publication_id, record in audit["publications"].items():
        pdf_path = root / record["retained_pdf_path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == record[
            "retained_pdf_sha256"
        ]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == record["page_count"] == 34
        assert sum(len(page.extract_text() or "") for page in reader.pages) == 0
        assert record["text_layer_char_count"] == 0
        page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=publication_id,
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        assert (
            hashlib.sha256(
                json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            == record["raster_set_sha256"]
        )

        second_pdf_path = root / record["second_live_pdf_path"]
        assert hashlib.sha256(second_pdf_path.read_bytes()).hexdigest() == record[
            "second_live_pdf_sha256"
        ]
        second_reader = patent_pdf_recovery.pypdf.PdfReader(str(second_pdf_path))
        second_page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} recheck",
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(second_reader.pages, start=1)
        ]
        assert second_page_hashes == page_hashes
        assert record["second_live_raster_set_equal"] is True
        assert len(record["drawing_page_numbers"]) == record["drawing_sheet_count"] == 18
        assert len(record["table_page_numbers"]) == 4

        contact_path = root / record["contact_sheet_path"]
        assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == record[
            "contact_sheet_sha256"
        ]


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


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-12429633-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "e6faadbdb770bfd3",
                "US-12429633-B2.html",
            ),
        ),
        (
            "US-20240077657-A1",
            (
                ".planning",
                "quick",
                "260716-patent-generic-family-73978649",
                "source-review",
                "US-20240077657-A1.html",
            ),
        ),
    ),
)
def test_low_reflection_light_blocking_exact_sources_are_terminal(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4, 5]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        and attempt.prescription is None
        for attempt in attempts
    )
    assert {
        attempt.error.reason_code for attempt in attempts[:4]
    } == {
        "confirmed_no_prescription."
        "low_reflection_coating_and_light_blocking_architecture_only"
    }
    assert attempts[4].error.reason_code == (
        "confirmed_no_prescription.camera_module_device_architecture_only"
    )


def test_low_reflection_light_blocking_prescription_marker_fails_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id = "US-12429633-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "e6faadbdb770bfd3"
        / "US-12429633-B2.html"
    )
    original = source_path.read_text(encoding="utf-8")
    raw_text = original + " radius of curvature"
    profile = (
        patent_to_zmx.
        _LOW_REFLECTION_LIGHT_BLOCKING_ARCHITECTURE_ONLY_SOURCE_PROFILES[patent_id]
    )
    monkeypatch.setitem(
        patent_to_zmx.
        _LOW_REFLECTION_LIGHT_BLOCKING_ARCHITECTURE_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            **profile,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                patent_to_zmx.normalize_patent_text(raw_text).encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 5
    assert all(attempt.prescription is None for attempt in attempts)
    assert {
        str(attempt.error) for attempt in attempts
    } == {
        "low-reflection light-blocking disclosure contains a prescription marker"
    }


def test_low_reflection_light_blocking_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-73978649"
    )
    audit = json.loads(
        (quick_root / "family-73978649-raster-audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert audit["family_id"] == "73978649"
    assert audit["numbered_figure_count"] == 5
    assert len(audit["figure_declarations"]) == 23
    expected = {
        "US-12429633-B2": {
            "drawing_page_numbers": list(range(3, 26)),
            "table_page_numbers": list(range(29, 35)),
        },
        "US-20240077657-A1": {
            "drawing_page_numbers": list(range(2, 25)),
            "table_page_numbers": list(range(28, 34)),
        },
    }
    first_raster_sets: dict[str, list[str]] = {}
    for publication_id, record in audit["publications"].items():
        assert record["drawing_page_numbers"] == expected[publication_id][
            "drawing_page_numbers"
        ]
        assert record["drawing_sheet_count"] == 23
        assert record["table_page_numbers"] == expected[publication_id][
            "table_page_numbers"
        ]
        contact_path = root / record["contact_sheet"]
        assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == record[
            "contact_sha256"
        ]

        publication_raster_sets: list[list[str]] = []
        for wrapper in record["wrappers"].values():
            pdf_path = root / wrapper["path"]
            assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper[
                "sha256"
            ]
            reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
            assert len(reader.pages) == wrapper["page_count"] == 39
            assert sum(len(page.extract_text() or "") for page in reader.pages) == 0
            page_hashes = [
                patent_pdf_recovery._canonical_raster_sha256(
                    patent_pdf_recovery._page_image(
                        page,
                        source=publication_id,
                        page_number=page_number,
                    )
                )
                for page_number, page in enumerate(reader.pages, start=1)
            ]
            assert page_hashes == wrapper["page_raster_sha256"]
            publication_raster_sets.append(page_hashes)
        assert all(
            page_hashes == publication_raster_sets[0]
            for page_hashes in publication_raster_sets[1:]
        )
        first_raster_sets[publication_id] = publication_raster_sets[0]

    assert all(
        left != right
        for left, right in zip(
            first_raster_sets["US-12429633-B2"],
            first_raster_sets["US-20240077657-A1"],
            strict=True,
        )
    )
    assert audit["cross_publication_equality"] == {
        "all_equal": False,
        "equal_pages": 0,
    }


def test_low_reflection_light_blocking_external_queue_is_source_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-73978649"
    )
    queue = json.loads(
        (quick_root / "family-73978649-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )

    assert queue["family_id"] == "73978649"
    assert queue["current_frozen_cohort_roots"] == ["US-12429633"]
    assert [
        (record["application_number"], record["publication_id"])
        for record in queue["external_family_members"]
    ] == [
        ("18/507179", "US-20240077657-A1"),
        ("16/935378", "US-11852848-B2"),
    ]
    source = patent_to_zmx.normalize_patent_text(
        (
            root
            / "data"
            / "patent-lake"
            / "uspto-ppubs-html"
            / "USPAT"
            / "e6faadbdb770bfd3"
            / "US-12429633-B2.html"
        ).read_text(encoding="utf-8")
    )
    for marker in (
        "US 20240077657 A1 Mar. 07, 2024",
        "16/935,378",
        "11,852,848",
    ):
        assert marker in source


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


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-12470822-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "3086bf4acc39aeea",
                "US-12470822-B2.html",
            ),
        ),
        (
            "US-20260039960-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "ae90751842fc7ce9",
                "US-20260039960-A1.html",
            ),
        ),
    ),
)
def test_shiftable_image_sensor_wire_exact_sources_are_terminal(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4, 5, 6]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        for attempt in attempts
    )
    assert {
        attempt.error.reason_code for attempt in attempts[:3]
    } == {
        "confirmed_no_prescription.shiftable_image_sensor_wire_geometry_only"
    }
    assert {
        attempt.error.reason_code for attempt in attempts[3:]
    } == {
        "confirmed_no_prescription.camera_module_device_architecture_only"
    }


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-12517281-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "8d33014a60dc3d2c",
                "US-12517281-B2.html",
            ),
        ),
        (
            "US-20260093056-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "925f82e175ec31eb",
                "US-20260093056-A1.html",
            ),
        ),
    ),
)
def test_meta_optical_architecture_exact_sources_are_terminal(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert attempts[0].embodiment_number is None
    assert attempts[0].prescription is None
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription.meta_optical_layer_and_device_architecture_only"
    )


def test_meta_optical_architecture_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    audit_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-85199256"
        / "family-85199256-raster-audit.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["family_id"] == "85199256"
    assert audit["numbered_figure_count"] == 19
    assert len(audit["figure_declarations"]) == 24
    for publication_id, record in audit["publications"].items():
        pdf_path = root / record["retained_pdf_path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == record[
            "retained_pdf_sha256"
        ]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == record["page_count"]
        assert sum(len(page.extract_text() or "") for page in reader.pages) == 0
        assert record["text_layer_char_count"] == 0
        page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=publication_id,
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        raster_set_sha256 = hashlib.sha256(
            json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert raster_set_sha256 == record["raster_set_sha256"]

        second_pdf_path = root / record["second_live_pdf_path"]
        assert hashlib.sha256(second_pdf_path.read_bytes()).hexdigest() == record[
            "second_live_pdf_sha256"
        ]
        second_reader = patent_pdf_recovery.pypdf.PdfReader(str(second_pdf_path))
        second_page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} recheck",
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(second_reader.pages, start=1)
        ]
        assert second_page_hashes == page_hashes
        assert record["second_live_raster_set_equal"] is True
        assert len(record["drawing_page_numbers"]) == record["drawing_sheet_count"] == 24
        assert record["table_page_numbers"] == []

        contact_path = root / record["contact_sheet_path"]
        assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == record[
            "contact_sheet_sha256"
        ]


def test_meta_optical_architecture_external_family_queue_is_source_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    queue_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-85199256"
        / "family-85199256-external-family-members.json"
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    assert queue["family_id"] == "85199256"
    assert queue["current_frozen_cohort_roots"] == [
        "US-12517281",
        "US-20260093056",
    ]
    assert queue["external_family_members"] == [
        {
            "application_number": "18/097820",
            "discovery_evidence": "US-12517281-B2 Prior Publication Data",
            "disposition": "queue_after_frozen_619_root_cohort",
            "publication_id": "US-20230236339-A1",
            "publication_root": "US-20230236339",
            "publication_date": "2023-07-27",
        }
    ]


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-10725279-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "df938fc2c5990798",
                "US-10725279-B2.html",
            ),
        ),
        (
            "US-20190162945-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "eb7cb67e831cc1c6",
                "US-20190162945-A1.html",
            ),
        ),
    ),
)
def test_edof_microscope_exact_sources_classify_all_five_examples(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4, 5]
    assert all(
        attempt.prescription is None
        and isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )
    assert [attempt.error.status for attempt in attempts] == [
        "confirmed_no_prescription",
        "confirmed_no_prescription",
        "metadata_unpublished",
        "confirmed_no_prescription",
        "confirmed_no_prescription",
    ]
    assert [attempt.error.reason_code for attempt in attempts] == [
        "confirmed_no_prescription.theoretical_imaging_analysis_only",
        "confirmed_no_prescription.edof_microscope_architecture_only",
        "metadata_unpublished."
        "prescription_specific_efl_f_number_and_angular_field_absent",
        "confirmed_no_prescription.metrology_results_only",
        "confirmed_no_prescription.microscopy_experimental_results_only",
    ]


def test_edof_microscope_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    audit_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-60001556"
        / "family-60001556-raster-audit.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["family_id"] == "60001556"
    assert audit["numbered_figure_count"] == 42
    assert len(audit["figure_declarations"]) == 72
    assert audit["table_text_sha256"] == (
        "d7b844bdf21ef1792cb616673cd828e2a56a9800f15b8ab464aa46260149b1fc"
    )
    for publication_id, record in audit["publications"].items():
        pdf_path = root / record["retained_pdf_path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == record[
            "retained_pdf_sha256"
        ]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == record["page_count"] == 47
        assert sum(len(page.extract_text() or "") for page in reader.pages) == 0
        assert record["text_layer_char_count"] == 0
        page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=publication_id,
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        raster_set_sha256 = hashlib.sha256(
            json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert raster_set_sha256 == record["raster_set_sha256"]

        second_pdf_path = root / record["second_live_pdf_path"]
        assert hashlib.sha256(second_pdf_path.read_bytes()).hexdigest() == record[
            "second_live_pdf_sha256"
        ]
        second_reader = patent_pdf_recovery.pypdf.PdfReader(str(second_pdf_path))
        second_page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} recheck",
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(second_reader.pages, start=1)
        ]
        assert second_page_hashes == page_hashes
        assert record["second_live_raster_set_equal"] is True
        assert len(record["drawing_page_numbers"]) == record["drawing_sheet_count"] == 23
        assert record["table_page_numbers"] == [39]

        contact_path = root / record["contact_sheet_path"]
        assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == record[
            "contact_sheet_sha256"
        ]


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-20160088216-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "041e2e327a607a20",
                "US-20160088216-A1.html",
            ),
        ),
        (
            "US-9699370-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "88d9daf89b28d351",
                "US-9699370-B2.html",
            ),
        ),
    ),
)
def test_deformable_lens_actuator_exact_sources_are_terminal(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert attempts[0].embodiment_number == 1
    assert attempts[0].embodiment == (
        "Example 1 and deformable-lens actuator/imaging-terminal architecture"
    )
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert attempts[0].error.status == "confirmed_no_prescription"
    assert attempts[0].error.reason_code == (
        "confirmed_no_prescription."
        "deformable_lens_actuator_and_imaging_terminal_architecture_only"
    )


def test_deformable_lens_actuator_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    audit_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-39526858"
        / "family-39526858-raster-audit.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["family_id"] == "39526858"
    assert audit["numbered_figure_count"] == 28
    assert audit["figure_declarations"] == [str(index) for index in range(1, 29)]
    expected = {
        "US-20160088216-A1": {
            "page_count": 37,
            "drawing_page_numbers": list(range(2, 18)),
            "table_page_numbers": [23, 24, 26, 27, 31],
        },
        "US-9699370-B2": {
            "page_count": 39,
            "drawing_page_numbers": list(range(5, 21)),
            "table_page_numbers": [26, 29, 30, 34],
        },
    }
    for publication_id, record in audit["publications"].items():
        pdf_path = root / record["retained_pdf_path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == record[
            "retained_pdf_sha256"
        ]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == record["page_count"] == expected[publication_id][
            "page_count"
        ]
        assert sum(len(page.extract_text() or "") for page in reader.pages) == 0
        assert record["text_layer_char_count"] == 0
        page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=publication_id,
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        raster_set_sha256 = hashlib.sha256(
            json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert raster_set_sha256 == record["raster_set_sha256"]

        second_pdf_path = root / record["second_live_pdf_path"]
        assert hashlib.sha256(second_pdf_path.read_bytes()).hexdigest() == record[
            "second_live_pdf_sha256"
        ]
        second_reader = patent_pdf_recovery.pypdf.PdfReader(str(second_pdf_path))
        second_page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} recheck",
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(second_reader.pages, start=1)
        ]
        assert second_page_hashes == page_hashes
        assert record["second_live_raster_set_equal"] is True
        assert record["drawing_page_numbers"] == expected[publication_id][
            "drawing_page_numbers"
        ]
        assert len(record["drawing_page_numbers"]) == record["drawing_sheet_count"] == 16
        assert record["table_page_numbers"] == expected[publication_id][
            "table_page_numbers"
        ]

        contact_path = root / record["contact_sheet_path"]
        assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == record[
            "contact_sheet_sha256"
        ]


def test_deformable_lens_actuator_external_family_queue_is_source_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-39526858"
    )
    queue = json.loads(
        (quick_root / "family-39526858-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )

    assert queue["family_id"] == "39526858"
    assert queue["current_frozen_cohort_roots"] == [
        "US-20160088216",
        "US-9699370",
    ]
    assert [
        (record["application_number"], record["publication_id"])
        for record in queue["external_family_members"]
    ] == [
        ("13/964801", "US-20140168787-A1"),
        ("13/964801", "US-9207367-B2"),
        ("12/901242", "US-20110017829-A1"),
        ("12/901242", "US-8505822-B2"),
        ("11/897924", "US-20080144185-A1"),
        ("11/897924", "US-7813047-B2"),
    ]
    source = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "041e2e327a607a20"
        / "US-20160088216-A1.html"
    ).read_text(encoding="utf-8")
    for marker in (
        "13/964,801",
        "2014/0168787",
        "9,207,367",
        "12/901,242",
        "2011/0017829",
        "8,505,822",
        "11/897,924",
        "2008/0144185",
        "7,813,047",
    ):
        assert marker in source


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-12631860-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "053e22371b8427c3",
                "US-12631860-B2.html",
            ),
        ),
        (
            "US-20260153717-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "0c6ae9d0c0d4606e",
                "US-20260153717-A1.html",
            ),
        ),
    ),
)
def test_catadioptric_module_exact_sources_are_terminal(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 10))
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        and attempt.prescription is None
        for attempt in attempts
    )
    assert {
        attempt.error.reason_code for attempt in attempts[:6]
    } == {
        "confirmed_no_prescription."
        "catadioptric_thin_film_and_module_architecture_only"
    }
    assert {
        attempt.error.reason_code for attempt in attempts[6:]
    } == {
        "confirmed_no_prescription.camera_module_device_architecture_only"
    }


def test_catadioptric_module_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    audit_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-88236580"
        / "family-88236580-raster-audit.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert audit["family_id"] == "88236580"
    assert len(audit["figure_declarations"]) == 18
    for publication_id, record in audit["publications"].items():
        pdf_path = root / record["retained_pdf_path"]
        content = pdf_path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == record["retained_pdf_sha256"]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == record["page_count"] == 30
        page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=publication_id,
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        raster_set_sha256 = hashlib.sha256(
            json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert raster_set_sha256 == record["raster_set_sha256"]
        second_pdf_path = root / record["second_live_pdf_path"]
        second_content = second_pdf_path.read_bytes()
        assert (
            hashlib.sha256(second_content).hexdigest()
            == record["second_live_pdf_sha256"]
        )
        second_reader = patent_pdf_recovery.pypdf.PdfReader(str(second_pdf_path))
        assert len(second_reader.pages) == record["page_count"]
        second_page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} recheck",
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(second_reader.pages, start=1)
        ]
        assert second_page_hashes == page_hashes
        assert len(record["drawing_page_numbers"]) == record["drawing_sheet_count"] == 18
        assert record["second_live_raster_set_equal"] is True


@pytest.mark.parametrize(
    ("patent_id", "path_parts"),
    (
        (
            "US-12235418-B2",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "USPAT",
                "90b705c9b510a788",
                "US-12235418-B2.html",
            ),
        ),
        (
            "US-20230067508-A1",
            (
                "data",
                "patent-lake",
                "uspto-ppubs-html",
                "US-PGPUB",
                "c13c69020e466001",
                "US-20230067508-A1.html",
            ),
        ),
    ),
)
def test_compact_barcode_telephoto_exact_sources_are_terminal(
    patent_id: str,
    path_parts: tuple[str, ...],
) -> None:
    source_path = Path(__file__).resolve().parents[1].joinpath(*path_parts)

    attempts = patent_to_zmx._parse_prescription_attempts(
        source_path.read_text(encoding="utf-8"),
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1]
    assert attempts[0].embodiment == (
        "Compact long-range barcode telephoto architecture"
    )
    assert isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert attempts[0].error.status == "confirmed_no_prescription"
    assert attempts[0].error.reason_code == (
        "confirmed_no_prescription.compact_barcode_telephoto_architecture_only"
    )


def _compact_barcode_telephoto_b2_source() -> tuple[str, str]:
    patent_id = "US-12235418-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "90b705c9b510a788"
        / "US-12235418-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def _install_compact_barcode_telephoto_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    original = (
        patent_to_zmx._COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_ONLY_SOURCE_PROFILES[
            patent_id
        ]
    )
    monkeypatch.setitem(
        patent_to_zmx._COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                patent_to_zmx.normalize_patent_text(raw_text).encode("utf-8")
            ).hexdigest(),
        },
    )


def test_compact_barcode_telephoto_system_value_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _compact_barcode_telephoto_b2_source()
    raw_text = original.replace("10.34 millimeters", "10.35 millimeters", 1)
    assert raw_text != original
    _install_compact_barcode_telephoto_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert str(attempts[0].error) == (
        "compact barcode telephoto system anchor 'the total length is 10.34 "
        "millimeters' occurs 0; expected 1"
    )


def test_compact_barcode_telephoto_prescription_marker_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _compact_barcode_telephoto_b2_source()
    raw_text = original.replace(
        "In the foregoing specification, specific embodiments have been described.",
        "Radius of curvature. In the foregoing specification, specific embodiments "
        "have been described.",
        1,
    )
    assert raw_text != original
    _install_compact_barcode_telephoto_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert str(attempts[0].error) == (
        "compact barcode telephoto disclosure contains a prescription marker"
    )


def _shiftable_image_sensor_wire_b2_source() -> tuple[str, str]:
    patent_id = "US-12470822-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "3086bf4acc39aeea"
        / "US-12470822-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def _catadioptric_module_b2_source() -> tuple[str, str]:
    patent_id = "US-12631860-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "053e22371b8427c3"
        / "US-12631860-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def _endoscopic_three_lens_b2_source() -> tuple[str, str]:
    patent_id = "US-11832791-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "2ef9a1fbb3aad093"
        / "US-11832791-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def _aac_telecentric_nine_lens_sources() -> tuple[tuple[str, str], ...]:
    root = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
    )
    sources = (
        (
            "US-12585096-B2",
            root / "USPAT" / "5bd759cb65d3d981" / "US-12585096-B2.html",
        ),
        (
            "US-20250102782-A1",
            root / "US-PGPUB" / "0d6559cf26680516" / "US-20250102782-A1.html",
        ),
    )
    return tuple(
        (patent_id, source_path.read_text(encoding="utf-8"))
        for patent_id, source_path in sources
    )


def _samsung_iris_b2_source() -> tuple[str, str]:
    patent_id = "US-11435552-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "fc7ffce9d6d1ba62"
        / "US-11435552-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def _meta_optical_b2_source() -> tuple[str, str]:
    patent_id = "US-12517281-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "8d33014a60dc3d2c"
        / "US-12517281-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def _edof_microscope_b2_source() -> tuple[str, str]:
    patent_id = "US-10725279-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "df938fc2c5990798"
        / "US-10725279-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def _install_edof_microscope_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    table_match = re.search(
        r"TABLE-US-00001(?P<body>.*?)<br\s*/?>",
        raw_text,
        re.DOTALL | re.IGNORECASE,
    )
    assert table_match is not None
    table_text = patent_to_zmx.normalize_patent_text(
        "TABLE-US-00001" + table_match.group("body")
    )
    original = patent_to_zmx._EDOF_MICROSCOPE_SOURCE_PROFILES[patent_id]
    monkeypatch.setitem(
        patent_to_zmx._EDOF_MICROSCOPE_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "table_sha256": hashlib.sha256(table_text.encode("utf-8")).hexdigest(),
            "phrase_counts": {
                phrase: len(re.findall(re.escape(phrase), normalized, re.IGNORECASE))
                for phrase in original["phrase_counts"]
            },
        },
    )


def _deformable_lens_actuator_b2_source() -> tuple[str, str]:
    patent_id = "US-9699370-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "88d9daf89b28d351"
        / "US-9699370-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def _install_deformable_lens_actuator_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    original = patent_to_zmx._DEFORMABLE_LENS_ACTUATOR_SOURCE_PROFILES[patent_id]
    table_hashes: list[str] = []
    for table_id in ("00001", "00002", "00003", "00004"):
        table_match = re.search(
            rf"TABLE-US-{table_id}(?P<body>.*?)<br\s*/?>",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        assert table_match is not None
        table_text = patent_to_zmx.normalize_patent_text(
            f"TABLE-US-{table_id}" + table_match.group("body")
        )
        table_hashes.append(hashlib.sha256(table_text.encode("utf-8")).hexdigest())
    monkeypatch.setitem(
        patent_to_zmx._DEFORMABLE_LENS_ACTUATOR_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "table_block_sha256": tuple(table_hashes),
            "phrase_counts": {
                phrase: len(re.findall(re.escape(phrase), normalized, re.IGNORECASE))
                for phrase in original["phrase_counts"]
            },
        },
    )


def _install_meta_optical_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    original = (
        patent_to_zmx._META_OPTICAL_LAYER_ARCHITECTURE_ONLY_SOURCE_PROFILES[
            patent_id
        ]
    )
    monkeypatch.setitem(
        patent_to_zmx._META_OPTICAL_LAYER_ARCHITECTURE_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        },
    )


def test_meta_optical_architecture_source_hash_drift_reopens_parser_review() -> None:
    patent_id, raw_text = _meta_optical_b2_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert str(attempts[0].error) == (
        f"meta-optical architecture official raw text hash changed for {patent_id}"
    )


def test_meta_optical_architecture_drawing_drift_reopens_parser_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _meta_optical_b2_source()
    raw_text = original.replace(
        "FIG. <b>19</b></figref> is a block diagram illustrating a configuration "
        "of a three-dimensional sensor",
        "FIG. <b>20</b></figref> is a block diagram illustrating a configuration "
        "of a three-dimensional sensor",
        1,
    )
    assert raw_text != original
    _install_meta_optical_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert str(attempts[0].error) == (
        "meta-optical architecture 24-panel drawing denominator changed"
    )


def test_meta_optical_architecture_prescription_marker_reopens_parser_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _meta_optical_b2_source()
    raw_text = original + " Surface No. 1 radius of curvature = 1.0 mm."
    _install_meta_optical_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert str(attempts[0].error) == (
        "meta-optical architecture disclosure contains a prescription marker"
    )


def test_edof_microscope_source_hash_drift_fails_all_five_items() -> None:
    patent_id, raw_text = _edof_microscope_b2_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 5
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        f"EDOF microscope official raw text hash changed for {patent_id}"
    }


def test_edof_microscope_example_heading_drift_fails_all_five_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _edof_microscope_b2_source()
    raw_text = original.replace(
        "Example V: Experimental Demonstration of EDOF SIM",
        "Example VI: Experimental Demonstration of EDOF SIM",
        1,
    )
    assert raw_text != original
    _install_edof_microscope_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 5
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "EDOF microscope five-example denominator changed"
    }


def test_edof_microscope_drawing_drift_fails_all_five_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _edof_microscope_b2_source()
    raw_text = original.replace(
        '<figref idref="DRAWINGS">FIGS. 42A-E</figref> illustrate, by examples',
        '<figref idref="DRAWINGS">FIGS. 42A-F</figref> illustrate, by examples',
        1,
    )
    assert raw_text != original
    _install_edof_microscope_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 5
    assert {str(attempt.error) for attempt in attempts} == {
        "EDOF microscope 42-number/72-panel drawing denominator changed"
    }


def test_edof_microscope_published_required_metadata_reopens_all_five_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _edof_microscope_b2_source()
    raw_text = original.replace(
        "Imaging plane Infinity 0.0000 2.0769 <br />",
        "Imaging plane Infinity 0.0000 2.0769 Effective focal length = 10 mm "
        "F-number = 2.8 angular field of view = 12 degrees <br />",
        1,
    )
    assert raw_text != original
    _install_edof_microscope_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 5
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "EDOF microscope required system metadata unexpectedly became numeric"
    }
    assert all(
        not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )


def test_deformable_lens_actuator_source_hash_drift_reopens_parser_review() -> None:
    patent_id, raw_text = _deformable_lens_actuator_b2_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert str(attempts[0].error) == (
        f"deformable-lens actuator official raw text hash changed for {patent_id}"
    )


def test_deformable_lens_actuator_table_drift_reopens_parser_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _deformable_lens_actuator_b2_source()
    raw_text = original.replace("896 0.075 mm", "897 0.075 mm", 1)
    assert raw_text != original
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    profile = patent_to_zmx._DEFORMABLE_LENS_ACTUATOR_SOURCE_PROFILES[patent_id]
    monkeypatch.setitem(
        patent_to_zmx._DEFORMABLE_LENS_ACTUATOR_SOURCE_PROFILES,
        patent_id,
        {
            **profile,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert str(attempts[0].error) == "deformable-lens actuator table digest changed"


def test_deformable_lens_actuator_drawing_drift_reopens_parser_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _deformable_lens_actuator_b2_source()
    raw_text = original.replace(
        '<figref idref="DRAWINGS">FIG. 28</figref> is a front perspective view',
        '<figref idref="DRAWINGS">FIG. 29</figref> is a front perspective view',
        1,
    )
    assert raw_text != original
    _install_deformable_lens_actuator_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert str(attempts[0].error) == (
        "deformable-lens actuator 28-figure denominator changed"
    )


def test_deformable_lens_actuator_prescription_marker_reopens_parser_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _deformable_lens_actuator_b2_source()
    raw_text = original + " Surface No. 1 radius of curvature = 1.0 mm."
    _install_deformable_lens_actuator_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 1
    assert isinstance(attempts[0].error, PatentParseError)
    assert not isinstance(attempts[0].error, patent_to_zmx.PatentTerminalParseError)
    assert str(attempts[0].error) == (
        "deformable-lens actuator disclosure contains a surface-prescription marker"
    )


def _install_samsung_iris_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    blocks = patent_to_zmx._patent_table_blocks(normalized)
    original = patent_to_zmx._SAMSUNG_IRIS_MOVING_GROUP_SOURCE_PROFILES[patent_id]
    monkeypatch.setitem(
        patent_to_zmx._SAMSUNG_IRIS_MOVING_GROUP_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "table_block_sha256": tuple(
                hashlib.sha256(block.text.encode("utf-8")).hexdigest()
                for block in blocks
            ),
        },
    )


def _install_endoscopic_three_lens_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    blocks = patent_to_zmx._patent_table_blocks(normalized)
    original = (
        patent_to_zmx._ENDOSCOPIC_THREE_LENS_MISSING_F_NUMBER_SOURCE_PROFILES[
            patent_id
        ]
    )
    monkeypatch.setitem(
        patent_to_zmx._ENDOSCOPIC_THREE_LENS_MISSING_F_NUMBER_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "table_block_sha256": tuple(
                hashlib.sha256(block.text.encode("utf-8")).hexdigest()
                for block in blocks
            ),
        },
    )


def _install_aac_telecentric_nine_lens_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    blocks = patent_to_zmx._patent_table_blocks(normalized)
    original = patent_to_zmx._AAC_TELECENTRIC_NINE_LENS_SOURCE_PROFILES[patent_id]
    monkeypatch.setitem(
        patent_to_zmx._AAC_TELECENTRIC_NINE_LENS_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "table_block_sha256": tuple(
                hashlib.sha256(block.text.encode("utf-8")).hexdigest()
                for block in blocks
            ),
        },
    )


def test_aac_telecentric_nine_lens_sources_are_exact_metadata_terminals() -> None:
    expected_reason_codes = [
        "metadata_unpublished.beam_splitter_material_f_number_and_angular_field_absent",
        *[
            "metadata_unpublished.beam_splitter_material_and_f_number_absent"
            for _ in range(5)
        ],
        (
            "metadata_unpublished.beam_splitter_material_f_number_and_"
            "table7_spacing_identity_absent"
        ),
    ]

    for patent_id, raw_text in _aac_telecentric_nine_lens_sources():
        attempts = patent_to_zmx._parse_prescription_attempts(
            raw_text,
            patent_id=patent_id,
        )

        assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 8))
        assert [
            getattr(attempt.error, "reason_code", None) for attempt in attempts
        ] == expected_reason_codes
        assert all(
            isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
            and attempt.error.status == "metadata_unpublished"
            and attempt.prescription is None
            for attempt in attempts
        )


def test_aac_telecentric_nine_lens_source_hash_drift_fails_all_items() -> None:
    patent_id, raw_text = _aac_telecentric_nine_lens_sources()[0]

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 7
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        f"AAC telecentric nine-lens official raw text hash changed for {patent_id}"
    }


def test_aac_telecentric_nine_lens_published_f_number_reopens_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _aac_telecentric_nine_lens_sources()[0]
    raw_text = original.replace(
        "BRIEF DESCRIPTION OF DRAWINGS",
        "System F-number 2.8. BRIEF DESCRIPTION OF DRAWINGS",
        1,
    )
    assert raw_text != original
    _install_aac_telecentric_nine_lens_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 7
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "AAC telecentric nine-lens F-number marker" in str(attempt.error)
        for attempt in attempts
    )


def test_aac_telecentric_nine_lens_table7_spacing_drift_reopens_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _aac_telecentric_nine_lens_sources()[0]
    raw_text = original.replace("d.sub.6-BS= 4.550", "d.sub.6-BS= 4.551", 1)
    assert raw_text != original
    _install_aac_telecentric_nine_lens_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 7
    assert {str(attempt.error) for attempt in attempts} == {
        "AAC telecentric TABLE 7 undefined d6-BS spacing chain changed"
    }
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        for attempt in attempts
    )


def _aac_near_eye_folded_three_lens_source() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[1]
    source_path = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "36dafd2330f06072"
        / "US-20250271635-A1.html"
    )
    return "US-20250271635-A1", source_path.read_text(encoding="utf-8")


def test_aac_near_eye_folded_three_lens_source_is_exact_metadata_terminal() -> None:
    patent_id, raw_text = _aac_near_eye_folded_three_lens_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "metadata_unpublished"
        and attempt.error.reason_code
        == "metadata_unpublished.prescription_specific_efl_and_f_number_absent"
        and attempt.prescription is None
        for attempt in attempts
    )


def test_aac_near_eye_folded_three_lens_numeric_efl_reopens_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _aac_near_eye_folded_three_lens_source()
    raw_text = original + " effective focal length = 42.0 mm"
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    profile = patent_to_zmx._AAC_NEAR_EYE_FOLDED_THREE_LENS_SOURCE_PROFILES[
        patent_id
    ]
    monkeypatch.setitem(
        patent_to_zmx._AAC_NEAR_EYE_FOLDED_THREE_LENS_SOURCE_PROFILES,
        patent_id,
        {
            **profile,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 2
    assert {str(attempt.error) for attempt in attempts} == {
        "AAC near-eye folded required system metadata unexpectedly became numeric"
    }
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.prescription is None
        for attempt in attempts
    )


def test_aac_near_eye_folded_three_lens_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-90845725"
    )
    audit = json.loads(
        (quick_root / "family-90845725-raster-audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert audit["family_id"] == "90845725"
    assert audit["publication_id"] == "US-20250271635-A1"
    assert audit["page_count"] == 14
    assert audit["drawing_declarations"] == [str(index) for index in range(1, 11)]
    assert audit["drawing_page_numbers"] == list(range(2, 8))
    assert audit["drawing_sheet_count"] == 6
    assert audit["table_numbers"] == list(range(1, 6))
    assert audit["table_page_numbers"] == list(range(11, 15))
    assert audit["decoded_raster_equality"] is True

    contact_path = root / audit["contact_sheet_path"]
    assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == audit[
        "contact_sheet_sha256"
    ]
    raster_sets: list[list[str]] = []
    for wrapper in audit["wrappers"].values():
        pdf_path = root / wrapper["path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == wrapper["page_count"] == 14
        assert [
            page_number
            for page_number, page in enumerate(reader.pages, start=1)
            if not (page.extract_text() or "")
        ] == wrapper["blank_text_pages"] == list(range(1, 15))
        page_hashes = [
            patent_pdf_recovery._canonical_raster_sha256(
                patent_pdf_recovery._page_image(
                    page,
                    source=audit["publication_id"],
                    page_number=page_number,
                )
            )
            for page_number, page in enumerate(reader.pages, start=1)
        ]
        assert page_hashes == wrapper["page_raster_sha256"]
        assert hashlib.sha256(
            json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
        ).hexdigest() == wrapper["raster_set_sha256"]
        raster_sets.append(page_hashes)
    assert raster_sets[0] == raster_sets[1]


def test_aac_near_eye_folded_three_lens_external_queue_is_source_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    queue_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-90845725"
        / "family-90845725-external-family-members.json"
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    assert queue["family_id"] == "90845725"
    assert queue["current_frozen_cohort_roots"] == ["US-20250271635"]
    assert queue["discovery"]["source_url"] == (
        "https://patents.google.com/patent/US20250271635A1/en"
    )
    assert queue["us_application_status"] == (
        "pending_notice_of_allowance_mailed_no_grant_publication_identified"
    )
    assert [
        (record["application_number"], record["publication_id"])
        for record in queue["external_family_members"]
    ] == [
        ("CN202410202541.6A", "CN-117970643-A"),
        ("JP2024089800A", "JP-7610062-B1"),
        ("JP2024089800A", "JP-2025129108-A"),
    ]


def test_endoscopic_three_lens_source_hash_drift_fails_all_items() -> None:
    patent_id, raw_text = _endoscopic_three_lens_b2_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 3
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        f"endoscopic three-lens official raw text hash changed for {patent_id}"
    }


def test_endoscopic_three_lens_system_row_drift_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _endoscopic_three_lens_b2_source()
    raw_text = original.replace(
        "EFL 0.43 f1 −0.35 f2 0.60 f3 0.59 HFOV 60.00",
        "EFL 0.44 f1 −0.35 f2 0.60 f3 0.59 HFOV 60.00",
        1,
    )
    assert raw_text != original
    _install_endoscopic_three_lens_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 3
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "endoscopic three-lens embodiment 1 system row changed"
    }


def test_endoscopic_three_lens_figure_drift_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _endoscopic_three_lens_b2_source()
    raw_text = original.replace(
        '(11) <figref idref="DRAWINGS">FIG. <b>11</b></figref> is a diagram',
        '(11) <figref idref="DRAWINGS">FIG. <b>12</b></figref> is a diagram',
        1,
    )
    assert raw_text != original
    _install_endoscopic_three_lens_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 3
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "endoscopic three-lens 11-figure denominator changed"
    }


def test_endoscopic_three_lens_published_f_number_reopens_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _endoscopic_three_lens_b2_source()
    raw_text = original.replace(
        "BRIEF DESCRIPTION OF THE DRAWINGS",
        "System F-number 2.8. BRIEF DESCRIPTION OF THE DRAWINGS",
        1,
    )
    assert raw_text != original
    _install_endoscopic_three_lens_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 3
    assert all(attempt.prescription is None for attempt in attempts)
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "endoscopic three-lens F-number marker" in str(attempt.error)
        for attempt in attempts
    )


def test_samsung_iris_source_hash_drift_fails_all_six_items() -> None:
    patent_id, raw_text = _samsung_iris_b2_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text + " publication revision",
        patent_id=patent_id,
    )

    assert len(attempts) == 6
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        f"Samsung iris official raw text hash changed for {patent_id}"
    }


def test_samsung_iris_figure_denominator_drift_fails_all_six_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _samsung_iris_b2_source()
    raw_text = original.replace(
        '<figref idref="DRAWINGS">FIG. 18</figref> is a block diagram',
        '<figref idref="DRAWINGS">FIG. 19</figref> is a block diagram',
        1,
    )
    assert raw_text != original
    _install_samsung_iris_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 6
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "Samsung iris 18-figure denominator changed"
    }


def test_samsung_iris_corrected_table8_reopens_source_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _samsung_iris_b2_source()
    raw_text = original.replace("1.530f377", "1.530377", 1)
    assert raw_text != original
    _install_samsung_iris_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 6
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "Samsung iris TABLE 8 damaged-radius signature changed"
    }


def _install_catadioptric_module_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    blocks = patent_to_zmx._suffixed_patent_table_blocks(normalized)
    original = (
        patent_to_zmx._CATADIOPTRIC_MODULE_ARCHITECTURE_ONLY_SOURCE_PROFILES[
            patent_id
        ]
    )
    monkeypatch.setitem(
        patent_to_zmx._CATADIOPTRIC_MODULE_ARCHITECTURE_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
            "table_block_sha256": tuple(
                hashlib.sha256(blocks[key].encode("utf-8")).hexdigest()
                for key in blocks
            ),
        },
    )


def test_catadioptric_module_system_row_drift_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _catadioptric_module_b2_source()
    raw_text = original.replace(
        "D (mm) 3.05 FNO 1.82 FOV (degrees) 19.1",
        "D (mm) 3.05 FNO 1.82 FOV (degrees) 19.2",
        1,
    )
    assert raw_text != original
    _install_catadioptric_module_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 9
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "catadioptric module system row 'D (mm) 3.05 FNO 1.82 FOV "
        "(degrees) 19.1' occurs 1; expected 2"
    }


def test_catadioptric_module_drawing_drift_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _catadioptric_module_b2_source()
    raw_text = original.replace(
        '>FIG. <b>7</b>C</figref> is another schematic view of the vehicle instrument',
        '>FIG. <b>7</b>D</figref> is another schematic view of the vehicle instrument',
        1,
    )
    assert raw_text != original
    _install_catadioptric_module_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 9
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "catadioptric module 18-drawing denominator changed"
    }


def test_catadioptric_module_prescription_marker_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _catadioptric_module_b2_source()
    raw_text = original.replace(
        "BRIEF DESCRIPTION OF THE DRAWINGS",
        "Radius of curvature. BRIEF DESCRIPTION OF THE DRAWINGS",
        1,
    )
    assert raw_text != original
    _install_catadioptric_module_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 9
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "catadioptric module disclosure contains a surface-prescription marker"
    }


def _install_shiftable_image_sensor_wire_drift_profile(
    monkeypatch: pytest.MonkeyPatch,
    *,
    patent_id: str,
    raw_text: str,
) -> None:
    original = patent_to_zmx._SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_ONLY_SOURCE_PROFILES[
        patent_id
    ]
    monkeypatch.setitem(
        patent_to_zmx._SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_ONLY_SOURCE_PROFILES,
        patent_id,
        {
            **original,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                patent_to_zmx.normalize_patent_text(raw_text).encode("utf-8")
            ).hexdigest(),
        },
    )


def test_shiftable_image_sensor_wire_table_drift_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _shiftable_image_sensor_wire_b2_source()
    raw_text = original.replace(
        "Dc/Wc 2.5 We/He 0.40 N 32",
        "Dc/Wc 2.5 We/He 0.40 N 33",
        1,
    )
    assert raw_text != original
    _install_shiftable_image_sensor_wire_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 6
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "shiftable image-sensor wire TABLE 1C binding changed"
    }


def test_shiftable_image_sensor_wire_prescription_marker_fails_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _shiftable_image_sensor_wire_b2_source()
    raw_text = original.replace(
        "The foregoing description, for purpose of explanation",
        "Radius of curvature. The foregoing description, for purpose of explanation",
        1,
    )
    assert raw_text != original
    _install_shiftable_image_sensor_wire_drift_profile(
        monkeypatch,
        patent_id=patent_id,
        raw_text=raw_text,
    )

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert len(attempts) == 6
    assert all(attempt.prescription is None for attempt in attempts)
    assert {str(attempt.error) for attempt in attempts} == {
        "shiftable image-sensor wire disclosure contains a prescription marker"
    }


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


def test_convert_candidate_retains_catadioptric_terminals_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, raw_text = _catadioptric_module_b2_source()

    async def fake_fetch(
        _client: object,
        _token: str,
        fetched_patent_id: str,
    ) -> patent_to_zmx.FetchedPatentHtml:
        assert fetched_patent_id == patent_id
        return patent_to_zmx.FetchedPatentHtml(
            html=raw_text,
            source_bucket="USPAT",
            attempts=(
                patent_to_zmx.SourceFetchAttempt(
                    publication_id=fetched_patent_id,
                    source_bucket="USPAT",
                    state=patent_to_zmx.SourceFetchState.RETAINED,
                    http_status=200,
                ),
            ),
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("confirmed-no-prescription outcomes must not launch a worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "token",
            patent_to_zmx.PatentCandidate(
                patent_id=patent_id,
                title="fixture",
                source_url="",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "zmx",
            raw_document_dir=tmp_path / "raw",
        )
    )

    assert [attempt.status for attempt in attempts] == [
        "confirmed_no_prescription"
    ] * 9
    assert {attempt.reason_code for attempt in attempts[:6]} == {
        "confirmed_no_prescription."
        "catadioptric_thin_film_and_module_architecture_only"
    }
    assert {attempt.reason_code for attempt in attempts[6:]} == {
        "confirmed_no_prescription.camera_module_device_architecture_only"
    }
    assert all(attempt.raw_document_path for attempt in attempts)
    assert not (tmp_path / "zmx").exists() or not any((tmp_path / "zmx").iterdir())


def test_convert_candidate_retains_endoscopic_terminals_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, raw_text = _endoscopic_three_lens_b2_source()

    async def fake_fetch(
        _client: object,
        _token: str,
        fetched_patent_id: str,
    ) -> patent_to_zmx.FetchedPatentHtml:
        assert fetched_patent_id == patent_id
        return patent_to_zmx.FetchedPatentHtml(
            html=raw_text,
            source_bucket="USPAT",
            attempts=(
                patent_to_zmx.SourceFetchAttempt(
                    publication_id=fetched_patent_id,
                    source_bucket="USPAT",
                    state=patent_to_zmx.SourceFetchState.RETAINED,
                    http_status=200,
                ),
            ),
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("metadata-unpublished outcomes must not launch a worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "token",
            patent_to_zmx.PatentCandidate(
                patent_id=patent_id,
                title="fixture",
                source_url="",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "zmx",
            raw_document_dir=tmp_path / "raw",
        )
    )

    assert [attempt.status for attempt in attempts] == ["metadata_unpublished"] * 3
    assert {attempt.reason_code for attempt in attempts} == {
        "metadata_unpublished.system_f_number_absent"
    }
    assert all(attempt.raw_document_path for attempt in attempts)
    assert not (tmp_path / "zmx").exists() or not any((tmp_path / "zmx").iterdir())


def test_convert_candidate_retains_aac_telecentric_terminals_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, raw_text = _aac_telecentric_nine_lens_sources()[0]

    async def fake_fetch(
        _client: object,
        _token: str,
        fetched_patent_id: str,
    ) -> patent_to_zmx.FetchedPatentHtml:
        assert fetched_patent_id == patent_id
        return patent_to_zmx.FetchedPatentHtml(
            html=raw_text,
            source_bucket="USPAT",
            attempts=(
                patent_to_zmx.SourceFetchAttempt(
                    publication_id=fetched_patent_id,
                    source_bucket="USPAT",
                    state=patent_to_zmx.SourceFetchState.RETAINED,
                    http_status=200,
                ),
            ),
        )

    def forbidden_worker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("metadata-unpublished outcomes must not launch a worker")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)
    monkeypatch.setattr(patent_to_zmx, "run_patent_conversion_attempt", forbidden_worker)
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "token",
            patent_to_zmx.PatentCandidate(
                patent_id=patent_id,
                title="fixture",
                source_url="",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "zmx",
            raw_document_dir=tmp_path / "raw",
        )
    )

    assert [attempt.status for attempt in attempts] == ["metadata_unpublished"] * 7
    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 8))
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


def _sunny_automotive_nineteen_lens_b2_source() -> tuple[str, str]:
    patent_id = "US-12591114-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "7128071564aad7e0"
        / "US-12591114-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def test_sunny_automotive_nineteen_lens_source_is_exact_metadata_terminal() -> None:
    patent_id, raw_text = _sunny_automotive_nineteen_lens_b2_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 20))
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "metadata_unpublished"
        and attempt.error.reason_code
        == "metadata_unpublished.system_f_number_absent"
        and attempt.prescription is None
        for attempt in attempts
    )


def test_sunny_automotive_nineteen_lens_published_f_number_reopens_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _sunny_automotive_nineteen_lens_b2_source()
    raw_text = original.replace(
        "BRIEF DESCRIPTION OF THE DRAWINGS",
        "System F-number = 2.8. BRIEF DESCRIPTION OF THE DRAWINGS",
        1,
    )
    assert raw_text != original
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    profile = patent_to_zmx._SUNNY_AUTOMOTIVE_NINETEEN_LENS_SOURCE_PROFILES[
        patent_id
    ]
    monkeypatch.setitem(
        patent_to_zmx._SUNNY_AUTOMOTIVE_NINETEEN_LENS_SOURCE_PROFILES,
        patent_id,
        {
            **profile,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 19
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "Sunny automotive nineteen-embodiment F-number marker"
        in str(attempt.error)
        and attempt.prescription is None
        for attempt in attempts
    )


def test_sunny_automotive_nineteen_lens_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-82157375"
    )
    audit = json.loads(
        (quick_root / "family-82157375-raster-audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert audit["family_id"] == "82157375"
    assert audit["drawing_declarations"] == [str(index) for index in range(1, 21)]
    assert audit["drawing_sheet_count"] == 7
    assert audit["table_identifiers"] == [
        *[str(index) for index in range(1, 40)],
        "40-1",
        "40-2",
        "40-3",
    ]
    expected_layouts = {
        "US-12591114-B2": {
            "page_count": 45,
            "drawing_pages": list(range(3, 10)),
            "table_pages": list(range(20, 41)),
        },
        "US-20230367104-A1": {
            "page_count": 42,
            "drawing_pages": list(range(2, 9)),
            "table_pages": list(range(20, 41)),
        },
    }
    for publication_id, expected in expected_layouts.items():
        publication = audit["publications"][publication_id]
        assert publication["page_count"] == expected["page_count"]
        assert publication["drawing_page_numbers"] == expected["drawing_pages"]
        assert publication["table_page_numbers"] == expected["table_pages"]
        assert publication["decoded_raster_equality"] is True
        contact_path = root / publication["contact_sheet"]
        assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == publication[
            "contact_sha256"
        ]

        raster_sets: list[list[str]] = []
        for wrapper in publication["wrappers"].values():
            pdf_path = root / wrapper["path"]
            assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
            reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
            page_count = expected["page_count"]
            assert len(reader.pages) == wrapper["page_count"] == page_count
            assert [
                page_number
                for page_number, page in enumerate(reader.pages, start=1)
                if not (page.extract_text() or "")
            ] == wrapper["blank_text_pages"] == list(range(1, page_count + 1))
            page_hashes = [
                patent_pdf_recovery._canonical_raster_sha256(
                    patent_pdf_recovery._page_image(
                        page,
                        source=publication_id,
                        page_number=page_number,
                    )
                )
                for page_number, page in enumerate(reader.pages, start=1)
            ]
            assert page_hashes == wrapper["page_raster_sha256"]
            assert hashlib.sha256(
                json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
            ).hexdigest() == wrapper["raster_set_sha256"]
            raster_sets.append(page_hashes)
        assert raster_sets[0] == raster_sets[1]


def test_sunny_automotive_nineteen_lens_external_queue_is_source_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    queue_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-82157375"
        / "family-82157375-external-family-members.json"
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    assert queue["family_id"] == "82157375"
    assert queue["current_frozen_cohort_roots"] == ["US-12591114"]
    assert queue["discovery"]["source_url"] == (
        "https://patents.google.com/patent/US12591114B2/en"
    )
    assert queue["us_application_status"] == "active_grant"
    assert [
        (record["application_number"], record["publication_id"])
        for record in queue["external_family_members"]
    ] == [
        ("US18/326553", "US-20230367104-A1"),
        ("PCT/CN2021/135070", "WO-2022135103-A1"),
    ]
    assert [
        (record["application_number"], record["publication_id"])
        for record in queue["priority_documents"]
    ] == [
        ("CN202011560293.0A", "CN-114690368-B"),
        ("CN202110744979.3A", "CN-115561875-B"),
    ]


def _variable_aperture_camera_module_b2_source() -> tuple[str, str]:
    patent_id = "US-12613396-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "348196f4c11cb75b"
        / "US-12613396-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def test_variable_aperture_camera_module_source_is_exact_architecture_terminal() -> None:
    patent_id, raw_text = _variable_aperture_camera_module_b2_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 10))
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        and attempt.prescription is None
        for attempt in attempts
    )
    assert [attempt.error.reason_code for attempt in attempts] == [
        *[
            "confirmed_no_prescription."
            "variable_aperture_camera_module_architecture_only"
            for _ in range(8)
        ],
        "confirmed_no_prescription.camera_module_device_architecture_only",
    ]


def test_variable_aperture_camera_module_direct_fno_reopens_all_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _variable_aperture_camera_module_b2_source()
    raw_text = original + " Direct embodiment FNO = 2.8."
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    profile = patent_to_zmx._VARIABLE_APERTURE_CAMERA_MODULE_SOURCE_PROFILES[
        patent_id
    ]
    monkeypatch.setitem(
        patent_to_zmx._VARIABLE_APERTURE_CAMERA_MODULE_SOURCE_PROFILES,
        patent_id,
        {
            **profile,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 9
    assert {str(attempt.error) for attempt in attempts} == {
        "variable-aperture camera-module range metadata became a direct value"
    }
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.prescription is None
        for attempt in attempts
    )


def test_variable_aperture_camera_module_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-85407590"
    )
    audit = json.loads(
        (quick_root / "family-85407590-raster-audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert audit["family_id"] == "85407590"
    assert audit["drawing_sheet_count"] == 33
    assert audit["table_count"] == 0
    assert audit["figure_panels"] == [
        *[f"1{letter}" for letter in "ABCDEFG"],
        *[f"2{letter}" for letter in "ABCDEFGH"],
        *[f"3{letter}" for letter in "ABCDEFGHIJKLMN"],
        *[f"4{letter}" for letter in "ABCDEFGHIJ"],
        "5A",
        "5B",
    ]
    expected_drawing_pages = {
        "US-12613396-B2": list(range(3, 36)),
        "US-20240111133-A1": list(range(2, 35)),
    }
    for publication_id, drawing_pages in expected_drawing_pages.items():
        publication = audit["publications"][publication_id]
        assert publication["page_count"] == 45
        assert publication["drawing_page_numbers"] == drawing_pages
        assert publication["table_page_numbers"] == []
        assert publication["decoded_raster_equality"] is True
        contact_path = root / publication["contact_sheet"]
        assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == publication[
            "contact_sha256"
        ]

        raster_sets: list[list[str]] = []
        for wrapper in publication["wrappers"].values():
            pdf_path = root / wrapper["path"]
            assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
            reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
            assert len(reader.pages) == wrapper["page_count"] == 45
            assert [
                page_number
                for page_number, page in enumerate(reader.pages, start=1)
                if not (page.extract_text() or "")
            ] == wrapper["blank_text_pages"] == list(range(1, 46))
            page_hashes = [
                patent_pdf_recovery._canonical_raster_sha256(
                    patent_pdf_recovery._page_image(
                        page,
                        source=publication_id,
                        page_number=page_number,
                    )
                )
                for page_number, page in enumerate(reader.pages, start=1)
            ]
            assert page_hashes == wrapper["page_raster_sha256"]
            assert hashlib.sha256(
                json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
            ).hexdigest() == wrapper["raster_set_sha256"]
            raster_sets.append(page_hashes)
        assert raster_sets[0] == raster_sets[1]


def test_variable_aperture_camera_module_external_queue_is_source_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    queue_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-85407590"
        / "family-85407590-external-family-members.json"
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    assert queue["family_id"] == "85407590"
    assert queue["current_frozen_cohort_roots"] == ["US-12613396"]
    assert queue["discovery"]["source_url"] == (
        "https://patents.google.com/patent/US20240111133A1/en"
    )
    assert queue["us_application_status"] == "active_grant"
    assert [record["publication_id"] for record in queue["external_family_members"]] == [
        "US-20240111133-A1",
        "EP-4345537-A1",
        "TW-I840980-B",
        "CN-117850123-A",
        "CN-218601649-U",
        "TW-202416036-A",
    ]


def _huawei_popup_camera_b2_source() -> tuple[str, str]:
    patent_id = "US-12591118-B2"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "8f7df2cc433e510c"
        / "US-12591118-B2.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def test_huawei_popup_camera_source_accounts_for_all_ten_states() -> None:
    patent_id, raw_text = _huawei_popup_camera_b2_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=patent_id,
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 11))
    assert [
        attempt.error.reason_code
        if isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        else None
        for attempt in attempts
    ] == [
        "metadata_unpublished.non_working_retracted_state_has_no_system_metadata",
        "metadata_unpublished.asphere_a26_exponent_marker_absent",
        "metadata_unpublished.non_working_retracted_state_has_no_system_metadata",
        None,
        "metadata_unpublished.non_working_retracted_state_has_no_system_metadata",
        None,
        "metadata_unpublished.non_working_retracted_state_has_no_system_metadata",
        "metadata_unpublished.asphere_a24_numeric_token_malformed",
        "metadata_unpublished.non_working_retracted_state_has_no_system_metadata",
        None,
    ]
    converted = [attempt.prescription for attempt in attempts if attempt.prescription]
    assert [
        (
            prescription.focal_length_mm,
            prescription.f_number,
            prescription.hfov_deg,
            len(prescription.surfaces),
        )
        for prescription in converted
    ] == [
        (7.93, 1.59, 44.9, 20),
        (8.23, 1.57, 43.915, 20),
        (8.60, 1.55, 42.585, 22),
    ]
    for prescription in converted:
        aspheres = [
            surface for surface in prescription.surfaces if surface.surface_type == "ASP"
        ]
        assert len(aspheres) in {14, 16}
        assert {len(surface.asphere_coefficients) for surface in aspheres} == {15}
        assert [surface.index for surface in prescription.surfaces] == list(
            range(1, len(prescription.surfaces) + 1)
        )
        assert [surface.label for surface in prescription.surfaces[:5]] == [
            "CG S1",
            "CG S2",
            "L1 S1",
            "Stop",
            "L1 S2",
        ]
        assert all(
            surface.thickness_mm is None or surface.thickness_mm >= 0.0
            for surface in prescription.surfaces
        )

    second_working = attempts[3].prescription
    assert second_working is not None
    assert second_working.surfaces[1].thickness_mm == pytest.approx(0.95)
    assert second_working.surfaces[2].thickness_mm == pytest.approx(0.15)
    assert second_working.surfaces[3].thickness_mm == pytest.approx(1.1508)
    assert (
        second_working.surfaces[3].material,
        second_working.surfaces[3].nd,
        second_working.surfaces[3].vd,
    ) == ("Glass", 1.44, 95.1)
    assert sum(
        surface.thickness_mm or 0.0 for surface in second_working.surfaces[:4]
    ) == pytest.approx(2.7508)


def test_huawei_popup_camera_valid_a26_reopens_only_embodiment_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patent_id, original = _huawei_popup_camera_b2_source()
    raw_text = original.replace("2.2728−07", "2.272E−07", 1)
    assert raw_text != original
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    profile = patent_to_zmx._HUAWEI_POPUP_CAMERA_SOURCE_PROFILES[patent_id]
    monkeypatch.setitem(
        patent_to_zmx._HUAWEI_POPUP_CAMERA_SOURCE_PROFILES,
        patent_id,
        {
            **profile,
            "raw_document_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "normalized_text_sha256": hashlib.sha256(
                normalized.encode("utf-8")
            ).hexdigest(),
        },
    )

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert attempts[1].error is None
    assert attempts[1].prescription is not None
    assert attempts[1].prescription.focal_length_mm == 8.38
    assert isinstance(attempts[7].error, patent_to_zmx.PatentTerminalParseError)
    assert attempts[7].error.reason_code == (
        "metadata_unpublished.asphere_a24_numeric_token_malformed"
    )


def test_huawei_popup_camera_source_hash_drift_reopens_all_states() -> None:
    patent_id, original = _huawei_popup_camera_b2_source()
    raw_text = original + " source drift"

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert len(attempts) == 10
    assert {str(attempt.error) for attempt in attempts} == {
        "Huawei pop-up camera official raw text hash changed for US-12591118-B2"
    }
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.prescription is None
        for attempt in attempts
    )


def test_huawei_popup_camera_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-87936009"
    )
    evidence = json.loads(
        (quick_root / "family-87936009-source-evidence.json").read_text(
            encoding="utf-8"
        )
    )

    assert evidence["family_id"] == "87936009"
    assert evidence["publication_id"] == "US-12591118-B2"
    assert evidence["application_number"] == "18/845222"
    assert evidence["figure_numbers"] == list(range(1, 24))
    assert evidence["table_count"] == 16
    assert [
        (
            triple["surface_table"],
            triple["asphere_table"],
            triple["system_table"],
            triple["lens_count"],
        )
        for triple in evidence["table_triplets"]
    ] == [
        (2, 3, 4, 7),
        (5, 6, 7, 7),
        (8, 9, 10, 7),
        (11, 12, 13, 8),
        (14, 15, 16, 8),
    ]
    assert evidence["outcome_denominator"] == {
        "converted_pending_intake": 1,
        "metadata_unpublished": 7,
        "terminal_items": 10,
        "trace_failed": 2,
    }
    assert [item["outcome"] for item in evidence["working_state_outcomes"]] == [
        "metadata_unpublished.asphere_a26_exponent_marker_absent",
        "converted_pending_intake.process_isolated_zmx_ready",
        "trace_failed",
        "metadata_unpublished.asphere_a24_numeric_token_malformed",
        "trace_failed",
    ]

    source_path = root / evidence["official_html"]["path"]
    raw_text = source_path.read_text(encoding="utf-8")
    assert hashlib.sha256(raw_text.encode("utf-8")).hexdigest() == evidence[
        "official_html"
    ]["sha256"]
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    assert hashlib.sha256(normalized.encode("utf-8")).hexdigest() == evidence[
        "official_html"
    ]["normalized_sha256"]


def test_huawei_popup_camera_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-87936009"
    )
    audit = json.loads(
        (quick_root / "family-87936009-raster-audit.json").read_text(
            encoding="utf-8"
        )
    )

    assert audit["family_id"] == "87936009"
    assert audit["drawing_sheet_count"] == 18
    assert audit["figure_numbers"] == list(range(1, 24))
    expected_publications = {
        "US-12591118-B2": {
            "drawing_pages": list(range(3, 21)),
            "table_pages": list(range(28, 42)),
            "contact_sha256": (
                "a4dca1ded48efc73282b05a216ce44e3310e4157a00f524603ae72b7f0dd6424"
            ),
            "defect_pages": {
                "TABLE 12 L2 S1 A24 malformed mantissa": 38,
                "TABLE 3 L4 S2 A26 exponent marker absent": 31,
            },
        },
        "US-20250199270-A1": {
            "drawing_pages": list(range(2, 20)),
            "table_pages": list(range(27, 42)),
            "contact_sha256": (
                "ecb5ac7816f0329dcff4fbe092f1528f373255d78aa213a33a5afa1c4b8bbc8e"
            ),
            "defect_pages": {
                "TABLE 12 L2 S1 A24 malformed mantissa": 38,
                "TABLE 3 L4 S2 A26 exponent marker absent": 30,
            },
        },
    }
    for publication_id, expected in expected_publications.items():
        publication = audit["publications"][publication_id]
        assert publication["page_count"] == 43
        assert publication["drawing_page_numbers"] == expected["drawing_pages"]
        assert publication["table_page_numbers"] == expected["table_pages"]
        assert publication["key_numeric_defect_pages"] == expected["defect_pages"]
        assert publication["decoded_raster_equality"] is True
        contact_path = root / publication["contact_sheet"]
        assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == expected[
            "contact_sha256"
        ]

        raster_sets: list[list[str]] = []
        for wrapper in publication["wrappers"].values():
            pdf_path = root / wrapper["path"]
            assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
            reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
            assert len(reader.pages) == wrapper["page_count"] == 43
            assert [
                page_number
                for page_number, page in enumerate(reader.pages, start=1)
                if not (page.extract_text() or "")
            ] == wrapper["blank_text_pages"] == list(range(1, 44))
            page_hashes: list[str] = []
            page_shapes: list[list[int]] = []
            page_image_counts: list[int] = []
            for page_number, page in enumerate(reader.pages, start=1):
                page_image_counts.append(len(page.images))
                page_image = patent_pdf_recovery._page_image(
                    page,
                    source=publication_id,
                    page_number=page_number,
                )
                page_shapes.append(
                    list(
                        patent_pdf_recovery._decoded_raster(
                            page_image,
                            source=publication_id,
                        ).shape
                    )
                )
                page_hashes.append(
                    patent_pdf_recovery._canonical_raster_sha256(page_image)
                )
            assert page_image_counts == wrapper["page_image_counts"]
            assert page_shapes == wrapper["page_shapes"]
            assert page_hashes == wrapper["page_raster_sha256"]
            assert hashlib.sha256(
                json.dumps(page_hashes, separators=(",", ":")).encode("utf-8")
            ).hexdigest() == wrapper["raster_set_sha256"]
            raster_sets.append(page_hashes)
        assert raster_sets[0] == raster_sets[1]


def test_huawei_popup_camera_external_queue_is_source_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    queue_path = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-87936009"
        / "family-87936009-external-family-members.json"
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    assert queue["family_id"] == "87936009"
    assert queue["current_frozen_cohort_roots"] == ["US-12591118"]
    assert queue["discovery"]["source_url"] == (
        "https://patents.google.com/patent/US20250199270A1/en"
    )
    assert queue["us_application_status"] == "active_grant"
    assert [record["publication_id"] for record in queue["external_family_members"]] == [
        "US-20250199270-A1",
        "CN-116774377-A",
        "CN-116774377-B",
        "WO-2023169441-A1",
        "EP-4468051-A1",
        "EP-4468051-A4",
        "CN-118843814-A",
        "CN-120103562-A",
    ]


def test_huawei_popup_camera_replay_determinism_artifact_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick_root = (
        root / ".planning" / "quick" / "260716-patent-generic-family-87936009"
    )
    artifact = json.loads(
        (quick_root / "family-87936009-replay-determinism.json").read_text(
            encoding="utf-8"
        )
    )

    assert artifact["root_id"] == "US-12591118"
    assert [attempt["result_attempt"] for attempt in artifact["attempts"]] == [3, 4]
    assert {attempt["semantic_sha256"] for attempt in artifact["attempts"]} == {
        "fbdc95ccdfddadb296c5d4c2eb21fc72d4387d9590da2dfc8d71fd92c5f6fafd"
    }
    assert sorted(artifact["embodiments"]) == ["10", "4", "6"]
    assert artifact["embodiments"]["4"]["candidate_zmx_sha256"] == (
        "8a24f5c8ed0da05ed42457b4caf67e39f94fe7b3b01e220fb8c94fd0b22a9760"
    )
    assert artifact["embodiments"]["6"]["candidate_zmx_sha256"] is None
    assert artifact["embodiments"]["10"]["candidate_zmx_sha256"] is None
    staging_path = (
        root
        / "data"
        / "zmx-staging"
        / "patent-local-replay"
        / "US-12591118-B2-e4.zmx"
    )
    assert hashlib.sha256(staging_path.read_bytes()).hexdigest() == artifact[
        "embodiments"
    ]["4"]["candidate_zmx_sha256"]


def _largan_moving_group_source() -> tuple[str, str]:
    patent_id = "US-20250216652-A1"
    source_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "a8ce8130d4420c43"
        / "US-20250216652-A1.html"
    )
    return patent_id, source_path.read_text(encoding="utf-8")


def test_largan_moving_group_source_accounts_for_all_25_items() -> None:
    patent_id, raw_text = _largan_moving_group_source()

    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 26))
    converted = [attempt for attempt in attempts if attempt.prescription]
    assert [attempt.embodiment_number for attempt in converted] == [
        1,
        3,
        5,
        7,
        9,
        11,
        13,
        15,
        19,
    ]
    assert [
        (
            attempt.prescription.focal_length_mm,
            attempt.prescription.f_number,
            attempt.prescription.hfov_deg,
            len(attempt.prescription.surfaces),
        )
        for attempt in converted
        if attempt.prescription is not None
    ] == [
        (18.58, 1.94, 16.8, 21),
        (18.40, 1.94, 17.1, 21),
        (17.10, 1.94, 17.8, 21),
        (18.59, 1.95, 17.0, 21),
        (17.84, 1.94, 17.2, 22),
        (17.05, 1.94, 17.4, 21),
        (18.57, 1.95, 16.9, 21),
        (16.88, 1.94, 17.8, 22),
        (18.57, 1.95, 17.0, 21),
    ]
    for attempt in converted:
        assert attempt.prescription is not None
        assert all(
            surface.thickness_mm is not None and surface.thickness_mm >= 0.0
            for surface in attempt.prescription.surfaces
        )
        assert len(
            [
                surface
                for surface in attempt.prescription.surfaces
                if surface.asphere_coefficients
            ]
        ) == 12

    macro_reviews = [
        attempt
        for attempt in attempts
        if attempt.embodiment_number in {2, 4, 6, 8, 10, 12, 14, 16, 20}
    ]
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "finite-object state is published but unsupported" in str(attempt.error)
        for attempt in macro_reviews
    )
    assert [
        (
            attempt.embodiment_number,
            attempt.error.status,
            attempt.error.reason_code,
        )
        for attempt in attempts
        if isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
    ] == [
        (
            17,
            "metadata_unpublished",
            "metadata_unpublished.surface_sequence_and_stop_radius_conflict",
        ),
        (
            18,
            "metadata_unpublished",
            "metadata_unpublished.surface_sequence_and_stop_radius_conflict",
        ),
        (
            21,
            "confirmed_no_prescription",
            "confirmed_no_prescription.imaging_apparatus_wrapper_only",
        ),
        *[
            (
                number,
                "confirmed_no_prescription",
                "confirmed_no_prescription.electronic_device_wrapper_only",
            )
            for number in range(22, 26)
        ],
    ]


def test_largan_moving_group_reorders_signed_stop_coordinates_without_value_repair() -> None:
    patent_id, raw_text = _largan_moving_group_source()
    attempts = patent_to_zmx._parse_prescription_attempts(raw_text, patent_id=patent_id)
    first = attempts[0].prescription
    assert first is not None

    assert [surface.label for surface in first.surfaces[:8]] == [
        "Fold Prism S1",
        "Fold Prism S2",
        "L1 S1",
        "Stop",
        "L1 S2",
        "L2 S1",
        "L2 S2",
        "Dummy Stop S2",
    ]
    surfaces = {surface.label: surface for surface in first.surfaces}
    assert surfaces["L1 S1"].thickness_mm == pytest.approx(1.055)
    assert surfaces["Stop"].thickness_mm == pytest.approx(0.951)
    assert (surfaces["L1 S1"].material, surfaces["Stop"].material) == (
        "Glass",
        "Glass",
    )
    assert surfaces["L1 S1"].thickness_mm + surfaces["Stop"].thickness_mm == (
        pytest.approx(2.006)
    )
    assert surfaces["L6 S1"].asphere_coefficients["A30"] == pytest.approx(
        6.56360470e-17
    )
    assert "A22" not in surfaces["L1 S1"].asphere_coefficients

    tenth = attempts[18].prescription
    assert tenth is not None
    assert [surface.label for surface in tenth.surfaces[:3]] == [
        "Fold Mirror",
        "L1 S1",
        "Stop",
    ]
    assert tenth.surfaces[1].thickness_mm == pytest.approx(1.555)
    assert tenth.surfaces[2].material == "Glass"


def test_largan_moving_group_source_hash_drift_reopens_all_items() -> None:
    patent_id, raw_text = _largan_moving_group_source()

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text + " source drift",
        patent_id=patent_id,
    )

    assert len(attempts) == 25
    assert {str(attempt.error) for attempt in attempts} == {
        "Largan moving-group official raw text hash changed for US-20250216652-A1"
    }
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.prescription is None
        for attempt in attempts
    )


def test_largan_moving_group_source_evidence_and_external_queue_rehash() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-95157884"
    )
    evidence = json.loads(
        (quick / "family-95157884-source-evidence.json").read_text(encoding="utf-8")
    )
    source_path = root / evidence["official_html"]["path"]
    raw_text = source_path.read_text(encoding="utf-8")
    normalized = patent_to_zmx.normalize_patent_text(raw_text)

    assert evidence["family_id"] == "95157884"
    assert evidence["denominator"] == {
        "architecture_wrapper_items": 5,
        "declared_embodiments": 15,
        "optical_state_items": 20,
        "optical_states_per_prescription_embodiment": 2,
        "prescription_embodiments": 10,
        "total_items": 25,
    }
    assert hashlib.sha256(raw_text.encode()).hexdigest() == evidence["official_html"][
        "raw_document_sha256"
    ]
    assert hashlib.sha256(normalized.encode()).hexdigest() == evidence["official_html"][
        "normalized_text_sha256"
    ]
    blocks = patent_to_zmx._suffixed_patent_table_blocks(normalized)
    observed_table_hashes = {
        f"{number}{suffix}": hashlib.sha256(block.encode()).hexdigest()
        for (number, suffix), block in sorted(blocks.items())
    }
    assert len(observed_table_hashes) == evidence["table_count"] == 39
    assert list(observed_table_hashes) == evidence["table_inventory"]
    assert observed_table_hashes == evidence["table_sha256"]
    assert [item["item_number"] for item in evidence["items"]] == list(range(1, 26))

    queue = json.loads(
        (quick / "family-95157884-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["current_frozen_cohort_roots"] == ["US-20250216652"]
    assert {
        (member["publication_id"], member["application_number"])
        for member in queue["external_family_members"]
    } == {
        ("CN120255132A", "CN202410873286.8A"),
        ("DE202024107550U1", "DE202024107550.1U"),
        ("TW202528789A", "TW113100162A"),
        ("TWI916734B", "TW113100162A"),
    }
    assert all(
        member["disposition"] == "queue_after_frozen_619_root_cohort"
        for member in queue["external_family_members"]
    )
    recovery_queue = json.loads(
        (quick / "queue-after.json").read_text(encoding="utf-8")
    )
    assert recovery_queue["result_set_sha256"] == (
        "0955e458afce6b57fd52a49784e5c29499bc5ec913eb1fc44181c681768b9429"
    )
    assert recovery_queue["next_exact_group"] == {
        "affected_items": 1,
        "affected_roots": 1,
        "family_id": "57585487",
        "layout_signature": (
            "0a4cc8e64f59fbadc5064e95adb03a86149542d55bad57c5a03acfe6eb056c84"
        ),
        "publication_id": "US-20180094086-A1",
        "root_id": "US-20180094086",
    }


def test_largan_moving_group_official_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-95157884"
    )
    audit = json.loads(
        (quick / "family-95157884-raster-audit.json").read_text(encoding="utf-8")
    )

    assert audit["family_id"] == "95157884"
    assert audit["publication_id"] == "US-20250216652-A1"
    assert audit["figure_panel_count"] == len(audit["figure_panels"]) == 64
    assert audit["drawing_page_numbers"] == list(range(2, 64))
    assert audit["drawing_sheet_count"] == 62
    assert audit["description_start_page"] == 64
    assert audit["table_count"] == len(audit["table_pages"]) == 39
    assert audit["table_page_numbers"] == [
        73,
        74,
        75,
        78,
        79,
        80,
        81,
        82,
        83,
        84,
        85,
        86,
        87,
        88,
        89,
        90,
        91,
        92,
        93,
        94,
        95,
        96,
        97,
        98,
        99,
        100,
    ]

    raster_hashes_by_wrapper: dict[str, list[str]] = {}
    for label, wrapper in audit["wrappers"].items():
        pdf_path = root / wrapper["path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == wrapper["page_count"] == 106
        page_hashes: list[str] = []
        image_counts: list[int] = []
        text_lengths: list[int] = []
        page_shapes: list[list[int]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            image_counts.append(len(page.images))
            text_lengths.append(len((page.extract_text() or "").strip()))
            image_bytes = patent_pdf_recovery._page_image(
                page,
                source=f"US-20250216652-A1 {label}",
                page_number=page_number,
            )
            page_hashes.append(
                patent_pdf_recovery._canonical_raster_sha256(image_bytes)
            )
            decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            assert decoded is not None
            page_shapes.append([int(decoded.shape[0]), int(decoded.shape[1])])
        assert image_counts == wrapper["page_image_counts"] == [1] * 106
        assert text_lengths == wrapper["page_text_lengths"] == [0] * 106
        assert wrapper["blank_text_pages"] == list(range(1, 107))
        assert page_shapes == wrapper["page_shapes"]
        assert page_hashes == wrapper["page_raster_sha256"]
        raster_hashes_by_wrapper[label] = page_hashes

    assert raster_hashes_by_wrapper["live-1"] == raster_hashes_by_wrapper["live-2"]
    assert audit["decoded_raster_equality"] == {
        "all_equal": True,
        "equal_pages": 106,
    }
    raster_set_sha256 = hashlib.sha256(
        json.dumps(
            raster_hashes_by_wrapper["live-1"], separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert raster_set_sha256 == audit["raster_set_sha256"]
    contact_path = root / audit["retained_contact_sheet"]
    assert hashlib.sha256(contact_path.read_bytes()).hexdigest() == audit[
        "retained_contact_sha256"
    ]
    defect = audit["critical_source_defects"][0]
    assert (defect["table"], defect["page_number"]) == ("9A", 96)
    assert defect["page_raster_sha256"] == raster_hashes_by_wrapper["live-1"][95]
    retained_page = root / defect["retained_page_path"]
    assert hashlib.sha256(retained_page.read_bytes()).hexdigest() == defect[
        "retained_page_sha256"
    ]


def test_largan_moving_group_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = (
        root
        / ".planning"
        / "quick"
        / "260716-patent-generic-family-95157884"
    )
    artifact = json.loads(
        (quick / "family-95157884-replay-determinism.json").read_text(
            encoding="utf-8"
        )
    )

    def semantic_digest(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    assert artifact["root_id"] == "US-20250216652"
    assert artifact["family_id"] == "95157884"
    assert [attempt["result_attempt"] for attempt in artifact["attempts"]] == [2, 3]
    for expected in artifact["attempts"]:
        result_path = (
            root
            / "data"
            / "patent-ledger"
            / "replay"
            / "local-uncovered"
            / "results"
            / "US-20250216652"
            / f"attempt-{expected['result_attempt']:04d}"
            / "result.json"
        )
        assert hashlib.sha256(result_path.read_bytes()).hexdigest() == expected[
            "result_sha256"
        ]
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result.pop("result_attempt")
        for item in result["items"]:
            item.pop("conversion_attempt_id", None)
            for evidence in item["evidence"]:
                if evidence["evidence_type"] != "patent_conversion_receipt":
                    continue
                receipt = json.loads(
                    (root / evidence["path"]).read_text(encoding="utf-8")
                )
                for field in artifact["excluded_receipt_fields"]:
                    receipt.pop(field, None)
                receipt_semantic_sha256 = semantic_digest(receipt)
                evidence.clear()
                evidence.update(
                    {
                        "evidence_type": "patent_conversion_receipt",
                        "receipt_semantic_sha256": receipt_semantic_sha256,
                    }
                )
        assert semantic_digest(result) == expected["semantic_sha256"]

    assert {attempt["semantic_sha256"] for attempt in artifact["attempts"]} == {
        "1f471dffb3d8ac3ee707eb3fcd7efad086f42897441507f64c1185e2e474b64c"
    }
    assert sorted(int(number) for number in artifact["embodiments"]) == [
        1,
        3,
        5,
        7,
        9,
        11,
        13,
        15,
        19,
    ]
    assert {
        number: record["candidate_zmx_sha256"]
        for number, record in artifact["embodiments"].items()
        if record["candidate_zmx_sha256"] is not None
    } == {
        "3": "6833120cecf53212745f0e4574fe42470c153c36e161040eaaacbef445b46559",
        "5": "15eba19d9acead6905f12f2f2bba67c28f7fd7438629bdc769990af7a59102ca",
        "7": "6eb237aeff0937b5ac358d4d4dc0a98e08e08d2cd006e01a5a8a1e05111082ad",
        "11": "2a60beb362ae17847b03979d689ae0a4cc4b5f0137dc55b8f949e195d573843f",
        "15": "31a006a6ba02333646e6709aa651b9a3ae03059446314a569806925f111be377",
        "19": "7d4236f9458f0a5dad99cb89f685d25f1ee0787d7057f7c5475a969d81fe7c55",
    }


def test_near_ir_absorbing_polymer_source_is_confirmed_no_prescription() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "b15bbe88f5f5126c"
        / "US-20180094086-A1.html"
    )
    raw_text = source.read_text(encoding="utf-8")

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id="US-20180094086-A1",
    )

    assert len(attempts) == 1
    assert attempts[0].embodiment_number is None
    assert attempts[0].embodiment == (
        "Near-infrared absorbing polymer and cut-filter materials document"
    )
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription."
        "near_ir_absorbing_polymer_and_cut_filter_materials_only"
    )

    altered = patent_to_zmx._parse_prescription_attempts(
        raw_text + " Surface No. 1 Radius of Curvature 1.0",
        patent_id="US-20180094086-A1",
    )
    assert len(altered) == 1
    assert isinstance(altered[0].error, PatentParseError)
    assert not isinstance(altered[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "raw text hash changed" in str(altered[0].error)


def test_near_ir_absorbing_polymer_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-57585487"
    evidence = json.loads(
        (quick / "family-57585487-source-evidence.json").read_text(encoding="utf-8")
    )
    source = root / evidence["official_html"]["path"]
    raw_text = source.read_text(encoding="utf-8")
    normalized = patent_to_zmx.normalize_patent_text(raw_text)

    assert evidence["family_id"] == "57585487"
    assert evidence["denominator"] == {
        "numbered_paragraphs": 620,
        "synthesis_examples": 24,
        "near_ir_cut_filter_examples": 32,
        "comparative_examples": 1,
        "figure_panels": 4,
        "drawing_sheets": 2,
        "source_tables": 1,
        "claims": 18,
        "terminal_items": 1,
    }
    assert hashlib.sha256(raw_text.encode()).hexdigest() == evidence["official_html"][
        "raw_document_sha256"
    ]
    assert hashlib.sha256(normalized.encode()).hexdigest() == evidence["official_html"][
        "normalized_text_sha256"
    ]
    assert [int(value) for value in re.findall(r"\[(\d{4})\]", normalized)] == list(
        range(1, 621)
    )
    table_match = re.search(
        r"(?P<table>TABLE-US-00001\s+TABLE\s+1.*?)"
        r"(?:<br\s*/?>\s*\[0605\])",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    assert table_match is not None
    table_text = patent_to_zmx.normalize_patent_text(table_match.group("table"))
    assert hashlib.sha256(table_text.encode()).hexdigest() == evidence["table_1"][
        "normalized_exact_body_sha256"
    ]
    assert len(
        re.findall(
            r"\b(?:Example\s+\d+|Comparative\s+Example\s+1)\s+"
            r"[ABC]\s+[ABC]\s+[ABC]\b",
            table_text,
        )
    ) == evidence["table_1"]["row_count"] == 33
    assert set(evidence["prescription_marker_counts"].values()) == {0}
    assert evidence["terminal_item"] == {
        "embodiment_number": None,
        "label": "Near-infrared absorbing polymer and cut-filter materials document",
        "status": "confirmed_no_prescription",
        "reason_code": (
            "confirmed_no_prescription."
            "near_ir_absorbing_polymer_and_cut_filter_materials_only"
        ),
    }

    queue = json.loads(
        (quick / "family-57585487-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["current_frozen_cohort_roots"] == ["US-20180094086"]
    assert {member["publication_id"] for member in queue["external_family_members"]} == {
        "WO2016208258A1",
        "JP6563014B2",
        "TW201700701A",
    }
    assert all(
        member["disposition"] == "queue_after_frozen_619_root_cohort"
        for member in queue["external_family_members"]
    )


def test_near_ir_absorbing_polymer_official_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-57585487"
    audit = json.loads(
        (quick / "family-57585487-raster-audit.json").read_text(encoding="utf-8")
    )

    assert audit["family_id"] == "57585487"
    assert audit["publication_id"] == "US-20180094086-A1"
    assert audit["page_count"] == 114
    assert audit["figure_panels"] == ["1", "2", "3", "4"]
    assert audit["drawing_page_numbers"] == [2, 3]
    assert audit["description_start_page"] == 4
    assert audit["description_paragraph_range"] == [1, 620]
    assert audit["table_page_numbers"] == [112, 113]
    assert audit["claims_start_page"] == 113

    raster_hashes_by_wrapper: dict[str, list[str]] = {}
    for label, wrapper in audit["wrappers"].items():
        pdf_path = root / wrapper["path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == wrapper["page_count"] == 114
        page_hashes: list[str] = []
        image_counts: list[int] = []
        text_lengths: list[int] = []
        page_shapes: list[list[int]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            image_counts.append(len(page.images))
            text_lengths.append(len((page.extract_text() or "").strip()))
            image_bytes = patent_pdf_recovery._page_image(
                page,
                source=f"US-20180094086-A1 {label}",
                page_number=page_number,
            )
            page_hashes.append(
                patent_pdf_recovery._canonical_raster_sha256(image_bytes)
            )
            decoded = cv2.imdecode(
                np.frombuffer(image_bytes, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            assert decoded is not None
            page_shapes.append([int(decoded.shape[0]), int(decoded.shape[1])])
        assert image_counts == wrapper["page_image_counts"] == [1] * 114
        assert text_lengths == wrapper["page_text_lengths"]
        assert wrapper["blank_text_pages"] == [
            index + 1 for index, length in enumerate(text_lengths) if length == 0
        ]
        assert page_shapes == wrapper["page_shapes"]
        assert page_hashes == wrapper["page_raster_sha256"]
        raster_hashes_by_wrapper[label] = page_hashes

    assert raster_hashes_by_wrapper["live-1"] == raster_hashes_by_wrapper["live-2"]
    assert raster_hashes_by_wrapper["live-1"] == raster_hashes_by_wrapper["google"]
    assert audit["decoded_raster_equality"] == {
        "all_equal": True,
        "equal_pages": 114,
        "wrappers": ["live-1", "live-2", "google"],
    }
    raster_set_sha256 = hashlib.sha256(
        json.dumps(
            raster_hashes_by_wrapper["live-1"],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert raster_set_sha256 == audit["raster_set_sha256"]
    contact = root / audit["retained_contact_sheet"]
    assert hashlib.sha256(contact.read_bytes()).hexdigest() == audit[
        "retained_contact_sha256"
    ]


def test_near_ir_absorbing_polymer_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-57585487"
    artifact = json.loads(
        (quick / "family-57585487-replay-determinism.json").read_text(
            encoding="utf-8"
        )
    )

    semantic_hashes: set[str] = set()
    assert artifact["root_id"] == "US-20180094086"
    assert artifact["family_id"] == "57585487"
    assert artifact["item_count"] == 1
    assert artifact["excluded_semantic_fields"] == ["result_attempt"]
    assert [record["result_attempt"] for record in artifact["attempts"]] == [2, 3]
    for expected in artifact["attempts"]:
        result_path = root / expected["path"]
        assert hashlib.sha256(result_path.read_bytes()).hexdigest() == expected[
            "file_sha256"
        ]
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result.pop("result_attempt")
        semantic_sha256 = hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert semantic_sha256 == expected["semantic_sha256"]
        semantic_hashes.add(semantic_sha256)
        assert result["root_state"] == "terminal"
        assert result["reason_code"] == "terminal.all_disclosed_items_terminal"
        assert len(result["items"]) == 1
        assert result["items"][0]["terminal_status"] == "confirmed_no_prescription"
        assert result["items"][0]["reason_code"] == (
            "terminal.confirmed_no_prescription."
            "near_ir_absorbing_polymer_and_cut_filter_materials_only"
        )
        assert result["items"][0]["conversion_attempt_id"] is None
        assert result["items"][0]["prescription_fingerprint"] is None

    assert artifact["semantic_equal"] is True
    assert semantic_hashes == {
        "3b7df3099b2bd195536f9f4d283cd893c3f1748ef4690993de1e2943f8074ad6"
    }


def test_xr_content_collaboration_source_is_confirmed_no_prescription() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "699f9e2331ebb851"
        / "US-12663910-B2.html"
    )
    raw_text = source.read_text(encoding="utf-8")

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id="US-12663910-B2",
    )

    assert len(attempts) == 1
    assert attempts[0].embodiment_number is None
    assert attempts[0].embodiment == (
        "XR content collaboration user-interface and device architecture"
    )
    error = attempts[0].error
    assert isinstance(error, patent_to_zmx.PatentTerminalParseError)
    assert error.status == "confirmed_no_prescription"
    assert error.reason_code == (
        "confirmed_no_prescription."
        "xr_content_collaboration_user_interface_and_device_architecture_only"
    )

    altered = patent_to_zmx._parse_prescription_attempts(
        raw_text + " Surface No. 1 Radius of Curvature 1.0",
        patent_id="US-12663910-B2",
    )
    assert len(altered) == 1
    assert isinstance(altered[0].error, PatentParseError)
    assert not isinstance(altered[0].error, patent_to_zmx.PatentTerminalParseError)
    assert "raw text hash changed" in str(altered[0].error)


def test_xr_content_collaboration_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-93653416"
    evidence = json.loads(
        (quick / "family-93653416-source-evidence.json").read_text(encoding="utf-8")
    )
    source = root / evidence["official_html"]["path"]
    raw_text = source.read_text(encoding="utf-8")
    normalized = patent_to_zmx.normalize_patent_text(raw_text)

    assert evidence["family_id"] == "93653416"
    assert evidence["denominator"] == {
        "pdf_pages": 108,
        "references_cited_pages": 12,
        "drawing_sheets": 52,
        "declared_figure_groups": 10,
        "actual_figure_panels": 57,
        "description_paragraphs": 248,
        "source_tables": 0,
        "claims": 48,
        "terminal_items": 1,
    }
    assert hashlib.sha256(raw_text.encode()).hexdigest() == evidence["official_html"][
        "raw_document_sha256"
    ]
    assert hashlib.sha256(normalized.encode()).hexdigest() == evidence["official_html"][
        "normalized_text_sha256"
    ]
    description_start = normalized.index("BRIEF DESCRIPTION OF THE DRAWINGS")
    claims_start = normalized.index(
        "Claims 1 . A computer system configured",
        description_start,
    )
    assert [
        int(value)
        for value in re.findall(
            r"\((\d+)\)",
            normalized[description_start:claims_start],
        )
    ] == list(range(1, 249))
    assert [
        int(value)
        for value in re.findall(
            r"(?:^|\s)(\d+)\s*\.\s*(?=(?:A|The)\s)",
            normalized[claims_start:],
            re.IGNORECASE,
        )
    ] == list(range(1, 49))
    assert patent_to_zmx._patent_table_blocks(normalized) == []
    assert set(evidence["prescription_marker_counts"].values()) == {0}
    assert evidence["terminal_item"] == {
        "embodiment_number": None,
        "label": "XR content collaboration user-interface and device architecture",
        "status": "confirmed_no_prescription",
        "reason_code": (
            "confirmed_no_prescription."
            "xr_content_collaboration_user_interface_and_device_architecture_only"
        ),
    }
    raster_audit = root / evidence["official_pdf_audit"]["path"]
    assert hashlib.sha256(raster_audit.read_bytes()).hexdigest() == evidence[
        "official_pdf_audit"
    ]["sha256"]

    queue = json.loads(
        (quick / "family-93653416-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["current_frozen_cohort_roots"] == ["US-12663910"]
    assert {member["publication_id"] for member in queue["external_family_members"]} == {
        "US-20240402869-A1",
        "WO2024249046A1",
    }
    assert all(
        member["disposition"] == "queue_after_frozen_619_root_cohort"
        for member in queue["external_family_members"]
    )


def test_xr_content_collaboration_official_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-93653416"
    audit = json.loads(
        (quick / "family-93653416-raster-audit.json").read_text(encoding="utf-8")
    )

    assert audit["family_id"] == "93653416"
    assert audit["publication_id"] == "US-12663910-B2"
    assert audit["b2_page_count"] == 108
    assert audit["references_cited_page_range"] == [2, 13]
    assert audit["drawing_page_range"] == [14, 65]
    assert audit["drawing_sheet_count"] == 52
    assert audit["actual_figure_panel_count"] == 57
    assert len(audit["actual_figure_panels_by_pdf_page"]) == 52
    assert audit["specification_page_range"] == [66, 104]
    assert audit["description_paragraph_range"] == [1, 248]
    assert audit["claims_page_range"] == [105, 108]
    assert audit["claim_range"] == [1, 48]
    assert audit["table_count"] == 0

    raster_hashes_by_wrapper: dict[str, list[str]] = {}
    for label, wrapper in audit["wrappers"].items():
        pdf_path = root / wrapper["path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == wrapper["page_count"]
        page_hashes: list[str] = []
        image_counts: list[int] = []
        text_lengths: list[int] = []
        page_shapes: list[list[int]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            image_counts.append(len(page.images))
            text_lengths.append(len((page.extract_text() or "").strip()))
            image_bytes = patent_pdf_recovery._page_image(
                page,
                source=f"US-12663910-B2 {label}",
                page_number=page_number,
            )
            page_hashes.append(
                patent_pdf_recovery._canonical_raster_sha256(image_bytes)
            )
            decoded = cv2.imdecode(
                np.frombuffer(image_bytes, dtype=np.uint8),
                cv2.IMREAD_UNCHANGED,
            )
            assert decoded is not None
            page_shapes.append([int(value) for value in decoded.shape])
        assert image_counts == wrapper["page_image_counts"] == [1] * len(
            reader.pages
        )
        assert text_lengths == wrapper["page_text_lengths"]
        assert wrapper["blank_text_pages"] == [
            index + 1 for index, length in enumerate(text_lengths) if length == 0
        ]
        assert page_shapes == wrapper["page_shapes"]
        assert page_hashes == wrapper["page_raster_sha256"]
        raster_hashes_by_wrapper[label] = page_hashes

    assert raster_hashes_by_wrapper["b2-live-1"] == raster_hashes_by_wrapper[
        "b2-live-2"
    ]
    assert raster_hashes_by_wrapper["a1-official"] == raster_hashes_by_wrapper[
        "a1-google"
    ]
    b2_raster_set_sha256 = hashlib.sha256(
        json.dumps(
            raster_hashes_by_wrapper["b2-live-1"],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    a1_raster_set_sha256 = hashlib.sha256(
        json.dumps(
            raster_hashes_by_wrapper["a1-official"],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert b2_raster_set_sha256 == audit["b2_raster_set_sha256"]
    assert a1_raster_set_sha256 == audit["a1_raster_set_sha256"]
    for retained in audit["retained_visual_audits"]:
        visual = root / retained["path"]
        assert hashlib.sha256(visual.read_bytes()).hexdigest() == retained["sha256"]


def test_xr_content_collaboration_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-93653416"
    artifact = json.loads(
        (quick / "family-93653416-replay-determinism.json").read_text(
            encoding="utf-8"
        )
    )

    semantic_hashes: set[str] = set()
    assert artifact["root_id"] == "US-12663910"
    assert artifact["family_id"] == "93653416"
    assert artifact["item_count"] == 1
    assert artifact["excluded_semantic_fields"] == ["result_attempt"]
    assert [record["result_attempt"] for record in artifact["attempts"]] == [2, 3]
    for expected in artifact["attempts"]:
        result_path = root / expected["path"]
        assert hashlib.sha256(result_path.read_bytes()).hexdigest() == expected[
            "file_sha256"
        ]
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result.pop("result_attempt")
        semantic_sha256 = hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert semantic_sha256 == expected["semantic_sha256"]
        semantic_hashes.add(semantic_sha256)
        assert result["root_state"] == "terminal"
        assert result["reason_code"] == "terminal.all_disclosed_items_terminal"
        assert len(result["items"]) == 1
        assert result["items"][0]["terminal_status"] == "confirmed_no_prescription"
        assert result["items"][0]["reason_code"] == (
            "terminal.confirmed_no_prescription."
            "xr_content_collaboration_user_interface_and_device_architecture_only"
        )
        assert result["items"][0]["conversion_attempt_id"] is None
        assert result["items"][0]["prescription_fingerprint"] is None

    assert artifact["semantic_equal"] is True
    assert semantic_hashes == {
        "972120083a620518e0c4d68c52c014bec0c5a7bb925a23b61fb929ebc5ec02ef"
    }


def test_light_blocking_dual_retainer_source_has_five_architecture_terminals() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "5d4e18bb5e2829ed"
        / "US-20260072233-A1.html"
    )
    raw_text = source.read_text(encoding="utf-8")

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id="US-20260072233-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2, 3, 4, 5]
    assert [attempt.embodiment for attempt in attempts] == [
        "Imaging lens assembly light-blocking and dual-retainer architecture embodiment 1",
        "Imaging lens assembly light-blocking and dual-retainer architecture embodiment 2",
        "Smartphone multi-camera architecture embodiment 3",
        "Smartphone multi-camera architecture embodiment 4",
        "Mobile transportation camera architecture embodiment 5",
    ]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        for attempt in attempts
    )
    assert [attempt.error.reason_code for attempt in attempts] == [
        "confirmed_no_prescription."
        "light_blocking_wedge_and_dual_retainer_architecture_only",
        "confirmed_no_prescription."
        "light_blocking_wedge_and_dual_retainer_architecture_only",
        "confirmed_no_prescription.camera_module_device_architecture_only",
        "confirmed_no_prescription.camera_module_device_architecture_only",
        "confirmed_no_prescription."
        "mobile_transportation_camera_module_architecture_only",
    ]

    altered = patent_to_zmx._parse_prescription_attempts(
        raw_text + " Surface No. 1 Radius of Curvature 1.0",
        patent_id="US-20260072233-A1",
    )
    assert len(altered) == 5
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "raw text hash changed" in str(attempt.error)
        for attempt in altered
    )


def test_light_blocking_dual_retainer_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-97227325"
    evidence = json.loads(
        (quick / "family-97227325-source-evidence.json").read_text(encoding="utf-8")
    )
    source = root / evidence["official_html"]["path"]
    raw_text = source.read_text(encoding="utf-8")
    normalized = patent_to_zmx.normalize_patent_text(raw_text)

    assert evidence["family_id"] == "97227325"
    assert evidence["denominator"] == {
        "pdf_pages": 44,
        "drawing_sheets": 30,
        "figure_panels": 30,
        "description_paragraphs": 116,
        "source_tables": 2,
        "claims": 30,
        "formal_embodiments": 5,
        "terminal_items": 5,
    }
    assert hashlib.sha256(raw_text.encode()).hexdigest() == evidence["official_html"][
        "raw_document_sha256"
    ]
    assert hashlib.sha256(normalized.encode()).hexdigest() == evidence["official_html"][
        "normalized_text_sha256"
    ]
    description_start = normalized.index("RELATED APPLICATIONS")
    claims_start = normalized.index(
        "Claims 1 . An imaging lens assembly having an optical axis",
        description_start,
    )
    source_scope = normalized[description_start:]
    assert [
        int(value)
        for value in re.findall(
            r"\[(\d+)\]",
            normalized[description_start:claims_start],
        )
    ] == list(range(1, 117))
    assert [
        int(value)
        for value in re.findall(
            r"(?:^|\s)(\d+)\s*\.\s*(?=(?:An?|The)\s)",
            normalized[claims_start:],
            re.IGNORECASE,
        )
    ] == list(range(1, 31))
    assert [block.number for block in patent_to_zmx._patent_table_blocks(normalized)] == [
        1,
        2,
    ]
    for table in evidence["table_evidence"]:
        number = table["table_number"]
        start = source_scope.index(f"TABLE-US-{number:05d} TABLE {number}")
        end = source_scope.index({1: "[0082]", 2: "[0098]"}[number], start)
        span = source_scope[start:end].strip()
        assert hashlib.sha256(span.encode()).hexdigest() == table[
            "normalized_span_sha256"
        ]
    assert set(evidence["prescription_marker_counts"].values()) == {0}
    assert [item["embodiment_number"] for item in evidence["terminal_items"]] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert all(
        item["status"] == "confirmed_no_prescription"
        for item in evidence["terminal_items"]
    )
    raster_audit = root / evidence["official_pdf_audit"]["path"]
    assert hashlib.sha256(raster_audit.read_bytes()).hexdigest() == evidence[
        "official_pdf_audit"
    ]["sha256"]

    queue = json.loads(
        (quick / "family-97227325-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["current_frozen_cohort_roots"] == ["US-20260072233"]
    assert {
        member["publication_id"] for member in queue["external_family_members"]
    } == {
        "TWI886040B",
        "TW202611585A",
        "CN121634443A",
        "CN223551938U",
        "DE202025105273U1",
        "GB2701229A",
    }
    assert all(
        member["disposition"] == "queue_after_frozen_619_root_cohort"
        for member in queue["external_family_members"]
    )


def test_light_blocking_dual_retainer_official_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-97227325"
    audit = json.loads(
        (quick / "family-97227325-raster-audit.json").read_text(encoding="utf-8")
    )

    assert audit["family_id"] == "97227325"
    assert audit["publication_id"] == "US-20260072233-A1"
    assert audit["page_count"] == 44
    assert audit["cover_pages"] == [1]
    assert audit["drawing_page_range"] == [2, 31]
    assert audit["drawing_sheet_count"] == 30
    assert audit["figure_panel_count"] == 30
    assert len(audit["figure_panels_by_pdf_page"]) == 30
    assert audit["specification_page_range"] == [32, 41]
    assert audit["description_paragraph_range"] == [1, 116]
    assert audit["claims_page_range"] == [41, 44]
    assert audit["claim_range"] == [1, 30]
    assert audit["table_count"] == 2
    assert audit["table_page_numbers"] == [37, 38, 39]

    raster_hashes_by_wrapper: dict[str, list[str]] = {}
    for label, wrapper in audit["wrappers"].items():
        pdf_path = root / wrapper["path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == wrapper["page_count"] == 44
        page_hashes: list[str] = []
        image_counts: list[int] = []
        text_lengths: list[int] = []
        page_shapes: list[list[int]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            image_counts.append(len(page.images))
            text_lengths.append(len((page.extract_text() or "").strip()))
            image_bytes = patent_pdf_recovery._page_image(
                page,
                source=f"US-20260072233-A1 {label}",
                page_number=page_number,
            )
            page_hashes.append(
                patent_pdf_recovery._canonical_raster_sha256(image_bytes)
            )
            decoded = cv2.imdecode(
                np.frombuffer(image_bytes, dtype=np.uint8),
                cv2.IMREAD_UNCHANGED,
            )
            assert decoded is not None
            page_shapes.append([int(value) for value in decoded.shape])
        assert image_counts == wrapper["page_image_counts"] == [1] * 44
        assert text_lengths == wrapper["page_text_lengths"] == [0] * 44
        assert wrapper["blank_text_pages"] == list(range(1, 45))
        assert page_shapes == wrapper["page_shapes"]
        assert page_hashes == wrapper["page_raster_sha256"]
        raster_hashes_by_wrapper[label] = page_hashes

    assert raster_hashes_by_wrapper["live-1"] == raster_hashes_by_wrapper["live-2"]
    raster_set_sha256 = hashlib.sha256(
        json.dumps(
            raster_hashes_by_wrapper["live-1"],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert raster_set_sha256 == audit["raster_set_sha256"]
    for visual in audit["retained_visual_audits"]:
        path = root / visual["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == visual["sha256"]


def test_light_blocking_dual_retainer_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-97227325"
    evidence = json.loads(
        (quick / "family-97227325-replay-determinism.json").read_text(
            encoding="utf-8"
        )
    )

    assert evidence["family_id"] == "97227325"
    assert evidence["root_id"] == "US-20260072233"
    assert evidence["item_count"] == 5
    assert evidence["excluded_semantic_fields"] == ["result_attempt"]
    assert evidence["semantic_equal"] is True
    semantic_hashes: set[str] = set()
    for attempt in evidence["attempts"]:
        path = root / attempt["path"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == attempt["file_sha256"]
        result = json.loads(raw)
        assert result["result_attempt"] == attempt["result_attempt"]
        assert result["root_state"] == "terminal"
        assert len(result["items"]) == 5
        assert all(
            item["state"] == "terminal"
            and item["terminal_status"] == "confirmed_no_prescription"
            and item["conversion_attempt_id"] is None
            and item["conversion_request_sha256"] is None
            and item["prescription_fingerprint"] is None
            for item in result["items"]
        )
        result.pop("result_attempt")
        semantic_sha256 = hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert semantic_sha256 == attempt["semantic_sha256"]
        semantic_hashes.add(semantic_sha256)
    assert semantic_hashes == {
        "cee792cdee9ea69c6818ada46b54dc26cb21378b31c9dc4a7cc93f820f7a4eb5"
    }


def test_folded_reflective_refractive_source_has_two_architecture_terminals() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "1f70d988271192e1"
        / "US-12669686-B2.html"
    )
    raw_text = source.read_text(encoding="utf-8")

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id="US-12669686-B2",
    )

    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
    assert [attempt.embodiment for attempt in attempts] == [
        "Folded reflective/refractive member architecture embodiment 1",
        "Folded reflective/refractive member architecture embodiment 2",
    ]
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        and attempt.error.reason_code
        == (
            "confirmed_no_prescription."
            "folded_reflective_refractive_member_and_stray_light_simulation_"
            "architecture_only"
        )
        for attempt in attempts
    )

    altered = patent_to_zmx._parse_prescription_attempts(
        raw_text + " Surface No. 1 Radius 1.0",
        patent_id="US-12669686-B2",
    )
    assert len(altered) == 2
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "raw text hash changed" in str(attempt.error)
        for attempt in altered
    )


def test_folded_reflective_refractive_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-90454980"
    evidence = json.loads(
        (quick / "family-90454980-source-evidence.json").read_text(encoding="utf-8")
    )
    source = root / evidence["official_html"]["path"]
    raw_text = source.read_text(encoding="utf-8")
    normalized = patent_to_zmx.normalize_patent_text(raw_text)

    assert evidence["family_id"] == "90454980"
    assert evidence["root_id"] == "US-12669686"
    assert evidence["denominator"] == {
        "b2_pdf_pages": 40,
        "drawing_sheets": 22,
        "figure_panels": 22,
        "background_paragraphs": 5,
        "summary_paragraphs": 4,
        "brief_drawing_paragraphs": 23,
        "detailed_description_paragraphs": 146,
        "source_tables": 0,
        "claims": 13,
        "main_architecture_embodiments": 2,
        "paired_stray_light_simulations": 8,
        "terminal_items": 2,
    }
    assert hashlib.sha256(raw_text.encode()).hexdigest() == evidence["official_html"][
        "raw_document_sha256"
    ]
    assert hashlib.sha256(normalized.encode()).hexdigest() == evidence[
        "official_html"
    ]["normalized_text_sha256"]

    starts = {
        "background": normalized.index("BACKGROUND 1. Field (1)"),
        "summary": normalized.index("SUMMARY (6)"),
        "brief_description_of_drawings": normalized.index(
            "BRIEF DESCRIPTION OF THE DRAWINGS (1)"
        ),
        "detailed_description": normalized.index("DETAILED DESCRIPTION (24)"),
        "claims": normalized.index("Claims 1 . An electronic device comprising:"),
    }
    sections = {
        "background": normalized[starts["background"] : starts["summary"]],
        "summary": normalized[
            starts["summary"] : starts["brief_description_of_drawings"]
        ],
        "brief_description_of_drawings": normalized[
            starts["brief_description_of_drawings"] : starts["detailed_description"]
        ],
        "detailed_description": normalized[
            starts["detailed_description"] : starts["claims"]
        ],
        "claims": normalized[starts["claims"] :],
    }
    for name, section in sections.items():
        assert hashlib.sha256(section.encode()).hexdigest() == evidence[
            "official_html"
        ]["section_sha256"][name]
    assert [
        int(value) for value in re.findall(r"\((\d+)\)", sections["background"])
    ] == list(range(1, 6))
    assert [
        int(value) for value in re.findall(r"\((\d+)\)", sections["summary"])
    ] == list(range(6, 10))
    assert [
        int(value)
        for value in re.findall(
            r"\((\d+)\)", sections["brief_description_of_drawings"]
        )
    ] == list(range(1, 24))
    assert [
        int(value)
        for value in re.findall(r"\((\d+)\)", sections["detailed_description"])
    ] == list(range(24, 170))
    assert [
        int(value)
        for value in re.findall(
            r"(?:^|\s)(\d+)\s*\.\s*(?=(?:An?|The)\s)",
            sections["claims"],
            re.IGNORECASE,
        )
    ] == list(range(1, 14))
    assert patent_to_zmx._patent_table_blocks(normalized) == []

    source_scope = normalized[starts["background"] :]
    for phrase, expected in evidence["source_scope_phrase_counts"].items():
        assert len(re.findall(re.escape(phrase), source_scope, re.IGNORECASE)) == expected
    assert len(evidence["figure_panels"]) == 22
    assert [(pair["architecture_figure"], pair["simulation_figure"]) for pair in evidence["simulation_pairs"]] == [
        (3, 4),
        (5, 6),
        (7, 8),
        (9, 10),
        (13, 14),
        (15, 16),
        (17, 18),
        (19, 20),
    ]
    assert all(
        item["status"] == "confirmed_no_prescription"
        for item in evidence["terminal_items"]
    )

    raster_audit = root / evidence["official_pdf_audit"]["path"]
    assert hashlib.sha256(raster_audit.read_bytes()).hexdigest() == evidence[
        "official_pdf_audit"
    ]["sha256"]
    queue = json.loads(
        (quick / "family-90454980-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["current_frozen_cohort_roots"] == ["US-12669686"]
    assert {
        member["publication_id"] for member in queue["external_family_members"]
    } == {
        "KR20240039985A",
        "WO2024063547A1",
        "EP4535806A1",
        "EP4535806A4",
        "CN119908121A",
    }
    assert all(
        member["disposition"] == "queue_after_frozen_619_root_cohort"
        for member in queue["external_family_members"]
    )


def test_dye_aggregate_optical_filter_source_has_one_materials_terminal() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "e7790b40f208dbfd"
        / "US-11118059-B2.html"
    )
    raw_text = source.read_text(encoding="utf-8")

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id="US-11118059-B2",
    )

    assert len(attempts) == 1
    assert attempts[0].embodiment_number == 1
    assert (
        attempts[0].embodiment
        == "Dye-aggregate film and optical-filter materials disclosure"
    )
    assert isinstance(
        attempts[0].error, patent_to_zmx.PatentTerminalParseError
    )
    assert attempts[0].error.status == "confirmed_no_prescription"
    assert attempts[0].error.reason_code == (
        "confirmed_no_prescription."
        "dye_aggregate_film_and_optical_filter_materials_only"
    )

    altered = patent_to_zmx._parse_prescription_attempts(
        raw_text + " Surface No. 1 Radius 1.0",
        patent_id="US-11118059-B2",
    )
    assert len(altered) == 1
    assert isinstance(altered[0].error, PatentParseError)
    assert not isinstance(
        altered[0].error, patent_to_zmx.PatentTerminalParseError
    )
    assert "raw text hash changed" in str(altered[0].error)


def test_dye_aggregate_optical_filter_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-59500840"
    evidence = json.loads(
        (quick / "family-59500840-source-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    source = root / evidence["official_html"]["path"]
    raw_text = source.read_text(encoding="utf-8")
    normalized = patent_to_zmx.normalize_patent_text(raw_text)

    assert evidence["family_id"] == "59500840"
    assert evidence["root_id"] == "US-11118059"
    assert evidence["denominator"] == {
        "b2_pdf_pages": 78,
        "a1_pdf_pages": 79,
        "cross_reference_paragraphs": 1,
        "background_paragraphs": 3,
        "summary_paragraphs": 49,
        "brief_drawing_paragraphs": 1,
        "detailed_description_paragraphs": 732,
        "source_tables": 6,
        "film_examples": 57,
        "comparative_examples": 18,
        "total_experimental_rows": 75,
        "resin_reference_rows": 19,
        "chemical_structure_tokens": 78,
        "claims": 29,
        "drawing_sheets": 1,
        "figure_panels": 1,
        "terminal_items": 1,
    }
    assert hashlib.sha256(raw_text.encode()).hexdigest() == evidence[
        "official_html"
    ]["raw_document_sha256"]
    assert hashlib.sha256(normalized.encode()).hexdigest() == evidence[
        "official_html"
    ]["normalized_text_sha256"]

    normalized_markers = {
        "cross_reference": "CROSS-REFERENCE TO RELATED APPLICATIONS (1)",
        "background": "BACKGROUND OF THE INVENTION 1. Field of the Invention (1)",
        "summary": "SUMMARY OF THE INVENTION (4)",
        "brief_description_of_drawing": "BRIEF DESCRIPTION OF THE DRAWING (1)",
        "description_of_preferred_embodiments": (
            "DESCRIPTION OF THE PREFERRED EMBODIMENTS (2)"
        ),
        "claims": "Claims 1. A film comprising:",
    }
    normalized_order = tuple(normalized_markers)
    normalized_starts = {
        name: normalized.index(marker)
        for name, marker in normalized_markers.items()
    }
    normalized_sections = {
        name: normalized[
            normalized_starts[name] : (
                normalized_starts[normalized_order[index + 1]]
                if index + 1 < len(normalized_order)
                else len(normalized)
            )
        ]
        for index, name in enumerate(normalized_order)
    }
    for name, section in normalized_sections.items():
        assert hashlib.sha256(section.encode()).hexdigest() == evidence[
            "official_html"
        ]["section_sha256"][name]

    raw_markers = {
        "cross_reference": "CROSS-REFERENCE TO RELATED APPLICATIONS",
        "background": "BACKGROUND OF THE INVENTION",
        "summary": "SUMMARY OF THE INVENTION",
        "brief_description_of_drawing": "BRIEF DESCRIPTION OF THE DRAWING",
        "description_of_preferred_embodiments": (
            "DESCRIPTION OF THE PREFERRED EMBODIMENTS"
        ),
        "claims": "<h3>Claims</h3>",
    }
    raw_order = tuple(raw_markers)
    raw_starts = {name: raw_text.index(marker) for name, marker in raw_markers.items()}
    raw_sections = {
        name: raw_text[
            raw_starts[name] : (
                raw_starts[raw_order[index + 1]]
                if index + 1 < len(raw_order)
                else len(raw_text)
            )
        ]
        for index, name in enumerate(raw_order)
    }
    for name, section in raw_sections.items():
        assert hashlib.sha256(section.encode()).hexdigest() == evidence[
            "official_html"
        ]["raw_section_sha256"][name]
    paragraph_pattern = re.compile(
        r"(?:<p>|<br\s*/?>)\s*\((\d+)\)",
        re.IGNORECASE,
    )
    assert [
        int(value) for value in paragraph_pattern.findall(raw_sections["background"])
    ] == list(range(1, 4))
    assert [
        int(value) for value in paragraph_pattern.findall(raw_sections["summary"])
    ] == list(range(4, 53))
    assert [
        int(value)
        for value in paragraph_pattern.findall(
            raw_sections["brief_description_of_drawing"]
        )
    ] == [1]
    assert [
        int(value)
        for value in paragraph_pattern.findall(
            raw_sections["description_of_preferred_embodiments"]
        )
    ] == list(range(2, 734))
    assert [
        int(value)
        for value in re.findall(
            r"(?:^|\s)(\d+)\.\s+(?=(?:An?|The)\s)",
            normalized_sections["claims"],
            re.IGNORECASE,
        )
    ] == list(range(1, 30))

    blocks = patent_to_zmx._patent_table_blocks(normalized)
    assert [block.number for block in blocks] == list(range(1, 7))
    end_markers = ("(291)", "(723)", "(724)", "(725)", "(730)", "(732)")
    for block, table, end_marker in zip(
        blocks, evidence["tables"], end_markers, strict=True
    ):
        assert hashlib.sha256(block.text.encode()).hexdigest() == table[
            "block_sha256"
        ]
        formal = block.text.split(end_marker, 1)[0]
        assert hashlib.sha256(formal.encode()).hexdigest() == table[
            "formal_table_sha256"
        ]
    assert [
        int(value)
        for value in re.findall(r"\bExample\s+(\d+)\b", blocks[1].text)
    ] == list(range(1, 39))
    assert [
        int(value)
        for value in re.findall(r"\b(3[9]|4\d|5[0-7])\s+Dye\b", blocks[2].text)
    ] == list(range(39, 58))
    assert [
        int(value)
        for value in re.findall(r"\bExample\s+(\d+)\b", blocks[3].text)
    ] == list(range(1, 19))
    assert [int(value) for value in re.findall(r"##STR(\d{5})##", normalized)] == [
        *range(1, 78),
        90,
    ]
    for phrase, expected in evidence["source_scope_phrase_counts"].items():
        assert len(re.findall(re.escape(phrase), normalized, re.IGNORECASE)) == expected
    assert evidence["terminal_items"] == [
        {
            "embodiment_number": 1,
            "label": "Dye-aggregate film and optical-filter materials disclosure",
            "status": "confirmed_no_prescription",
            "reason_code": (
                "confirmed_no_prescription."
                "dye_aggregate_film_and_optical_filter_materials_only"
            ),
        }
    ]

    raster_audit = root / evidence["official_pdf_audit"]["path"]
    assert hashlib.sha256(raster_audit.read_bytes()).hexdigest() == evidence[
        "official_pdf_audit"
    ]["sha256"]
    queue = json.loads(
        (quick / "family-59500840-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["current_frozen_cohort_roots"] == ["US-11118059"]
    assert {
        member["publication_id"] for member in queue["external_family_members"]
    } == {
        "WO2017135300A1",
        "JPWO2017135300A1",
        "JP6751726B2",
        "CN108603959A",
        "CN108603959B",
        "TW201739804A",
        "TWI781917B",
    }
    assert all(
        member["disposition"] == "queue_after_frozen_619_root_cohort"
        for member in queue["external_family_members"]
    )


def test_dye_aggregate_optical_filter_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-59500840"
    audit = json.loads(
        (quick / "family-59500840-raster-audit.json").read_text(encoding="utf-8")
    )

    assert audit["family_id"] == "59500840"
    assert audit["root_id"] == "US-11118059"
    b2 = audit["publications"]["US-11118059-B2"]
    a1 = audit["publications"]["US-20180340070-A1"]
    assert b2["drawing_page_range"] == [3, 3]
    assert b2["specification_page_range"] == [4, 76]
    assert b2["claims_page_range"] == [76, 78]
    assert a1["drawing_page_range"] == [2, 2]
    assert a1["specification_page_range"] == [3, 78]
    assert a1["claims_page_range"] == [78, 79]
    assert b2["claim_range"] == a1["claim_range"] == [1, 29]
    assert b2["table_count"] == a1["table_count"] == 6

    raster_hashes: dict[str, dict[str, list[str]]] = {}
    for publication_id, publication in audit["publications"].items():
        raster_hashes[publication_id] = {}
        for label, wrapper in publication["wrappers"].items():
            pdf_path = root / wrapper["path"]
            assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper[
                "sha256"
            ]
            reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
            assert len(reader.pages) == wrapper["page_count"] == publication[
                "page_count"
            ]
            page_hashes: list[str] = []
            image_counts: list[int] = []
            text_lengths: list[int] = []
            page_shapes: list[list[int]] = []
            for page_number, page in enumerate(reader.pages, start=1):
                image_counts.append(len(page.images))
                text_lengths.append(len((page.extract_text() or "").strip()))
                image_bytes = patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} {label}",
                    page_number=page_number,
                )
                page_hashes.append(
                    patent_pdf_recovery._canonical_raster_sha256(image_bytes)
                )
                decoded = cv2.imdecode(
                    np.frombuffer(image_bytes, dtype=np.uint8),
                    cv2.IMREAD_UNCHANGED,
                )
                assert decoded is not None
                page_shapes.append([int(value) for value in decoded.shape])
            assert image_counts == wrapper["page_image_counts"]
            assert text_lengths == wrapper["page_text_lengths"]
            assert page_shapes == wrapper["page_shapes"]
            assert page_hashes == wrapper["page_raster_sha256"]
            assert wrapper["blank_text_pages"] == [
                number
                for number, length in enumerate(text_lengths, start=1)
                if length == 0
            ]
            raster_hashes[publication_id][label] = page_hashes
        reference_label = next(iter(publication["wrappers"]))
        raster_set_sha256 = hashlib.sha256(
            json.dumps(
                raster_hashes[publication_id][reference_label],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert raster_set_sha256 == publication["raster_set_sha256"]
        for visual in publication["retained_visual_audits"]:
            path = root / visual["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == visual["sha256"]

    assert raster_hashes["US-11118059-B2"]["live-1"] == raster_hashes[
        "US-11118059-B2"
    ]["live-2"]
    assert raster_hashes["US-20180340070-A1"]["official"] == raster_hashes[
        "US-20180340070-A1"
    ]["google"]
    assert all(
        b2_hash != a1_hash
        for b2_hash, a1_hash in zip(
            raster_hashes["US-11118059-B2"]["live-1"],
            raster_hashes["US-20180340070-A1"]["official"],
            strict=False,
        )
    )
    assert audit["cross_publication_raster_comparison"]["equal_pages"] == []


def test_folded_reflective_refractive_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-90454980"
    audit = json.loads(
        (quick / "family-90454980-raster-audit.json").read_text(encoding="utf-8")
    )

    assert audit["family_id"] == "90454980"
    assert audit["root_id"] == "US-12669686"
    b2 = audit["publications"]["US-12669686-B2"]
    a1 = audit["publications"]["US-20240094515-A1"]
    assert b2["drawing_page_range"] == [3, 24]
    assert b2["specification_page_range"] == [25, 39]
    assert b2["claims_page_range"] == [39, 40]
    assert b2["claim_range"] == [1, 13]
    assert a1["drawing_page_range"] == [2, 23]
    assert a1["specification_page_range"] == [24, 38]
    assert a1["claims_page_range"] == [38, 40]
    assert a1["claim_range"] == [1, 20]
    assert b2["table_count"] == a1["table_count"] == 0

    raster_hashes: dict[str, dict[str, list[str]]] = {}
    for publication_id, publication in audit["publications"].items():
        raster_hashes[publication_id] = {}
        for label, wrapper in publication["wrappers"].items():
            pdf_path = root / wrapper["path"]
            assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper[
                "sha256"
            ]
            reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
            assert len(reader.pages) == wrapper["page_count"] == 40
            page_hashes: list[str] = []
            image_counts: list[int] = []
            text_lengths: list[int] = []
            page_shapes: list[list[int]] = []
            for page_number, page in enumerate(reader.pages, start=1):
                image_counts.append(len(page.images))
                text_lengths.append(len((page.extract_text() or "").strip()))
                image_bytes = patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} {label}",
                    page_number=page_number,
                )
                page_hashes.append(
                    patent_pdf_recovery._canonical_raster_sha256(image_bytes)
                )
                decoded = cv2.imdecode(
                    np.frombuffer(image_bytes, dtype=np.uint8),
                    cv2.IMREAD_UNCHANGED,
                )
                assert decoded is not None
                page_shapes.append([int(value) for value in decoded.shape])
            assert image_counts == wrapper["page_image_counts"] == [1] * 40
            assert text_lengths == wrapper["page_text_lengths"] == [0] * 40
            assert wrapper["blank_text_pages"] == list(range(1, 41))
            assert page_shapes == wrapper["page_shapes"]
            assert page_hashes == wrapper["page_raster_sha256"]
            raster_hashes[publication_id][label] = page_hashes
        reference_label = next(iter(publication["wrappers"]))
        raster_set_sha256 = hashlib.sha256(
            json.dumps(
                raster_hashes[publication_id][reference_label],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert raster_set_sha256 == publication["raster_set_sha256"]
        for visual in publication["retained_visual_audits"]:
            path = root / visual["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == visual["sha256"]

    assert raster_hashes["US-12669686-B2"]["live-1"] == raster_hashes[
        "US-12669686-B2"
    ]["live-2"]
    assert raster_hashes["US-20240094515-A1"]["official"] == raster_hashes[
        "US-20240094515-A1"
    ]["google"]
    assert all(
        b2_hash != a1_hash
        for b2_hash, a1_hash in zip(
            raster_hashes["US-12669686-B2"]["live-1"],
            raster_hashes["US-20240094515-A1"]["official"],
            strict=True,
        )
    )
    assert audit["cross_publication_raster_comparison"]["equal_pages"] == []


def test_folded_reflective_refractive_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-90454980"
    evidence = json.loads(
        (quick / "family-90454980-replay-determinism.json").read_text(
            encoding="utf-8"
        )
    )

    assert evidence["family_id"] == "90454980"
    assert evidence["root_id"] == "US-12669686"
    assert evidence["item_count"] == 2
    assert evidence["excluded_semantic_fields"] == ["result_attempt"]
    assert evidence["semantic_equal"] is True
    semantic_hashes: set[str] = set()
    for attempt in evidence["attempts"]:
        path = root / attempt["path"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == attempt["file_sha256"]
        result = json.loads(raw)
        assert result["result_attempt"] == attempt["result_attempt"]
        assert result["root_state"] == "terminal"
        assert result["reason_code"] == "terminal.all_disclosed_items_terminal"
        assert len(result["items"]) == 2
        assert all(
            item["state"] == "terminal"
            and item["terminal_status"] == "confirmed_no_prescription"
            and item["reason_code"]
            == (
                "terminal.confirmed_no_prescription."
                "folded_reflective_refractive_member_and_stray_light_simulation_"
                "architecture_only"
            )
            and item["conversion_attempt_id"] is None
            and item["conversion_request_sha256"] is None
            and item["prescription_fingerprint"] is None
            for item in result["items"]
        )
        result.pop("result_attempt")
        semantic_sha256 = hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert semantic_sha256 == attempt["semantic_sha256"]
        semantic_hashes.add(semantic_sha256)
    assert semantic_hashes == {
        "d69a58ebfb3aba86cd77c91d79ca1cae9eb3d53939a9404cb539c99a007e3de6"
    }


def test_dye_aggregate_optical_filter_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-59500840"
    evidence = json.loads(
        (quick / "family-59500840-replay-determinism.json").read_text(
            encoding="utf-8"
        )
    )

    assert evidence["family_id"] == "59500840"
    assert evidence["root_id"] == "US-11118059"
    assert evidence["item_count"] == 1
    assert evidence["excluded_semantic_fields"] == ["result_attempt"]
    assert evidence["semantic_equal"] is True
    semantic_hashes: set[str] = set()
    for attempt in evidence["attempts"]:
        path = root / attempt["path"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == attempt["file_sha256"]
        result = json.loads(raw)
        assert result["result_attempt"] == attempt["result_attempt"]
        assert result["root_state"] == "terminal"
        assert result["reason_code"] == "terminal.all_disclosed_items_terminal"
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["state"] == "terminal"
        assert item["terminal_status"] == "confirmed_no_prescription"
        assert item["reason_code"] == (
            "terminal.confirmed_no_prescription."
            "dye_aggregate_film_and_optical_filter_materials_only"
        )
        assert item["conversion_attempt_id"] is None
        assert item["conversion_request_sha256"] is None
        assert item["prescription_fingerprint"] is None
        result.pop("result_attempt")
        semantic_sha256 = hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert semantic_sha256 == attempt["semantic_sha256"]
        semantic_hashes.add(semantic_sha256)
    assert semantic_hashes == {
        "dfd4e7207e014f2257f25541d2d0906df81e0a74da25f0da4a07f5d5ff8bc6a9"
    }


def test_aac_five_lens_f_number_bound_sources_have_two_terminals_each() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = {
        "US-10739565-B2": (
            root
            / "data"
            / "patent-lake"
            / "uspto-ppubs-html"
            / "USPAT"
            / "c53ccd5b2c25bd7a"
            / "US-10739565-B2.html"
        ),
        "US-20190154990-A1": (
            root
            / "data"
            / "patent-lake"
            / "uspto-ppubs-html"
            / "US-PGPUB"
            / "4e138b2b1f79af68"
            / "US-20190154990-A1.html"
        ),
    }

    for patent_id, source in sources.items():
        raw_text = source.read_text(encoding="utf-8")
        attempts = patent_to_zmx._parse_prescription_attempts(
            raw_text,
            patent_id=patent_id,
        )

        assert [attempt.embodiment_number for attempt in attempts] == [1, 2]
        assert [attempt.embodiment for attempt in attempts] == [
            "AAC camera optical lens embodiment 1",
            "AAC camera optical lens embodiment 2",
        ]
        assert all(
            isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
            and attempt.error.status == "metadata_unpublished"
            and attempt.error.reason_code == "metadata_unpublished.system_f_number_absent"
            for attempt in attempts
        )

        altered = patent_to_zmx._parse_prescription_attempts(
            raw_text + " FNO 2.0",
            patent_id=patent_id,
        )
        assert len(altered) == 2
        assert all(
            isinstance(attempt.error, PatentParseError)
            and not isinstance(
                attempt.error,
                patent_to_zmx.PatentTerminalParseError,
            )
            and "raw text hash changed" in str(attempt.error)
            for attempt in altered
        )


def test_aac_five_lens_f_number_bound_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-62052738"
    evidence = json.loads(
        (quick / "family-62052738-source-evidence.json").read_text(encoding="utf-8")
    )

    assert evidence["family_id"] == "62052738"
    assert evidence["application_number"] == "16/101656"
    assert evidence["denominator"] == {
        "frozen_cohort_roots": 2,
        "source_publications": 2,
        "pdf_pages_per_publication": 12,
        "drawing_sheets_per_publication": 5,
        "figure_panels_per_publication": 8,
        "source_tables_per_publication": 12,
        "optical_embodiments_per_publication": 2,
        "ordered_surface_rows_per_embodiment": 13,
        "asphere_rows_per_embodiment": 10,
        "asphere_values_per_row": 8,
        "inflexion_rows_per_embodiment": 10,
        "arrest_rows_per_embodiment": 10,
        "condition_rows_per_embodiment": 8,
        "b2_claims": 9,
        "a1_claims": 10,
        "terminal_items": 4,
    }
    assert evidence["metadata_boundary"] == {
        "object_distance_narrative_cm": 35,
        "ttl_upper_bound_mm": 4.4,
        "f_number_disclosure": "less than or equal to 2.0",
        "f_number_bound_phrase_count_per_publication": 2,
        "exact_embodiment_f_number_published": False,
        "derived_f_number_allowed": False,
        "reason": (
            "entrance-pupil diameter and system focal length are not substituted "
            "to manufacture an exact source F-number"
        ),
    }

    for publication_id, publication in evidence["publications"].items():
        source = root / publication["official_html"]["path"]
        raw_text = source.read_text(encoding="utf-8")
        normalized = patent_to_zmx.normalize_patent_text(raw_text)
        assert (
            hashlib.sha256(raw_text.encode()).hexdigest()
            == publication["official_html"]["raw_document_sha256"]
        )
        assert (
            hashlib.sha256(normalized.encode()).hexdigest()
            == publication["official_html"]["normalized_text_sha256"]
        )

        markers = publication["official_html"]["section_markers"]
        names = tuple(markers)
        starts = {name: normalized.index(marker) for name, marker in markers.items()}
        sections = {
            name: normalized[
                starts[name] : (
                    starts[names[index + 1]] if index + 1 < len(names) else len(normalized)
                )
            ]
            for index, name in enumerate(names)
        }
        for name, section in sections.items():
            assert (
                hashlib.sha256(section.encode()).hexdigest()
                == publication["official_html"]["section_sha256"][name]
            )

        paragraph_pattern = re.compile(publication["paragraph_pattern"])
        for section_name, bounds in publication["paragraph_ranges"].items():
            assert [
                int(value) for value in paragraph_pattern.findall(sections[section_name])
            ] == list(range(bounds[0], bounds[1] + 1))
        assert [
            int(value)
            for value in re.findall(
                r"(?:^|\s)(\d+)\s*\.\s+(?=(?:A|The)\s)",
                sections["claims"],
                re.IGNORECASE,
            )
        ] == list(range(publication["claim_range"][0], publication["claim_range"][1] + 1))
        assert [
            int(value)
            for value in re.findall(
                r"\bFIG\.\s*(\d+)\s+(?=is|shows|presents)",
                sections["brief"],
                re.IGNORECASE,
            )
        ] == publication["declared_figures"]

        blocks = patent_to_zmx._patent_table_blocks(normalized)
        assert [block.number for block in blocks] == list(range(1, 13))
        for block, table in zip(blocks, publication["tables"], strict=True):
            assert hashlib.sha256(block.text.encode()).hexdigest() == table["block_sha256"]
            formal = re.split(
                r"\s+(?:\(\d+\)|\[\d{4}\])\s+",
                block.text,
                maxsplit=1,
            )[0]
            assert hashlib.sha256(formal.encode()).hexdigest() == table["formal_table_sha256"]

        attempts = patent_to_zmx._parse_prescription_attempts(
            raw_text,
            patent_id=publication_id,
        )
        assert len(attempts) == 2
        assert all(
            isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
            and attempt.error.reason_code == "metadata_unpublished.system_f_number_absent"
            for attempt in attempts
        )

    assert len(evidence["terminal_items"]) == 4
    assert all(
        item["status"] == "metadata_unpublished"
        and item["reason_code"] == "metadata_unpublished.system_f_number_absent"
        for item in evidence["terminal_items"]
    )
    raster_audit = root / evidence["official_pdf_audit"]["path"]
    assert (
        hashlib.sha256(raster_audit.read_bytes()).hexdigest()
        == evidence["official_pdf_audit"]["sha256"]
    )

    queue = json.loads(
        (quick / "family-62052738-external-family-members.json").read_text(encoding="utf-8")
    )
    assert queue["current_frozen_cohort_roots"] == [
        "US-10739565",
        "US-20190154990",
    ]
    assert {member["publication_id"] for member in queue["external_family_members"]} == {
        "CN108008524A",
        "CN108008524B",
        "JP2019095768A",
        "JP6522839B1",
    }
    assert all(
        member["disposition"] == "queue_after_frozen_619_root_cohort"
        for member in queue["external_family_members"]
    )


def test_aac_five_lens_f_number_bound_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-62052738"
    audit = json.loads((quick / "family-62052738-raster-audit.json").read_text(encoding="utf-8"))

    assert audit["family_id"] == "62052738"
    assert audit["root_ids"] == ["US-10739565", "US-20190154990"]
    b2 = audit["publications"]["US-10739565-B2"]
    a1 = audit["publications"]["US-20190154990-A1"]
    assert b2["drawing_page_range"] == a1["drawing_page_range"] == [2, 6]
    assert b2["specification_page_range"] == a1["specification_page_range"] == [7, 11]
    assert b2["claims_page_range"] == a1["claims_page_range"] == [11, 12]
    assert b2["claim_range"] == [1, 9]
    assert a1["claim_range"] == [1, 10]
    assert b2["table_count"] == a1["table_count"] == 12

    raster_hashes: dict[str, dict[str, list[str]]] = {}
    for publication_id, publication in audit["publications"].items():
        raster_hashes[publication_id] = {}
        for label, wrapper in publication["wrappers"].items():
            pdf_path = root / wrapper["path"]
            assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
            reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
            assert len(reader.pages) == wrapper["page_count"] == 12
            page_hashes: list[str] = []
            image_counts: list[int] = []
            text_lengths: list[int] = []
            page_shapes: list[list[int]] = []
            for page_number, page in enumerate(reader.pages, start=1):
                image_counts.append(len(page.images))
                text_lengths.append(len((page.extract_text() or "").strip()))
                image_bytes = patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} {label}",
                    page_number=page_number,
                )
                page_hashes.append(patent_pdf_recovery._canonical_raster_sha256(image_bytes))
                decoded = cv2.imdecode(
                    np.frombuffer(image_bytes, dtype=np.uint8),
                    cv2.IMREAD_UNCHANGED,
                )
                assert decoded is not None
                page_shapes.append([int(value) for value in decoded.shape])
            assert image_counts == wrapper["page_image_counts"]
            assert text_lengths == wrapper["page_text_lengths"]
            assert page_shapes == wrapper["page_shapes"]
            assert page_hashes == wrapper["page_raster_sha256"]
            raster_hashes[publication_id][label] = page_hashes

        wrapper_sets = list(raster_hashes[publication_id].values())
        assert wrapper_sets[0] == wrapper_sets[1]
        for visual in publication["retained_visual_audits"]:
            path = root / visual["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == visual["sha256"]

    assert audit["cross_publication_raster_comparison"]["equal_page_count"] == 0
    assert audit["cross_publication_raster_comparison"]["equal_pages"] == []
    assert all(
        b2_hash != a1_hash
        for b2_hash, a1_hash in zip(
            raster_hashes["US-10739565-B2"]["live-1"],
            raster_hashes["US-20190154990-A1"]["official"],
            strict=True,
        )
    )


def test_aac_five_lens_f_number_bound_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-62052738"
    evidence = json.loads(
        (quick / "family-62052738-replay-determinism.json").read_text(encoding="utf-8")
    )

    assert evidence["family_id"] == "62052738"
    assert evidence["root_count"] == 2
    assert evidence["item_count"] == 4
    assert evidence["excluded_semantic_fields"] == ["result_attempt"]
    assert evidence["semantic_equal"] is True
    semantic_hashes: set[str] = set()
    for root_record in evidence["roots"]:
        assert root_record["item_count"] == 2
        assert root_record["semantic_equal"] is True
        root_semantic_hashes: set[str] = set()
        for attempt in root_record["attempts"]:
            path = root / attempt["path"]
            raw = path.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == attempt["file_sha256"]
            result = json.loads(raw)
            assert result["result_attempt"] == attempt["result_attempt"]
            assert result["root_id"] == root_record["root_id"]
            assert result["root_state"] == "terminal"
            assert result["reason_code"] == "terminal.all_disclosed_items_terminal"
            assert len(result["items"]) == 2
            assert all(
                item["state"] == "terminal"
                and item["terminal_status"] == "metadata_unpublished"
                and item["reason_code"] == "terminal.metadata_unpublished.system_f_number_absent"
                and item["conversion_attempt_id"] is None
                and item["conversion_request_sha256"] is None
                and item["prescription_fingerprint"] is None
                for item in result["items"]
            )
            result.pop("result_attempt")
            semantic_sha256 = hashlib.sha256(
                json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            assert semantic_sha256 == attempt["semantic_sha256"]
            assert semantic_sha256 == root_record["semantic_sha256"]
            root_semantic_hashes.add(semantic_sha256)
            semantic_hashes.add(semantic_sha256)
        assert root_semantic_hashes == {root_record["semantic_sha256"]}
    assert semantic_hashes == {
        "87fa187194a547f93786253acb090331b465c989299f82de0df594ef4c453c92",
        "0a026f0f3b04978d6e7ce2aa9103deebcc423c65d215e7a7f9d9d2ba60bf6437",
    }


def test_largan_folded_image_sensor_filter_source_has_twenty_terminals() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "US-PGPUB"
        / "af4c1f9b7a42a688"
        / "US-20250189695-A1.html"
    )
    raw_text = source.read_text(encoding="utf-8")
    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id="US-20250189695-A1",
    )

    assert [attempt.embodiment_number for attempt in attempts] == list(range(1, 21))
    assert len(attempts) == 20
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        and attempt.error.reason_code
        == (
            "confirmed_no_prescription."
            "folded_image_sensor_filter_and_nano_rough_surface_architecture_only"
        )
        for attempt in attempts[:15]
    )
    assert all(
        isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and attempt.error.status == "confirmed_no_prescription"
        and attempt.error.reason_code
        == "confirmed_no_prescription.camera_module_device_architecture_only"
        for attempt in attempts[15:]
    )

    altered = patent_to_zmx._parse_prescription_attempts(
        raw_text + " EFL 4.0",
        patent_id="US-20250189695-A1",
    )
    assert len(altered) == 20
    assert all(
        isinstance(attempt.error, PatentParseError)
        and not isinstance(attempt.error, patent_to_zmx.PatentTerminalParseError)
        and "raw text hash changed" in str(attempt.error)
        for attempt in altered
    )


def test_largan_folded_image_sensor_filter_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-94531539"
    evidence = json.loads(
        (quick / "family-94531539-source-evidence.json").read_text(encoding="utf-8")
    )

    assert evidence["family_id"] == "94531539"
    assert evidence["application_number"] == "18/964621"
    assert evidence["root_ids"] == ["US-20250189695"]
    assert evidence["denominator"] == {
        "frozen_cohort_roots": 1,
        "source_publications": 1,
        "official_pdf_pages": 68,
        "drawing_sheets": 53,
        "figure_panels": 53,
        "formal_embodiments": 9,
        "embodiment_1_examples": 7,
        "embodiment_2_examples": 6,
        "source_tables": 2,
        "coating_layers": 70,
        "r50_samples": 8,
        "description_paragraphs": 189,
        "claims": 29,
        "terminal_items": 20,
    }

    html = evidence["official_html"]
    source = root / html["path"]
    raw_text = source.read_text(encoding="utf-8")
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    assert hashlib.sha256(raw_text.encode()).hexdigest() == html["raw_document_sha256"]
    assert hashlib.sha256(normalized.encode()).hexdigest() == html["normalized_text_sha256"]

    markers = html["section_markers"]
    names = tuple(markers)
    starts = {name: normalized.index(marker) for name, marker in markers.items()}
    sections = {
        name: normalized[
            starts[name] : (
                starts[names[index + 1]] if index + 1 < len(names) else len(normalized)
            )
        ]
        for index, name in enumerate(names)
    }
    for name, section in sections.items():
        assert hashlib.sha256(section.encode()).hexdigest() == html["section_sha256"][name]
    for name, bounds in html["paragraph_ranges"].items():
        assert [int(value) for value in re.findall(r"\[(\d{4})\]", sections[name])] == list(
            range(bounds[0], bounds[1] + 1)
        )
    assert [
        int(value)
        for value in re.findall(
            r"(?:^|\s)(\d+)\s*\.\s+(?=(?:An?|The)\s)",
            sections["claims"],
            re.IGNORECASE,
        )
    ] == list(range(1, 30))

    brief_start = raw_text.index("BRIEF DESCRIPTION OF THE DRAWINGS<br />")
    brief_end = raw_text.index("DETAILED DESCRIPTION<br />", brief_start)
    raw_brief = raw_text[brief_start:brief_end]
    assert hashlib.sha256(raw_brief.encode()).hexdigest() == html["raw_drawing_section_sha256"]
    figure_records: list[dict[str, int | str]] = []
    for paragraph, body in re.findall(
        r"\[(\d{4})\]\s*(.*?)(?=<br\s*/?>\[\d{4}\]|$)",
        raw_brief,
        re.IGNORECASE | re.DOTALL,
    ):
        match = re.search(
            r"<figref[^>]*>FIG\.\s*<b>([^<]+)</b>([A-Z]?)</figref>\s+(?:is|shows)",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if match is not None:
            figure_records.append(
                {
                    "paragraph": int(paragraph),
                    "panel": f"{match.group(1)}{match.group(2)}",
                }
            )
    assert figure_records == html["raw_figure_declarations"]
    assert [record["paragraph"] for record in figure_records] == list(range(9, 62))
    assert len(html["canonical_raster_figure_panels"]) == 53
    assert html["html_to_raster_label_repairs"] == [
        {"paragraph": 17, "html_label": "11", "raster_label": "1I"},
        {"paragraph": 42, "html_label": "21", "raster_label": "2I"},
    ]

    blocks = patent_to_zmx._patent_table_blocks(normalized)
    assert [block.number for block in blocks] == [1, 2]
    for block, table in zip(blocks, html["tables"], strict=True):
        assert hashlib.sha256(block.text.encode()).hexdigest() == table["block_sha256"]
        formal = re.split(r"\s+\[\d{4}\]\s+", block.text, maxsplit=1)[0]
        assert hashlib.sha256(formal.encode()).hexdigest() == table["formal_table_sha256"]
    assert html["table_1_layer_sequence"] == list(range(1, 71))
    assert html["table_1_group_sequence"] == [
        "H" if number % 2 else "L" for number in range(1, 71)
    ]
    assert html["table_2_r50_values_nm"] == [661, 670, 682, 692, 701, 664, 672, 681]
    assert set(evidence["optical_boundary"]["absent_marker_counts"].values()) == {0}
    for marker in ("EFL", "FOV", "TTL", "FNO"):
        assert re.search(rf"\b{marker}\b", normalized, re.IGNORECASE) is None
    assert evidence["optical_boundary"]["ordered_surface_prescription_published"] is False
    assert evidence["optical_boundary"]["system_efl_f_number_field_published"] is False

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id=evidence["publication_id"],
    )
    assert len(attempts) == len(evidence["terminal_items"]) == 20
    raster_audit = root / evidence["official_pdf_audit"]["path"]
    assert (
        hashlib.sha256(raster_audit.read_bytes()).hexdigest()
        == evidence["official_pdf_audit"]["sha256"]
    )

    queue = json.loads(
        (quick / "family-94531539-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["current_frozen_cohort_roots"] == ["US-20250189695"]
    assert {member["publication_id"] for member in queue["external_family_members"]} == {
        "JP3250120U",
        "KR20250000908U",
        "CN120111342A",
        "TWI919493B",
    }
    assert all(
        member["disposition"] == "queue_after_frozen_619_root_cohort"
        for member in queue["external_family_members"]
    )


def test_largan_folded_image_sensor_filter_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-94531539"
    audit = json.loads(
        (quick / "family-94531539-raster-audit.json").read_text(encoding="utf-8")
    )

    assert audit["family_id"] == "94531539"
    assert audit["root_ids"] == ["US-20250189695"]
    assert audit["page_count"] == 68
    assert audit["drawing_page_range"] == [2, 54]
    assert audit["drawing_sheet_count"] == 53
    assert audit["specification_page_range"] == [55, 68]
    assert audit["claims_page_range"] == [66, 68]
    assert audit["claim_range"] == [1, 29]
    assert audit["table_pages"] == {"1": 60, "2": 62}
    assert audit["html_to_raster_label_repairs"] == [
        {"paragraph": 17, "pdf_page": 10, "html_label": "11", "raster_label": "1I"},
        {"paragraph": 42, "pdf_page": 34, "html_label": "21", "raster_label": "2I"},
    ]

    raster_sets: dict[str, list[str]] = {}
    for label, wrapper in audit["wrappers"].items():
        pdf_path = root / wrapper["path"]
        assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == wrapper["sha256"]
        reader = patent_pdf_recovery.pypdf.PdfReader(str(pdf_path))
        assert len(reader.pages) == wrapper["page_count"] == 68
        page_hashes: list[str] = []
        image_counts: list[int] = []
        text_lengths: list[int] = []
        page_shapes: list[list[int]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            image_counts.append(len(page.images))
            text_lengths.append(len((page.extract_text() or "").strip()))
            image_bytes = patent_pdf_recovery._page_image(
                page,
                source=f"US-20250189695-A1 {label}",
                page_number=page_number,
            )
            page_hashes.append(patent_pdf_recovery._canonical_raster_sha256(image_bytes))
            decoded = cv2.imdecode(
                np.frombuffer(image_bytes, dtype=np.uint8),
                cv2.IMREAD_UNCHANGED,
            )
            assert decoded is not None
            page_shapes.append([int(value) for value in decoded.shape])
        assert image_counts == wrapper["page_image_counts"]
        assert text_lengths == wrapper["page_text_lengths"]
        assert page_shapes == wrapper["page_shapes"]
        assert page_hashes == wrapper["page_raster_sha256"]
        raster_sets[label] = page_hashes

    assert raster_sets["official-live-1"] == raster_sets["official-live-2"]
    assert raster_sets["official-live-1"] == raster_sets["google"]
    for comparison in audit["decoded_raster_equality"].values():
        assert comparison == {"all_equal": True, "equal_pages": 68}
    for visual in audit["retained_visual_audits"]:
        path = root / visual["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == visual["sha256"]


def test_largan_folded_image_sensor_filter_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-94531539"
    evidence = json.loads(
        (quick / "family-94531539-replay-determinism.json").read_text(encoding="utf-8")
    )

    assert evidence["family_id"] == "94531539"
    assert evidence["root_id"] == "US-20250189695"
    assert evidence["item_count"] == 20
    assert evidence["excluded_semantic_fields"] == ["result_attempt"]
    assert evidence["semantic_equal"] is True
    semantic_hashes: set[str] = set()
    for attempt in evidence["attempts"]:
        path = root / attempt["path"]
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == attempt["file_sha256"]
        result = json.loads(raw)
        assert result["result_attempt"] == attempt["result_attempt"]
        assert result["root_state"] == "terminal"
        assert result["reason_code"] == "terminal.all_disclosed_items_terminal"
        assert len(result["items"]) == 20
        assert all(
            item["state"] == "terminal"
            and item["terminal_status"] == "confirmed_no_prescription"
            and item["conversion_attempt_id"] is None
            and item["conversion_request_sha256"] is None
            and item["prescription_fingerprint"] is None
            for item in result["items"]
        )
        assert all(
            item["reason_code"]
            == (
                "terminal.confirmed_no_prescription."
                "folded_image_sensor_filter_and_nano_rough_surface_architecture_only"
            )
            for item in result["items"][:15]
        )
        assert all(
            item["reason_code"]
            == "terminal.confirmed_no_prescription.camera_module_device_architecture_only"
            for item in result["items"][15:]
        )
        result.pop("result_attempt")
        semantic_sha256 = hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        assert semantic_sha256 == attempt["semantic_sha256"]
        assert semantic_sha256 == evidence["semantic_sha256"]
        semantic_hashes.add(semantic_sha256)
    assert semantic_hashes == {
        "8d5c826e4d2f1f414fd4a21d01fc10037bd4a9215454572a7c2116efd4063a7b"
    }


def test_aac_seven_lens_exact_source_parses_three_complete_prescriptions() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "data"
        / "patent-lake"
        / "uspto-ppubs-html"
        / "USPAT"
        / "d06dcb7578f86ca8"
        / "US-11467375-B2.html"
    )
    raw_text = source.read_text(encoding="utf-8")

    attempts = patent_to_zmx._parse_prescription_attempts(
        raw_text,
        patent_id="US-11467375-B2",
    )
    assert len(attempts) == 3
    assert all(attempt.error is None for attempt in attempts)
    prescriptions = [attempt.prescription for attempt in attempts]
    assert all(prescription is not None for prescription in prescriptions)
    parsed = [prescription for prescription in prescriptions if prescription is not None]

    assert [prescription.embodiment for prescription in parsed] == [
        "AAC seven-lens camera optical lens embodiment 1",
        "AAC seven-lens camera optical lens embodiment 2",
        "AAC seven-lens camera optical lens embodiment 3",
    ]
    assert [
        (
            prescription.focal_length_mm,
            prescription.f_number,
            prescription.hfov_deg,
        )
        for prescription in parsed
    ] == [(4.925, 1.55, 38.54), (4.762, 1.55, 39.43), (4.981, 1.55, 38.325)]
    assert [prescription_fingerprint(prescription) for prescription in parsed] == [
        "70caae14a7653f68",
        "8cf47e69f12717a1",
        "ab1d414097059056",
    ]
    assert all(len(prescription.surfaces) == 18 for prescription in parsed)
    assert [[surface.label for surface in prescription.surfaces] for prescription in parsed] == [
        [
            "Stop",
            *(f"L{lens} S{side}" for lens in range(1, 8) for side in (1, 2)),
            "GF S1",
            "GF S2",
            "Image",
        ]
    ] * 3
    assert [prescription.surfaces[0].thickness_mm for prescription in parsed] == [
        -0.552,
        -0.513,
        -0.546,
    ]
    assert all(
        sum(surface.surface_type == "ASP" for surface in prescription.surfaces) == 14
        for prescription in parsed
    )
    assert all(
        [surface.material for surface in prescription.surfaces if surface.material]
        == ["Glass", "Glass", "Plastic", "Plastic", "Plastic", "Plastic", "Plastic", "Filter"]
        for prescription in parsed
    )

    canonical_payload = [
        {
            "embodiment": prescription.embodiment,
            "focal_length_mm": prescription.focal_length_mm,
            "f_number": prescription.f_number,
            "hfov_deg": prescription.hfov_deg,
            "reference_wavelength_um": prescription.reference_wavelength_um,
            "surfaces": [
                {
                    "index": surface.index,
                    "label": surface.label,
                    "radius_mm": (
                        "Infinity"
                        if surface.radius_mm is not None and math.isinf(surface.radius_mm)
                        else surface.radius_mm
                    ),
                    "thickness_mm": surface.thickness_mm,
                    "material": surface.material,
                    "nd": surface.nd,
                    "vd": surface.vd,
                    "surface_type": surface.surface_type,
                    "asphere_coefficients": surface.asphere_coefficients,
                }
                for surface in prescription.surfaces
            ],
        }
        for prescription in parsed
    ]
    assert hashlib.sha256(
        json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == "a6f737dda646a564b1b45e0dcbf20a4861f1069d486e29732322db4ad8fa8286"

    mutated = raw_text.replace("FNO 1.55 1.55 1.55", "FNO 1.55 1.55 1.56", 1)
    failed = patent_to_zmx._parse_prescription_attempts(
        mutated,
        patent_id="US-11467375-B2",
    )
    assert len(failed) == 3
    assert all(attempt.prescription is None for attempt in failed)
    assert all(
        isinstance(attempt.error, PatentParseError)
        and "official raw text hash changed" in str(attempt.error)
        for attempt in failed
    )


def test_aac_seven_lens_exact_source_evidence_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-71121572"
    evidence = json.loads(
        (quick / "family-71121572-source-evidence.json").read_text(encoding="utf-8")
    )

    assert evidence["family_id"] == "71121572"
    assert evidence["root_ids"] == ["US-11467375"]
    assert evidence["publication_id"] == "US-11467375-B2"
    assert evidence["application_number"] == "16/675252"
    assert evidence["denominator"] == {
        "frozen_cohort_roots": 1,
        "retained_classification_publications": 1,
        "same_application_cross_check_publications": 1,
        "official_b2_pdf_pages": 18,
        "drawing_sheets": 7,
        "figures": 12,
        "exact_prescription_embodiments": 3,
        "surfaces_per_embodiment": 18,
        "asphere_surfaces_per_embodiment": 14,
        "source_tables": 13,
        "description_paragraphs": 147,
        "claims": 19,
        "terminal_items": 3,
        "trace_failed_items": 3,
    }

    html = evidence["official_html"]
    source = root / html["path"]
    raw_text = source.read_text(encoding="utf-8")
    normalized = patent_to_zmx.normalize_patent_text(raw_text)
    assert hashlib.sha256(raw_text.encode()).hexdigest() == html["raw_document_sha256"]
    assert hashlib.sha256(normalized.encode()).hexdigest() == html["normalized_text_sha256"]

    names = tuple(html["section_markers"])
    starts = {
        name: normalized.index(marker)
        for name, marker in html["section_markers"].items()
    }
    sections = {
        name: normalized[
            starts[name] : (
                starts[names[index + 1]]
                if index + 1 < len(names)
                else len(normalized)
            )
        ]
        for index, name in enumerate(names)
    }
    assert {
        name: hashlib.sha256(section.encode()).hexdigest()
        for name, section in sections.items()
    } == html["section_sha256"]
    assert [
        int(value)
        for value in re.findall(
            r"(?:^|\s)(\d+)\s*\.\s+(?=(?:A|The)\s)",
            sections["claims"],
            re.IGNORECASE,
        )
    ] == list(range(1, 20))
    assert [
        int(value)
        for value in re.findall(
            r"\(\d+\)\s+FIG\.\s*(\d+)\s+is\s+a\s+schematic",
            sections["brief"],
            re.IGNORECASE,
        )
    ] == list(range(1, 13))

    blocks = patent_to_zmx._patent_table_blocks(normalized)
    assert [block.number for block in blocks] == list(range(1, 14))
    assert [
        hashlib.sha256(block.text.encode()).hexdigest() for block in blocks
    ] == html["table_block_sha256"]
    formal_tables = [
        patent_to_zmx._aac_seven_lens_exact_formal_table(block.text)
        for block in blocks
    ]
    assert [
        hashlib.sha256(table.encode()).hexdigest() for table in formal_tables
    ] == html["formal_table_sha256"]
    assert [record["outcome"] for record in evidence["embodiments"]] == [
        "trace_failed",
        "trace_failed",
        "trace_failed",
    ]

    raster_path = root / evidence["official_pdf_audit"]["path"]
    assert hashlib.sha256(raster_path.read_bytes()).hexdigest() == evidence[
        "official_pdf_audit"
    ]["sha256"]

    queue = json.loads(
        (quick / "family-71121572-external-family-members.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["current_frozen_cohort_roots"] == ["US-11467375"]
    assert queue["discovery"]["source_url"] == (
        "https://patents.google.com/patent/US11467375B2/en"
    )
    assert [record["publication_id"] for record in queue["external_family_members"]] == [
        "US-20200209560-A1",
        "JP-2020106789-A",
        "JP-6805300-B2",
        "WO-2020134286-A1",
        "CN-109839722-A",
        "CN-109839722-B",
        "CN-109828350-A",
        "CN-109828350-B",
    ]


def test_aac_seven_lens_exact_pdf_raster_audit_rehashes() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-71121572"
    audit = json.loads(
        (quick / "family-71121572-raster-audit.json").read_text(encoding="utf-8")
    )

    assert audit["family_id"] == "71121572"
    assert audit["publications"]["US-11467375-B2"]["page_count"] == 18
    assert audit["publications"]["US-11467375-B2"]["drawing_page_range"] == [3, 9]
    assert audit["publications"]["US-11467375-B2"]["table_page_range"] == [12, 16]
    assert audit["publications"]["US-11467375-B2"]["claims_page_range"] == [16, 18]
    assert audit["publications"]["US-20200209560-A1"]["page_count"] == 17

    raster_sets: dict[str, list[str]] = {}
    for publication_id, publication in audit["publications"].items():
        expected_hashes = publication["page_raster_sha256"]
        expected_shape = publication["page_shape"]
        for label, wrapper in publication["wrappers"].items():
            path = root / wrapper["path"]
            assert path.stat().st_size == wrapper["bytes"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == wrapper["sha256"]
            reader = patent_pdf_recovery.pypdf.PdfReader(str(path))
            assert len(reader.pages) == publication["page_count"]
            page_hashes: list[str] = []
            text_lengths: list[int] = []
            for page_number, page in enumerate(reader.pages, start=1):
                assert len(page.images) == publication["page_image_count"]
                text_lengths.append(len((page.extract_text() or "").strip()))
                image = patent_pdf_recovery._page_image(
                    page,
                    source=f"{publication_id} {label}",
                    page_number=page_number,
                )
                assert list(
                    patent_pdf_recovery._decoded_raster(
                        image,
                        source=f"{publication_id} {label}",
                    ).shape
                ) == expected_shape
                page_hashes.append(
                    patent_pdf_recovery._canonical_raster_sha256(image)
                )
            assert text_lengths == wrapper["page_text_lengths"]
            assert page_hashes == expected_hashes
            assert hashlib.sha256(
                json.dumps(page_hashes, separators=(",", ":")).encode()
            ).hexdigest() == publication["raster_set_sha256"]
            raster_sets[f"{publication_id}:{label}"] = page_hashes

    assert raster_sets["US-11467375-B2:official-live-1"] == raster_sets[
        "US-11467375-B2:official-live-2"
    ] == raster_sets["US-11467375-B2:google"]
    assert raster_sets["US-20200209560-A1:official"] == raster_sets[
        "US-20200209560-A1:google"
    ]
    assert sum(
        first == second
        for first, second in zip(
            raster_sets["US-11467375-B2:official-live-1"],
            raster_sets["US-20200209560-A1:official"],
            strict=False,
        )
    ) == audit["cross_publication_same_position_raster_equality"]["equal_pages"] == 0
    for retained in audit["retained_visual_audits"]:
        assert hashlib.sha256((root / retained["path"]).read_bytes()).hexdigest() == retained[
            "sha256"
        ]


def test_aac_seven_lens_exact_replay_is_semantically_deterministic() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-71121572"
    artifact = json.loads(
        (quick / "family-71121572-replay-determinism.json").read_text(
            encoding="utf-8"
        )
    )

    def semantic_digest(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    assert artifact["family_id"] == "71121572"
    assert artifact["root_id"] == "US-11467375"
    assert [attempt["result_attempt"] for attempt in artifact["attempts"]] == [2, 3]
    for expected in artifact["attempts"]:
        result_path = (
            root
            / "data"
            / "patent-ledger"
            / "replay"
            / "local-uncovered"
            / "results"
            / "US-11467375"
            / f"attempt-{expected['result_attempt']:04d}"
            / "result.json"
        )
        assert hashlib.sha256(result_path.read_bytes()).hexdigest() == expected[
            "result_sha256"
        ]
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result.pop("result_attempt") == expected["result_attempt"]
        assert result["root_state"] == "terminal"
        assert result["reason_code"] == "terminal.all_disclosed_items_terminal"
        assert len(result["items"]) == 3
        for item in result["items"]:
            assert item["state"] == "terminal"
            assert item["terminal_status"] == "trace_failed"
            item.pop("conversion_attempt_id", None)
            embodiment = artifact["embodiments"][str(item["embodiment_number"])]
            assert item["prescription_fingerprint"] == embodiment[
                "prescription_fingerprint"
            ]
            assert item["conversion_request_sha256"] == embodiment["request_sha256"]
            for evidence in item["evidence"]:
                if evidence["evidence_type"] != "patent_conversion_receipt":
                    continue
                receipt_path = root / evidence["path"]
                assert hashlib.sha256(receipt_path.read_bytes()).hexdigest() == embodiment[
                    "receipt_sha256_by_result_attempt"
                ][str(expected["result_attempt"])]
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                for label, field in {
                    "request": "request_path",
                    "response": "response_path",
                    "stdout": "stdout_path",
                    "stderr": "stderr_path",
                }.items():
                    assert hashlib.sha256((root / receipt[field]).read_bytes()).hexdigest() == (
                        embodiment["worker_artifact_sha256"][label]
                    )
                for field in artifact["excluded_receipt_fields"]:
                    receipt.pop(field, None)
                receipt_semantic_sha256 = semantic_digest(receipt)
                assert receipt_semantic_sha256 == embodiment["receipt_semantic_sha256"]
                evidence.clear()
                evidence.update(
                    {
                        "evidence_type": "patent_conversion_receipt",
                        "receipt_semantic_sha256": receipt_semantic_sha256,
                    }
                )
        assert semantic_digest(result) == expected["semantic_sha256"]

    assert {attempt["semantic_sha256"] for attempt in artifact["attempts"]} == {
        "23fbae389abed9710e28b79e030dee3f3ad39aa107c1dc291ca215807c2aefb8"
    }
    assert all(
        embodiment["candidate_zmx_sha256"] is None
        for embodiment in artifact["embodiments"].values()
    )


def test_aac_seven_lens_exact_generic_census_retires_one_root() -> None:
    root = Path(__file__).resolve().parents[1]
    quick = root / ".planning" / "quick" / "260717-patent-generic-family-71121572"
    before = json.loads(
        (quick / "generic-residual-before-141.json").read_text(encoding="utf-8")
    )
    after_1_path = quick / "generic-residual-after-1.json"
    after_2_path = quick / "generic-residual-after-2.json"
    after = json.loads(after_1_path.read_text(encoding="utf-8"))

    assert before["affected_roots"] == before["affected_items"] == 141
    assert after["affected_roots"] == after["affected_items"] == 140
    assert after["result_set_sha256"] == (
        "1d1abad32b40d72d8db88191553adb69fe344c413e50d4bd40a886d633d34d43"
    )
    assert after_1_path.read_bytes() == after_2_path.read_bytes()
    assert hashlib.sha256(after_1_path.read_bytes()).hexdigest() == (
        "34faa5dd28e62aa1a19ca60435b8020f7a982fe1737e33dedd5a0056cea8ea55"
    )
    assert all(item["root_id"] != "US-11467375" for item in after["items"])

    queue = json.loads((quick / "queue-after.json").read_text(encoding="utf-8"))
    assert queue["result_set_sha256"] == after["result_set_sha256"]
    assert queue["next_exact_group"] == {
        "family_id": "64459548",
        "root_id": "US-20210373283",
        "publication_id": "US-20210373283-A1",
        "layout_signature": (
            "18f601741e46968dd9aa08221b03b91587e37313eeac6ae406034b44be026e21"
        ),
        "raw_document_sha256": (
            "f12d20d6c4a675d50fe7245fcda60aea7eb19389bfb0ca7cc314868053203431"
        ),
        "title": "IMAGING LENS UNIT AND METHOD FOR MANUFACTURING THE SAME",
        "affected_roots": 1,
        "affected_items": 1,
    }
