"""RAG retrieval endpoints — keyword mock for v1, pgvector + BGE-M3 for v2.

The relay station does not currently surface an embedding channel
(`/v1/embeddings` returns 503 for text-embedding-3-large, bge-m3, voyage-3),
so v1 ships a keyword-overlap MockLensPatentStore (see app/core/rag/store.py).
The endpoint contract is stable — when channels recover or owner provisions
a self-hosted embedder, the store gets swapped, no client changes needed.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.lens_system import Scenario
from app.core.rag import LensPatentHit, get_default_store

router = APIRouter()


class LensPatentQuery(BaseModel):
    query: str = Field(..., min_length=2)
    scenario: Scenario
    top_k: int = Field(5, ge=1, le=20)


class LensPatentResponse(BaseModel):
    query: str
    scenario: Scenario
    hits: list[LensPatentHit]
    backend: str = Field(
        ..., description="'pgvector' when DB is live, 'mock' otherwise"
    )


@router.post("/lens-patents", response_model=LensPatentResponse)
async def lens_patents(req: LensPatentQuery) -> LensPatentResponse:
    """Retrieve relevant lens design patents for the requested scenario.

    The active store is decided by `get_default_store()` — today the keyword
    mock, tomorrow pgvector + embeddings without changing this handler.
    """
    store = get_default_store()
    hits = store.search(query=req.query, scenario=req.scenario, top_k=req.top_k)
    return LensPatentResponse(
        query=req.query,
        scenario=req.scenario,
        hits=hits,
        backend=store.backend_name,
    )
