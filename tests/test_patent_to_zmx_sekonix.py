from __future__ import annotations

import math

import pytest

from scripts import patent_to_zmx
from scripts.patent_to_zmx import PatentParseError

# Verbatim table text copied from the English Google Patents publication pages.
# Whitespace is flattened in the same way as normalize_patent_text().
US_11099361_B2_RDY = """
TABLE-US-00001 TABLE 1 RDY Nd Vd Surface (Radius of THI (Refractive (Abbe
(Surface Number) Curvature) (Thickness) Index) Number)
FOCAL OBJECT INFINITY INFINITY
1 1.823 1.13 1.544 56.0 2 −9.001 0.11 3 −66.481 0.22 1.671 19.5
STO: 4.136 1.04 5 −42.890 0.21 1.544 56.0 6 3.065 1.81
7 −2.506 0.25 1.544 56.0 8 −13.680 0.05 9 4.482 0.61 1.671 19.5
10 −2000.000 0.10 11 INFINITY 0.11 1.517 64.2 12 INFINITY 0.62 IMG: INFINITY 0.00
TABLE-US-00002 TABLE 2 K A3 A4 A5 A6 A7
s1 0.12627 1.552030E−04 7.296990E−05 1.297390E−03 1.451520E−03 7.267430E−04
s2 99.00000 5.057870E−04 1.850330E−02 1.984990E−02 1.134910E−02 3.943210E−03
The effective focal length f of the lens system and the distance TTL from the
front surface to the image surface may satisfy TTL/f<0.85. An angle of view VA
may satisfy 26 degrees<VA<32 degrees.
"""

US_12619054_B2_SPHERE_ASPHERE = """
TABLE-US-00001 TABLE 1 Surface Surface Y Y Semi- Number Type Radius Thickness
Glass Code Aperture Object Sphere infinity infinity
1 Sphere infinity 0.0000 3.2624
2 Asphere 336.6808 0.4450 535000.5600 3.2500
3 Asphere 120.8270 0.0500 3.2518
4 Asphere 3.6593 2.7391 535000.5600 3.1743
5 Asphere 707.8568 0.5400 2.6224
Stop Asphere −68.6152 0.6243 634000.2390 2.3609
7 Asphere 4.1505 3.5402 2.1830
8 Asphere 44.0441 0.4400 535000.5600 2.0500
9 Asphere 13.0481 0.4000 2.0700
10 Asphere 15.5931 0.4800 661000.2040 2.1200
11 Asphere −42.8125 6.0000 2.2000
12 Sphere infinity 0.1100 'D263T' 3.1746
13 Sphere infinity 2.1812 3.1858 Image Sphere infinity 0.0000 3.5280
TABLE-US-00002 TABLE 2 Surface 2 3 4 5 Stop
Y Radius 3.36681.E+02 1.20827.E+02 3.65932.E+00 7.07857.E+02 −6.86152.E+01
K −9.90000.E+01 9.90000.E+01 −5.14326.E−01 9.90000.E+01 9.90000.E+01
4th Qcon Coefficient 2.20510.E−03 −8.23429.E−04 −1.94150.E−03 1.63444.E−03 8.19553.E−04
6th Qcon Coefficient −7.96835.E−04 1.74659.E−04 9.59243.E−04 1.62629.E−04 6.37131.E−04
Also, in one embodiment of the present invention, the field of view FOV of the
lens system satisfies FOV=21.8°, and the F number Fno of the lens system satisfies Fno=2.79.
"""

