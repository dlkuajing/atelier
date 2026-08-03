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
import re

from scripts.p2_pair_census import (
    ASSIGNEE_STOPWORDS,
    ASSIGNEE_TOKEN_SPELLING_FIXES,
    assignee_tokens,
    brand_of_assignee,
    load_provenance,
)

#: How alike two member strings may look before someone has to say why they are
#: different companies.
#:
#: WARNING: an earlier version of this comment claimed a clean calibration gap of
#: [0.7879, 0.8696]. That was wrong. A full 780-pair member sweep puts
#: `FUJIFILM Corporation` / `Fujinon Corporation` at **0.8205** -- inside the band
#: the comment called empty -- and that pair is deliberately unmerged (see
#: `UNRESOLVED_SAME_COMPANY`). The honest picture:
#:
#: * real duplicates found so far: **0.8696 - 0.9836**
#: * the deliberately-unresolved pair: **0.8205**
#: * nearest reviewed-distinct pair: **0.7541** (`ALTEK` / `ZEBRA`)
#:
#: So the bar has **0.0041** of clearance below it and no empty band above it.
#: That discomfort is the point: the way to quiet this test is to add a reason to
#: the reviewed list, not to raise the number.
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
#: ⚠️ This constant silences **this test only**. It does not change bucketing:
#: `census()` still treats the two as cross-source, and nothing fires when one
#: of them enters a pool. Live impact today is none -- neither appears in any
#: P2 pool -- but that is a fact about today's data, not a guarantee anyone
#: enforces. Settling it needs a source, and settling it is a separate shovel.
UNRESOLVED_SAME_COMPANY: frozenset[frozenset[str]] = frozenset(
    {frozenset({"FUJIFILM Corporation", "Fujinon Corporation"})}
)


def _members_by_brand() -> dict[str, list[str]]:
    provenance = load_provenance()
    members: dict[str, list[str]] = collections.defaultdict(list)
    for assignee, brand in provenance.brand_of.items():
        members[brand].append(assignee)
    return members


def _tokens_without_the_fix_table(raw: str) -> set[str]:
    """`assignee_tokens` applies the fix table, so building the reference set with
    it makes every fix target live *by construction*. Same function, minus that."""

    cleaned = re.sub(r"[^0-9a-z]+", " ", raw.lower())
    return {token for token in cleaned.split() if token and token not in ASSIGNEE_STOPWORDS}


def test_the_fix_table_folds_every_entry_onto_a_token_the_data_uses() -> None:
    """A fix pointing at a token nobody produces would be inventing a company
    rather than merging two records of one.

    WARNING: the first version built the reference set with `assignee_tokens`,
    which **applies the fix table** -- so every target was live by construction
    and the test could not detect the failure it names. Raw tokenisation now.
    """

    provenance = load_provenance()
    live: set[str] = set()
    for assignee in provenance.brand_of:
        live |= _tokens_without_the_fix_table(assignee)
    for wrong, right in ASSIGNEE_TOKEN_SPELLING_FIXES.items():
        assert right != wrong
        assert right in live, f"{wrong!r} folds onto {right!r}, which no record produces"
        assert wrong in live, f"{wrong!r} is not a spelling this corpus contains"


def test_the_known_misspellings_land_in_one_bucket() -> None:
    for wrong, right in (
        ("Corephontonics Ltd.", "Corephotonics Ltd."),
        ("Largen Precision Co., Ltd.", "Largan Precision Co., Ltd."),
        ("Jiangxi OFLM Optical Co., Ltd.", "Jiangxi OFILM Optical Co., Ltd."),
    ):
        assert assignee_tokens(wrong) == assignee_tokens(right), (wrong, right)


def test_the_raytech_spellings_bucket_together_without_an_asserted_attribution() -> None:
    """`raytech` sat in the stopword list, so every word in these two was stopped
    and they tokenised to nothing -- each its own brand, both reading as
    cross-source against AAC and against each other.

    The fix is to take `raytech` **out of the stopword list** (it is a company
    name, not an industry word), not to map it onto `aac`. The merge then follows
    from the corpus's own `Changzhou AAC Raytech Optronics Co., Ltd.` carrying
    both tokens -- evidence, not an attribution someone asserted. Both routes give
    bit-identical buckets (40, zero members differ), so this asserts the
    *property* and does not pin the cleaner route shut.
    """

    names = [
        "Changzhou Raytech Optronics Co., Ltd.",
        "Raytech Optical (Changzhou) Co., Ltd.",
        "Changzhou AAC Raytech Optronics Co., Ltd.",
    ]
    for name in names:
        assert assignee_tokens(name), f"{name!r} still tokenises to nothing"
    assert len(set(brand_of_assignee(set(names)).values())) == 1


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


def test_merging_only_ever_shrinks_the_bucket_count() -> None:
    """The direction argument the whole fix table rests on, made executable: a
    spelling fix coarsens the token partition, and union-find over a coarser
    partition can only merge. A previous commit deleted this while widening the
    table from 2 entries to 4 -- exactly when it was most worth keeping."""

    import scripts.p2_pair_census as census_mod

    assignees = set(load_provenance().brand_of)
    merged = len(set(brand_of_assignee(assignees).values()))
    original = census_mod.ASSIGNEE_TOKEN_SPELLING_FIXES
    census_mod.ASSIGNEE_TOKEN_SPELLING_FIXES = {}
    try:
        unmerged = len(set(brand_of_assignee(assignees).values()))
    finally:
        census_mod.ASSIGNEE_TOKEN_SPELLING_FIXES = original
    assert merged <= unmerged, (merged, unmerged)


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
