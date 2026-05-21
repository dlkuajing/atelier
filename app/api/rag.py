"""RAG retrieval endpoints — pgvector + BGE-M3 + SigLIP-2.

Phase 0: placeholder.
Phase 2 wave 3: real retrieval (mock DB fallback when no DATABASE_URL).
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.lens_system import Scenario


router = APIRouter()


class LensPatentQuery(BaseModel):
    query: str = Field(..., min_length=2)
    scenario: Scenario
    top_k: int = Field(5, ge=1, le=20)


class LensPatentHit(BaseModel):
    id: str = Field(..., description="Patent number, e.g. US20200333565A1")
    title: str
    abstract: str
    assignee: str
    score: float = Field(..., description="Cosine similarity (0..1)")
    source: str
    source_url: str


class LensPatentResponse(BaseModel):
    query: str
    scenario: Scenario
    hits: list[LensPatentHit]
    backend: str = Field(..., description="'pgvector' if live DB, 'mock' if no DB configured")


@router.post(
    "/lens-patents",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=LensPatentResponse,
)
async def lens_patents(req: LensPatentQuery) -> LensPatentResponse:
    """Retrieve relevant lens design patents via vector search.

    Phase 2 wave 3: real implementation (with mock DB fallback).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2 wave 3: RAG retrieval pending (pgvector + BGE-M3 + SigLIP-2)",
    )
