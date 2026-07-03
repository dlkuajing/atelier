# Project Research Summary

**Project:** Atelier — CODE V deep-optimization integration + local demo web frontend
**Domain:** CODE V macro-batch automation (Python<->Windows) + dual-engine optical design demo (Optiland fast path + CODE V deep path), single-machine local deployment for expert/decision-maker demo
**Researched:** 2026-07-03
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a dual-engine optical design demo product: an existing FastAPI backend with a fast in-process compute engine (Optiland) needs to gain a slow, offline "deep optimization" path driven by CODE V, plus a new local web frontend that shows both audiences (senior optical designers and factory decision-makers) a credible, traceable requirement-to-design-to-CODE-V-cross-validated-result narrative. Experts building this kind of system converge on the same shape everywhere: a pluggable engine abstraction with runtime capability detection (so the deep engine can be absent without breaking anything), a generic in-process async job layer (no Celery/Redis — this is single-user, single-license-seat, single-machine), CODE V driven via sequence-file/Macro-PLUS batch mode (not COM/interactive API — the same failure class that already killed Zemax ZOS-API for this project at 10s-to-118s), and a strict "everything CODE V produces must re-enter through the existing ZMX ingest pipeline" discipline so a second engine never becomes a second source of truth.

The recommended approach is: build the engine abstraction and job layer first (testable against a null/fake engine on any machine, CODE V or not), spike the ZMX-CODE V round-trip second (this validates the two riskiest unknowns — macro batch mechanics and export fidelity — before real code depends on them), then wire the real CodeVEngine into the proven job layer, then close the remaining table-stakes feature gaps (field curvature/distortion plot, tolerance sensitivity summary, prescription table) and build the before/after comparison narrative, and only then build the one-click launcher and rehearse. The frontend is htmx + Jinja2 + CDN-loaded JS (no Node toolchain) — this is a demo-reliability decision, not a technology preference: a broken npm install on demo day is an unacceptable risk this project doesn't need to take.

The key risks are not "will the feature work" but "will it look done while silently being wrong, and will it survive live demo conditions." This project has already been burned twice by exactly this failure class in its own ZMX ingest pipeline (E1-01 XASPHERE truncation, E1-02 vignetting/glass-catalog drift) — a CODE V round-trip adds a second, independent conversion boundary where the same failure class can recur (glass name not equal to optical equivalence across vendors, extended-asphere term truncation, license checkout failures that silently produce stale-but-parseable output). The single highest-leverage mitigation across all four research files is the same one: never trust "the file parses" or "exit code 0" as proof of correctness — always validate with numeric diffs (EFL, per-surface glass nd/vd, asphere term counts, artifact counts) and never compute the CODE V result live during a customer-facing demo (pre-cache it, rehearse the license/network-failure fallback explicitly).

## Key Findings

### Recommended Stack

Backend: CODE V automation via generated .seq sequence files + Macro-PLUS, invoked with plain subprocess.run()/Popen (pywin32 COM only as a documented-but-unverified fallback if the license requires an interactive session — must be spiked, not assumed). sse-starlette streams both LLM tokens and CODE V job progress over SSE. Frontend: FastAPI + Jinja2 server-rendered shell, htmx for form-submit/DOM-swap interactivity, Alpine.js for small client-only state, Plotly.js (CDN) for MTF/spot-diagram charts, Pico.css or Tailwind CDN for polish — all loaded via CDN script tags with no Node/npm build toolchain, explicitly to eliminate demo-day build-breakage risk. Vendor the CDN assets locally under app/static/vendor/ if rehearsal reveals unreliable demo-site internet.

**Core technologies:**
- CODE V .seq + Macro-PLUS batch mode — documented, supported automation surface; avoids per-call COM overhead that already disqualified Zemax ZOS-API for this project
- subprocess.run()/Popen — simplest robust invocation surface for "generate script, run headless, parse output," no COM apartment-threading complexity
- sse-starlette + htmx-sse — server-push progress/streaming without hand-rolled EventSource plumbing, needed because CODE V optimization runs take minutes
- htmx + Jinja2 + CDN JS (Plotly.js, Alpine.js) — zero Node build pipeline, matches the "single command, reliable reproduction on demo machine" constraint
- pywin32 (fallback only, unverified) — only if the ZMX-interop spike shows CODE V's license requires interactive/COM-attached automation instead of pure batch

**Critical unresolved item:** exact CODE V invocation mechanics (executable name, CLI flags, .lis/output format) are gated behind a licensed Synopsys/Keysight docs portal not reachable via web search — this must be read directly from the installed CODE V's own Macro-PLUS Reference Manual once installed, not assumed from training data or secondary sources.

