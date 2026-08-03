"""The 10 backfilled assignees must not become a fail-open cross-source leak.

These patents carried a valid patent number but no assignee record anywhere in
`data/patents`, so `brand_of_case` returned None and they were dropped from BOTH the
control and the seed role. Measured effect of the backfill (my own recomputation of the
pairing): independent samples 27 -> 37, trials 49 -> 59, seed designs 5 -> 6.

The danger is the opposite of the one that motivated the work. If a backfilled assignee
string fails to bucket with the corpus's existing spelling for the same company, those
patents count as cross-source *with that company* -- which manufactures par pairs out of
a spelling difference. That is the property these tests exist to pin.

Why nothing here skips any more
-------------------------------
It used to. Commit f0e5b3c7 landed this file but not the data it reads: `.gitignore`
carried a blanket `/data/patents/*` with a negation only for `uspto-smartphone-batch*`,
so `git add` silently dropped the backfill. Every test then took its own
`skipif(not BACKFILL.is_file())` and the suite went green while `brand_of_case` returned
None for all ten patents -- main produced 49 trials while
`.planning/evidence/north-star-scoreboard-2026-07-30.md` reported the 59 this backfill
was supposed to unlock. A test that disarms itself when its subject is missing cannot
report the one failure that matters, so the file's presence is now an assertion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

BACKFILL = Path("data/patents/uspto-legacy-assignee-backfill.jsonl")

#: Every field here was read off the patent page. Nothing else is written -- an invented
#: abstract or IPC class would defeat the point of a provenance backfill.
_ALLOWED_FIELDS = {
    "id",
    "title",
    "assignee",
    "inventors",
    "filing_date",
    "source",
    "source_url",
}

_BACKFILLED = [
    "US20140118844A1",
    "US20170045714A1",
    "US20210165194A1",
    "US8908290B1",
    "US9063319B1",
    "US9195030B2",
    "US9239447B1",
    "US9316811B2",
    "US9557532B2",
    "US9651759B2",
]


def test_the_backfill_data_is_actually_committed() -> None:
    """The failure this whole file previously could not report."""

    assert BACKFILL.is_file(), (
        f"{BACKFILL} is missing. It is provenance evidence, not crawl output: without "
        "it `brand_of_case` returns None for ten patents and they drop out of BOTH the "
        "control and the seed role. If .gitignore swallowed it again, re-add the "
        "negation rather than restoring the skips."
    )


def _records() -> list[dict]:
    return [
        json.loads(line)
        for line in BACKFILL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_every_backfilled_patent_is_present_exactly_once() -> None:
    from scripts.p2_pair_census import normalise_patent_id

    ids = [normalise_patent_id(str(r["id"])) for r in _records()]
    assert len(ids) == len(set(ids)) == len(_BACKFILLED)
    assert set(ids) == {normalise_patent_id(p) for p in _BACKFILLED}


def test_no_field_was_invented() -> None:
    for record in _records():
        assert set(record) <= _ALLOWED_FIELDS, f"unexpected field in {record['id']}"
        assert record["assignee"].strip()
        # Provenance is the deliverable: an assignee with no source is unusable.
        assert record["source_url"].startswith("https://patents.google.com/patent/")
        assert record["source"].startswith("google-patents-manual-backfill")


def test_every_backfilled_patent_resolves_to_a_brand() -> None:
    """None means excluded, so an unresolved record leaves the sample where it was."""

    from scripts.p2_pair_census import load_provenance, normalise_patent_id

    provenance = load_provenance()
    for patent in _BACKFILLED:
        key = normalise_patent_id(patent)
        assignee = provenance.assignee_of_patent.get(key)
        assert assignee, f"{patent} has no assignee after backfill"
        assert provenance.brand_of.get(assignee), f"{patent} assignee has no brand"


def test_backfilled_assignees_bucket_WITH_the_corpus_spelling_not_beside_it() -> None:
    """THE fail-open guard.

    `Largan Precision Co Ltd` (as printed by the source) must land in the same brand as
    the corpus's `LARGAN PRECISION CO., LTD.` / `LARGAN DIGITAL CO., LTD.` / etc. If it
    did not, nine of these ten would read as cross-source against Largan and every par
    they produced would be an artefact of punctuation.
    """

    from scripts.p2_pair_census import load_provenance

    provenance = load_provenance()
    brands_by_company: dict[str, set[str]] = {}
    for assignee, brand in provenance.brand_of.items():
        upper = assignee.upper()
        for company in ("LARGAN", "APPLE"):
            if company in upper:
                brands_by_company.setdefault(company, set()).add(brand)

    for company, brands in brands_by_company.items():
        assert len(brands) == 1, f"{company} is split across brands {brands}"

    backfilled = {r["assignee"] for r in _records()}
    assert "Largan Precision Co Ltd" in backfilled
    assert provenance.brand_of["Largan Precision Co Ltd"] in brands_by_company["LARGAN"]
    assert provenance.brand_of["Apple Inc"] in brands_by_company["APPLE"]


def test_the_backfill_does_not_pair_a_control_with_a_seed_of_the_same_design() -> None:
    """A backfilled assignee could in principle open a pair between two publications of
    one design. Measured: it does not -- but this must stay measured, not assumed."""

    from app.core.engines.prescription_identity import fingerprint_zmx
    from scripts.p2_pair_census import CASE_INDEX, census

    index = {r["case_id"]: r for r in json.loads(CASE_INDEX.read_text(encoding="utf-8"))}
    census_path = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl")
    if not census_path.is_file():
        pytest.skip("runtime census not present on this machine")

    zmx_dir = Path("data") / "zmx"

    def fingerprint(case_id: str) -> str | None:
        return fingerprint_zmx(zmx_dir / index[case_id]["source_zmx"])

    pairs = census(census_path)["trial_pairs"]
    same = [p for p in pairs if fingerprint(p["control"]) == fingerprint(p["seed"])]
    assert not same, f"same-design pairs appeared: {same}"
