# Feature Research

**Domain:** AI-assisted optical lens design demo product (requirement → design → assessment → deep-optimization showcase, dual audience: senior optical designers + factory decision-makers)
**Researched:** 2026-07-03
**Confidence:** MEDIUM-HIGH (Zemax/CODE V standard outputs = HIGH, verified against Ansys/Synopsys official docs; tolerancing credibility norms = HIGH, multiple industry sources agree; AI-design-assistant competitive landscape = MEDIUM, thin field, cross-checked with one directly-relevant arXiv paper; decision-maker narrative patterns = MEDIUM, vendor marketing sources, directionally consistent but not empirically tested on this audience)

## Feature Landscape

### Table Stakes (Experts Dismiss the Demo Without These)

These are the outputs any resident optical designer expects to see before they consider a result "real". Missing any one of these reads as "toy" or "black box" — the exact failure mode the Core Value in PROJECT.md forbids.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Spot diagram (multi-field, multi-wavelength) | Standard first-look diagnostic in every native tool (Zemax/CODE V); designers read RMS spot size vs Airy disk radius at a glance to judge diffraction-limited vs aberration-limited | MEDIUM | Optiland can compute geometric spot data; needs field/wavelength grid + Airy-radius overlay rendering. Already have ray trace infra (`optical_engine.py`) |
| MTF plot (through-frequency, per field) | Universal acceptance criterion in imaging optics; "MTF at Nyquist" is the de facto pass/fail number factories quote | LOW | Already implemented (`aberration.py`, `mtf_fields.py`) — table stakes already met |
| Field curvature + distortion plot | Standard OpticStudio/CODE V output pair; designers immediately check "is the field flat enough" and "what's the TV distortion %" for consumer lens use cases | MEDIUM | Not yet in codebase per ARCHITECTURE.md — needs new analysis module reading trace/paraxial data across field |
| 2D layout / cross-section diagram | Baseline sanity check — designer wants to see the physical lens stack before trusting any number | DONE (LOW residual) | Already implemented via `layout_svg.py` |
| Paraxial summary (EFL, F/#, EPD, BFD, TTL) | First-order sanity check; any deviation from spec here disqualifies the design before deeper analysis | DONE | Already implemented (`compute_paraxial_summary`) |
| RMS wavefront error / Strehl ratio | Diffraction-based quality metric that spot diagrams (geometric only) can't show; used to judge near-diffraction-limited designs | MEDIUM | Optiland supports wavefront/Zernike computation per ARCHITECTURE.md aberration.py — likely partially present, needs surfacing in UI |
| Prescription / lens data table (radii, thickness, glass, conic/asphere coeffs) | The literal "design" artifact — every native tool leads with this table; designers cross-check it against physical plausibility (edge thickness, glass availability) | LOW | Data already exists in LensAssembly schema; needs a formatted table view |
| Tolerance sensitivity summary (even simplified) | Table-stakes for designers because a "perfect nominal design" that can't be manufactured is worthless; native tools always ship tolerancing modules | HIGH | Not yet built. Full Monte Carlo is CODE V's job (deep engine); demo needs at minimum a "top N sensitive parameters" table pulled from CODE V tolerancing output — this is the credibility linchpin for the CODE V showcase |
| Traceable data provenance ("this came from real ray trace / real CODE V run, not an LLM guess") | Directly maps to PROJECT.md's non-negotiable constraint: LLM never touches numerics; designers actively probe for "is this actually computed or just plausible-sounding text" | LOW | Architecturally already true (parameter guards + deterministic core); needs UI-level provenance labeling so it's *visible*, not just true |

### Differentiators (Where This Demo Wins)

Align tightly with Core Value: prove Code V-caliber output while keeping the online loop fast, and prove traceability end-to-end. Don't differentiate on raw feature count against 30-year-old incumbents — differentiate on speed of the requirement→design loop and on narrative packaging.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Natural-language requirement → constrained design in seconds | This is the entire pitch of AI-assisted design (see OPTIAGENT arXiv 2602.23761 — LLM-generated starting points feeding local optimizer). No native tool does this; Zemax/CODE V require an expert to hand-build the starting point | DONE (needs polish) | Wizard LLM extraction already exists; differentiator is UX polish + speed perception, not new backend work |
| Before/after optimization comparison (Optiland seed vs CODE V-refined) | Directly visualizes "what deep optimization bought you" — MTF curve overlay, spot diagram shrink, RMS wavefront delta. This is the single most persuasive slide for both audiences simultaneously (designer sees the number improve, decision-maker sees the visual "wow") | MEDIUM | Requires Code V macro-batch integration (Active in PROJECT.md) + a diff-rendering layer on top of existing plot components |
| "Cross-validated by CODE V" badge/narrative on every deep-tier result | Borrows CODE V's own market credibility (per Keysight/Synopsys marketing, CODE V's optimization reputation is why it was chosen over Zemax) — turns a competitor's brand equity into this product's trust signal | LOW | Pure narrative/UI layer once ZMX↔CODE V round-trip works; zero new computation |
| Case-library-grounded "nearest real precedent" (already have 39 designs incl. patent seeds) | Most AI-design demos show designs in a vacuum; grounding a new spec against 39 real/patent designs with a match score gives designers something to sanity-check against — directly counters "is this AI hallucinating a lens" skepticism | DONE | `case_library.py` / `match_case()` already implemented — market this harder in the demo narrative, it's a real differentiator vs pure-generation tools like AutoLens |
| Bilingual (CN/EN) executive summary with plain-language translation of aberration jargon | Decision-makers (factory leadership) don't read Zernike coefficients; a narrative layer translating "RMS wavefront 0.05λ" into "meets diffraction-limited spec for this camera tier" bridges both audiences in one screen | DONE | Already implemented per PROJECT.md Validated section — reuse and extend for CODE V results too |
| One-click full pipeline replay (requirement text → final CODE V-optimized design) for live demo reliability | Decision-makers and designers both react to "watch it happen live"; a flaky multi-step manual demo kills the pitch fast. Single command / single click orchestrating the whole chain reduces demo-day failure risk | MEDIUM | This is the "一键启动" + "演示彩排" Active items in PROJECT.md — treat as differentiator, not just ops hygiene |
| Optimization convergence visualization (merit function decreasing over iterations) | Native CODE V shows this as a log/graph; surfacing it in the demo gives decision-makers a "the AI is doing real work, not magic" narrative beat, and gives designers confidence the optimizer isn't stuck in a bad local minimum | MEDIUM | Requires parsing CODE V batch log output for merit-function-per-iteration; moderate parsing effort once macro-batch integration lands |

