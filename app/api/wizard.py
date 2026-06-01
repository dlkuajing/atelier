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
from app.core.llm_relay import PRIMARY_IMAGE, get_async_client, model_for_role
from app.core.mtf_fields import format_mtf_field_fraction
from app.core.optical_sample import DesignAssessment
from app.core.parameter_guards import SCENARIO_BOUNDS

router = APIRouter()


SYSTEM_PROMPT = """You are the intake step of an optical-design wizard.

The user describes (in any language — English, 中文, etc.) what optical
system they want to design. Your job:

1. Classify their use case into EXACTLY ONE of these six scenarios:
   - smartphone-telephoto: phone tele or zoom camera, EFL 5-18 mm
   - smartphone-wide: phone main camera (the "wide" or default), EFL 2.4-4.1 mm
   - smartphone-ultrawide: phone wide-FOV auxiliary seed, EFL 2.6-3.0 mm, FOV 85-95°
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
- smartphone-wide:         EFL [2.4, 4.1] mm, f/[1.7, 2.6], FOV [57, 90]°,   img height [1.7, 3.5] mm
- smartphone-ultrawide:    EFL [2.6, 3.0] mm, f/[1.7, 2.1], FOV [85, 95]°,   img height [2.7, 3.1] mm
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


def _extract_json_value(raw: str) -> str | None:
    """Robustly extract the first balanced JSON value (object or array) from `raw`.

    Handles every variant we've actually seen Claude / GPT emit:
    - Pure JSON: `{"k":"v"}` or `[1,2,3]` → returned as-is.
    - Fenced JSON: ` ```json\n{...}\n``` ` → strip fences then return.
    - Prose-prefixed: "Here is the JSON:\n{...}" → scan for first opener.
    - JSON-with-trailing-text: "{...}\n\nLet me know if..." → balance-stop
      at the matching closer.

    Returns the substring that *parses* to a value, not necessarily an object
    — caller still needs to validate the shape (`isinstance(data, dict)`).
    Brace/bracket depth tracking is naïve about delimiters inside string
    literals; that's never a problem in practice because the JSON we ask
    for never embeds `{`/`}`/`[`/`]` inside its string values.
    """
    text = _strip_markdown_fences(raw)
    # Find the first '{' or '[' as the start of the JSON value.
    starts = [p for p in (text.find("{"), text.find("[")) if p >= 0]
    if not starts:
        return None
    start = min(starts)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


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
        focal_length_mm=_clamp(data.get("focal_length_mm"), bounds.efl_mm_min, bounds.efl_mm_max),
        f_number=_clamp(data.get("f_number"), bounds.f_number_min, bounds.f_number_max),
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


# ---------------------------------------------------------------------------
# Cover image generation — gpt-image-2 via relay
# ---------------------------------------------------------------------------

_COVER_PROMPT_PREFIX = (
    "Cinematic macro photograph of a precision optical lens module cross-section. "
    "Black void background, subtle photon-blue (#7dedff) and prism-amber (#ffb876) "
    "rim-light highlights on glass element edges, sharp specular reflections, "
    "studio lighting, abstract minimal architectural composition, premium "
    "scientific-instrument aesthetic, ultra-sharp focus, no text, no logos, no "
    "watermarks, no UI elements, photorealistic, 8k detail. Subject: "
)

_SCENARIO_COVER_HINTS: dict[Scenario, str] = {
    Scenario.SMARTPHONE_TELEPHOTO: (
        "a compact folded-periscope telephoto camera module from a flagship "
        "smartphone, exposed lens stack visible through a transparent housing, "
        "subtle prism reflections."
    ),
    Scenario.SMARTPHONE_WIDE: (
        "a smartphone main wide-angle camera module, dense vertical lens "
        "stack, large rear sensor visible, hint of OLED-glow background."
    ),
    Scenario.SMARTPHONE_ULTRAWIDE: (
        "a smartphone ultrawide camera module, very wide-angle front element, "
        "compact 6-element stack, glassy reflections."
    ),
    Scenario.AR_NEAR_EYE: (
        "a freeform optical waveguide for an AR/VR headset, paper-thin glass "
        "substrate with microscopic surface relief, ethereal light projection "
        "from a micro-display."
    ),
    Scenario.DSLR_PRIME: (
        "a full-frame mirrorless camera prime lens disassembled to show the "
        "internal element stack, multi-coated glass, aperture diaphragm visible."
    ),
    Scenario.MICROSCOPE_OBJECTIVE: (
        "a high-numerical-aperture microscope objective barrel cut open to "
        "show its multi-element correction stack, immersion-oil meniscus on "
        "front element."
    ),
}


class CoverImageRequest(BaseModel):
    scenario: Scenario
    efl_mm: float | None = Field(None, gt=0)
    f_number: float | None = Field(None, gt=0)
    size: str = Field(
        "1024x1024",
        description="Image size — gpt-image-2 supports 1024x1024 / 1024x1536 / 1536x1024",
    )


class CoverImageResponse(BaseModel):
    b64_png: str = Field(..., description="Base64-encoded PNG payload, no data: prefix")
    revised_prompt: str | None = Field(
        None, description="The prompt as rewritten by the image model (if it does)"
    )
    model: str
    scenario: Scenario


@router.post("/cover-image", response_model=CoverImageResponse)
async def generate_cover_image(req: CoverImageRequest) -> CoverImageResponse:
    """Generate a brand-aligned cover image for the Atelier PDF report.

    Runs gpt-image-2 via the relay. Called fire-and-forget by the Wizard after
    Generate succeeds; the PDF assembler embeds the result if it arrives in
    time, otherwise falls back to the text-only cover.
    """
    prompt = _COVER_PROMPT_PREFIX + _SCENARIO_COVER_HINTS[req.scenario]
    if req.efl_mm is not None and req.f_number is not None:
        prompt += f" Approximate focal length {req.efl_mm:.1f} mm, aperture f/{req.f_number:.1f}."

    client = get_async_client()
    try:
        response = await client.images.generate(
            model=PRIMARY_IMAGE,
            prompt=prompt,
            size=req.size,
            n=1,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "image_relay_failure",
                "message": str(e)[:300],
                "model": PRIMARY_IMAGE,
            },
        ) from e

    if not response.data or not response.data[0].b64_json:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "image_relay_empty_response",
                "model": PRIMARY_IMAGE,
            },
        )

    item = response.data[0]
    return CoverImageResponse(
        b64_png=item.b64_json,
        revised_prompt=getattr(item, "revised_prompt", None),
        model=PRIMARY_IMAGE,
        scenario=req.scenario,
    )


# ---------------------------------------------------------------------------
# Executive summary — claude-opus-4-7 writes the narrative paragraph that
# opens the PDF data page. Bilingual single-call: returns both en + zh so the
# frontend doesn't have to round-trip twice for the locale switcher.
# ---------------------------------------------------------------------------


_EXEC_SUMMARY_SYSTEM_PROMPT = """You are a senior optical engineer authoring
the executive-summary paragraph that opens a Lumira Atelier PDF report.

