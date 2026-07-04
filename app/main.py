"""FastAPI app entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Apply Optiland 0.6 runtime patches FIRST — before any other Optiland import
# happens. See app/core/optiland_patches.py for the bug each one addresses.
from app.core import optiland_patches as _optiland_patches  # noqa: I001

_optiland_patches.apply_all()

from app.api import optical, rag, wizard  # noqa: E402
from app.core.config import settings  # noqa: E402


logger = structlog.get_logger(__name__)
WEB_ROOT = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=WEB_ROOT / "templates")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("lumira_backend_starting", env=settings.env, version="0.1.0")
    yield
    logger.info("lumira_backend_stopping")


app = FastAPI(
    title="Lumira Atelier Backend",
    description=(
        "Optical Co-Pilot — deterministic optics (Optiland/prysm/rayoptics) + "
        "RAG (pgvector + BGE-M3 + SigLIP-2) + LLM orchestration (Opus 4.7 / GPT-5.5 / Gemini 3.1 Pro via LiteLLM)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")

app.include_router(optical.router, prefix="/api/optical", tags=["optical"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
app.include_router(wizard.router, prefix="/api/wizard", tags=["wizard"])


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.get("/", response_class=HTMLResponse, tags=["web"])
async def root(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "product_name": "Atelier",
            "nav_items": (
                ("Workbench", "#request"),
                ("Library", "#library"),
                ("Analysis", "#analysis"),
                ("API", "/docs"),
            ),
        },
    )