### Anti-Features (Do NOT Build for This Milestone)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Full interactive tolerancing UI (drag sliders, live Monte Carlo re-run) | "Designers love playing with tolerances live" — feels like a natural showcase feature | Monte Carlo tolerancing is compute-heavy and CODE V is explicitly offline/batch per PROJECT.md constraints; live interactive re-run breaks the sub-second online-loop requirement and risks demo-day timeouts | Precompute tolerancing for the showcased design during the CODE V batch pass; present as a static "sensitivity ranking" table + one Monte Carlo yield number, refreshed only when a new deep-optimization run completes |
| Real-time CODE V optimization in the online interactive loop | Would let users tweak sliders and see CODE V re-optimize instantly — feels maximally impressive | PROJECT.md explicitly rules this out: CODE V is offline/deep-layer only, online path must stay sub-second; license concurrency + macro-batch startup cost make this infeasible | Keep two-speed architecture: Optiland instant preview, CODE V "Send to Deep Optimization" as an explicit, visibly-batched action with a progress narrative (this itself is a good demo beat — "kicking off the CODE V run") |
| Full native-tool feature parity (every Zemax/CODE V analysis panel: Seidel diagrams, polarization, thermal, stray light, tolerancing Monte Carlo full suite, etc.) | Feels like "matching the incumbent tool" removes all objections | Scope explosion for a demo product; most of these analyses are irrelevant to the 5-6 target scenarios (smartphone/AR/DSLR/microscope) and won't be seen by decision-makers; diminishing credibility return per engineering hour | Cover the high-frequency subset designers actually check first (spot/MTF/field-curvature-distortion/wavefront/tolerance-summary) and be explicit in the narrative that this is a focused showcase, not a CAD replacement |
| Cloud/multi-user SaaS demo mode | "What if a customer wants to try it remotely without a Windows machine with CODE V" | Already explicitly Out of Scope in PROJECT.md (CODE V is Windows-only, licensed per-seat, not designed for concurrent server use); building this now is scope creep against the stated milestone | Ship the local one-click demo; if remote demo need arises later, screen-share the local instance rather than re-architecting for hosting |
| Full ZOS-API / Zemax OpticStudio integration alongside CODE V | "Cover both major tools so any visiting designer feels at home" | PROJECT.md already rejected Zemax after measuring ZOS-API per-call overhead (10s→118s regression); reintroducing it duplicates integration effort for a slower, already-rejected path | Keep the pluggable engine interface (already planned) so Zemax could be added post-milestone if ever justified, but do not build it now |
| AI auto-generates full novel lens topology from scratch (zero seed) | "True end-to-end AI design" sounds like the ultimate wow feature | Current SOTA (see OPTIAGENT paper) still uses LLM output only as a *starting point* fed into a local/global optimizer — pure zero-shot LLM lens generation is not reliably physically valid yet; overpromising here is exactly the kind of thing that makes a senior designer distrust the whole demo | Keep the case-library-grounded approach (nearest real precedent + parameter scaling) as the generation strategy; frame CODE V's role explicitly as refining a grounded seed, matching actual state of the art rather than overclaiming |

