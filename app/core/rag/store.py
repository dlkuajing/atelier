"""Lens patent retrieval store — abstract interface + mock implementation.

The abstract `LensPatentStore` lets the Wizard's RAG step call `.search(...)`
without knowing whether the backend is pgvector+BGE-M3 or a keyword mock.
v1 ships `MockLensPatentStore`; a `PgVectorLensPatentStore` lands when the
relay's embedding channel comes back or owner provisions a self-hosted
embedding service (see PROJECT.md §IV).

The mock's scoring is intentionally simple: tokenize query + each patent's
title/abstract/claim, then Jaccard overlap. Scenario filter narrows the
corpus before scoring. Good enough for a demo where the Wizard names a
clear scenario and the corpus is curated.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from functools import lru_cache

from pydantic import BaseModel, Field

from app.core.lens_system import Scenario


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class LensPatentHit(BaseModel):
    id: str
    title: str
    abstract: str
    assignee: str
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance in [0, 1]")
    source: str
    source_url: str


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class LensPatentStore(ABC):
    """Search interface every backend (mock / pgvector / etc.) implements."""

    @abstractmethod
    def search(
        self, query: str, scenario: Scenario, top_k: int = 5
    ) -> list[LensPatentHit]:
        ...

    @property
    @abstractmethod
    def backend_name(self) -> str:
        ...


# ---------------------------------------------------------------------------
# Seed corpus (small but realistic — Largan/Sunny smartphone tele patents)
# ---------------------------------------------------------------------------


_SEED_PATENTS: list[dict] = [
    {
        "id": "US20200333565A1",
        "title": "Optical Imaging Lens Assembly",
        "abstract": (
            "An optical imaging lens assembly includes seven lens elements "
            "with refractive power, arranged from object to image side. Suited "
            "for smartphone telephoto modules with EFL around 7 mm and F/# 2.4. "
            "First lens positive, alternating powers."
        ),
        "claim_excerpt": (
            "An optical imaging lens assembly comprising seven lens elements "
            "with refractive power, the first lens element with positive refractive "
            "power having a convex object-side surface in the paraxial region."
        ),
        "assignee": "Largan Precision Co., Ltd.",
        "scenarios": [Scenario.SMARTPHONE_TELEPHOTO],
        "source_url": "https://patents.google.com/patent/US20200333565A1",
    },
    {
        "id": "US20210311293A1",
        "title": "Imaging Lens Assembly and Electronic Device",
        "abstract": (
            "An imaging lens assembly with six lens elements yields a compact "
            "telephoto module for smartphone integration. EFL around 12 mm, "
            "designed for periscope folded optical path."
        ),
        "claim_excerpt": (
            "An imaging lens assembly comprising six lens elements with the first "
            "element of positive refractive power and a folded periscope arrangement."
        ),
        "assignee": "Largan Precision Co., Ltd.",
        "scenarios": [Scenario.SMARTPHONE_TELEPHOTO],
        "source_url": "https://patents.google.com/patent/US20210311293A1",
    },
    {
        "id": "US20220197099A1",
        "title": "Optical Imaging System",
        "abstract": (
            "Optical imaging system for compact electronic devices, TTL under 5 mm, "
            "wide aperture F/1.7. Five lens elements suited for smartphone wide-angle "
            "main camera modules."
        ),
        "claim_excerpt": "An optical imaging system comprising five lens elements.",
        "assignee": "Sunny Optical Technology (Group) Co., Ltd.",
        "scenarios": [Scenario.SMARTPHONE_WIDE, Scenario.SMARTPHONE_ULTRAWIDE],
        "source_url": "https://patents.google.com/patent/US20220197099A1",
    },
    {
        "id": "US20230015432A1",
        "title": "Compact Wide-Angle Lens for Smartphone",
        "abstract": (
            "Compact wide-angle lens assembly for smartphone main camera, 24 mm "
            "equivalent EFL, F/1.8, six element design with aspheric surfaces and "
            "low f-tan(θ) distortion for full-frame sensor coverage."
        ),
        "claim_excerpt": "An optical lens assembly for wide-angle smartphone imaging.",
        "assignee": "Genius Electronic Optical (GSEO)",
        "scenarios": [Scenario.SMARTPHONE_WIDE],
        "source_url": "https://patents.google.com/patent/US20230015432A1",
    },
    {
        "id": "US20210284651A1",
        "title": "Near-Eye Display Optical System for Augmented Reality",
        "abstract": (
            "Optical waveguide-based near-eye display for augmented reality glasses, "
            "field of view 40 degrees diagonal, eyebox 12 mm, weight under 8 g per eye. "
            "Freeform substrate with MicroLED projector."
        ),
        "claim_excerpt": "A near-eye display system comprising a freeform optical waveguide.",
        "assignee": "Magic Leap / generic AR research",
        "scenarios": [Scenario.AR_NEAR_EYE],
        "source_url": "https://patents.google.com/patent/US20210284651A1",
    },
]


# ---------------------------------------------------------------------------
# Mock implementation: keyword overlap
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


# Stop words to remove from queries (don't help relevance signal).
_STOP = frozenset(
    {
        "a", "an", "the", "for", "with", "of", "to", "in", "on", "and", "or",
        "i", "we", "want", "need", "design", "make", "build", "lens", "lenses",
        "optical", "system", "assembly", "element", "elements",
    }
)


def _significant_tokens(text: str) -> set[str]:
    return {t for t in _tokens(text) if t not in _STOP and len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class MockLensPatentStore(LensPatentStore):
    """Keyword-overlap retrieval over a curated seed corpus.

    Two-step scoring:
    1. Filter corpus to patents whose `scenarios` list includes the requested
       scenario (cuts out obvious non-matches).
    2. Score remaining patents by Jaccard overlap between the query's
       significant tokens and each patent's title+abstract+claim tokens.
    """

    backend_name = "mock"  # type: ignore[assignment]

    def __init__(self, patents: list[dict] | None = None) -> None:
        self._patents = patents if patents is not None else _SEED_PATENTS
        # Pre-tokenize each patent for speed.
        self._patent_tokens: list[set[str]] = [
            _significant_tokens(
                f"{p['title']} {p['abstract']} {p['claim_excerpt']}"
            )
            for p in self._patents
        ]

    def search(
        self, query: str, scenario: Scenario, top_k: int = 5
    ) -> list[LensPatentHit]:
        if top_k <= 0:
            return []

        query_tokens = _significant_tokens(query)

        scored: list[tuple[float, dict]] = []
        for patent, ptoks in zip(self._patents, self._patent_tokens, strict=True):
            if scenario not in patent.get("scenarios", []):
                continue
            score = _jaccard(query_tokens, ptoks)
            scored.append((score, patent))

        # Stable sort by score desc.
        scored.sort(key=lambda x: x[0], reverse=True)

        hits: list[LensPatentHit] = []
        for score, p in scored[:top_k]:
            hits.append(
                LensPatentHit(
                    id=p["id"],
                    title=p["title"],
                    abstract=p["abstract"],
                    assignee=p["assignee"],
                    score=score,
                    source=self.backend_name,
                    source_url=p["source_url"],
                )
            )
        return hits


# ---------------------------------------------------------------------------
# Default store factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_default_store() -> LensPatentStore:
    """Return the currently-active store.

    Today: MockLensPatentStore. When pgvector + embeddings come online, this
    factory will inspect env (e.g. DATABASE_URL is set + embedding channel
    available) and return a PgVectorLensPatentStore instead — calling code
    needn't change.
    """
    return MockLensPatentStore()
