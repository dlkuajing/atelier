"""LLM Relay — single OpenAI-compatible client for ALL LLM / image calls.

Lumira routes everything through one OpenAI-compatible relay (configured via
`OPENAI_BASE_URL` + `OPENAI_API_KEY`). This module is the single source of
truth — do NOT instantiate `openai.OpenAI` clients elsewhere.

Why one relay (replaces v1.1's LiteLLM HK VPS plan):
- Owner-provided relay is pre-deployed; no VPS to babysit
- Single credential, single billing, single fallback ladder
- Removes ~80% of OWNER-CHECKLIST credentials work

Trade-off: relay vendor availability matters; see `KNOWN_UNAVAILABLE` for
models the relay returned 503 on as of 2026-05-21. When Claude channels
recover, just change `PRIMARY_CHAT` below.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from openai import AsyncOpenAI, OpenAI

from app.core.config import settings

# Model IDs — verified against relay at https://api.openbili.com/v1 on 2026-05-21
# (see ~/.claude/projects/-Users-c-joelin-Desktop-----/memory/reference_lumira_credentials.md)

PRIMARY_CHAT: Final = "claude-opus-4-7"
"""Wizard dialogue main control + multi-step tool use + parameter JSON.
Original v1.1 pick. Relay channel briefly unavailable on 2026-05-21 morning;
recovered same day."""

PRIMARY_LONG_CONTEXT: Final = "gemini-3.1-pro-preview"
"""Long-form report generation + multimodal image (e.g. optical layout)
understanding. 2M context, GPQA 94.3%."""

FALLBACK_CHAT: Final = "claude-sonnet-4-6"
"""Used when PRIMARY_CHAT is rate-limited or unresponsive. Same prompt style
as Opus 4.7, faster TTFT, ~1/3 cost. GPT-5.5 / gemini-3.5-flash are deeper
fallbacks if the whole Anthropic channel goes down again."""

PRIMARY_IMAGE: Final = "gpt-image-2"
"""Report cover, brand image, info-graphic. LMArena Elo +242 over Nano Banana
on the date the v1.1 fuel mix was chosen."""

ALTERNATE_IMAGE_4K: Final = "gemini-3-pro-image-preview-4k"
"""Higher-res alternative; response shape needs more validation before
shipping (chat endpoint returns content=None on simple prompts, may use
attachments)."""


# Models the relay returns HTTP 503 "No available channels" for. Keep this
# list updated; the Wizard fall-back ladder consults it. As of 2026-05-21
# afternoon all Anthropic channels were restored (verified curl 200 OK).
KNOWN_UNAVAILABLE: Final[frozenset[str]] = frozenset()


# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------


def _require_credentials() -> None:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. See OWNER-CHECKLIST.md or "
            "reference_lumira_credentials.md."
        )


@lru_cache(maxsize=1)
def get_sync_client() -> OpenAI:
    """Synchronous OpenAI client pointing at the relay.

    Use for image generation and short utility calls; prefer the async client
    inside route handlers so the Wizard's concurrent requests don't block.
    """
    _require_credentials()
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


@lru_cache(maxsize=1)
def get_async_client() -> AsyncOpenAI:
    """Asynchronous OpenAI client pointing at the relay."""
    _require_credentials()
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


# ---------------------------------------------------------------------------
# Role → model mapping (single source of truth, used by Wizard route handler)
# ---------------------------------------------------------------------------


_ROLE_MODEL: Final[dict[str, str]] = {
    "wizard.main": PRIMARY_CHAT,
    "wizard.params": PRIMARY_CHAT,
    "report.long": PRIMARY_LONG_CONTEXT,
    "report.multimodal": PRIMARY_LONG_CONTEXT,
    "image.cover": PRIMARY_IMAGE,
    "fallback.chat": FALLBACK_CHAT,
}


def model_for_role(role: str) -> str:
    """Look up which relay model to use for a logical role.

    Valid roles: wizard.main, wizard.params, report.long, report.multimodal,
    image.cover, fallback.chat
    """
    try:
        return _ROLE_MODEL[role]
    except KeyError as e:
        raise ValueError(
            f"Unknown role {role!r}. Valid roles: {sorted(_ROLE_MODEL)}"
        ) from e


def is_available(model_id: str) -> bool:
    """Quick check whether a model is known-available on the relay.

    Returns False for models in the empirically-blocked list. Note: relay
    state changes; for live confirmation use a real probe request.
    """
    return model_id not in KNOWN_UNAVAILABLE
