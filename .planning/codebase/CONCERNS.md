# Codebase Concerns

**Analysis Date:** 2026-07-03

## Tech Debt

**Optiland 0.6.0 compatibility patches:**
- Issue: Runtime monkey-patches required for three upstream Optiland 0.6 bugs that break real smartphone designs
  - NumPy 2.x coordinate-system serialization fails on shape-(1,) arrays 
  - XASPHERE (Extended Asphere) surface type unsupported, silently drops coefficients → 407µm RMS error
  - Glass-material catalog incomplete (Japanese resins + CDGM glasses), falls back to placeholders → 18% EFL drift
- Files: `app/core/optiland_patches.py`, `app/core/zmx_materials.py`, `app/core/zmx_ingest.py`
- Impact: Every ZMX load must apply patches at module-import time; patches become maintenance debt when Optiland ships fixes
- Fix approach: Monitor Optiland releases (>=0.7 target) and retire patches incrementally; validate each retirement with full-ammo test suite

**Coordinate-system array serialization (NumPy 2.x):**
- Issue: WideAngle100FOV reference design's array-style surface construction yields numpy arrays of shape (1,) instead of scalars for coordinates; float() coercion fails
- Files: `app/core/optiland_patches.py:_patch_coordinate_system_to_dict()`
- Trigger: Reliable on smartphone-ultrawide scenarios; other scenarios (Telephoto, CookeTriplet) use scalar z values and miss this
- Workaround: `_safe_float()` converts via `.item()` which handles both 0-d and shape-(1,) arrays
- Retirement: When Optiland >= 0.7 includes upstream fix

**XASPHERE coefficient mapping off-by-one error (E1-01):**
- Issue: Previous code mapped XDAT 3 → conic (should stay as-is) and XDAT 4..11 → param_0..7, losing the first polynomial term AND truncating 10-term files to 8 terms; off-axis image quality destroyed silently while EFL<2% gate never caught it
- Files: `app/core/optiland_patches.py:_patch_zemax_xasphere_reader()`
- Evidence: 9 XASPHERE seeds silently broke; dropped terms are O(1) at clear-aperture edge
- Status: E1-01 merged; correct mapping now param_i = XDAT(3+i), preserves all 10 terms
- Risk: Any new ZMX ingest **must** validate via `tests/test_zmx_ingest.py::test_load_efl_within_2pct` (EFL<2% accuracy gate)

**Glass-material fidelity (E1-02 upstream issue):**
- Issue: Optiland's catalog doesn't recognize real materials in smartphone designs (ZEONEX/OKP/APL/EP/CDGM), falls back to placeholder nd/vd
- Files: `app/core/optiland_patches.py:_patch_zemax_glass_materials()`, `app/core/zmx_materials.py`
- Impact: 18% EFL drift on real 5-element designs before real table applied; paraxial EFL gate didn't catch it (gate is 2% on already-broken nominal)
- Workaround: `app/core/zmx_materials.MATERIAL_ND_VD` lookup table (public datasheet nd/vd); patch rebuilds AbbeMaterial only if catalog miss AND name in real table
- Retirement: When Optiland ships these materials in its catalog (>=0.7?)

## Known Bugs

