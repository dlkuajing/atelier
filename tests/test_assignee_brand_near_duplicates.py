"""Gate: no two brand **buckets** may contain a string that names one company.

`tests/test_p2_pair_census.py` already pins the spellings that were found by
hand -- Sunny three ways, AAC four ways, Ability with an em-dash, Samsung twice.
Each of those was found by somebody reading the data. This finds the next one by
machine.

Why it matters is the same reason as there: `brand_of_case` deciding that two
publications of one company are cross-source **inflates 异源打平率**, and the
inflation is invisible because the pair looks like every other pair. Merging two
buckets that turn out to be distinct costs sample size. The error is not
symmetric, so this test is deliberately noisy in the safe direction: anything
that *looks* like a duplicate must be merged or listed here with a reason.

Compares **members, not bucket labels**
---------------------------------------
The first version compared the representative label of each bucket, and the
representative is the lexicographically smallest member -- which need not be a
representative spelling. It scored `LARGAN DIGITAL CO., LTD.` against
`Largen Precision Co., Ltd.` at **0.7200** and passed, while the member pair
`Largan Precision Co., Ltd.` / `Largen Precision Co., Ltd.` scores **0.9615**.
Comparing every member pair found four real misses the label comparison could
not see, one of them against LARGAN -- the dominant control brand.

What this test still cannot see
--------------------------------
It is a **string** check. Two spellings of one company that share no substring
(an acronym against a full name, a Chinese-vs-English rendering, a subsidiary
under a different trade name) are invisible to it, and no threshold fixes that.
`raytech` was exactly that case and had to be entered in the fix table by hand
after reading the data. Treat a green result as "no *lexical* duplicate", never
as "provenance is correct".
"""

from __future__ import annotations

import collections
import difflib
import itertools

from scripts.p2_pair_census import (
    ASSIGNEE_TOKEN_SPELLING_FIXES,
    assignee_tokens,
    brand_of_assignee,
    load_provenance,
)

#: How alike two member strings may look before someone has to say why they are
#: different companies. Set from the measured distribution: after the fix table
#: the closest surviving pair is `Cognex Corporation` / `WNC Corporation` at
#: **0.7879**, and every real duplicate found so far scored **>= 0.8696**. The
#: gap between those is where this sits. It is *not* comfortable -- the nearest
#: reviewed-distinct pair (`ALTEK` / `ZEBRA`, 0.7541) is only 0.0041 above the
#: bar -- which is why the reviewed list carries reasons rather than being tuned
#: away by raising the number.
SIMILARITY_LIMIT = 0.75

#: **Brand pairs** -- not member pairs -- that look alike and are different
#: companies. Keyed on the bucket, because keying on the highest-scoring member
#: pair is brittle: the data holds `AAC TECHNOLOGIES PTE. LTD.` *and*
#: `AAC Technologies Pte. Ltd.`, so adding one spelling silently moves which pair
#: wins and re-opens an exemption that was already reviewed. The member pair is
#: evidence, not identity.
#:
#: Each entry is a claim someone is making; adding one is how this test goes
#: quiet, and it is meant to be slightly uncomfortable.
REVIEWED_DISTINCT_BRANDS: frozenset[frozenset[str]] = frozenset(
    {
        # Shared corporate suffix and nothing else. `Corporation` / `Technologies`
        # are stopwords for *token* grouping but still dominate *label* similarity.
        frozenset({"ALTEK BIOTECHNOLOGY CORPORATION", "ZEBRA TECHNOLOGIES CORPORATION"}),
        frozenset({"Cognex Corporation", "WNC Corporation"}),
        # `Fujinon Corporation` is its own bucket (see UNRESOLVED_SAME_COMPANY),
        # so both it and FUJIFILM collide with the other `... Corporation` labels.
        frozenset({"Cognex Corporation", "Fujinon Corporation"}),
        frozenset({"Fujinon Corporation", "WNC Corporation"}),
        frozenset({"AAC Acoustic Technologies (Shenzhen) Co., Ltd.", "HUAWEI TECHNOLOGIES CO., LTD."}),
        # Both render as `<Chinese province> <name> Optical Co., Ltd.`; OFILM and
        # Sunny are separate companies.
        frozenset(
            {
                "AAC Acoustic Technologies (Shenzhen) Co., Ltd.",
                "NINGBO SUNNY AUTOMOTIVE OPTECH CO., LTD.",
            }
        ),
    }
)

#: Brand pairs this repository **cannot settle**, kept apart from the reviewed
#: list so an open question is never filed as a decision.
#:
#: `FUJIFILM Corporation` (6 records) / `Fujinon Corporation` (1 record): Fujinon
#: was absorbed into FUJIFILM in 2010, which would make them one house -- but that
#: is outside knowledge and nothing in `data/patents` says so (`family_hint` is
#: null on both). An earlier draft merged them in
#: `ASSIGNEE_TOKEN_SPELLING_FIXES` on the strength of that recollection; it was
#: removed, because a code comment asserting a fact nobody here can check is the
#: same failure as a number with no provenance.
#:
#: Live impact today: **none** -- neither appears in any P2 pool. The moment
#: either does, this has to be settled from a source, not from memory.
UNRESOLVED_SAME_COMPANY: frozenset[frozenset[str]] = frozenset(
    {frozenset({"FUJIFILM Corporation", "Fujinon Corporation"})}
)


