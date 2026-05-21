"""RAG retrieval endpoints — pgvector + BGE-M3 + SigLIP-2.

Phase 0: placeholder. Real implementation in Phase 2 after the patent crawler
populates the pgvector table (see scripts/patent_crawler.py).
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field


router = APIRouter()


class LensPatentQuery(BaseModel):
    query: str = Field(..., min_length=2)
    scenario: str = Field(..., description="e.g. 'smartphone-telephoto', 'ar-near-eye'")
    top_k: int = Field(5, ge=1, le=20)


@router.post("/lens-patents", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def lens_patents(req: LensPatentQuery) -> dict:
    """Retrieve relevant lens design patents via vector search.

    Phase 2 implementation.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: pgvector + BGE-M3 retrieval pending",
    )