US_12498545_B2_QCON = """
TABLE-US-00001 TABLE 1 Surface Y Thick- Y Semi- Type Radius ness Glass Code Aperture
Object Sphere Infinity Infinity
1 Sphere Infinity 0.0000 0.7145
2 Qcon Asphere 2.1199 0.1573 535000.5600 0.6900
Stop Qcon Asphere 2.0649 0.0421 0.6915
4 Qcon Asphere 1.3159 0.3975 544100.5600 0.6997
5 Qcon Asphere −7.3890 0.0718 0.6906
6 Qcon Asphere −3.5406 0.1000 670000.1940 0.6500
7 Qcon Asphere Infinity 0.3080 0.6703
8 Qcon Asphere 1.6411 0.1039 670000.1940 0.7336
9 Qcon Asphere 1.8476 0.4178 0.8005
10 Qcon Asphere 12.2632 0.4910 544100.5600 0.9800
11 Qcon Asphere −0.6224 0.0594 1.3856
12 Qcon Asphere −3.9286 0.1400 535000.5600 1.6756
13 Qcon Asphere 0.5125 0.1412 1.8240
14 Sphere Infinity 0.1100 BK7_SCHOTT 2.1034
15 Sphere Infinity 0.6204 2.1436 Image Sphere Infinity −0.0004 2.5200
TABLE-US-00002 TABLE 2 Surface 2 Stop 4 5 6 7
Y Radius 2.11986.E+00 2.06492.E+00 1.31591.E+00 −7.38900.E+00 −3.54059.E+00 1.00000.E+18
Normalization Radius 7.30000.E−01 7.38989.E−01 7.57518.E−01 7.50000.E−01 7.30000.E−01 8.33748.E−01
K −2.73434.E+01 6.83977.E+00 1.64834.E+00 −4.02017.E+01 0.00000.E+00 −7.16111.E+01
4th Qcon Coefficient −6.42401.E−02 −2.08364.E−01 −1.25167.E−01 −8.44660.E−02 −1.81601.E−02 −2.22981.E−04
6th Qcon Coefficient 5.54240.E−03 1.05262.E−02 −1.70173.E−02 −3.34258.E−03 1.16324.E−02 −2.07430.E−03
"""


@pytest.mark.parametrize(
    ("text", "expected_count", "radius", "thickness", "nd", "vd"),
    [
        (US_11099361_B2_RDY, 13, 1.823, 1.13, 1.544, 56.0),
        (US_12619054_B2_SPHERE_ASPHERE, 12, 336.6808, 0.4450, 1.535, 56.0),
        (US_12498545_B2_QCON, 14, 2.1199, 0.1573, 1.535, 56.0),
    ],
)
def test_sekonix_real_publication_surface_fixtures(
    text: str,
    expected_count: int,
    radius: float,
    thickness: float,
    nd: float,
    vd: float,
) -> None:
    normalized = patent_to_zmx.normalize_patent_text(text)
    block = patent_to_zmx._patent_table_blocks(normalized)[0]
    surface_text = block.text
    # The two Glass Code publications end in a named IR-filter substrate whose
    # nd/vd are not printed.  Exercise the complete powered-lens prescription
    # through its last numeric-code surface, then append the publication's
    # verbatim Image row; separate tests below assert that the uncut full table
    # fails closed at the named substrate.
    if "'D263T'" in surface_text:
        surface_text = surface_text.split(" 12 Sphere", 1)[0] + " Image Sphere infinity 0.0000"
    if "BK7_SCHOTT" in surface_text:
        surface_text = surface_text.split(" 14 Sphere", 1)[0] + " Image Sphere Infinity -0.0004"
    surfaces, _ = patent_to_zmx._parse_sekonix_surface_table(
        surface_text,
        embodiment_number=1,
    )

    assert len(surfaces) == expected_count
    lens = surfaces[0] if "RDY" in text else surfaces[1]
    assert lens.radius_mm == pytest.approx(radius)
    assert lens.thickness_mm == pytest.approx(thickness)
    assert lens.nd == pytest.approx(nd)
    assert lens.vd == pytest.approx(vd)
    assert surfaces[-1].label == "Image"
    assert math.isinf(surfaces[-1].radius_mm)


def test_sekonix_glass_code_decodes_all_six_nd_digits() -> None:
    assert patent_to_zmx._sekonix_glass_code("535000.5600") == pytest.approx((1.535, 56.0))
    assert patent_to_zmx._sekonix_glass_code("544100.5600") == pytest.approx((1.5441, 56.0))
    assert patent_to_zmx._sekonix_glass_code("634000.2390") == pytest.approx((1.634, 23.9))

    text = patent_to_zmx.normalize_patent_text(US_12498545_B2_QCON)
    surface_text = patent_to_zmx._patent_table_blocks(text)[0].text
    surface_text = surface_text.split(" 14 Sphere", 1)[0] + " Image Sphere Infinity -0.0004"
    surfaces, _ = patent_to_zmx._parse_sekonix_surface_table(surface_text, embodiment_number=1)
    for surface_index in (4, 10):
        surface = surfaces[surface_index - 1]
        assert surface.nd == pytest.approx(1.5441)
        assert surface.vd == pytest.approx(56.0)