def _members_by_brand() -> dict[str, list[str]]:
    provenance = load_provenance()
    members: dict[str, list[str]] = collections.defaultdict(list)
    for assignee, brand in provenance.brand_of.items():
        members[brand].append(assignee)
    return members


def test_the_fix_table_folds_every_entry_onto_a_token_the_data_uses() -> None:
    """A fix pointing at a token nobody produces would be inventing a company
    rather than merging two records of one."""

    provenance = load_provenance()
    live: set[str] = set()
    for assignee in provenance.brand_of:
        live |= set(assignee_tokens(assignee))
    for wrong, right in ASSIGNEE_TOKEN_SPELLING_FIXES.items():
        assert right != wrong
        assert right in live, f"{wrong!r} folds onto {right!r}, which no record produces"


def test_the_known_misspellings_land_in_one_bucket() -> None:
    for wrong, right in (
        ("Corephontonics Ltd.", "Corephotonics Ltd."),
        ("Largen Precision Co., Ltd.", "Largan Precision Co., Ltd."),
        ("Jiangxi OFLM Optical Co., Ltd.", "Jiangxi OFILM Optical Co., Ltd."),
    ):
        assert assignee_tokens(wrong) == assignee_tokens(right), (wrong, right)


def test_the_raytech_spellings_stop_producing_empty_token_sets() -> None:
    """Every word in these two is a stopword, so before the fix they tokenised to
    `frozenset()`, each became its own brand, and both read as cross-source
    against AAC -- whose own corpus string is `Changzhou AAC Raytech Optronics`."""

    for name in ("Changzhou Raytech Optronics Co., Ltd.", "Raytech Optical (Changzhou) Co., Ltd."):
        tokens = assignee_tokens(name)
        assert tokens, f"{name!r} still tokenises to nothing"
        assert "aac" in tokens


def test_no_two_buckets_hold_a_string_that_names_one_company() -> None:
    members = _members_by_brand()
    suspicious: list[tuple[float, str, str]] = []
    for left, right in itertools.combinations(sorted(members), 2):
        best = 0.0
        pair = ("", "")
        for a in members[left]:
            for b in members[right]:
                ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
                if ratio > best:
                    best, pair = ratio, (a, b)
        known = REVIEWED_DISTINCT_BRANDS | UNRESOLVED_SAME_COMPANY
        if best >= SIMILARITY_LIMIT and frozenset({left, right}) not in known:
            suspicious.append((best, pair[0], pair[1]))
    suspicious.sort(reverse=True)
    assert not suspicious, (
        "member strings in different brand buckets that may name one company: "
        + "; ".join(f"{a!r} <-> {b!r} ({r:.4f})" for r, a, b in suspicious)
        + ". Either add a token spelling fix (same company) or list the *brand "
        "pair* in REVIEWED_DISTINCT_BRANDS with a reason."
    )


def test_comparing_labels_instead_of_members_would_have_missed_largan() -> None:
    """Pins why this test compares members. If the label comparison ever became
    sufficient this would fail and the simpler form could come back."""

    label_similarity = difflib.SequenceMatcher(
        None, "largan digital co., ltd.", "largen precision co., ltd."
    ).ratio()
    member_similarity = difflib.SequenceMatcher(
        None, "largan precision co., ltd.", "largen precision co., ltd."
    ).ratio()
    assert label_similarity < SIMILARITY_LIMIT <= member_similarity


def test_the_hand_found_spellings_still_merge() -> None:
    """The fixes must not disturb what already worked."""

    sunny = {
        "ZHEJIANG SUNNY OPTICS CO., LTD.",
        "ZHEJIANG SUNNY OPTICS CO., LTD",
        "Zhejiang Sunny Optical Co., Ltd",
    }
    ability = {
        "ABILITY OPTO-ELECTRONICS TECHNOLOGY CO., LTD.",
        "ABILITY OPTO—ELECTRONICS TECHNOLOGY CO., LTD.",
    }
    for group in (sunny, ability):
        assert len(set(brand_of_assignee(set(group)).values())) == 1, group


def test_every_listed_pair_is_still_a_pair_the_data_produces() -> None:
    """Dead entries hide regressions: a listed pair whose strings no longer
    exist silences nothing and makes the list look more considered than it is."""

    brands = set(_members_by_brand())
    for pair in REVIEWED_DISTINCT_BRANDS:
        missing = [name for name in pair if name not in brands]
        assert not missing, f"REVIEWED_DISTINCT_BRANDS names buckets that no longer exist: {missing}"
    members = {name for names in _members_by_brand().values() for name in names}
    for pair in UNRESOLVED_SAME_COMPANY:
        missing = [name for name in pair if name not in members]
        assert not missing, f"UNRESOLVED_SAME_COMPANY names strings the data no longer has: {missing}"


def test_the_unresolved_pair_is_not_filed_as_a_decision() -> None:
    """An open question must stay visibly open."""

    assert UNRESOLVED_SAME_COMPANY
    assert not (REVIEWED_DISTINCT_BRANDS & UNRESOLVED_SAME_COMPANY)