**Patent seed image-height routability blocker (E2-01 batch 0 → batch 2 work item):**
- Symptoms: Patent-sourced seeds (US* case_id prefix) ingested from IDMxS have no direct ZMX image-height declaration; runtime image_height_mm extracts from case_id filename or defaults to 0.0 → routing can't find them
- Files: `app/core/case_library.py:_case_image_height_mm()` (line 563-573), `scripts/e2_intake.py` (patent-seed manifest builder)
- Root cause: Patent seeds extracted from IDMxS tool don't carry image-height metadata in ZMX file itself; case_id filename is only source (e.g. `5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.33` → extracts IMH=2.9); if extraction fails, defaults to 0.0
- Impact: Seeds with IMH=0.0 have zero image-height weight in routing (22 patent seeds in batch 1 affected); cannot route unless EFL/FOV/F# are perfect matches
- Current mitigation: E1-02 fixed vignetting-MTF artifacts; E2-01 batch 1 (22 seeds) dual-source-verified with real embodiment cross-validation gate (→ PASS verdict confirms ZMX data integrity); batch 1 is routable because EFL/FOV/F# happen to cluster real phones
- Blocker status: **Cleared at evidence layer** (E2-01 batch 1 has real full-field high-FOV evidence now); high-FOV acquisition gap from batch 0 is no longer a no-seed zone
- Next work: E2 batch 2 "**Routability-First Reconstruction**" — three-piece work item:
  1. **Real IMH from ZMX**: Compute true image height via paraxial trace (not case_id extraction)
  2. **Routing re-anchor**: Rebuild seed-selection distance function to use computed IMH instead of filename extraction
  3. **Evaluation re-anchor**: Update all downstream assessment / acceptance-task pipelines to use computed IMH

**Vignetting artifact in older seeds (E1-02 resolved):**
- Symptoms: VDX/VDY (vignetting decenter) lost after out-of-focus surface handling; off-axis MTF artificially flatlined
- Files: Resolved in commit `31a4c70` (E1-02 fix)
- Evidence: Two genuinely-broken ingest seeds (RMS ~1200/4700 µm, floor gap ~12/47) remain from batch 0; E1-02 exonerated remaining artifact seeds
- Status: FIXED; `tests/test_zmx_ingest.py` validates via `test_load_efl_within_2pct` gate

## Security Considerations

**LLM API key exposure in CI placeholders:**
- Risk: CI uses `OPENAI_API_KEY: ci-placeholder` and `OPENAI_BASE_URL: https://example.invalid/v1` to mock LLM calls; production credentials must never be committed
- Files: `.github/workflows/ci.yml`, `app/main.py` (loads via pydantic-settings from `.env` only)
- Current mitigation: `.env` is gitignored; CI uses env-var injection; LLM calls are mocked in tests
- Recommendations: 
  - Never hardcode API keys in source code (currently not done)
  - Keep CI env placeholders non-production (currently correct)
  - Audit `.env` handling in `app/core/config.py` before any prod deployment

**Windows UTF-8 encoding breakage:**
- Risk: Case JSON files are UTF-8; Chinese Windows defaults to GBK → silent corruption or test failures
- Files: `tests/test_*.py` (all tests), `app/core/case_library.py:_case_image_height_mm()` reads case JSON
- Current mitigation: Documented in `AGENTS.md` ("Windows 本机跑测试必须 `PYTHONUTF8=1`"); CI runs on Ubuntu so not affected
- Recommendations:
  - Add CI check: run a subset of tests on Windows (if ever needed) with `PYTHONUTF8=1`
  - Document in `CONTRIBUTING.md` or `.github/TESTING.md`
  - Do NOT hardcode UTF-8 encoding in Windows-only paths; use explicit `encoding="utf-8"` in `.open()` calls

## Performance Bottlenecks

**MTF ray-aiming hang on real multi-element designs:**
- Problem: Real zmx files define ~12 RealImageHeight fields; GeometricMTF ray-aims by iteratively solving for object-space ray → >25 s or non-terminating on real designs
- Files: `app/core/zmx_ingest.py:regularize_fields_to_angle()` (lines 80-102)
- Cause: Inverse solve for ray-landing-height is numerically expensive on multi-element systems
- Improvement path: Switch to ANGLE fields (direct ray-direction aiming, no inverse solve) and collapse 12 dense fields to 4 canonical MTF fractions
- Evidence: Verified fix drops MTF + SVG generation from >25 s to ~0.3 s; full field (1.0) is still stable after XASPHERE coefficient fix

