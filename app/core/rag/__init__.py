"""RAG (Retrieval-Augmented Generation) for the Lumira Atelier.

v1 ships with a **MockLensPatentStore** that scores queries by keyword overlap
against a small seeded patent corpus. This is intentional — the OpenAI-compatible
relay station does not currently surface an `/v1/embeddings` upstream channel,
and self-hosting BGE-M3 / SigLIP-2 would add ~2GB of model weights to the
container image. The mock interface is the *same* as the future real store, so
swapping to pgvector + relay embeddings (when channels recover) or self-hosted
BGE-M3 (Wave 3 stretch) is a one-class change.
"""

from app.core.rag.store import (
    LensPatentHit,
    LensPatentStore,
    MockLensPatentStore,
    get_default_store,
)


__all__ = [
    "LensPatentHit",
    "LensPatentStore",
    "MockLensPatentStore",
    "get_default_store",
]