### Expected Features

**Must have (table stakes — experts dismiss the demo without these):**
- Spot diagram (multi-field/wavelength, Airy-radius overlay)
- MTF plot (already implemented)
- Field curvature + distortion plot (not yet in codebase — cheapest remaining gap, no CODE V dependency)
- 2D layout/cross-section diagram (already implemented)
- Paraxial summary (already implemented)
- RMS wavefront error / Strehl ratio (partially present, needs UI surfacing)
- Prescription/lens-data table (data exists, needs formatted view)
- Tolerance sensitivity summary — the credibility linchpin; hard-gated on CODE V integration since Optiland has no tolerancing module in this codebase
- Visible data-provenance labeling (architecturally already true — parameter guards + deterministic core — needs to be visible in UI, not just true)

**Should have (differentiators):**
- Natural-language requirement to constrained design in seconds (mostly done, needs UX polish)
- Before/after optimization comparison (Optiland seed vs CODE V-refined) — single highest-leverage feature, lands with both audiences simultaneously
- "Cross-validated by CODE V" narrative badge (near-zero cost once round-trip works)
- Case-library-grounded "nearest real precedent" matching (already implemented, market it harder)
- Bilingual executive summary (already implemented, extend to CODE V results)
- One-click full pipeline replay for demo reliability

**Defer (v2+):**
- Optimization convergence visualization (P2, nice-to-have reinforcement)
- Full Monte Carlo yield distribution chart (P2, deepen tolerancing story later)
- Interactive/live tolerancing UI, Zemax OpticStudio engine plugin, cloud/multi-user SaaS mode — all explicitly out of scope for this milestone (conflict with sub-second online-loop constraint, already-rejected performance path, or out-of-scope deployment model)

### Architecture Approach

Extend the existing FastAPI backend with a ComputeEngine abstraction (FastEngine=Optiland wrapper, DeepEngine=CodeVEngine, NullDeepEngine=graceful degradation) detected once at startup via a lifespan-hook capability probe, never re-probed per-request. A generic in-process job layer (asyncio.create_task + run_in_executor, in-memory JobStore, no Celery/Redis — concurrency is capped at 1 CODE V license seat anyway) owns the lifecycle of long-running CODE V batch runs and streams progress over SSE. CODE V-specific mechanics (.seq generation, subprocess driver with Windows taskkill /F /T escalation, output parsing) live in their own module, isolated from the generic job orchestration so a second slow engine could reuse the job layer later. The single most important architectural discipline: CODE V output must always be converted to a .zmx file and handed to the existing zmx_ingest.py — never parsed into a bespoke bridge format — because that pipeline already has two hard-won bug fixes (E1-01, E1-02) that a parallel path would not inherit.

**Major components:**
1. app/core/engines/ — pluggable engine abstraction + registry + null-engine degradation (build first — lets everything downstream be developed/tested without real CODE V present)
2. app/core/jobs/ — generic async job layer (build second, against a fake SleepEngine to prove SSE plumbing before real CODE V exists)
3. app/core/codev/ — .seq generator, subprocess driver, output parser, ZMX bridge (build third/fourth, using spike findings)
4. Validation gate + case-library ingest — pure reuse of existing image_quality_floor.py/parameter_guards.py/zmx_ingest.py, no special-casing for the deep engine
5. frontend/ — separate top-level directory, htmx/Jinja2/SSE client, served by FastAPI StaticFiles for one-command launch

### Critical Pitfalls