**Large case_library.py monolith:**
- Problem: `app/core/case_library.py` is 14,617 lines; contains paraxial calc + MTF + layout-SVG + routing + seed-selection + acceptance-gate + full design-assessment pipeline
- Files: `app/core/case_library.py`
- Cause: Historical accretion during E0/E1/E2 phases; no intermediate modularization
- Impact: Load time ~300 ms per import (LRU cache @ module level mitigates runtime), but dev/debug cycle slow
- Improvement path: 
  - Extract seed-selection routing into `app/core/seed_routing.py`
  - Extract acceptance-gate logic into `app/core/acceptance_gates.py`
  - Extract design-assessment builders into `app/core/design_assessment.py`
  - Preserve case_library.py for paraxial + MTF + layout-SVG pipelines only

**Patent seed metadata extraction regex (fragile):**
- Problem: `_case_image_height_mm()` extracts image height via regex from case_id filename; falls back to 0.0 on parse failure
- Files: `app/core/case_library.py:_case_image_height_mm()` (line 567-573), `app/core/optical_sample.py` (CaseMetadata definition)
- Cause: Patent seeds have no ZMX-embedded image height; filename is single source of truth
- Risk: If manifest or ingest tool renames cases, regex breaks silently → 0.0 routability ghost seed
- Improvement: E2 batch 2 should compute real IMH from paraxial trace (eliminates filename dependency)

## Fragile Areas

**Patent seed full-embodiment cross-validation gate:**
- Files: `scripts/e2_intake.py:cross_validate_embodiments()`, `tests/test_e2_intake_gate.py`
- Why fragile: 
  1. Trap 1 (E2-01 batch 1 bug): Embodiment-1-only check → false negatives on designs matching embodiment 3 exactly but embodiment 1 wildly different (test case: US10007086B2)
  2. Trap 2 (E2-01 batch 1 bug): Perfect 0.0 EFL/FOV diff demoted by `x or default` falsy trap → true matches treated as missing (test case: embodiment 2 exact match)
  3. Trap 3 (unreported): TTL comparison may use ratio-form ("TL/ImgH = 1.5") which requires reliable image_height_mm; if IMH=0.0, TTL check becomes meaningless
- Safe modification: 
  - Always scan all embodiments, not just first
  - Use explicit None-check (`result is None`) instead of falsy coercion
  - Validate IMH before TTL ratio checks; emit CAVEAT if IMH=0.0
- Test coverage: `tests/test_e2_intake_gate.py` covers traps 1 & 2; add test for trap 3 (TTL ratio w/ IMH=0.0)

**Optiland NaN propagation in wide-FOV edge fields:**
- Files: `app/core/case_library.py:_mtf_with_fallback()` (full-field recovery probe)
- Why fragile: Some designs' 1.0-field edge rays trace to NaN, crashing MTF; fallback retries with progressively smaller field sets (0.85, 0.8, 0.7, 0.5)
- Observed: WideAngle100FOV (Optiland reference) and high-FOV patent seeds (>89° FOV)
- Safe modification: 
  - Always run `protected_full_field_recovery_probe()` during ingest validation
  - Log fallback field fraction to metadata (currently done: `sample.metadata.mtf_max_field_frac`)
  - Test new seeds against `tests/test_seed_intake_audit.py::test_mtf_fallback_inventory_keeps_085_seed_payloads()` to verify edge-cliff behavior
- Impact: Metadata `mtf_max_field_frac` (0.7, 0.8, 0.85, 1.0) drives routing field-stability tiebreaking

**Routing distance function relies on image_height_mm weight:**
- Files: `app/core/case_library.py:match_case()` → `_seed_distance_parts()` (line ~750)
- Why fragile: Weight `imh` = 0.30 if IMH not None else 0.0
  - Patent seeds (IMH=0.0 from failed extraction) get 0 weight → ignore image_height dimension entirely
  - Even perfect parameter matches can't overcome image-height misalignment if IMH is known
  - Ghost-seed problem: Patent case_id extraction can fail → 0.0 weight → wrong routing
