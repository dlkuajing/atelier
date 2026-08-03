"""Gate: the seed quality limit may not be quoted without its denominator.

`app/core/corpus_quality.py` states the rule this project already agreed to --
"We report the number and name the denominator" -- but
`default_seed_quality_limit_um()` returned a bare float, so every downstream
count of the form "N of M seeds are at or below the limit" was uninterpretable
across corpus versions.

That is not hypothetical. Measured 2026-08-03 on the 187 staging files that pass
the promotion screens: adding them to the reference population moves the median
from **10.2312 to 11.4262 um (+11.7%)**. Both the limit and every count derived
from it would move together, in the same direction, with nothing in the artefact
saying so -- the "threshold defined as a corpus statistic" trap.

This does not decide *which* population is right. That is a live judge on the
main indicator's path and is left for ratification. What it enforces is that the
number never travels alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.corpus_quality import load_distribution
from scripts.p2_pair_census import default_seed_quality_limit_um, seed_quality_limit_basis

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTEFACTS = (
    REPO_ROOT / ".planning" / "evidence" / "upstream-supply-funnel-2026-08-02.json",
    REPO_ROOT / ".planning" / "evidence" / "staging-seed-supply-2026-08-02.json",
)


def test_the_basis_agrees_with_the_bare_limit() -> None:
    assert seed_quality_limit_basis()["limit_um"] == default_seed_quality_limit_um()


def test_the_basis_names_the_denominator() -> None:
    """A population, a criterion, a size and a census -- enough for a reader to
    tell whether two reported counts are comparable."""

    basis = seed_quality_limit_basis()
    for field in ("population", "criterion", "quantity", "n", "census_run", "census_sha256"):
        assert basis.get(field), f"{field} is missing from the limit basis"
    assert isinstance(basis["n"], int) and basis["n"] > 0


def test_the_basis_is_copied_from_the_artefact_not_restated() -> None:
    """A restated description drifts from the distribution it describes. These
    fields must be the artefact's own strings."""

    payload = load_distribution()
    basis = seed_quality_limit_basis()
    assert basis["population"] == payload["pool"]
    assert basis["criterion"] == payload["criterion"]
    assert basis["quantity"] == payload["quantity"]
    assert basis["n"] == payload["n"]
    assert basis["census_sha256"] == payload["provenance"]["census_sha256"]


@pytest.mark.parametrize("path", ARTEFACTS, ids=lambda p: p.name)
def test_every_artefact_that_uses_the_limit_records_its_basis(path: Path) -> None:
    """The artefacts are what a later reader actually holds. A limit recorded
    without its population is the same defect one layer out."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    inputs = payload["inputs"]
    assert inputs["seed_quality_limit_um"] == pytest.approx(inputs["seed_quality_limit_basis"]["limit_um"])
    assert inputs["seed_quality_limit_basis"]["n"] > 0
    assert inputs["seed_quality_limit_basis"]["census_sha256"]
