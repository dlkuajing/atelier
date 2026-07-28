"""Gate: no ZMX asset silently enters the corpus carrying a broken prescription.

Why this is a separate axis from the traceability census. The census asks "can
CODE V push real rays through this seed", which the north star needs because a
seed that will not trace cannot produce 像质指标 and cannot serve as a P2
control. But that question is blind to whether the prescription is *the design
it claims to be* -- and blind in the dangerous direction: a surface stripped of
its aspheric terms degenerates to a smooth conic, which traces at least as
easily as the intact design. Measured on the 2026-07-28 per-field census,
fidelity-defective seeds trace no worse than clean ones (``data/zmx`` 47.3% vs
49.6% all-fields-positive; staging 41.2% vs 38.5%), so no amount of trace
health will ever surface this class.

Why it matters to the headline number rather than only to hygiene. The corpus
is the control group for 异源打平率: a candidate counts as 打平 when it is no
worse than the patent design it is compared against. A control that lost its
aspheric terms is a *worse* lens than the patent, so beating it is easier than
beating the real thing -- the defect biases the north star's main indicator
**upward**. That is the failure mode the project must never ship, so the gate
is fail-closed on new entries rather than advisory.

Source-verified instance behind ``aspheric_surface_without_terms``:
``US-12216248-B2`` embodiment 1. The retained source document
(``data/patent-lake/uspto-ppubs-html/...``) publishes ``A4 A6 A8 A10 A12 A14
A16 A18 A20`` for surfaces S1-S6; the parsed prescription in the conversion
request carries only ``K``, and the published seed is conic-only. The same
record also carries ``f_number = 0.239``, which is below the f/0.5 limit in air
and therefore self-evidently wrong without consulting the patent at all.

Two decoding traps this file also pins, both of which produced a wrong headline
count during the investigation before being caught:

* Native Zemax ZMX is UTF-16 with a BOM while pipeline-written ZMX is ASCII.
  Reading everything as UTF-8 makes all 17 hand-built real designs parse as if
  every record were missing -- which first read as "17 seeds have no aperture
  and no field" rather than as a decoding mistake.
* ``data/zmx`` holds 5 assets with an upper-case ``.ZMX`` suffix. A
  case-sensitive glob reports the pool as 437 when it is 442.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.corpus_fidelity_audit import (
    DEFAULT_POOLS,
    MIN_PHYSICAL_F_NUMBER,
    CorpusFidelityError,
    audit_corpus,
    audit_pool,
    audit_seed,
    read_zmx_text,
)

QUARANTINE_PATH = (
    Path(__file__).resolve().parents[1]
    / ".planning"
    / "evidence"
    / "corpus-fidelity-quarantine.json"
)


def _zmx(
    *,
    fnum: str = "2.0",
    ftyp: int = 0,
    yfln: str = "0 20.3",
    surfaces: str = "",
) -> str:
    return (
        "VERS 191028 13541 33913 33913\n"
        "MODE SEQ\n"
        "NAME SYNTHETIC\n"
        "UNIT MM X W X CM MR CPMM\n"
        f"FNUM {fnum} 0\n"
        f"FTYP {ftyp} 0 2 3 0 0 0 2\n"
        "XFLN 0 0\n"
        f"YFLN {yfln}\n"
        "WAVM 1 0.4861 1\n" + surfaces
    )


def _surface(stype: str, body: str = "") -> str:
    return f'SURF 1\n  TYPE {stype}\n  CURV 0.5 0 0 0 0 ""\n{body}  DISZ 0.5\n'


def _write(tmp_path: Path, text: str, name: str = "synthetic.zmx", encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    raw = text.encode(encoding)
    if encoding == "utf-16-le":
        raw = b"\xff\xfe" + raw  # codecs='utf-16-le' omits the BOM Zemax writes
    path.write_bytes(raw)
    return path


# --------------------------------------------------------------------------
# hard family: physically impossible values
# --------------------------------------------------------------------------


def test_f_number_below_the_physical_limit_is_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, _zmx(fnum="0.23888888888888887"))
    assert audit_seed(path, "t").hard == ("fno_below_physical_limit",)


def test_a_fast_but_possible_f_number_is_not_flagged(tmp_path: Path) -> None:
    path = _write(tmp_path, _zmx(fnum="1.4"))
    assert audit_seed(path, "t").hard == ()


def test_the_physical_limit_itself_is_accepted(tmp_path: Path) -> None:
    """f/0.5 is NA 1.0 exactly -- the boundary is reachable, not impossible."""
    path = _write(tmp_path, _zmx(fnum=str(MIN_PHYSICAL_F_NUMBER)))
    assert audit_seed(path, "t").hard == ()


@pytest.mark.parametrize("angle", ["90.0", "94.0", "120.0"])
def test_angular_field_at_or_beyond_90_degrees_is_flagged(tmp_path: Path, angle: str) -> None:
    path = _write(tmp_path, _zmx(ftyp=0, yfln=f"0 {angle}"))
    assert audit_seed(path, "t").hard == ("angular_field_at_or_beyond_90deg",)


def test_image_height_field_type_is_exempt_from_the_angle_rule(tmp_path: Path) -> None:
    """The 17 real designs use the real-image-height field type (``FTYP 3``;
    ``FTYP 2`` is the paraxial one), where YFLN is millimetres. A 3.4 mm field is
    ordinary; only angular fields have a 90 limit, so the exemption must key on
    FTYP rather than pass everything large."""
    path = _write(tmp_path, _zmx(ftyp=3, yfln="0 1.63 3.414"))
    assert audit_seed(path, "t").hard == ()


# --------------------------------------------------------------------------
# fidelity family: the file is not the design it claims to be
# --------------------------------------------------------------------------


def test_aspheric_surface_with_all_zero_parm_terms_is_flagged(tmp_path: Path) -> None:
    body = "".join(f"  PARM {i} 0\n" for i in range(1, 9))
    path = _write(tmp_path, _zmx(surfaces=_surface("EVENASPH", body)))
    audit = audit_seed(path, "t")
    assert audit.fidelity == ("aspheric_surface_without_terms",)
    assert audit.aspheric_surfaces_without_terms == 1


def test_aspheric_surface_with_a_real_term_is_not_flagged(tmp_path: Path) -> None:
    body = "  PARM 1 0.021411\n" + "".join(f"  PARM {i} 0\n" for i in range(2, 9))
    path = _write(tmp_path, _zmx(surfaces=_surface("EVENASPH", body)))
    assert audit_seed(path, "t").fidelity == ()


def test_xdat_control_slots_do_not_count_as_aspheric_terms(tmp_path: Path) -> None:
    """The high-order writer emits ``XDAT 1 10`` / ``XDAT 2 1`` / ``XDAT 3 0`` as
    control words before any coefficient. Counting those as terms would mark
    every stripped XASPHERE surface as intact -- a false all-clear."""
    body = '  XDAT 1 10 0 0 1 0 0 ""\n  XDAT 2 1 0 0 1 0 0 ""\n  XDAT 3 0 0 0 1 0 0 ""\n' + "".join(
        f'  XDAT {i} 0 0 0 1 0 0 ""\n' for i in range(4, 12)
    )
    path = _write(tmp_path, _zmx(surfaces=_surface("XASPHERE", body)))
    assert audit_seed(path, "t").fidelity == ("aspheric_surface_without_terms",)


def test_xdat_coefficient_slots_do_count_as_aspheric_terms(tmp_path: Path) -> None:
    body = (
        '  XDAT 1 10 0 0 1 0 0 ""\n'
        '  XDAT 2 1 0 0 1 0 0 ""\n'
        '  XDAT 3 0 0 0 1 0 0 ""\n'
        '  XDAT 4 -0.0048529 0 0 1 0 0 ""\n'
    )
    path = _write(tmp_path, _zmx(surfaces=_surface("XASPHERE", body)))
    assert audit_seed(path, "t").fidelity == ()


def test_a_spherical_surface_without_terms_is_not_an_asphere_defect(tmp_path: Path) -> None:
    path = _write(tmp_path, _zmx(surfaces=_surface("STANDARD")))
    audit = audit_seed(path, "t")
    assert audit.aspheric_surfaces == 0
    assert audit.fidelity == ()


# --------------------------------------------------------------------------
# decoding and enumeration traps
# --------------------------------------------------------------------------


def test_native_utf16_zmx_is_decoded_rather_than_read_as_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, _zmx(fnum="2.05"), name="native.zmx", encoding="utf-16-le")
    assert path.read_bytes()[:2] == b"\xff\xfe"
    assert "FNUM" in read_zmx_text(path)
    audit = audit_seed(path, "t")
    assert audit.f_number == pytest.approx(2.05)
    assert audit.hard == ()


def test_upper_case_zmx_suffix_is_part_of_the_pool(tmp_path: Path) -> None:
    _write(tmp_path, _zmx(), name="lower.zmx")
    _write(tmp_path, _zmx(), name="UPPER.ZMX")
    assert audit_pool("t", tmp_path).total == 2


def test_an_asset_without_any_aperture_record_raises_rather_than_passing(tmp_path: Path) -> None:
    text = _zmx().replace("FNUM 2.0 0\n", "")
    path = _write(tmp_path, text)
    with pytest.raises(CorpusFidelityError, match="aperture"):
        audit_seed(path, "t")


def test_an_asset_without_any_field_record_raises_rather_than_passing(tmp_path: Path) -> None:
    text = _zmx().replace("YFLN 0 20.3\n", "")
    path = _write(tmp_path, text)
    with pytest.raises(CorpusFidelityError, match="YFLN"):
        audit_seed(path, "t")


# --------------------------------------------------------------------------
# corpus gate
# --------------------------------------------------------------------------


def test_corpus_defects_stay_inside_the_recorded_quarantine() -> None:
    """Fail-closed on growth, permissive on repair.

    The baseline is keyed by ``(asset, reason)`` rather than by asset alone.
    Keying by asset was tried first and proved unsound: mutating an already
    listed seed to also violate the f/0.5 limit still passed, because its name
    was already on the list. An asset that is known bad for one reason must not
    become a free pass for every other reason.

    A repaired asset simply drops out of the audit and still satisfies the
    subset relation, so fixing defects never requires touching this test.
    """
    quarantine = json.loads(QUARANTINE_PATH.read_text(encoding="utf-8"))
    audits = {a.pool: a for a in audit_corpus()}
    assert set(audits) == set(quarantine["pools"])

    for pool, recorded in quarantine["pools"].items():
        audit = audits[pool]
        assert audit.total == recorded["total"], (
            f"{pool}: pool size changed ({audit.total} vs recorded {recorded['total']}); "
            "re-run scripts/corpus_fidelity_audit.py and review before updating the baseline"
        )
        allowed = {
            (name, reason) for name, reasons in recorded["defective"].items() for reason in reasons
        }
        observed = {
            (seed.name, reason)
            for seed in audit.defective()
            for reason in (*seed.hard, *seed.fidelity)
        }
        new = sorted(observed - allowed)
        assert not new, f"{pool}: {len(new)} new (asset, reason) defect(s): {new[:10]}"


def test_every_configured_pool_directory_exists() -> None:
    for pool, root in DEFAULT_POOLS:
        assert root.is_dir(), f"{pool}: {root} is missing"