## Feature Dependencies

```
Requirement extraction (Wizard LLM) [DONE]
    └──requires──> Parameter guards / scenario bounds [DONE]
                       └──requires──> Case library routing [DONE]
                                          └──requires──> Optiland raytrace/MTF/SVG [DONE]

Field curvature + distortion plot [NEW]
    └──requires──> Existing paraxial/trace data (already computed per-field)

Tolerance sensitivity summary [NEW]
    └──requires──> CODE V macro-batch integration [ACTIVE]
                       └──requires──> ZMX ↔ CODE V round-trip validated [ACTIVE, spike-first]

Before/after optimization comparison [DIFFERENTIATOR]
    └──requires──> CODE V macro-batch integration [ACTIVE]
    └──requires──> Existing MTF/spot-diagram rendering [DONE + NEW]

"Cross-validated by CODE V" narrative badge [DIFFERENTIATOR]
    └──requires──> Before/after optimization comparison [DIFFERENTIATOR]
    └──requires──> ZMX ↔ CODE V round-trip validated [ACTIVE]

Optimization convergence visualization [DIFFERENTIATOR]
    └──requires──> CODE V macro-batch integration [ACTIVE] (log parsing)

One-click full pipeline replay [DIFFERENTIATOR]
    └──requires──> ALL of the above wired end-to-end
    └──enhances──> Demo reliability (decision-maker narrative)

Demo web frontend [ACTIVE]
    └──requires──> All table-stakes analysis outputs surfaced via API
    └──enhances──> All differentiators (they need a stage to be shown on)

Real-time interactive CODE V tolerancing [ANTI-FEATURE]
    └──conflicts──> Sub-second online loop constraint (PROJECT.md)

Zemax OpticStudio integration [ANTI-FEATURE]
    └──conflicts──> Pluggable-engine simplicity for this milestone (already rejected on perf grounds)
```

### Dependency Notes

- **Tolerance sensitivity summary requires CODE V macro-batch integration:** CODE V's fast wavefront differential tolerancing is the credible source for sensitivity ranking; Optiland alone has no established tolerancing module in this codebase, so this feature cannot land before the CODE V spike succeeds. This makes CODE V integration the hard gate for the single most important table-stakes-for-designers item that's currently missing.
- **Field curvature + distortion plot does NOT require CODE V:** this can be built purely on top of existing Optiland trace data (per-field ray fan sampling), so it should be sequenced early/independent of the CODE V spike — it's the cheapest remaining table-stakes gap to close.
- **Before/after comparison enhances both audiences simultaneously:** it is the highest-leverage single feature because it's the one demo beat that lands with designers (numbers improve) and decision-makers (visual shrinkage, "AI + CODE V made it better") at the same time — it should be prioritized once the CODE V pipeline exists.
- **One-click pipeline replay conflicts with nothing technically but blocks on everything else being done:** it's an integration/ops feature, not a new capability, and should be the last item wired before rehearsal, per PROJECT.md's own milestone acceptance criterion ("演示彩排").
- **Real-time interactive CODE V conflicts with the sub-second constraint:** explicitly incompatible with the two-speed architecture; must not be attempted even as a "stretch goal."

