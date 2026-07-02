"""Unit tests for the E2-01 full-embodiment cross-validation gate.

The gate (scripts/e2_intake.cross_validate_embodiments) is the standard patent
cross-check for batch 2+. These tests lock the behaviors that burned us in
batch 1: comparing embodiment 1 only (false negatives), and a perfect 0.0 diff
being demoted by the ``x or default`` falsy trap.
"""

from __future__ import annotations

from scripts.e2_intake import cross_validate_embodiments


def _emb(n, f, hfov, nel, ttl=None, notes=""):
    return {
        "embodiment": n,
        "f_mm": f,
        "hfov_deg": hfov,
        "n_elements": nel,
        "ttl_mm": ttl,
        "notes": notes,
    }


def test_gate_scans_all_embodiments_not_just_the_first():
    # The design matches embodiment 3 exactly; embodiment 1 is a completely
    # different focal/FOV. An embodiment-1-only check would false-negative this.
    computed = {"efl": 3.62, "fov": 91.0, "nel": 7, "ttl": 5.4, "imgh": 3.68}
    embodiments = [
        _emb(1, 4.28, 39.8, 7),  # 79.6 deg -- Table 1, the old trap
        _emb(2, 4.38, 38.9, 7),
        _emb(3, 3.62, 45.5, 7),  # 91.0 deg -- the real match
    ]
    result = cross_validate_embodiments(computed, embodiments)
    assert result["verdict"] == "PASS"
    assert result["matched_embodiment"] == 3
    assert result["fov_diff_deg"] == 0.0
    assert result["efl_diff_pct"] == 0.0


def test_gate_perfect_match_is_not_demoted_by_zero_diff():
    # A 0.0 EFL/FOV diff must rank as the best match, not be treated as missing.
    computed = {"efl": 3.0, "fov": 90.0, "nel": 6, "ttl": 4.4, "imgh": 3.0}
    embodiments = [
        _emb(1, 3.05, 46.0, 6),  # 92.0 deg, small nonzero diffs
        _emb(2, 3.00, 45.0, 6),  # 90.0 deg, exact
    ]
    result = cross_validate_embodiments(computed, embodiments)
    assert result["verdict"] == "PASS"
    assert result["matched_embodiment"] == 2


def test_gate_fails_when_fov_off_every_embodiment():
    computed = {"efl": 3.0, "fov": 70.0, "nel": 6, "ttl": 4.4, "imgh": 2.5}
    embodiments = [_emb(1, 3.0, 45.0, 6), _emb(2, 3.0, 46.0, 6)]  # 90 / 92 deg
    result = cross_validate_embodiments(computed, embodiments)
    assert result["verdict"] == "FAIL"


def test_gate_fails_on_element_count_mismatch():
    computed = {"efl": 3.0, "fov": 90.0, "nel": 5, "ttl": 4.4, "imgh": 3.0}
    embodiments = [_emb(1, 3.0, 45.0, 6)]  # every embodiment is 6P
    result = cross_validate_embodiments(computed, embodiments)
    assert result["verdict"] == "FAIL"
    assert result["nel_match"] is False


def test_gate_ttl_only_miss_is_a_caveat_not_a_fail():
    # Core (EFL/FOV/element) matches, but the absolute TTL is >10% off.
    computed = {"efl": 3.0, "fov": 90.0, "nel": 6, "ttl": 6.0, "imgh": 3.0}
    embodiments = [_emb(1, 3.0, 45.0, 6, ttl=4.4)]
    result = cross_validate_embodiments(computed, embodiments)
    assert result["verdict"] == "CAVEAT_TTL"
    assert result["core_ok"] is True
    assert result["ttl_ok"] is False


def test_gate_compares_ttl_by_ratio_when_only_ratio_is_declared():
    # No absolute TTL; the note states TL/ImgH, so the gate uses ratio x imgh.
    computed = {"efl": 3.0, "fov": 90.0, "nel": 6, "ttl": 4.5, "imgh": 3.0}
    embodiments = [_emb(1, 3.0, 45.0, 6, notes="TL/ImgH = 1.5")]  # -> 4.5 mm
    result = cross_validate_embodiments(computed, embodiments)
    assert result["verdict"] == "PASS"
    assert result["ttl_diff_pct"] == 0.0