1. **License checkout failure mid-batch silently corrupts/truncates results** — CODE V's "keep going" batch philosophy can mask a mid-run license failure as a completed run. Avoid: never trust exit-code-0 alone; verify output-artifact-count == input-count; add an explicit license self-test macro command at .seq start.
2. **ZMX-CODE V-ZMX round-trip silently degrades exactly the surfaces this project already knows are fragile** — a second independent conversion boundary on top of Optiland's own ZMX reader, same failure class as E1-01 (XASPHERE truncation) and E1-02 (glass/vignetting drift). Avoid: extend the existing EFL<2% gate with per-surface glass nd/vd numeric diffs (not name-string match) and asphere polynomial term-count diffs, pre/post round-trip, before any CODE V-sourced case enters the library.
3. **CODE V macro output is a human-readable log, not a stable machine contract** — column widths/precision can shift across versions/settings. Avoid: use Macro-PLUS WRITE commands to emit fixed-format output you control, not scraped interactive-log text; pin the CODE V version and add a canary known-answer smoke test.
4. **Demo depends on an invisible-until-it-fails resource (license seat/network) for its single most differentiated feature** — Avoid: never compute the CODE V result live during a customer demo; pre-cache all demo-case results; rehearse the network/license-down fallback explicitly and make any engine downgrade visibly flagged in the UI, never silent.
5. **Windows subprocess automation of a GUI-capable app hangs invisibly on a hidden modal/dialog** — indistinguishable from a legitimately long optimization from the outside. Avoid: use the documented pure-batch entry point only, hard timeout + CPU-activity heartbeat, taskkill /F /T (not .kill()) on timeout, and test cold-start on a genuinely clean machine (no prior manual license-acceptance clicks).

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Engine Abstraction + Null Degradation
**Rationale:** This is the seam everything else plugs into; building it first lets CI and all other dev machines exercise the full code path via NullDeepEngine from day one, rather than retrofitting degradation later. Zero dependency on CODE V actually being installed.
**Delivers:** ComputeEngine/DeepEngine Protocol, FastEngine wrapper around existing optical_engine.py (no behavior change), NullDeepEngine, startup capability-probe registry.
**Uses:** Existing FastAPI lifespan hooks; no new third-party deps.
**Avoids:** Nothing yet fails here — this phase exists specifically to make later pitfalls (license failure, hangs) isolable behind a clean interface instead of scattered through route code.

### Phase 2: Generic Job Layer (fake engine first)
**Rationale:** Prove out SSE plumbing, JobStore lifecycle, and progress streaming against a fake SleepEngine before any real CODE V dependency exists — decouples "does the async/SSE architecture work" from "does CODE V automation work."
**Delivers:** app/core/jobs/ (JobRecord, JobStore, JobRunner), sse-starlette-based /stream/{id} endpoint, asyncio.Semaphore(1) guarding submits.
**Uses:** sse-starlette, htmx-sse extension (frontend side can start consuming this against the fake engine).
**Implements:** Pattern 2 (In-Process Async Job Runner) and Pattern 4-avoidance (SSE push, not polling) from ARCHITECTURE.md.

### Phase 3: ZMX to CODE V Round-Trip Spike
**Rationale:** Validates the two riskiest unknowns (macro batch mechanics, ZMX export fidelity) before any production code depends on them. This is the project's own already-planned first Active requirement, and PITFALLS.md confirms this sequencing is correct — do not let CODE V integration proceed past this gate.
**Delivers:** Confirmed CODE V invocation mechanics (exe/flags/output format, read from the installed Macro-PLUS manual), a real .seq example round-tripped through CODE V, and an extended acceptance gate (EFL<2% + per-surface glass nd/vd diff + asphere term-count diff + VDX/VDY survival check).
**Addresses:** Feature dependency gate for "Tolerance sensitivity summary" and "Before/after comparison" — nothing downstream can be trusted without this passing.
**Avoids:** Pitfall 2 (silent round-trip degradation) — this phase's entire purpose is catching that class of bug before it reaches the demo.

### Phase 4: CODE V Engine Adapter (real integration)
**Rationale:** Now wire the real CodeVEngine into the job layer proven in Phase 2, using the spike findings from Phase 3. Building the subprocess driver defensively from day one (not retrofitting after a version-drift failure) is cheaper than fixing it later.
**Delivers:** .seq generator, subprocess driver with taskkill /F /T timeout escalation, structured-output parser (WRITE-based, not log-scraping), ZMX bridge feeding the existing zmx_ingest.py, license self-test macro, canary known-answer smoke test.
**Implements:** app/core/codev/ module; Patterns 1 and 3 from ARCHITECTURE.md.
**Avoids:** Pitfalls 1 (license mid-batch failure), 3 (output format instability), 5 (invisible hang) — all three are explicitly scoped to this phase in PITFALLS.md's phase mapping.

### Phase 5: Remaining Table-Stakes Features + Before/After Narrative
**Rationale:** Close the last native-tool-parity gaps and build the single highest-leverage differentiator once the CODE V pipeline is trustworthy. Field curvature/distortion has no CODE V dependency and could in principle be pulled earlier/parallelized, but grouping it here keeps feature work batched after the risky integration work is de-risked.
**Delivers:** Field curvature/distortion plot, prescription/lens-data table view, RMS wavefront/Strehl UI surfacing, tolerance sensitivity summary (top-N from CODE V), before/after comparison view, "Cross-validated by CODE V" badge, engine-provenance labeling in the UI.
**Addresses:** All P1 items from FEATURES.md's MVP Definition.
**Avoids:** UX Pitfall of "no visible distinction between fast/deep results" and "silent engine downgrade" — provenance labeling must be built in, not bolted on.