## MVP Definition

### Launch With (v1 — this milestone's demo)

- [ ] Spot diagram (multi-field/wavelength, with Airy radius overlay) — designers check this first, cheapest to add on top of existing trace infra
- [ ] Field curvature + distortion plot — closes the last major native-tool-parity gap that's independent of CODE V
- [ ] Prescription/lens-data table view — literal design artifact, currently only implicit in JSON schema
- [ ] RMS wavefront error / Strehl surfaced in UI — differentiates "geometric-only toy" from "diffraction-aware real tool"
- [ ] CODE V macro-batch integration + ZMX round-trip validated (spike-first, per PROJECT.md) — hard dependency for everything below
- [ ] Before/after optimization comparison (Optiland seed vs CODE V result) — single highest-leverage differentiator, hits both audiences
- [ ] Tolerance sensitivity summary (top-N sensitive parameters from CODE V) — the credibility linchpin; without it, "deep optimization" claim rings hollow to designers
- [ ] "Cross-validated by CODE V" narrative badge — near-zero cost once above lands, big trust payoff
- [ ] One-click pipeline start + rehearsed demo flow — explicit milestone acceptance criterion in PROJECT.md

### Add After Validation (v1.x)

- [ ] Optimization convergence visualization (merit function over iterations) — nice reinforcement of "real work happening" narrative, not blocking for first rehearsal
- [ ] Full Monte Carlo yield distribution chart (beyond top-N sensitivity table) — deepens tolerancing story once basic version is proven to land with the designer audience
- [ ] Expanded scenario coverage beyond initial 5-6 (e.g. add automotive/machine-vision if factory customer asks)

### Future Consideration (v2+)

- [ ] Interactive/live tolerancing exploration UI — only if a customer explicitly asks and compute cost is solved
- [ ] Zemax OpticStudio engine plugin — only if a specific prospect's design team is Zemax-only and the relationship justifies the integration cost
- [ ] Multi-user / hosted demo mode — only if in-person Windows-machine demos become a genuine sales-motion bottleneck

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|----------------------|----------|
| Spot diagram + Airy overlay | HIGH | MEDIUM | P1 |
| Field curvature + distortion plot | HIGH | MEDIUM | P1 |
| Prescription/lens-data table | HIGH | LOW | P1 |
| RMS wavefront / Strehl surfaced | MEDIUM | MEDIUM | P1 |
| CODE V macro-batch + ZMX round-trip | HIGH (blocks all deep-tier claims) | HIGH | P1 |
| Before/after optimization comparison | HIGH | MEDIUM | P1 |
| Tolerance sensitivity summary | HIGH | HIGH | P1 |
| "Cross-validated by CODE V" badge | MEDIUM | LOW | P1 |
| One-click pipeline + rehearsal | HIGH (demo-day risk mitigation) | MEDIUM | P1 |
| Optimization convergence visualization | MEDIUM | MEDIUM | P2 |
| Full Monte Carlo yield chart | MEDIUM | HIGH | P2 |
| Interactive live tolerancing | LOW (for this audience/stage) | HIGH | P3 |
| Zemax engine plugin | LOW (no current customer demand signal) | HIGH | P3 |

