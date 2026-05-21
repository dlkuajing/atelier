"""Wizard intake endpoints — LLM-backed natural-language scenario extraction.

Phase 1 Step 1 free-text mode. The user types something like
"我想要 5x 变焦的手机长焦" or "design a fast 50mm full-frame prime"; we
hand it to claude-opus-4-7 via the relay station with a tight JSON-only
schema, then clamp the proposed numerics to scenario bounds. The final
output drops cleanly into the Wizard's `PICK_SCENARIO` + `SET_SPECS` actions.

The LLM is never trusted with numerics — `parameter_guards.SCENARIO_BOUNDS`
clamps every field. If the LLM proposes EFL=0.5mm for a phone tele, we
quietly raise it to 5mm and continue.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.lens_system import Scenario
from app.core.llm_relay import get_async_client, model_for_role
from app.core.parameter_guards import SCENARIO_BOUNDS


router = APIRouter()


SYSTEM_PROMPT = """You are the intake step of an optical-design wizard.

The user describes (in any language — English, 中文, etc.) what optical
system they want to design. Your job:

1. Classify their use case into EXACTLY ONE of these six scenarios:
   - smartphone-telephoto: phone tele or zoom camera, EFL 5-18 mm
   - smartphone-wide: phone main camera (the "wide" or default), EFL 3-8 mm
   - smartphone-ultrawide: phone ultrawide auxiliary, EFL 1.5-4 mm, FOV 100-130°
   - ar-near-eye: AR/VR headset optics, EFL 12-30 mm
   - dslr-prime: full-frame DSLR / mirrorless prime, EFL 24-300 mm
   - microscope-objective: high-NA microscope objective

2. If the user mentioned numbers (focal length, f-number, field of view,
   image height, lens element count), extract them. Otherwise leave them null
   and we'll fill in sensible defaults from the scenario.

3. Reply ONLY with valid JSON in this exact shape — no markdown fences,
   no surrounding prose:

{
  "scenario": "<one of the six ids exactly>",
  "focal_length_mm": <number or null>,
  "f_number": <number or null>,
  "field_of_view_deg": <number or null>,
  "image_height_mm": <number or null>,
  "n_elements": <integer or null>,
  "reasoning": "<one short sentence in the user's language>"
}

Bounds you MUST respect — never propose numbers outside these:
- smartphone-telephoto:    EFL [5, 18] mm,   f/[1.8, 4.0],  FOV [15, 45]°,   img height [2.5, 8] mm
- smartphone-wide:         EFL [3, 8] mm,    f/[1.4, 2.8],  FOV [60, 90]°,   img height [3.5, 10] mm
- smartphone-ultrawide:    EFL [1.5, 4] mm,  f/[1.8, 3.5],  FOV [100, 130]°, img height [3, 8] mm
- ar-near-eye:             EFL [12, 30] mm,  f/[1.2, 2.5],  FOV [25, 60]°,   img height [4, 15] mm
- dslr-prime:              EFL [24, 300] mm, f/[1.2, 5.6],  FOV [6, 85]°,    img height [21, 22] mm
- microscope-objective:    EFL [2, 50] mm,   f/[0.5, 4.0],  FOV [0.5, 15]°,  img height [1, 15] mm
"""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class ExtractScenarioRequest(BaseModel):
    user_input: str = Field(..., min_length=3, max_length=2000)


class ExtractScenarioResponse(BaseModel):
    scenario: Scenario
    focal_length_mm: float | None = None
    f_number: float | None = None
    field_of_view_deg: float | None = None
    image_height_mm: float | None = None
    n_elements: int | None = None
    reasoning: str | None = None


# ---------------------------------------------------------------------------
# Parser (exposed for unit testing — endpoint is a thin wrapper)
# ---------------------------------------------------------------------------


def _strip_markdown_fences(raw: str) -> str:
    """Sometimes Claude wraps JSON in ```json ... ``` fences despite the system
    prompt asking it not to. Strip them defensively."""
    text = raw.strip()
    if not text.startswith("```"):
        return text
    # Drop opening fence (with optional language hint)
    first_newline = text.find("\n")
    if first_newline == -1:
        return text
    inside = text[first_newline + 1 :]
    # Drop closing fence
    if inside.endswith("```"):
        inside = inside[: -len("```")]
    return inside.strip()


def _clamp(v: float | None, lo: float, hi: float) -> float | None:
    if v is None:
        return None
    return max(lo, min(hi, float(v)))


def parse_llm_scenario_response(raw_text: str) -> ExtractScenarioResponse:
    """Parse the LLM's JSON output and clamp every numeric field to the
    scenario's allowed range. Raises ValueError on unparseable JSON or
    unknown scenario id."""
    cleaned = _strip_markdown_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM output is not valid JSON: {e}\n--- raw ---\n{raw_text[:500]}") from e

    if not isinstance(data, dict):
        raise ValueError(f"LLM output is not a JSON object: got {type(data).__name__}")

    raw_scenario = data.get("scenario")
    if not isinstance(raw_scenario, str):
        raise ValueError(f"LLM response missing 'scenario' (got {raw_scenario!r})")

    try:
        scenario = Scenario(raw_scenario)
    except ValueError as e:
        raise ValueError(
            f"LLM proposed unknown scenario {raw_scenario!r}; expected one of "
            f"{[s.value for s in Scenario]}"
        ) from e

    bounds = SCENARIO_BOUNDS[scenario]

    n_el_raw = data.get("n_elements")
    n_elements: int | None
    if n_el_raw is None:
        n_elements = None
    else:
        try:
            n_elements = int(n_el_raw)
            n_elements = max(bounds.n_elements_min, min(bounds.n_elements_max, n_elements))
        except (TypeError, ValueError):
            n_elements = None

    return ExtractScenarioResponse(
        scenario=scenario,
        focal_length_mm=_clamp(
            data.get("focal_length_mm"), bounds.efl_mm_min, bounds.efl_mm_max
        ),
        f_number=_clamp(
            data.get("f_number"), bounds.f_number_min, bounds.f_number_max
        ),
        field_of_view_deg=_clamp(
            data.get("field_of_view_deg"), bounds.fov_deg_min, bounds.fov_deg_max
        ),
        image_height_mm=_clamp(
            data.get("image_height_mm"),
            bounds.image_height_mm_min,
            bounds.image_height_mm_max,
        ),
        n_elements=n_elements,
        reasoning=data.get("reasoning") if isinstance(data.get("reasoning"), str) else None,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/extract-scenario", response_model=ExtractScenarioResponse)
async def extract_scenario(req: ExtractScenarioRequest) -> ExtractScenarioResponse:
    """Run a single LLM extraction over the user's free-text description.

    Returns scenario + clamped suggested numerics. The Wizard then dispatches
    PICK_SCENARIO + SET_SPECS with these values.
    """
    client = get_async_client()
    model = model_for_role("wizard.main")

    try:
        completion = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": req.user_input},
            ],
            max_tokens=500,
            temperature=0.2,  # low — extraction should be deterministic
        )
    except Exception as e:  # network / relay channel error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "llm_relay_failure",
                "message": str(e)[:300],
                "model": model,
            },
        ) from e

    raw = completion.choices[0].message.content or ""

    try:
        return parse_llm_scenario_response(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "llm_response_unparseable",
                "message": str(e)[:500],
            },
        ) from e