- Safe modification: 
  - E2 batch 2: Compute real IMH from paraxial trace (eliminate filename dependency)
  - Add pre-routing validation: If IMH=0.0 and case is patent-sourced, emit WARNING log + add IMH to unsolved-metadata inventory
  - Test: `tests/test_case_library.py` should validate that all cases with non-None IMH are routable with correct image-height tiebreaking

**AbbeMaterial polynomial dispersion model hidden footgun:**
- Files: `app/core/zmx_materials.py:_abbe()` (line 76-87)
- Why fragile: Optiland 0.6 defaults to `model='polynomial'`; v0.7 switches default to `'buchdahl'`, which shifts indices and invalidates EFL<2% verification gate
- Risk: Silent dispatch of new Optiland → different MTF/RMS under identical inputs → acceptance gate re-baseline required
- Safe modification: 
  - Explicitly pin `model='polynomial'` in all AbbeMaterial() calls (done in `_abbe()`, not elsewhere)
  - Add test: `tests/test_optical_engine.py` should validate that AbbeMaterial always uses polynomial, even if Optiland default changes
  - Pre-deployment gate: If Optiland version bumps, re-run full EFL<2% gate on all ammo cases

## Scaling Limits

**ZMX case library singleton caching:**
- Current capacity: 39 cases (17 real + 22 patent); load time ~300 ms @ 3.12 cold
- Limit: LRU cache @ module level; no cache eviction strategy; library grows as E2 batches accumulate
- Scaling path: 
  - E2-01 batch 1 (22 seeds) → 39 total; batch 2-4 projected to reach ~100 cases by EOY
  - At 100 cases, load time ~800 ms; paraxial + MTF per case ~0.5 s per generation, so ingest time ~50 s for full batch
  - Cache remains in-memory for daemon lifetime; no disk persistence layer needed for <1000 cases
  - If >500 cases: Consider lazy-loading (on-demand sample building) instead of preloading all in `load_case_library()`

**Parameter-guard bounds calibration static data:**
- Current: Scenario bounds hard-coded in `app/core/parameter_guards.py:SCENARIO_BOUNDS`
- Limit: Manual stat derivation from ammo cases; comments note when bounds were last re-derived (E2-01 batch 1 for wide/ultrawide)
- Scaling path: 
  - E2-01 batch 1 derivation: "min-5%/max+5% statistical derivation" from 31 wide-FOV cases
  - After batch 2 (more telephoto evidence): Re-derive TELEPHOTO bounds; current hard-coded values are not validated against real batch 1 ammo
  - Add script: `scripts/recompute_parameter_bounds.py` (like `scripts/compute_bounds_stats.py`) to auto-derivation as ammo grows

## Dependencies at Risk

**Optiland 0.6 EOL pending:**
- Risk: Three upstream bugs requiring production patches; fixes promised in 0.7 (not yet released)
- Impact: Dependency on 0.6.0 exact pin to avoid 0.7-dev instability; upgrade blocked until 0.7 ships stable
- Migration plan: 
  - Monitor Optiland releases; test 0.7 release candidate in isolated branch
  - Retire patches incrementally (coordinate-system first, then XASPHERE, then glass materials)
  - Re-validate EFL<2% gate after each retirement
  - Full test suite must pass before merging upgrade

**OpenAI API client library version pinning:**
- Current: `openai>=1.50.0` (loose lower bound); CI uses mock
- Risk: v1.5x changed parameter names; newer versions may change API surface
- Recommendation: Tighten to `openai>=1.50.0,<2.0.0` to prevent major-version surprises

## Missing Critical Features

**Real image-height computation for patent seeds:**
- Problem: Patent seeds have no ZMX-embedded image-height; routine falls back to filename extraction → 0.0 on parse failure
- Blocks: 
  - Routing cannot weight image-height dimension for patent seeds
  - Acceptance-task export cannot fill true image-height in design-handoff packets
  - Embodiment cross-validation TTL/ImgH ratio checks become meaningless if IMH=0.0