**Priority key:**
- P1: Must have for launch (this milestone's demo rehearsal)
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor / Reference Feature Analysis

| Feature | Zemax OpticStudio (native) | CODE V (native) | Atelier's Approach |
|---------|----------------------------|-------------------|---------------------|
| Spot diagram | Yes, geometric, standard first analysis | Yes, geometric + pupil maps | Add on top of existing Optiland trace; match visual convention (per-field grid) so it reads as "familiar" to designers |
| Field curvature/distortion | Yes, standard combined plot | Yes | Build new module reading existing paraxial/trace data; match F-tan(theta)/F-theta convention options if time allows |
| MTF | Yes | Yes | Already implemented |
| Tolerancing | Yes (sensitivity + Monte Carlo, full suite) | Yes (fast wavefront differential tolerancing, noted stronger reputation) | Thin slice only: top-N sensitivity table sourced from CODE V batch output — enough to prove the concept, not a tolerancing module replacement |
| Starting-point generation | Manual (expert builds from scratch or catalog) / CODE V 2026 added "AI Start Expert" | CODE V 2026 added AI-driven starting points (per Keysight) | This is the core differentiator: NL requirement → case-library-grounded seed in seconds, well ahead of typical native-tool manual workflow, roughly parallel to (but pre-dating in this codebase) CODE V's own new AI Start Expert feature |
| AI-native automated design (research-stage) | N/A | N/A | OPTIAGENT (arXiv 2602.23761) validates the "LLM generates seed, local optimizer refines" pattern as current best-practice; Atelier's case-library-routing approach is a more conservative, more traceable variant of the same idea (grounds in real/patent designs rather than free-form LLM lens topology) |
| Executive/plain-language summary | No (native tools are engineer-facing only) | No | Clear differentiator — bilingual plain-language summary bridges to decision-maker audience, something neither native tool attempts |

## Sources

- [Field Curvature and Distortion — Ansys/Zemax OpticStudio User Guide](https://ansyshelp.ansys.com/public/Views/Secured/Zemax/v251/en/OpticStudio_User_Guide/OpticStudio_Help/topics/Field_Curvature_and_Distortion.html) — HIGH confidence, official docs
- [OpticsTalk: Deep Dive into Creating Wavefront, Spot Diagram, PSF, MTF — Zemax Community](https://community.zemax.com/people-pointers-9/opticstalk-deep-dive-into-creating-the-wavefront-spot-diagram-psf-and-mtf-in-opticstudio-81) — MEDIUM-HIGH, official vendor community
- [CODE V Optical Design Software — Keysight product page](https://www.keysight.com/us/en/products/software/optical-solutions-software/optical-design-solutions/codev.html) — HIGH confidence, official vendor
- [CODE V Optical Design Software brochure — Synopsys/EDS Technologies](https://edstechnologies.com/wp-content/uploads/2024/09/code-v-optical-design-software.pdf) — HIGH confidence, official vendor materials
- [CODE V 2026: Faster Optical Design with AI-Driven Starting Points — Keysight blog](https://www.keysight.com/blogs/en/tech/sim-des/code-v-faster-optical-design-ai-driven-starting-points) — HIGH confidence, official vendor, directly confirms AI-starting-point trend as 2026 SOTA
- [OPTIAGENT: A Physics-Driven Agentic Framework for Automated Optical Design — arXiv 2602.23761](https://arxiv.org/abs/2602.23761) — MEDIUM-HIGH confidence, peer-reviewed-track research, directly validates the "LLM seed + local optimizer refine" architecture this project already uses
- [AutoLens — GitHub, AI4Optics](https://github.com/AI4Optics/AutoLens) — MEDIUM confidence, open-source reference point for pure-differentiable automated design (contrast case for anti-feature reasoning)
- [The Importance of Tolerance Analysis in Optical Design — Joya Team](https://www.joyateam.com/post/the-importance-of-tolerance-analysis-in-optical-design) — MEDIUM confidence, industry blog, consistent with Synopsys/Lambda Research official framing
- [Sensitivity and Tolerance Analysis in Optics Guide — Apollo Optical](https://www.apollooptical.com/feeds/blog/sensitivity-tolerance-analysis-optics) — MEDIUM confidence, industry practitioner source
- [CODE V Optical System Tolerancing whitepaper — Synopsys](https://www.synopsys.com/content/dam/synopsys/optical-solutions/documents/whitepapers/optical-design-tolerancing.pdf) — HIGH confidence, official vendor whitepaper
- Project context: `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md` (existing capability baseline)

---
*Feature research for: AI-assisted optical lens design demo product*
*Researched: 2026-07-03*