### Phase 6: Local Web Frontend
**Rationale:** Can start in parallel with Phases 2-3 against the existing fast-path API (spot diagrams, MTF, etc. don't need CODE V), then wire in SSE consumption once Phase 2's job layer is stable, then wire deep-tier views once Phase 5 lands.
**Delivers:** htmx + Jinja2 + Plotly.js frontend: Wizard to Design view to "Send to CODE V" to job progress to before/after comparison narrative. CDN assets vendored locally if rehearsal shows unreliable demo-site internet.
**Uses:** htmx, Alpine.js, Plotly.js, Pico.css/Tailwind (all CDN, no Node toolchain).

### Phase 7: One-Click Launch + Demo Rehearsal
**Rationale:** Last item — depends on backend, CODE V integration, and frontend all being independently runnable, and on real CODE V invocation path being fully known. This is the project's own explicit milestone acceptance criterion ("demo rehearsal").
**Delivers:** scripts/launch_demo.ps1 (single command: start uvicorn + open browser), pre-cached CODE V results for every demo case, rehearsed network/license-failure fallback with honest degradation narrative, cold-start test on a genuinely clean machine.
**Avoids:** Pitfall 4 (live demo dependency on invisible resource) — this phase's core deliverable is the pre-computation/caching discipline and the rehearsed failure path, not a "hope it works live" demo.

### Phase Ordering Rationale

- Engine abstraction and job layer come first specifically so every subsequent phase (including CI and any non-CODE-V dev machine) can be built and tested without a real CODE V install — this mirrors the project's own existing pattern of runtime engine detection/degradation.
- The ZMX round-trip spike is deliberately sequenced before the real engine adapter is built, per both ARCHITECTURE.md's suggested build order and PITFALLS.md's explicit confirmation that this sequencing is correct — it's cheaper to discover format/fidelity problems in a throwaway spike than inside production code.
- Feature work (table-stakes gaps) is grouped after the CODE V integration risk is retired, because the single most valuable feature (tolerance sensitivity summary) is hard-gated on it, and the second most valuable (before/after comparison) needs it too.
- Demo rehearsal is explicitly last and treated as an architecture-affecting phase, not just an ops checklist — the "never compute live" and "pre-cache everything" decisions must be made during CODE V integration (Phase 4), not retrofitted the day before a demo.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (ZMX to CODE V round-trip spike):** CODE V's authoritative Macro-PLUS reference and exact CLI/output-format details are gated behind a licensed docs portal not reachable via web search — this phase must read the actual installed CODE V manual directly; treat all CLI-flag/output-format assumptions in STACK.md/ARCHITECTURE.md as unverified until then.
- **Phase 4 (CODE V engine adapter):** Windows subprocess lifecycle specifics (does batch mode need a visible window, does it spawn child processes taskkill /T must catch, exact license-checkout failure behavior) are LOW-MEDIUM confidence from secondary sources only — needs empirical verification against the actual license during this phase, not assumption from general Windows-automation knowledge.
- **Phase 1 (fallback COM path, if triggered):** If Phase 3's spike reveals batch mode is insufficient and COM/interactive automation is required, there is no verified Python+CODE V COM code sample anywhere in current research — this would need a dedicated research pass before implementation.

Phases with standard patterns (skip research-phase):
- **Phase 2 (job layer):** In-process asyncio + SSE for single-user long-running tasks is a well-documented, standard FastAPI pattern (confirmed by official FastAPI docs and multiple independent sources) — no additional research needed.
- **Phase 6 (frontend):** htmx + Jinja2 + CDN JS for a server-driven demo dashboard is a well-trodden, well-documented pattern — no additional research needed.
- **Phase 5 (feature UI surfacing):** Spot diagram, field curvature/distortion, MTF, wavefront/Strehl are all standard, well-documented optical-design analysis outputs (HIGH confidence, official Zemax/Ansys docs) — implementation is engineering work on top of existing trace infrastructure, not a research gap.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM (CODE V specifics) / HIGH (frontend) | Frontend stack (htmx/Jinja2/Plotly/SSE) verified across multiple independent sources and official FastAPI docs. CODE V automation specifics rely on community/secondary sources since Synopsys/Keysight gate authoritative docs behind a licensed portal — exact invocation mechanics are an explicit required spike, not a settled fact. |
| Features | MEDIUM-HIGH | Standard optical analysis outputs (spot/MTF/field curvature/wavefront) verified against official Ansys/Zemax docs — HIGH. Tolerancing credibility norms cross-checked across multiple industry sources — HIGH. AI-design-assistant competitive landscape is a thin field, cross-checked with one directly-relevant arXiv paper (OPTIAGENT) — MEDIUM. Decision-maker narrative patterns are vendor-marketing-sourced, directionally consistent but untested on this specific audience — MEDIUM. |
| Architecture | MEDIUM-HIGH | Engine-abstraction/job-layer/SSE patterns are well-established industrial practice, confirmed by official FastAPI docs and Python subprocess docs — HIGH. CODE V-specific automation details (subprocess lifecycle nuances, macro structure) rely on secondary/community sources since Synopsys docs aren't indexable — MEDIUM. |
| Pitfalls | MEDIUM | Licensing/FlexNet facts and cross-vendor glass-dispersion disagreement are HIGH confidence (official Synopsys docs, peer-reviewed-adjacent source). Pattern-continuation reasoning from this project's own already-proven E1-01/E1-02 bugs is HIGH confidence (internal, validated). General demo-reliability wisdom is MEDIUM (cross-industry, not optics-specific). CODE V-specific failure-mode details (exact error codes, exact hang behavior) are LOW-MEDIUM since no public API reference or issue tracker exists for CODE V — mitigations correctly flagged as "verify empirically during the spike." |

**Overall confidence:** MEDIUM-HIGH — the demo-frontend and job-orchestration architecture is solidly grounded in well-documented patterns; the CODE V-specific automation layer is the one genuine unknown across all four files, and every research file independently arrives at the same mitigation: spike it first, validate empirically, never assume from secondary sources.

### Gaps to Address

- **Exact CODE V CLI/invocation mechanics** (executable name, batch flags, output file format): unresolvable via public research — must be read from the installed CODE V's own Macro-PLUS Reference Manual during Phase 3's spike before any production automation code is written.
- **COM fallback path feasibility**: no verified Python+CODE V COM sample exists anywhere; only pursue if Phase 3 proves batch mode insufficient, and treat as its own research spike if triggered.
- **CODE V license type on the actual demo machine** (node-locked vs. floating): determines whether Pitfall 4 (network/license-dependent live failure) is even a real risk — must be confirmed once CODE V is installed, and if floating-only, escalate rather than silently accept the demo-day risk.
- **CODE V catalog completeness for known-fragile glass materials** (Japanese resins, CDGM — already flagged fragile on the Optiland side per E1-02): unverified whether CODE V's catalog is better or worse; treat as a priority stress-test target during the round-trip spike, not an assumption either way.

## Sources

### Primary (HIGH confidence)
- D:\atelier\.planning\PROJECT.md — authoritative source for already-made architecture decisions (macro-batch over interactive API, dual-engine design, local-service constraint)
- D:\atelier\.planning\codebase\ARCHITECTURE.md — existing system structure baseline
- D:\atelier\.planning\codebase\CONCERNS.md — E1-01/E1-02 bug history, used as pattern-continuation evidence for CODE V round-trip risk
- FastAPI official docs (Background Tasks) — https://fastapi.tiangolo.com/reference/background/
- Python subprocess official docs — https://docs.python.org/3/library/subprocess.html
- Synopsys Licensing QuickStart (FlexNet/SCL confirmation) — https://www.synopsys.com/optical-solutions/support/choosing-license-option.html
- Ansys/Zemax OpticStudio User Guide (field curvature/distortion, spot/MTF standards) — official vendor docs
- Keysight CODE V product pages and 2026 AI-starting-point blog — official vendor

### Secondary (MEDIUM confidence)
- github.com/BrianJKoopman/autov — independent confirmation of sequence-file batch as CODE V's practitioner automation pattern
- John Loomis CODE V teaching notes (johnloomis.org) — .seq semantics, batch "continue on progress" behavior
- OPTIAGENT arXiv 2602.23761 — validates "LLM seed + local optimizer refine" as current SOTA, directly parallel to this project's architecture
- ResearchGate cross-vendor glass dispersion comparison — confirms glass-name is not proof of optical-equivalence across CODE V/OSLO/Zemax
- OpTaliX file-conversion documentation — confirms format-converter incompleteness as an industry-wide pattern
- htmx vs React/Svelte comparisons (dev.to, Medium) — consistent convergence on htmx for server-driven demo dashboards

### Tertiary (LOW confidence)
- "Macro in CODE V: A Comprehensive Training Guide" (manuals.plus) and github.com/ksyoung/CodeV_macros — secondary/community sources on Macro-PLUS structure, needs verification against the actual installed CODE V manual
- pywin32 COM fallback pattern — no verified Python+CODE V COM code sample found anywhere; treat as unverified until spiked

---
*Research completed: 2026-07-03*
*Ready for roadmap: yes*
