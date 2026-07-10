from __future__ import annotations

import pytest

from scripts import patent_to_zmx
from scripts.patent_to_zmx import PatentParseError

# Google Patents English publication pages, copied verbatim and whitespace-flattened.
US_10101561_B2_EMBODIMENT_3 = """
TABLE-US-00005 TABLE 5 Embodiment 3 f(focal length) = 3.35 mm, Fno = 2.2,
FOV = 84 deg. Surface Curvature Radius Thickness Material index Abbe # Focal length
0 object Infinity Infinity 1 Infinity 0.160 2 stop Infinity −0.160
3 lens 1 1.172 (ASP) 0.479 plastic 1.544 56.000 2.420
4 8.872 (ASP) 0.030 5 lens 2 38.922 (ASP) 0.195 plastic 1.650 21.400 −5.321
6 3.202 (ASP) 0.295 7 lens 3 −29.017 (ASP) 0.290 plastic 1.650 21.400 −31.372
8 71.504 (ASP) 0.491 9 lens 4 −9.666 (ASP) 0.586 plastic 1.544 56.000 1.883
10 −0.950 (ASP) 0.205 11 lens 5 −4.597 (ASP) 0.330 plastic 1.544 56.000 −1.580
12 1.090 (ASP) 0.380 13 IR-filter Infinity 0.210 glass 1.517 64.167 —
14 Infinity 0.425 15 image plane Infinity Infinity
TABLE-US-00006 TABLE 6 Aspheric Coefficients surface 3 4 5 6 7
K: −7.3032E+00 1.0830E+02 −7.8511E+01 1.3248E+01 1.3955E+02
A: 5.4995E−01 −2.3465E−01 −1.0387E−01 1.4748E−02 −3.1986E−01
B: −9.5530E−01 −2.2344E−01 3.5714E−01 7.6289E−01 5.9614E−02
C: 1.7778E+00 6.7115E+00 4.9115E+00 −1.9302E+00 4.2589E−01
D: −2.6835E+00 −2.5331E+01 −2.0513E+01 5.5979E+00 −2.8265E+00
E: 2.5611E+00 3.6318E+01 3.0079E+01 −1.0043E+01 6.6074E+00
F: −1.7283E+00 −1.8996E+01 −1.5186E+01 8.1314E+00 −5.2382E+00
surface 8 9 10 11 12 K: −1.4153E+02 −5.0325E+01 −6.1060E+00 −2.0000E+02 −5.7726E+00
A: −2.3878E−01 −2.8320E−02 −1.2992E−01 −7.2460E−02 −1.4138E−01
B: 9.6490E−02 2.0047E−01 4.9726E−01 −1.4520E−02 7.6866E−02
C: −4.8500E−02 −4.1564E−01 −6.4484E−01 3.8511E−02 −2.8690E−02
D: −2.1877E−01 2.7288E−01 3.9390E−01 −1.5690E−02 6.4720E−03
E: 6.8488E−01 −7.2060E−02 −1.1833E−01 2.5900E−03 −7.9000E−04
F: −4.0041E−01 6.6870E−03 1.4047E−02 −1.6000E−04 3.9100E−05
"""

US_12596237_B2_EMBODIMENT_1 = """
TABLE-US-00001 TABLE 1 Embodiment 1 f = 2.47 mm, Fno = 1.21, FOV = 149.87°
Refractive Abbe Radius of Thickness/ index number Focal Surface curvature gap
Material (nd) (vd) length 0 Object Infinity Infinity
1 First lens −96.977 (ASP) 1.200 plastic 1.643 22.5 −4.34
2 2.784 (ASP) 1.962 3 Second lens 6.029 (ASP) 0.900 plastic 1.643 22.5 74.35
4 6.537 (ASP) 0.371 5 Stop Infinity 0.529
6 Third lens −11.237 (ASP) 2.030 plastic 1.643 22.5 9.13 7 −4.028 (ASP) 0.049
8 Fourth lens 8.203 (ASP) 2.440 plastic 1.643 22.5 9.30 9 −17.306 (ASP) 1.724
10 Fifth lens 3.769 (ASP) 1.913 plastic 1.643 22.5 9.51 11 8.400 (ASP) 1.669
12 Optical filter Infinity 0.210 glass 1.517 64.2 13 Infinity 0.403
14 Image plane Infinity — The reference wavelength is 940 nm.
TABLE-US-00002 TABLE 2 Embodiment 1 Aspheric Coefficients Surface 1 2 3 4 6
K: −9.8834E+01 −7.3206E−01 −5.7336E+01 7.5411E+00 4.1271E+00
A2: 0.0000E+00 0.0000E+00 0.0000E+00 0.0000E+00 0.0000E+00
A4: 2.5005E−03 3.5113E−03 1.8258E−02 −3.3043E−03 6.1224E−03
A6: −1.2047E−04 3.4868E−04 −1.4231E−02 1.1189E−03 4.8347E−04
A8: 4.7090E−06 1.1677E−05 4.4287E−03 −4.3397E−03 −4.8429E−06
A10: −9.7600E−08 0.0000E+00 −9.2175E−04 3.8238E−03 −1.3264E−04
A12: 3.0000E−10 0.0000E+00 7.8124E−05 −1.7257E−03 5.0387E−05
A14: 0.0000E+00 0.0000E+00 4.9770E−06 3.8720E−04 −7.2003E−06
A16: 0.0000E+00 0.0000E+00 −8.8570E−07 −3.3978E−05 3.6570E−07
Surface 7 8 9 10 11 K: −1.1325E+00 −1.7683E+01 1.3705E+01 −3.5122E−01 −2.7370E+01
A2: 0.0000E+00 0.0000E+00 0.0000E+00 0.0000E+00 0.0000E+00
A4: −4.8357E−03 −2.6691E−03 −9.7538E−03 −9.7194E−03 4.2237E−03
A6: 3.4237E−03 2.1131E−03 1.0866E−03 3.7473E−04 −1.6540E−03
A8: −1.3490E−03 −7.4683E−04 −6.1489E−05 −7.6498E−05 2.0323E−04
A10: 3.0222E−04 1.3600E−04 −6.3658E−06 3.9770E−06 −1.9408E−05
A12: −4.2192E−05 −1.4622E−05 1.4589E−06 3.1580E−07 1.3783E−06
A14: 3.2775E−06 8.4990E−07 −1.0990E−07 −3.1700E−08 −5.5400E−08
A16: −1.0420E−07 −2.0100E−08 3.2000E−09 7.0000E−10 9.0000E−10
"""