def test_sekonix_malformed_glass_code_fails_loud() -> None:
    malformed = US_12498545_B2_QCON.replace("544100.5600", "54410.5600", 1)
    text = patent_to_zmx.normalize_patent_text(malformed)
    block = patent_to_zmx._patent_table_blocks(text)[0]
    with pytest.raises(PatentParseError, match="malformed SEKONIX Glass Code: 54410.5600"):
        patent_to_zmx._parse_sekonix_surface_table(block.text, embodiment_number=1)


def test_sekonix_a3_names_map_explicitly_to_codev_even_orders() -> None:
    # US-11099361-B2, Equation 1 (Google Patents, verbatim term sequence):
    # "A3 · Y^4 + A4 · Y^6 + A5 · Y^8 + A6 · Y^10 + ... + A14 · Y^26"
    text = patent_to_zmx.normalize_patent_text(US_11099361_B2_RDY)
    blocks = patent_to_zmx._patent_table_blocks(text)
    _, labels = patent_to_zmx._parse_sekonix_surface_table(blocks[0].text, embodiment_number=1)
    coefficients = patent_to_zmx._parse_sekonix_asphere_table(
        blocks[1].text,
        index_by_label=labels,
    )

    first = coefficients[labels["1"]]
    assert first["K"] == pytest.approx(0.12627)
    assert first["A"] == pytest.approx(1.552030e-4)
    assert first["B"] == pytest.approx(7.296990e-5)
    assert first["E"] == pytest.approx(7.267430e-4)


def test_sekonix_qcon_basis_fails_closed() -> None:
    # US-12619054-B2, Mathematical Expression 1 (Google Patents, verbatim):
    # "u^4 · sum[m=0..13](a_m · Q_m^con(u^2))"; "u indicates r/r_n".
    # US-12498545-B2 prints the same Qcon basis (sum ends at m=12).
    text = patent_to_zmx.normalize_patent_text(US_12619054_B2_SPHERE_ASPHERE)
    blocks = patent_to_zmx._patent_table_blocks(text)
    powered_surfaces = blocks[0].text.split(" 12 Sphere", 1)[0] + " Image Sphere infinity 0.0000"
    _, labels = patent_to_zmx._parse_sekonix_surface_table(
        powered_surfaces,
        embodiment_number=1,
    )
    with pytest.raises(PatentParseError, match="Qcon basis conversion not implemented"):
        patent_to_zmx._parse_sekonix_asphere_table(blocks[1].text, index_by_label=labels)


def test_sekonix_range_only_metadata_fails_loud_per_embodiment() -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(
        US_11099361_B2_RDY,
        patent_id="US-11099361-B2",
    )

    assert len(attempts) == 1
    assert attempts[0].prescription is None
    assert isinstance(attempts[0].error, PatentParseError)
    assert "lacks exact instance" in str(attempts[0].error)
    assert "range-only metadata" in str(attempts[0].error)


def test_sekonix_named_glass_code_without_catalog_indices_fails_closed() -> None:
    text = patent_to_zmx.normalize_patent_text(US_12498545_B2_QCON)
    block = patent_to_zmx._patent_table_blocks(text)[0]

    with pytest.raises(PatentParseError, match="Glass Code cannot be split deterministically"):
        patent_to_zmx._parse_sekonix_surface_table(block.text, embodiment_number=1)


def test_sekonix_all_qcon_orders_fail_loud_before_mapping() -> None:
    text = patent_to_zmx.normalize_patent_text(
        US_12619054_B2_SPHERE_ASPHERE.replace(
            "6th Qcon Coefficient",
            "32th Qcon Coefficient",
        )
    )
    blocks = patent_to_zmx._patent_table_blocks(text)
    powered_surfaces = blocks[0].text.split(" 12 Sphere", 1)[0] + " Image Sphere infinity 0.0000"
    _, labels = patent_to_zmx._parse_sekonix_surface_table(
        powered_surfaces,
        embodiment_number=1,
    )

    with pytest.raises(PatentParseError, match="Qcon basis conversion not implemented"):
        patent_to_zmx._parse_sekonix_asphere_table(blocks[1].text, index_by_label=labels)