- Scheduled: E2 batch 2 "routability-first reconstruction" (see Known Bugs section)

**Embodiment-independent image-height validation:**
- Problem: Cross-validation gate validates EFL/FOV/TTL per embodiment; image-height left unchecked
- Blocks: Can't verify that ZMX-computed image_height matches patent's declared design envelope
- Example: 5P_F1.9 design claims ImgH=2.9; if ZMX actually computes 3.2, gate doesn't catch it
- Recommendation: Add image-height cross-check to `cross_validate_embodiments()` (with optional caveat if off by <5%)

**Fidelity audit trail for glass-material substitutions:**
- Problem: `_patch_zemax_glass_materials()` rebuilds AbbeMaterial if zmx placeholder missed; no log of what was substituted
- Blocks: Can't trace which designs relied on real-table fallback vs. catalog-resolved glasses
- Impact: Design-handoff packets should disclose which surfaces use fallback glasses for manufacturing communication
- Recommendation: Add audit metadata to CaseMetadata: list of surfaces with material fallback applied

## Test Coverage Gaps

**Windows UTF-8 encoding (PYTHONUTF8=1) not validated in CI:**
- What's not tested: Loading case JSON on Windows GBK default
- Files: `tests/test_case_library.py`, `tests/test_api_optical.py` (API loads cases)
- Risk: Windows developers may silently corrupt UTF-8 case metadata if PYTHONUTF8 not set; CI doesn't catch it
- Priority: Medium (CI runs on Ubuntu, but if Windows agents ever added, this breaks)
- Recommendation: 
  - Document PYTHONUTF8=1 requirement in CONTRIBUTING.md (already in AGENTS.md)
  - Add CI check: intentionally test with `PYTHONUTF8=0` and expect failures (to verify the requirement is real)

**Patent seed manifest generation (e2_intake.py) end-to-end:**
- What's not tested: `scripts/e2_intake.py` full pipeline (read staging directory, run cross-validation gate, emit manifest)
- Files: `scripts/e2_intake.py` (no test file)
- Risk: Batch ingestion may fail silently if gate logic regresses; manifest may contain invalid entries
- Priority: High (batch 2+ depends on this automation)
- Recommendation: 
  - Add `tests/test_e2_intake_full_pipeline.py` with sample IDMxS staging directory (3-5 mock ZMX files + jsonl)
  - Validate manifest structure, embodiment cross-check PASS verdicts, and case_id format

**Image-height extraction regex robustness:**
- What's not tested: `_case_image_height_mm()` regex against malformed case_id filenames
- Files: `app/core/case_library.py:_case_image_height_mm()` (no dedicated unit test)
- Risk: Regression to 0.0 if naming scheme changes or manifest inconsistency introduced
- Priority: Low (naming scheme is stable, but safety-critical for routing)
- Recommendation: 
  - Add `tests/test_case_library.py::test_image_height_extraction_edge_cases()` covering:
    - Valid: `5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.33` → 2.9
    - Missing component: `5P_F1.9_FOV89.5_EFL2.8_TTL4.33` → 0.0 (should log WARNING)
    - Malformed: `5P_INVALID_FOV_EFL_TTL` → 0.0
    - Patent case_id (no filename IMH): `US20170003482A1` → 0.0 (expected; computed later)

**Paraxial EFL fidelity gate (EFL<2%) not documented in test name:**
- What's not tested explicitly by name: `tests/test_zmx_ingest.py::test_load_efl_within_2pct` is the gate, but its role as the **production acceptance criterion** is buried in comments
- Priority: Low (test exists and is critical, but visibility could improve)
- Recommendation: Add docstring to the test explaining that <2% EFL error is the production-readiness gate for all new ammo

---

*Concerns audit: 2026-07-03*