@pytest.mark.parametrize(
    ("text", "patent_id", "f", "fno", "hfov", "surface_count", "nd", "vd"),
    [
        (US_10101561_B2_EMBODIMENT_3, "US-10101561-B2", 3.35, 2.2, 42.0, 15, 1.544, 56.0),
        (US_12596237_B2_EMBODIMENT_1, "US-12596237-B2", 2.47, 1.21, 74.935, 14, 1.643, 22.5),
    ],
)
def test_newmax_complete_real_embodiments_end_to_end(
    text: str,
    patent_id: str,
    f: float,
    fno: float,
    hfov: float,
    surface_count: int,
    nd: float,
    vd: float,
) -> None:
    attempts = patent_to_zmx._parse_prescription_attempts(text, patent_id=patent_id)
    assert len(attempts) == 1
    assert attempts[0].error is None
    prescription = attempts[0].prescription
    assert prescription is not None
    assert prescription.focal_length_mm == pytest.approx(f)
    assert prescription.f_number == pytest.approx(fno)
    assert prescription.hfov_deg == pytest.approx(hfov)
    assert len(prescription.surfaces) == surface_count
    powered = next(surface for surface in prescription.surfaces if surface.nd is not None)
    assert powered.nd == pytest.approx(nd)
    assert powered.vd == pytest.approx(vd)
    assert powered.asphere_coefficients


def test_newmax_alphabetic_equation_maps_a_and_f_to_h4_and_h14() -> None:
    # US-10101561-B2, Equation 1 (verbatim term sequence):
    # "A h^4 + B h^6 + C h^8 + D h^10 + E h^12 + G h^14 + …"
    # The patent's coefficient table labels its sixth printed high-order row F;
    # paragraph 68 calls A, B, C, D, E, F, ... the high-order coefficients.
    prescription = patent_to_zmx._parse_prescription_attempts(
        US_10101561_B2_EMBODIMENT_3, patent_id="US-10101561-B2"
    )[0].prescription
    assert prescription is not None
    surface = prescription.surfaces[2]
    assert surface.asphere_coefficients["A"] == pytest.approx(5.4995e-1)
    assert surface.asphere_coefficients["F"] == pytest.approx(-1.7283)


def test_newmax_a4_order_is_not_shifted_by_zero_a2() -> None:
    # US-12596237-B2, Equation 2 (verbatim):
    # "z(h) = ch^2/{1+[1-(k+1)c^2h^2]^0.5} + Σ(A_i)·(h^i)"
    prescription = patent_to_zmx._parse_prescription_attempts(
        US_12596237_B2_EMBODIMENT_1, patent_id="US-12596237-B2"
    )[0].prescription
    assert prescription is not None
    first = prescription.surfaces[0].asphere_coefficients
    assert "A2" not in first
    assert first["A"] == pytest.approx(2.5005e-3)
    assert first["B"] == pytest.approx(-1.2047e-4)


def test_newmax_nonzero_a2_fails_loud_per_embodiment() -> None:
    malformed = US_12596237_B2_EMBODIMENT_1.replace("A2: 0.0000E+00", "A2: 1.0000E-06", 1)
    attempt = patent_to_zmx._parse_prescription_attempts(
        malformed, patent_id="US-12596237-B2"
    )[0]
    assert attempt.prescription is None
    assert isinstance(attempt.error, PatentParseError)
    assert "nonzero NEWMAX A2 term" in str(attempt.error)


def test_newmax_missing_inline_glass_indices_fails_closed() -> None:
    malformed = US_12596237_B2_EMBODIMENT_1.replace("plastic 1.643 22.5", "plastic — —", 1)
    attempt = patent_to_zmx._parse_prescription_attempts(
        malformed, patent_id="US-12596237-B2"
    )[0]
    assert attempt.prescription is None
    assert isinstance(attempt.error, PatentParseError)



def test_newmax_alphabetic_letters_beyond_f_are_ambiguous_and_fail_loud() -> None:
    # US-10101561-B2 Equation 1 skips the letter F and names the h^14 term G,
    # while its printed table uses positional A..F.  A table letter beyond F is
    # therefore ambiguous between the two lettering schemes (positional
    # G=h^16 vs equation G=h^14) and a nonzero value must not be mapped.
    with pytest.raises(PatentParseError, match="ambiguous NEWMAX alphabetic coefficient"):
        patent_to_zmx._newmax_codev_asphere_label("G", 1.0e-6, "3")


def test_newmax_alphabetic_letters_beyond_f_with_zero_value_are_skipped() -> None:
    assert patent_to_zmx._newmax_codev_asphere_label("G", 0.0, "3") is None