You're given the customer's design brief and the Optiland-computed result.

Write a SHORT paragraph in BOTH English (80-120 words) AND Chinese (200-280
characters). The Chinese version should NOT be a literal translation — it
should be a natively-written paragraph for a Chinese reader. Cover, in any
order:

1. What was actually designed — call the scenario by its industry name
2. The one or two facts that make this design credible — e.g. total track
   under X mm beats a class benchmark, MTF cutoff matches the Airy limit,
   element count sits in the published-design range
3. The honest disclaimer — this is a starting point, not a finished lens
4. If a design-agent match assessment is provided, mention the selected
   real seed, the strongest tradeoff, and the next optimization move
5. The honest disclaimer — this is a starting point, not a finished lens

Tone: confident, technical, honest. No marketing fluff, no fake humility,
no "exciting" / "powerful" / "cutting-edge" filler. First sentence
should land cleanly without throat-clearing.
Do not invent performance claims beyond the computed result and match
assessment. Do not describe the seed as a finished production prescription.

Reply ONLY with valid JSON in this exact shape — no markdown fences, no
surrounding prose:

{
  "summary_en": "<80-120 words>",
  "summary_zh": "<200-280 characters>"
}
"""


class ExecutiveSummaryRequest(BaseModel):
    scenario: Scenario
    scenario_label_en: str = Field(..., min_length=1, max_length=100)
    focal_length_mm: float = Field(..., gt=0)
    f_number: float = Field(..., gt=0)
    field_of_view_deg: float = Field(..., gt=0, le=180)
    image_height_mm: float = Field(..., gt=0)
    n_elements: int | None = Field(None, ge=2, le=30)
    wavelength_nm: float = Field(550, gt=0)
    total_track_mm: float = Field(..., gt=0)
    airy_disc_diameter_um: float = Field(..., gt=0)
    cutoff_freq_lp_per_mm: float = Field(..., gt=0)
    design_assessment: DesignAssessment | None = None


class ExecutiveSummaryResponse(BaseModel):
    summary_en: str
    summary_zh: str
    model: str
    fallback_reason: str | None = None


def _primary_summary_tradeoff(assessment: DesignAssessment | None) -> str:
    if assessment is None:
        return "no design-assessment packet was available"
    for item in assessment.requirement_coverage:
        if item.status != "met":
            detail = f"{item.label} is {item.status}"
            if item.delta is not None and item.unit:
                detail += f" ({item.delta:+.2f} {item.unit})"
            elif item.delta is not None:
                detail += f" ({item.delta:+.2f})"
            if item.next_action:
                detail += f"; action: {item.next_action}"
            return detail
    if assessment.warnings:
        return assessment.warnings[0]
    return "no critical deterministic tradeoff is currently flagged"


def _primary_summary_next_action(assessment: DesignAssessment | None) -> str:
    if assessment is None:
        return "rerun the optical review when design-assessment evidence is available"
    if (
        assessment.draft_acceptance_gate is not None
        and assessment.draft_acceptance_gate.required_next_actions
    ):
        return assessment.draft_acceptance_gate.required_next_actions[0]
    if assessment.acceptance_improvement_tasks:
        task = assessment.acceptance_improvement_tasks[0]
        return f"{task.task_id}: {task.objective}"
    if assessment.optimization_task_queue:
        task = assessment.optimization_task_queue[0]
        return f"{task.task_id}: {task.objective}"
    if assessment.next_steps:
        return assessment.next_steps[0]
    return "run tolerance, yield, and supplier review before production claims"


def _deterministic_executive_summary(
    req: ExecutiveSummaryRequest,
    *,
    model: str,
    fallback_reason: str,
) -> ExecutiveSummaryResponse:
    assessment = req.design_assessment
    seed = assessment.matched_case_id if assessment is not None else "the computed seed"
    score = f"{assessment.score:.3f}" if assessment is not None else "unscored"
    acceptance = (
        assessment.draft_acceptance_gate.status
        if assessment is not None and assessment.draft_acceptance_gate is not None
        else "not_gated"
    )
    coverage = (
        assessment.requirement_coverage_summary.summary
        if assessment is not None and assessment.requirement_coverage_summary is not None
        else "requirement coverage was not provided"
    )
    tradeoff = _primary_summary_tradeoff(assessment)
    next_action = _primary_summary_next_action(assessment)
    summary_en = (
        f"{req.scenario_label_en} first-pass draft based on real seed {seed}. "
        f"The deterministic review reports match score {score}, total track "
        f"{req.total_track_mm:.2f} mm, Airy diameter {req.airy_disc_diameter_um:.2f} um, "
        f"and acceptance state {acceptance}. Requirement coverage: {coverage}. "
        f"Main tradeoff: {tradeoff}. Next action: {next_action}. "
        "This is a starting optical design packet, not a production-ready prescription."
    )
    summary_zh = (
        f"这是基于真实 seed {seed} 的{req.scenario_label_en}初稿。确定性评审给出"
        f"匹配分 {score}、TTL {req.total_track_mm:.2f} mm、Airy "
        f"{req.airy_disc_diameter_um:.2f} um，当前验收状态为 {acceptance}。"
        f"需求覆盖：{coverage}。主要取舍：{tradeoff}。下一步：{next_action}。"
        "该结果只能作为初始设计包，不能当作量产处方。"
    )
    return ExecutiveSummaryResponse(
        summary_en=summary_en,
        summary_zh=summary_zh,
        model=f"deterministic-fallback:{model}",
        fallback_reason=fallback_reason,
    )


def _format_design_assessment_for_summary(assessment: DesignAssessment) -> str:
    """Compact design-agent context for the executive-summary LLM prompt."""
    lines = [
        "\nDesign-agent match assessment:",
        f"- Matched real seed: {assessment.matched_case_id}",
        (
            f"- Match score: {assessment.score:.3f}; "
            f"normalized distance: {assessment.normalized_distance:.3f}"
        ),
        (
            "- Deltas vs target: "
            f"EFL {assessment.delta_efl_mm:+.2f} mm, "
            f"F/# {assessment.delta_f_number:+.2f}, "
            f"FOV {assessment.delta_fov_deg:+.1f} deg"
        ),
    ]

    optional_deltas: list[str] = []
    if assessment.delta_image_height_mm is not None:
        optional_deltas.append(f"image height {assessment.delta_image_height_mm:+.2f} mm")
    if assessment.delta_n_elements is not None:
        optional_deltas.append(f"elements {assessment.delta_n_elements:+d}")
    if assessment.delta_total_track_mm is not None:
        optional_deltas.append(f"TTL {assessment.delta_total_track_mm:+.2f} mm")
    if optional_deltas:
        lines.append(f"- Secondary deltas: {', '.join(optional_deltas)}")

    if assessment.warnings:
        lines.append(f"- Warnings: {'; '.join(assessment.warnings[:3])}")

    if assessment.seed_selection_scorecard is not None:
        scorecard = assessment.seed_selection_scorecard
        lines.append(
            "- Seed selection scorecard: "
            f"selected={scorecard.selected_case_id}; "
            f"score={scorecard.selected_score:.3f}; "
            f"distance={scorecard.normalized_distance:.3f}; "
            f"profile={scorecard.scoring_profile}; {scorecard.summary}"
        )
        if scorecard.metric_scores:
            metric_bits = [
                f"{item.metric_id}: weight={item.weight:.2f}, "
                f"miss={item.normalized_miss:.3f}, contribution={item.contribution:.3f}, "
                f"{item.status}"
                for item in scorecard.metric_scores[:6]
            ]
            lines.append("  - Selection metric scores: " + "; ".join(metric_bits))
        if scorecard.accepted_tradeoffs:
            lines.append(
                "  - Selection accepted tradeoffs: "
                + "; ".join(scorecard.accepted_tradeoffs[:4])
            )
        if scorecard.rejected_alternatives:
            lines.append(
                "  - Selection rejected alternatives: "
                + "; ".join(scorecard.rejected_alternatives[:4])
            )
        lines.append(f"  - Selection next action: {scorecard.next_action}")

    if assessment.designer_readiness_rubric is not None:
        designer = assessment.designer_readiness_rubric
        lines.append(
            "- Designer readiness rubric: "
            f"{designer.status}; score={designer.score:.3f}; "
            f"weakest={designer.weakest_dimension_id or 'unknown'}; "
            f"{designer.summary}"
        )
        lines.append(f"  - Readiness claim boundary: {designer.claim_boundary}")
        if designer.blockers:
            lines.append("  - Readiness blockers: " + "; ".join(designer.blockers[:4]))
        for dimension in designer.dimensions[:6]:
            lines.append(
                f"  - Readiness {dimension.dimension_id}: {dimension.status}; "
                f"score={dimension.score:.3f}; action={dimension.next_action or 'none'}"
            )
        lines.append(f"  - Readiness next action: {designer.next_improvement_action}")

    if assessment.requirement_coverage_summary is not None:
        coverage = assessment.requirement_coverage_summary
        lines.append(
            "- Requirement coverage: "
            f"{coverage.status}; met={coverage.met_count}, "
            f"tradeoff={coverage.tradeoff_count}, miss={coverage.miss_count}, "
            f"unscored={coverage.unscored_count}; {coverage.summary}"
        )
        flagged_requirements = [
            item
            for item in assessment.requirement_coverage
            if item.status in {"tradeoff", "miss", "unscored"}
        ]
        for item in flagged_requirements[:5]:
            lines.append(
                f"  - {item.requirement_id}: {item.status}; "
                f"target={item.target}; actual={item.actual}; "
                f"next={item.next_action or 'no immediate action'}"
            )

    if assessment.design_intent_contract is not None:
        contract = assessment.design_intent_contract
        lines.append(
            "- Design intent contract: "
            f"{contract.status}; {contract.normalized_query}; "
            f"hard={len(contract.hard_constraints)}; "
            f"soft={len(contract.soft_preferences)}"
        )
        if contract.hard_constraints:
            hard_bits = [
                f"{item.requirement_id}={item.status}/{item.negotiability}"
                for item in contract.hard_constraints[:6]
            ]
            lines.append("  - Intent hard constraints: " + "; ".join(hard_bits))
        if contract.conflict_flags:
            lines.append(
                "  - Intent conflicts: " + "; ".join(contract.conflict_flags[:4])
            )
        if contract.inferred_assumptions:
            lines.append(
                "  - Intent assumptions: "
                + "; ".join(contract.inferred_assumptions[:4])
            )
        lines.append(f"  - Intent-safe interpretation: {contract.safe_interpretation}")
        lines.append(f"  - Intent next action: {contract.next_action}")

    if assessment.manufacturability_review is not None:
        review = assessment.manufacturability_review
        lines.append(
            "- Manufacturability review: "
            f"{review.status}; tier={review.tier or 'unspecified'}; "
            f"score={review.score:.2f}; {review.summary}"
        )
        for check in review.checks[:5]:
            lines.append(
                f"  - {check.check_id}: {check.status}; "
                f"target={check.target}; actual={check.actual}; "
                f"mitigation={check.mitigation or 'none'}"
            )
        if review.limitations:
            lines.append("  - Limitations: " + "; ".join(review.limitations[:3]))

    if assessment.manufacturing_sensitivity_audit is not None:
        audit = assessment.manufacturing_sensitivity_audit
        lines.append(
            "- Manufacturing sensitivity audit: "
            f"{audit.status}; confidence={audit.confidence:.2f}; "
            f"dominant={audit.dominant_factor_id or 'none'}; {audit.summary}"
        )
        for factor in audit.factors[:5]:
            lines.append(
                f"  - {factor.factor_id}: {factor.status}/{factor.sensitivity}; "
                f"source={factor.source}; metric={factor.metric}; "
                f"next={factor.next_action}"
            )
        if audit.required_evidence:
            lines.append(
                "  - Manufacturing required evidence: "
                + "; ".join(audit.required_evidence[:4])
            )
        if audit.limitations:
            lines.append("  - Sensitivity limitations: " + "; ".join(audit.limitations[:3]))

    if assessment.manufacturing_clearance_checklist is not None:
        checklist = assessment.manufacturing_clearance_checklist
        lines.append(
            "- Manufacturing clearance checklist: "
            f"{checklist.status}; items={len(checklist.items)}; "
            f"review_blockers={checklist.review_blocking_count}; "
            f"production_blockers={checklist.production_blocking_count}; "
            f"{checklist.summary}"
        )
        for item in checklist.items[:5]:
            lines.append(
                f"  - {item.item_id}: {item.status}; owner={item.owner_role}; "
                f"objective={item.clearance_objective}; next={item.next_action}"
            )
        lines.append(f"  - Manufacturing clearance next action: {checklist.next_clearance_action}")
        if checklist.forbidden_claims:
            lines.append(
                "  - Manufacturing forbidden claims: "
                + "; ".join(checklist.forbidden_claims[:4])
            )

    if assessment.draft_acceptance_gate is not None:
        gate = assessment.draft_acceptance_gate
        lines.append(
            "- Draft acceptance gate: "
            f"{gate.status}; candidate={gate.candidate_id or 'unresolved'}; "
            f"deliverable={gate.deliverable_type}; score={gate.score:.2f}; "
            f"{gate.summary}"
        )
        for check in gate.checks[:6]:
            lines.append(
                f"  - {check.check_id}: {check.status}; "
                f"evidence={check.evidence}; "
                f"action={check.required_action or 'none'}"
            )
        if gate.blockers:
            lines.append("  - Acceptance blockers: " + "; ".join(gate.blockers[:4]))
        if gate.review_notes:
            lines.append("  - Review notes: " + "; ".join(gate.review_notes[:4]))
        if gate.required_next_actions:
            lines.append(
                "  - Acceptance next actions: " + "; ".join(gate.required_next_actions[:4])
            )
        if gate.upgrade_actions:
            lines.append("  - Acceptance upgrade actions:")
            for action in gate.upgrade_actions[:4]:
                criteria = "; ".join(action.acceptance_criteria[:3]) or "criteria pending"
                unblocks = (
                    "; ".join(action.unblocks_claims[:2]) if action.unblocks_claims else "none"
                )
                lines.append(
                    f"    - P{action.priority} {action.action_id} "
                    f"from {action.source_check_id}: {action.action}; "
                    f"criteria={criteria}; effect={action.expected_effect}; "
                    f"unblocks={unblocks}"
                )
        if gate.forbidden_claims:
            lines.append("  - Acceptance forbidden claims: " + "; ".join(gate.forbidden_claims[:4]))

    if assessment.evidence_closeout_plan is not None:
        plan = assessment.evidence_closeout_plan
        lines.append(
            "- Evidence closeout plan: "
            f"{plan.status}; review blockers={plan.review_blocking_count}; "
            f"production blockers={plan.production_blocking_count}; {plan.summary}"
        )
        for item in plan.items[:5]:
            lines.append(
                f"  - P{item.priority} {item.item_id}: {item.status}; "
                f"source={item.source}; owner={item.owner_role}; "
                f"evidence={item.required_evidence}; next={item.next_action}; "
                f"unblocks={item.claim_unblocked}"
            )
        if plan.safe_next_action:
            lines.append(f"  - Evidence-safe next action: {plan.safe_next_action}")
        if plan.forbidden_claims:
            lines.append("  - Evidence forbidden claims: " + "; ".join(plan.forbidden_claims[:4]))

    if assessment.design_handoff_packet is not None:
        handoff = assessment.design_handoff_packet
        lines.append(
            "- Design handoff packet: "
            f"{handoff.status}; candidate={handoff.candidate_id}; "
            f"source={handoff.prescription_source}; {handoff.summary}"
        )
        lines.append(f"  - Payload policy: {handoff.payload_policy}")
        if handoff.headline_metrics:
            metric_bits = [
                f"{metric.metric_id}={metric.value}/{metric.status}"
                for metric in handoff.headline_metrics[:7]
            ]
            lines.append("  - Handoff metrics: " + "; ".join(metric_bits))
        if handoff.accepted_tradeoffs:
            lines.append("  - Handoff tradeoffs: " + "; ".join(handoff.accepted_tradeoffs[:4]))
        if handoff.review_focus:
            lines.append("  - Handoff review focus: " + "; ".join(handoff.review_focus[:4]))
        if handoff.forbidden_claims:
            lines.append(
                "  - Handoff forbidden claims: " + "; ".join(handoff.forbidden_claims[:4])
            )

    if assessment.design_traceability_manifest is not None:
        manifest = assessment.design_traceability_manifest
        lines.append(
            "- Traceability manifest: "
            f"{manifest.status}; source={manifest.source_case_id}/{manifest.source_zmx}; "
            f"delivered={manifest.delivered_candidate_id}; payload={manifest.delivered_payload}; "
            f"MTF field={manifest.mtf_field_evidence}"
        )
        lines.append(
            "  - Traceability paths: "
            f"source_zmx={manifest.source_zmx_path}; case_json={manifest.generated_case_path}"
        )
        if manifest.report_sections:
            lines.append("  - Report sections: " + "; ".join(manifest.report_sections[:5]))
        if manifest.validation_evidence:
            lines.append(
                "  - Traceability validation: "
                + "; ".join(manifest.validation_evidence[:4])
            )
        if manifest.replay_commands:
            lines.append(f"  - Traceability replay: {manifest.replay_commands[0]}")
        if manifest.forbidden_mutations:
            lines.append(
                "  - Forbidden mutations: "
                + "; ".join(manifest.forbidden_mutations[:4])
            )

    if assessment.design_constraint_ledger is not None:
        ledger = assessment.design_constraint_ledger
        lines.append(
            "- Constraint ledger: "
            f"{ledger.status}; locked={ledger.locked_count}; "
            f"accepted tradeoffs={ledger.accepted_tradeoff_count}; "
            f"unresolved={ledger.unresolved_count}; {ledger.summary}"
        )
        lines.append(f"  - Variable policy: {ledger.variable_policy_summary}")
        if ledger.constraints:
            constraint_bits = [
                f"{item.requirement_id}={item.status}"
                for item in ledger.constraints[:7]
            ]
            lines.append("  - Constraint states: " + "; ".join(constraint_bits))
        if ledger.variables:
            variable_bits = [
                f"{item.variable_id}={item.status}"
                for item in ledger.variables[:5]
            ]
            lines.append("  - Variable governance: " + "; ".join(variable_bits))
        if ledger.forbidden_actions:
            lines.append(
                "  - Constraint forbidden actions: "
                + "; ".join(ledger.forbidden_actions[:4])
            )
        lines.append(f"  - Constraint next action: {ledger.next_action}")

    if assessment.candidate_comparison:
        lines.append("- Candidate branches:")
        for candidate in assessment.candidate_comparison[:4]:
            strength = candidate.strengths[0] if candidate.strengths else "usable seed"
            tradeoff = candidate.tradeoffs[0] if candidate.tradeoffs else "no major tradeoff"
            lines.append(
                f"  - {candidate.role}: {candidate.case_id}, "
                f"score {candidate.score:.3f}, "
                f"FOV {candidate.fov_deg:.1f} deg, "
                f"TTL {candidate.total_track_mm:.2f} mm, "
                f"strength: {strength}, tradeoff: {tradeoff}"
            )

    if assessment.next_steps:
        lines.append(f"- Suggested next steps: {'; '.join(assessment.next_steps[:3])}")
    if assessment.readiness is not None:
        lines.append(
            f"- Readiness: {assessment.readiness.level}, "
            f"confidence {assessment.readiness.confidence:.2f}; "
            f"{assessment.readiness.summary}"
        )
    if assessment.risk_register:
        lines.append("- Risk register:")
        for risk in assessment.risk_register[:3]:
            lines.append(
                f"  - {risk.severity}: {risk.risk}; "
                f"evidence: {risk.evidence}; mitigation: {risk.mitigation}"
            )
    if assessment.optimization_plan:
        lines.append("- Optimization plan:")
        for action in assessment.optimization_plan[:3]:
            focus = ", ".join(action.parameter_focus[:3])
            lines.append(
                f"  - P{action.priority} {action.objective}; "
                f"focus: {focus}; verify: {action.verification}"
            )
    if assessment.optimization_attempt is not None:
        attempt = assessment.optimization_attempt
        lines.append(
            f"- Protected optimizer attempt: {attempt.status}; {attempt.summary}; "
            f"applied_to_payload={attempt.applied_to_payload}"
        )
        if attempt.before_efl_mm is not None and attempt.after_efl_mm is not None:
            lines.append(
                f"  - EFL before/after: {attempt.before_efl_mm:.3f} -> "
                f"{attempt.after_efl_mm:.3f} mm"
            )
        if attempt.variable_changes:
            change = attempt.variable_changes[0]
            lines.append(
                f"  - Proposed variable: {change.variable} S{change.surface_index} "
                f"{change.before:.4f} -> {change.after:.4f}"
            )
        if attempt.variable_candidates:
            eligible = [
                f"{candidate.variable} S{candidate.surface_index}"
                for candidate in attempt.variable_candidates
                if candidate.status == "eligible"
            ]
            if eligible:
                lines.append(f"  - Candidate variables: {', '.join(eligible[:6])}")
        if attempt.candidate_trials:
            first_rejection = next(
                (
                    trial
                    for trial in attempt.candidate_trials
                    if trial.status in {"rejected", "failed", "skipped"}
                ),
                None,
            )
            trial_line = f"  - Candidate trials: {len(attempt.candidate_trials)}"
            if first_rejection is not None:
                trial_line += (
                    f"; first non-promotion: {first_rejection.variable} "
                    f"S{first_rejection.surface_index} {first_rejection.reason}"
                )
            lines.append(trial_line)
        if attempt.verification is not None:
            gate = attempt.verification
            lines.append(f"  - Verification gate: {gate.status}; {gate.summary}")
            if gate.mtf_max_field_frac is not None:
                lines.append(
                    f"  - Verified MTF field: {format_mtf_field_fraction(gate.mtf_max_field_frac)}"
                )
            if gate.mtf_multiband_min_score is not None:
                lines.append(
                    f"  - Verified MTF 50/100/150 score: {gate.mtf_multiband_min_score:.3f}"
                )
            if gate.mtf_field_weighted_score is not None:
                lines.append(
                    f"  - Verified field-weighted MTF score: {gate.mtf_field_weighted_score:.3f}"
                )
        if attempt.before_metrics is not None and attempt.after_metrics is not None:
            before = attempt.before_metrics
            after = attempt.after_metrics
            metric_bits = []
            if (
                before.effective_focal_length_mm is not None
                and after.effective_focal_length_mm is not None
            ):
                metric_bits.append(
                    f"EFL {before.effective_focal_length_mm:.3f}->{after.effective_focal_length_mm:.3f} mm"
                )
            if (
                before.max_rms_spot_radius_um is not None
                and after.max_rms_spot_radius_um is not None
            ):
                metric_bits.append(
                    f"max RMS {before.max_rms_spot_radius_um:.2f}->{after.max_rms_spot_radius_um:.2f} um"
                )
            if (
                before.mtf_multiband_min_score is not None
                and after.mtf_multiband_min_score is not None
            ):
                metric_bits.append(
                    f"MTF band score {before.mtf_multiband_min_score:.3f}->{after.mtf_multiband_min_score:.3f}"
                )
            if (
                before.mtf_field_weighted_score is not None
                and after.mtf_field_weighted_score is not None
            ):
                metric_bits.append(
                    f"field-weighted MTF {before.mtf_field_weighted_score:.3f}->{after.mtf_field_weighted_score:.3f}"
                )
            if metric_bits:
                lines.append(f"  - Metric delta: {'; '.join(metric_bits)}")
    if assessment.merit_optimization_probe is not None:
        probe = assessment.merit_optimization_probe
        lines.append(
            f"- Protected RMS merit probe: {probe.status}; {probe.summary}; "
            f"operand={probe.operand}; applied_to_payload={probe.applied_to_payload}"
        )
        if probe.field_samples:
            lines.append(
                "  - Merit fields: "
                + ", ".join(f"{field:.1f}" for field in probe.field_samples[:5])
            )
        if probe.rms_improvement_um is not None:
            lines.append(f"  - Verified RMS improvement: {probe.rms_improvement_um:.2f} um")
        if probe.variable_changes:
            change = probe.variable_changes[0]
            lines.append(
                f"  - Merit variable: {change.variable} S{change.surface_index} "
                f"{change.before:.4f} -> {change.after:.4f}"
            )
        if probe.variable_candidates:
            eligible = [
                f"{candidate.variable} S{candidate.surface_index}"
                for candidate in probe.variable_candidates
                if candidate.status == "eligible"
            ]
            audited = [
                (
                    f"S{candidate.surface_index}:c{candidate.coefficient_index} "
                    f"r^{candidate.asphere_power} "
                    f"sag={candidate.edge_sag_delta_um:.2f}um "
                    f"slope={candidate.edge_slope_delta_mrad:.2f}mrad "
                    f"{candidate.manufacturability_status}"
                )
                for candidate in probe.variable_candidates
                if candidate.variable == "asphere_coefficient"
                and candidate.status == "audited_only"
                and candidate.asphere_power is not None
                and candidate.edge_sag_delta_um is not None
                and candidate.edge_slope_delta_mrad is not None
            ]
            if eligible:
                lines.append(f"  - Merit candidate variables: {', '.join(eligible[:6])}")
            if audited:
                lines.append(f"  - Asphere candidates audited only: {', '.join(audited[:6])}")
        if probe.candidate_trials:
            promotion_scores = [
                trial.promotion_score
                for trial in probe.candidate_trials
                if trial.promotion_score is not None
            ]
            floor_gap_closures = [
                trial.image_quality_floor_gap_closure
                for trial in probe.candidate_trials
                if trial.image_quality_floor_gap_closure is not None
            ]
            first_rejection = next(
                (
                    trial
                    for trial in probe.candidate_trials
                    if trial.status in {"rejected", "failed", "skipped"}
                ),
                None,
            )
            trial_line = f"  - Merit candidate trials: {len(probe.candidate_trials)}"
            if promotion_scores:
                trial_line += f"; best promotion score: {max(promotion_scores):.3f}"
            if floor_gap_closures:
                trial_line += f"; best floor-gap closure: {max(floor_gap_closures):+.3f}"
            if first_rejection is not None:
                trial_line += (
                    f"; first non-promotion: {first_rejection.variable} "
                    f"S{first_rejection.surface_index} {first_rejection.reason}"
                )
            lines.append(trial_line)
        if probe.verification is not None:
            lines.append(
                f"  - Merit verification gate: {probe.verification.status}; "
                f"{probe.verification.summary}"
            )
    if assessment.full_field_recovery_diagnostic is not None:
        diagnostic = assessment.full_field_recovery_diagnostic
        lines.append(
            "- Full-field recovery diagnostic: "
            f"{diagnostic.status}; mode={diagnostic.failure_mode}; "
            "current field="
            f"{format_mtf_field_fraction(diagnostic.current_field_frac)}; "
            f"next={diagnostic.recommended_variable_family}"
        )
        if diagnostic.best_partial_rms_delta_um is not None:
            lines.append(
                f"  - Best partial RMS delta: {diagnostic.best_partial_rms_delta_um:+.2f} um"
            )
        if diagnostic.best_recovery_trial is not None:
            trial = diagnostic.best_recovery_trial
            bits = [
                f"{trial.variable_family} S{trial.surface_index}",
                trial.status,
            ]
            if trial.mtf_max_field_frac is not None:
                bits.append(f"field {format_mtf_field_fraction(trial.mtf_max_field_frac)}")
            if trial.rms_delta_um is not None:
                bits.append(f"RMS delta {trial.rms_delta_um:+.2f} um")
            lines.append("  - Best recovery replay: " + "; ".join(bits))
        if diagnostic.local_variable_families_tested:
            lines.append(
                "  - Local families tested: "
                + ", ".join(diagnostic.local_variable_families_tested[:6])
            )
    if assessment.library_coverage_diagnostic is not None:
        diagnostic = assessment.library_coverage_diagnostic
        lines.append(
            "- Library coverage diagnostic: "
            f"{diagnostic.status}; target FOV={diagnostic.target_fov_deg:.1f}; "
            f"strategy={diagnostic.recommended_strategy}"
        )
        if diagnostic.nearest_full_field_case_id is not None:
            lines.append(
                f"  - Nearest full-field seed: {diagnostic.nearest_full_field_case_id} "
                f"at {diagnostic.nearest_full_field_fov_deg:.1f} deg"
            )
    if assessment.reference_influence_audit is not None:
        audit = assessment.reference_influence_audit
        lines.append(
            "- Reference influence audit: "
            f"{audit.status}; confidence={audit.confidence:.2f}; "
            f"selected={audit.selected_reference_id}; {audit.summary}"
        )
        if audit.data_gaps:
            lines.append("  - Reference data gaps: " + "; ".join(audit.data_gaps[:4]))
        if audit.rejected_reference_ids:
            lines.append(
                "  - Rejected references: " + ", ".join(audit.rejected_reference_ids[:4])
            )
        if audit.safe_next_action:
            lines.append(f"  - Reference-safe next action: {audit.safe_next_action}")
    if assessment.design_strategy_decision is not None:
        decision = assessment.design_strategy_decision
        lines.append(
            f"- Design strategy decision: {decision.selected_strategy}; {decision.summary}"
        )
        if decision.required_evidence:
            lines.append("  - Required evidence: " + "; ".join(decision.required_evidence[:3]))
        if decision.fallback_strategies:
            lines.append("  - Fallbacks: " + ", ".join(decision.fallback_strategies))
        for option in decision.options[:3]:
            fov_label = f"{option.fov_deg:.1f} deg" if option.fov_deg is not None else "unknown"
            lines.append(
                f"  - Option {option.option_id}: {option.recommendation}; "
                f"candidate={option.candidate_id or 'new-seed'}; "
                f"FOV={fov_label}; "
                f"field={format_mtf_field_fraction(option.mtf_max_field_frac)}; "
                f"{option.spec_impact}"
            )
        if decision.seed_acquisition_brief is not None:
            brief = decision.seed_acquisition_brief
            lines.append(
                "  - Seed acquisition brief: "
                f"{brief.source_format}; FOV>={brief.minimum_fov_deg:.1f} deg; "
                f"EFL {brief.efl_window_mm[0]:.2f}-{brief.efl_window_mm[1]:.2f} mm; "
                f"F/# {brief.f_number_window[0]:.2f}-{brief.f_number_window[1]:.2f}; "
                f"required field={format_mtf_field_fraction(brief.required_mtf_field_frac)}"
            )
            if brief.validation_requirements:
                lines.append("  - Seed validation: " + "; ".join(brief.validation_requirements[:3]))
    if assessment.seed_intake_audit is not None:
        audit = assessment.seed_intake_audit
        lines.append(
            "- Seed intake audit: "
            f"{audit.status}; accepted={audit.accepted_seed_count}; "
            f"high-FOV seeds={audit.high_fov_seed_count}; "
            f"full-field seeds={audit.full_field_seed_count}; {audit.summary}"
        )
        if audit.nearest_candidates:
            nearest_bits = [
                f"{item.role}={item.case_id} FOV={item.fov_deg:.1f} "
                f"field={format_mtf_field_fraction(item.mtf_max_field_frac)}"
                for item in audit.nearest_candidates[:3]
            ]
            lines.append("  - Intake nearest candidates: " + "; ".join(nearest_bits))
        if audit.missing_evidence:
            lines.append("  - Intake missing evidence: " + "; ".join(audit.missing_evidence[:4]))
        lines.append(f"  - Intake probe command: {audit.next_probe_command}")
        lines.append(f"  - Intake candidate preflight: {audit.candidate_preflight_command}")
    if assessment.seed_acquisition_contract is not None:
        contract = assessment.seed_acquisition_contract
        lines.append(
            "- Seed acquisition contract: "
            f"{contract.status}; {contract.acceptance_target}; {contract.summary}"
        )
        if contract.required_candidate_properties:
            lines.append(
                "  - Required candidate properties: "
                + "; ".join(contract.required_candidate_properties[:5])
            )
        if contract.pass_criteria:
            lines.append("  - Seed pass criteria: " + "; ".join(contract.pass_criteria[:4]))
        if contract.current_gap_evidence:
            prioritized_gap_evidence = [
                *(
                    item
                    for item in contract.current_gap_evidence
                    if item.startswith("near miss")
                ),
                *(
                    item
                    for item in contract.current_gap_evidence
                    if not item.startswith("near miss")
                ),
            ]
            lines.append(
                "  - Seed current gap evidence: "
                + "; ".join(prioritized_gap_evidence[:4])
            )
        if contract.fallback_paths:
            lines.append("  - Fallback paths: " + "; ".join(contract.fallback_paths[:3]))
        if contract.blocked_claims:
            lines.append("  - Seed-blocked claims: " + "; ".join(contract.blocked_claims[:4]))
        if contract.preflight_command:
            lines.append(f"  - Seed contract preflight: {contract.preflight_command}")
        lines.append(f"  - Seed contract next action: {contract.next_action}")
    if assessment.delivery_gate is not None:
        gate = assessment.delivery_gate
        lines.append(f"- Delivery gate: {gate.status}; {gate.deliverable_type}; {gate.summary}")
        if gate.allowed_claims:
            lines.append("  - Allowed claims: " + "; ".join(gate.allowed_claims[:4]))
        if gate.forbidden_claims:
            lines.append("  - Forbidden claims: " + "; ".join(gate.forbidden_claims[:4]))
        if gate.promotion_requirements:
            lines.append(
                "  - Promotion requirements: " + "; ".join(gate.promotion_requirements[:4])
            )
    if assessment.draft_quality_rubric is not None:
        rubric = assessment.draft_quality_rubric
        lines.append(
            f"- Draft quality rubric: {rubric.level}; score={rubric.score:.3f}; "
            f"{rubric.summary}"
        )
        if rubric.weakest_dimension_id or rubric.minimum_next_action:
            lines.append(
                f"  - Quality closeout: weakest={rubric.weakest_dimension_id or 'unknown'}; "
                f"target={rubric.promotion_target or 'n/a'}; "
                f"minimum_next_action={rubric.minimum_next_action or 'none'}"
            )
        if rubric.promotion_actions:
            lines.append(
                "  - Quality promotion actions: "
                + "; ".join(rubric.promotion_actions[:4])
            )
        for dimension in rubric.dimensions[:5]:
            lines.append(
                f"  - Quality {dimension.dimension_id}: {dimension.status}; "
                f"score={dimension.score:.3f}; action={dimension.recommended_action or 'none'}"
            )
    if assessment.branch_selection_policy is not None:
        policy = assessment.branch_selection_policy
        lines.append(
            f"- Branch selection policy: {policy.status}; active={policy.active_candidate_id}; "
            f"primary={policy.primary_candidate_id or 'unresolved'}; "
            f"deliverable={policy.current_deliverable_candidate_id or 'unresolved'}; "
            f"{policy.summary}"
        )
        if policy.candidate_priority_order:
            lines.append(
                "  - Candidate priority: " + " > ".join(policy.candidate_priority_order[:5])
            )
        if policy.promotion_requirements:
            lines.append(
                "  - Branch promotion requirements: " + "; ".join(policy.promotion_requirements[:4])
            )
        if policy.forbidden_claims:
            lines.append("  - Branch forbidden claims: " + "; ".join(policy.forbidden_claims[:4]))
    if assessment.strategy_tradeoff_matrix:
        lines.append("- Strategy tradeoff matrix:")
        for row in assessment.strategy_tradeoff_matrix[:5]:
            metrics = []
            if row.fov_deg is not None:
                metrics.append(f"FOV={row.fov_deg:.1f} deg")
            if row.mtf_max_field_frac is not None:
                metrics.append(
                    f"MTF field={format_mtf_field_fraction(row.mtf_max_field_frac)}"
                )
            if row.efl_mm is not None:
                metrics.append(f"EFL={row.efl_mm:.2f} mm")
            lines.append(
                f"  - #{row.priority_rank} {row.candidate_id}: "
                f"roles={','.join(row.role_tags) or 'review'}; "
                f"claim={row.claim_status}; evidence={row.evidence_level}; "
                f"{'; '.join(metrics)}; next={row.next_action}"
            )
    if assessment.spec_repair_preview is not None:
        preview = assessment.spec_repair_preview
        lines.append(
            "- Spec repair preview: "
            f"{preview.status}; candidate={preview.selected_case_id}; "
            f"repaired EFL={preview.repaired_target_focal_length_mm:.2f} mm; "
            f"score={preview.score:.3f}; {preview.coverage_summary.summary}"
        )
        if preview.remaining_tradeoffs:
            lines.append(
                "  - Remaining after repair: " + "; ".join(preview.remaining_tradeoffs[:4])
            )
        lines.append(f"  - Payload policy: {preview.payload_policy}")
    if assessment.spec_repair_decision is not None:
        decision = assessment.spec_repair_decision
        lines.append(
            "- Spec repair decision: "
            f"{decision.status}; {decision.recommended_decision}; "
            f"locked={decision.locked_constraint}; repair={decision.repaired_parameter}; "
            f"{decision.decision_summary}"
        )
        if decision.required_record:
            lines.append(f"  - Required record: {decision.required_record}")
        if decision.alternatives:
            lines.append(
                "  - Alternatives: " + "; ".join(decision.alternatives[:3])
            )
        if decision.acceptance_effect:
            lines.append(f"  - Acceptance effect: {decision.acceptance_effect}")
        if decision.rerun_contract is not None:
            contract = decision.rerun_contract
            lines.append(
                "  - Rerun contract: "
                f"{contract.status}; {contract.query_summary}; "
                f"expected={contract.expected_case_id or 'unresolved'}"
            )
            if contract.validation_checks:
                lines.append(
                    "  - Rerun validation: "
                    + "; ".join(contract.validation_checks[:4])
                )
    if assessment.spec_repair_auto_closure is not None:
        closure = assessment.spec_repair_auto_closure
        lines.append(
            "- Spec repair auto-closure: "
            f"{closure.status}; repaired EFL={closure.repaired_target_focal_length_mm:.2f} mm; "
            f"delta={closure.repair_delta_mm:.2f} mm / {closure.repair_delta_pct:.1f}%; "
            f"{closure.summary}"
        )
        if closure.accepted_tradeoff_ids:
            lines.append(
                "  - Auto-closed tradeoffs: "
                + ", ".join(closure.accepted_tradeoff_ids)
            )
        if closure.forbidden_claims:
            lines.append(
                "  - Auto-closure forbidden claims: "
                + "; ".join(closure.forbidden_claims[:3])
            )
    if assessment.draft_candidates:
        lines.append(f"- Recommended draft candidate: {assessment.recommended_candidate_id}")
        for candidate in assessment.draft_candidates[:5]:
            branch_bits = [
                f"{candidate.status}/{candidate.recommendation}",
            ]
            if candidate.strategy_option_id is not None:
                branch_bits.append(f"strategy={candidate.strategy_option_id}")
            if candidate.metrics is not None and candidate.metrics.mtf_max_field_frac is not None:
                branch_bits.append(
                    f"MTF field={format_mtf_field_fraction(candidate.metrics.mtf_max_field_frac)}"
                )
            line = f"  - {candidate.candidate_id}: {', '.join(branch_bits)}; {candidate.summary}"
            if candidate.evidence:
                line += f"; evidence: {candidate.evidence[0]}"
            if candidate.risks:
                line += f"; risk: {candidate.risks[0]}"
            lines.append(line)
    if assessment.prescription_change_set is not None:
        change_set = assessment.prescription_change_set
        lines.append(
            f"- Prescription change set from {change_set.source_candidate_id}: "
            f"{change_set.expected_effect}; policy: {change_set.application_policy}"
        )
        if change_set.changes:
            change = change_set.changes[0]
            lines.append(
                f"  - Change: {change.variable} S{change.surface_index} "
                f"{change.before:.4f}->{change.after:.4f}"
            )
        if change_set.verification_checklist:
            lines.append(
                f"  - Verification checklist: {'; '.join(change_set.verification_checklist[:3])}"
            )
    if assessment.acceptance_improvement_tasks:
        lines.append("- Acceptance improvement tasks:")
        for task in assessment.acceptance_improvement_tasks[:4]:
            deps = f"; depends_on: {', '.join(task.depends_on)}" if task.depends_on else ""
            blocks = (
                f"; blocks claims: {'; '.join(task.blocks_claims[:2])}"
                if task.blocks_claims
                else ""
            )
            probe = ""
            if task.evidence_probe is not None:
                probe = (
                    f"; probe={task.evidence_probe.status}: {task.evidence_probe.summary}; "
                    f"known={'; '.join(task.evidence_probe.known_evidence[:2])}; "
                    f"missing={'; '.join(task.evidence_probe.missing_evidence[:2])}"
                )
                if task.evidence_probe.next_probe_command:
                    probe += f"; command={task.evidence_probe.next_probe_command}"
            lines.append(
                f"  - P{task.priority} {task.task_id}: {task.status}/{task.stage}; "
                f"owner={task.owner}; objective={task.objective}; "
                f"exit={'; '.join(task.exit_criteria[:2])}{deps}{blocks}{probe}"
            )
    if assessment.optimization_task_queue:
        lines.append("- Optimization task queue:")
        for task in assessment.optimization_task_queue[:4]:
            deps = f"; depends_on: {', '.join(task.depends_on)}" if task.depends_on else ""
            lines.append(
                f"  - {task.task_id}: {task.status}/{task.stage}; "
                f"candidate: {task.candidate_id}; stop: {task.stop_condition}{deps}"
            )
    if assessment.optimization_task_runs:
        lines.append("- Optimization task run evidence:")
        for run in assessment.optimization_task_runs[:3]:
            metric_bits = [
                (
                    f"{metric.metric} {metric.before:.3f}->{metric.after:.3f}"
                    if metric.before is not None and metric.after is not None
                    else f"{metric.metric} {metric.direction}"
                )
                for metric in run.metric_updates[:3]
            ]
            metrics = f"; metrics: {'; '.join(metric_bits)}" if metric_bits else ""
            unlocked = f"; unlocked: {', '.join(run.unlocked_tasks)}" if run.unlocked_tasks else ""
            lines.append(
                f"  - {run.task_id}: {run.status}; next: {run.next_action}{metrics}{unlocked}"
            )

    return "\n".join(lines) + "\n"


@router.post("/executive-summary", response_model=ExecutiveSummaryResponse)
async def generate_executive_summary(
    req: ExecutiveSummaryRequest,
) -> ExecutiveSummaryResponse:
    """Generate a bilingual executive-summary paragraph for the PDF report.

    Fire-and-forget by the Wizard after Generate succeeds (similar to cover
    image). If it lands before Download PDF, the report gets a polished
    opening paragraph; if not, the report still ships (the section is
    optional).
    """
    user_msg = (
        f"Customer brief:\n"
        f"- Scenario: {req.scenario_label_en} ({req.scenario.value})\n"
        f"- Target focal length: {req.focal_length_mm:.2f} mm\n"
        f"- Target f-number: f/{req.f_number:.2f}\n"
        f"- Field of view: {req.field_of_view_deg:.1f}°\n"
        f"- Image height: {req.image_height_mm:.2f} mm\n"
        f"- Wavelength: {req.wavelength_nm:.0f} nm\n"
    )
    if req.n_elements:
        user_msg += f"- Element count: {req.n_elements}\n"

    user_msg += (
        f"\nOptiland-computed result:\n"
        f"- Total track length: {req.total_track_mm:.2f} mm\n"
        f"- Airy disc diameter: {req.airy_disc_diameter_um:.2f} µm at "
        f"λ={req.wavelength_nm:.0f} nm\n"
        f"- Diffraction cutoff: {req.cutoff_freq_lp_per_mm:.0f} lp/mm\n"
    )
    if req.design_assessment is not None:
        user_msg += _format_design_assessment_for_summary(req.design_assessment)

    client = get_async_client()
    model = model_for_role("wizard.main")

    async def call_llm(retry_hint: str = "") -> str:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _EXEC_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
        if retry_hint:
            messages.append({"role": "user", "content": retry_hint})
        completion = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=600,
            temperature=0.5,
        )
        return completion.choices[0].message.content or ""

    # First attempt.
    try:
        raw = await call_llm()
    except Exception as e:
        return _deterministic_executive_summary(
            req,
            model=model,
            fallback_reason=f"llm_relay_failure: {str(e)[:120]}",
        )

    # Try to parse with the robust extractor (handles fences, prose prefix,
    # trailing text). If THAT fails, ask Claude to re-emit JSON only and try
    # once more. We've observed the first-shot non-JSON case ~3% of the time
    # under cover-image-concurrent load; the retry pattern recovers ~all of
    # them and keeps the executive-summary callout on the PDF.
    extracted = _extract_json_value(raw)
    if extracted is None:
        try:
            raw = await call_llm(
                retry_hint=(
                    "Your previous reply was not valid JSON. Reply ONLY with "
                    'the JSON object {"summary_en": "...", "summary_zh": '
                    '"..."} — no prose, no fences, no commentary. Begin with '
                    "the opening `{` and end with the closing `}`."
                ),
            )
            extracted = _extract_json_value(raw)
        except Exception:
            pass  # fall through to the unparseable error below

    if extracted is None:
        return _deterministic_executive_summary(
            req,
            model=model,
            fallback_reason="llm_response_unparseable",
        )

    try:
        data = json.loads(extracted)
    except json.JSONDecodeError as e:
        return _deterministic_executive_summary(
            req,
            model=model,
            fallback_reason=f"llm_response_unparseable: {str(e)[:120]}",
        )

    if not isinstance(data, dict):
        return _deterministic_executive_summary(
            req,
            model=model,
            fallback_reason=f"llm_response_not_object: {type(data).__name__}",
        )

    summary_en = str(data.get("summary_en", "")).strip()
    summary_zh = str(data.get("summary_zh", "")).strip()
    if not summary_en and not summary_zh:
        return _deterministic_executive_summary(
            req,
            model=model,
            fallback_reason="llm_response_missing_summary",
        )

    return ExecutiveSummaryResponse(
        summary_en=summary_en,
        summary_zh=summary_zh,
        model=model,
    )
