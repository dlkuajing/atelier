"""Gate: no two brands in the provenance data may be the same company.

`tests/test_p2_pair_census.py` already pins the spellings that were found by
hand -- Sunny three ways, AAC four ways, Ability with an em-dash, Samsung twice.
Each of those was found by somebody reading the data. This test finds the next
one by machine.

Why it matters is the same reason as there: `brand_of_case` deciding that two
publications of one company are cross-source **inflates 异源打平率** and the
inflation is invisible, because the pair looks like every other pair. Merging
two brands that turn out to be distinct only costs sample size. The error is
therefore not symmetric and this test is deliberately noisy in the safe
direction: anything that *looks* like a duplicate must be either merged or
listed here as reviewed.

Found by this test on the day it was written: `Corephontonics Ltd.` (an `n`
where an `o` belongs) sat in its own brand next to `COREPHOTONICS LTD.`. It was
not live -- Corephotonics designs are staging-only -- which is exactly why a
hand review had never caught it, and exactly why it would have gone live the
moment the staging pool was promoted.
"""

from __future__ import annotations

import difflib
import itertools

from scripts.p2_pair_census import (
    ASSIGNEE_TOKEN_SPELLING_FIXES,
    assignee_tokens,
    brand_of_assignee,
    load_provenance,
)

#: How alike two brand labels may look before a human has to say why they differ.
#: Set from the measured distribution: the confirmed duplicate pair scored 0.97
#: and the closest genuinely-distinct pair scored 0.82, so anything at or above
#: this needs a reason on the record.
SIMILARITY_LIMIT = 0.75

#: Brand pairs that look alike and are genuinely different companies. Each entry
#: is a claim someone is making; adding one is the way to silence this test, and
#: it is meant to be slightly uncomfortable.
REVIEWED_DISTINCT: frozenset[frozenset[str]] = frozenset(
    {
        # Two unrelated companies that merely share the word "Corporation" --
        # the stopword list keeps the shared token out of the grouping, but the
        # *label* similarity is high because the suffix dominates the string.
        frozenset({"ALTEK BIOTECHNOLOGY CORPORATION", "ZEBRA TECHNOLOGIES CORPORATION"}),
        frozenset({"Cognex Corporation", "Fujinon Corporation"}),
        frozenset({"Cognex Corporation", "WNC Corporation"}),
        frozenset({"Fujinon Corporation", "WNC Corporation"}),
        frozenset({"FUJIFILM Corporation", "Fujinon Corporation"}),
    }
)


def test_the_known_misspelling_folds_onto_its_canonical_token() -> None:
    assert assignee_tokens("Corephontonics Ltd.") == assignee_tokens("Corephotonics Ltd.")
    assert assignee_tokens("Fujinon Corporation") == assignee_tokens("FUJIFILM Corporation")


def test_a_fix_never_invents_a_token_that_was_not_there() -> None:
    """Each fix maps one misspelling onto a token that some *other* spelling in
    the data already produces. A fix pointing at a token nobody uses would be
    inventing a company rather than merging two records of one."""

    provenance = load_provenance()
    live = {token for assignee in provenance.brand_of for token in assignee_tokens(assignee)}
    for wrong, right in ASSIGNEE_TOKEN_SPELLING_FIXES.items():
        assert right != wrong
        assert right in live, f"{wrong!r} folds onto {right!r}, which no record produces"


def test_no_two_brands_look_like_the_same_company() -> None:
    provenance = load_provenance()
    brands = sorted(set(provenance.brand_of.values()))
    suspicious: list[tuple[float, str, str]] = []
    for left, right in itertools.combinations(brands, 2):
        if frozenset({left, right}) in REVIEWED_DISTINCT:
            continue
        ratio = difflib.SequenceMatcher(None, left.lower(), right.lower()).ratio()
        if ratio >= SIMILARITY_LIMIT:
            suspicious.append((ratio, left, right))
    suspicious.sort(reverse=True)
    assert not suspicious, (
        "brand labels that may be one company: "
        + "; ".join(f"{a!r} <-> {b!r} ({r:.2f})" for r, a, b in suspicious)
        + ". Either add a token spelling fix (if they are the same company) or "
        "list the pair in REVIEWED_DISTINCT with a reason."
    )


def test_the_grouping_still_merges_the_hand_found_spellings() -> None:
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
        brands = brand_of_assignee(set(group))
        assert len(set(brands.values())) == 1, group


def test_merging_only_ever_shrinks_the_cross_source_sample() -> None:
    """The direction argument, made executable: applying the fixes cannot
    increase the number of distinct brands."""

    provenance = load_provenance()
    assignees = set(provenance.brand_of)
    merged = len(set(brand_of_assignee(assignees).values()))

    unfixed = {a: frozenset(_raw_tokens(a)) for a in assignees}
    unmerged = len(set(_group_by(unfixed).values()))
    assert merged <= unmerged


def _raw_tokens(raw: str) -> set[str]:
    import re

    from scripts.p2_pair_census import ASSIGNEE_STOPWORDS

    cleaned = re.sub(r"[^0-9a-z]+", " ", raw.lower())
    return {t for t in cleaned.split() if t and t not in ASSIGNEE_STOPWORDS}


def _group_by(tokens: dict[str, frozenset[str]]) -> dict[str, str]:
    parent = {a: a for a in tokens}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_token: dict[str, list[str]] = {}
    for assignee, ts in tokens.items():
        for token in ts:
            by_token.setdefault(token, []).append(assignee)
    for members in by_token.values():
        head = find(members[0])
        for other in members[1:]:
            root = find(other)
            if root != head:
                parent[root] = head
    return {a: find(a) for a in tokens}
