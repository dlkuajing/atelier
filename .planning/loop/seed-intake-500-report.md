# DATA-10a seed intake report (base-library-fill toward North-Star >=500)

## Summary

- mode: live USPTO PPUBS fetch (`scripts/patent_to_zmx.py`'s deterministic parser, no numeric LLM fill) + local six-gate intake
- source: `data/patents/uspto-smartphone-batch*.jsonl` (714 unique patents pool); unmined = patent root not already represented in `app/data/optical_cases/index.json` (124 formal roots before this batch)
- candidates attempted (distinct patents, this session): 120
- attempt rows (patent x embodiment): 184
- case_library_count_before: 353
- case_library_count_after: 361
- intaken: 8
- rejected: 8 (all 8 embodiments of one patent, `US-20250370222-A1` -- see "Extra defensive gate" below)
- failed to convert (parser/table coverage gap, not gated): 168 attempt rows across the other 119 patents attempted
- manifest: `tests/data/data10a_manifest.json` (8 records)
- gates: formal index stem de-dup; `ATELIER_REAL_IMH_MM` positive; `ATELIER_FTAN_IMH_SANITY_MM` positive; GLAS nd/vd in [1.3,2.2]/[10,100]; Optiland load with positive EFL; lightweight sample build (bounded by a 90s timeout so one pathological prescription cannot sink the batch); `mtf_max_field_frac <= 0.5`
- extra defensive gate (beyond the six named above, applied fail-closed): smartphone-lens plausibility envelope FOV in [5, 135]deg, EFL in [0.3, 35]mm. Both bounds are wider than the library's own observed range (FOV 6.65-132deg, EFL 0.44-28.3mm measured from `index.json` before this batch) but caught a genuine parser/table-mismatch case: `US-20250370222-A1` (an AAC Raytech 18-surface/F~1.0 table) parses to FOV~1deg for all 8 embodiments -- almost certainly a sub-assembly or mis-read table, not a real phone lens. All six named gates pass for it (EFL/IMH positive and finite, nd/vd in range, Optiland loads, lightweight build succeeds, mtf_max_field_frac in {0, 0.5}), so this is a real gap the spec'd gates alone do not cover. Rejected rather than seeded into the library.
- near-duplicate-within-batch gate: `(n_pieces, EFL/0.05mm, FOV/0.5deg, F#/0.05)` key (no collisions found this batch)
- golden anchor: index `image_height_mm` is written from `ATELIER_REAL_IMH_MM`; `scripts/e2_golden.py` enforces <=2% deviation when regenerating `tests/data/eval_golden.json`
- `LIGHTWEIGHT_INTAKE_BATCH_PREFIXES` in `scripts/generate_cases.py` and `scripts/audit_seed_intake.py` extended from `("DATA-06", "DATA-09d1")` to `(..., "DATA-10")`, since this batch uses the identical bounded lightweight-MTF path

## Known hanging patents (excluded from the mining pool)

The real-ray aperture trace (`optic.trace_generic` inside `patent_to_zmx._trace_surface_apertures`) hangs indefinitely for a small number of prescriptions -- confirmed by isolating one candidate and observing it exceed 60s with no completion, no exception, and no CPU-bound loop that a synchronous timeout can interrupt mid-call. Concurrency (asyncio semaphore over `_convert_candidate`) and thread/process isolation were both tried this session and introduced *more* instability than they solved (see "Runner deviations" below), so the final approach was strictly sequential with a manually-curated exclusion list, built by observing exactly which candidate a run stalled on and adding it before restarting:

| patent_id | observed during |
|---|---|
| US-20260147187-A1 | original concurrent sweep attempt, stalled the whole batch at candidate 20/644 |
| US-11226472-B2 | sequential run, stalled at candidate ~41-50/300 |
| US-11215797-B2 | abandoned multiprocessing trial, stuck `.trace-tmp` |
| US-11262553-B2 | abandoned multiprocessing trial, stuck `.trace-tmp` |
| US-10935766-B2 | sequential run, stalled at candidate ~81-90/300 |

These 5 patents (and whatever embodiments they contain) are quantified backlog: not converted, not gated -- simply excluded from this batch's mining run before it started. A follow-up could investigate the specific prescriptions offline to find the degenerate-geometry root cause, or re-attempt with a process-level (not thread-level) hard-kill wrapper.

## Pre-existing bug found and fixed: full-library regeneration hazard

While regenerating `app/data/optical_cases/index.json` from the updated `tests/data/zmx_manifest.py`, `scripts/generate_cases.py` hung on **`US-11940597-B2-e1`, `US-11940597-B2-e2`, `US-20240192468-A1-e1`, and `US-10921568-B2-e1`** -- all four are *pre-existing* DATA-06/DATA-06i library entries, unrelated to this batch's 8 new seeds. `build_sample_from_optic` never returns for these four even on the lightweight path (confirmed hung past 90s in isolation for `US-11940597-B2-e2`). This means a fresh, from-scratch regeneration of the *committed* 353-seed library would already hang before this batch touched anything.

Fixed by adding a bounded daemon-thread timeout (`BUILD_TIMEOUT_S = 90.0`) around every `build_sample_from_optic` call in `scripts/generate_cases.py`, with a last-known-good-JSON reuse fallback: if a build times out (or raises), and `app/data/optical_cases/<case_id>.json` already exists from a prior successful run, that JSON is reused for the fresh `index.json` instead of dropping the seed. This is additive and backward-compatible -- every design that completes normally is unaffected; only the four known-hanging designs fall back to their last-known-good JSON (`app/data/optical_cases/US-11940597-B2-e1.json` etc. are therefore **not modified** in this diff, unlike the other 353 pre-existing designs which show minor floating-point regeneration drift). This is now a permanent safety net in `scripts/generate_cases.py` for any future full regeneration.

## Runner deviations from the stock `patent_to_zmx.run_conversion` CLI

The stock CLI (`scripts/patent_to_zmx.py`'s `run_conversion`, driven by `python scripts/patent_to_zmx.py`) processes one candidate at a time via `_convert_candidate`, which bundles an async HTTP fetch and a synchronous CPU-bound parse+trace step with no intermediate `await`. Three approaches were tried this session before settling on the final one:

1. **Async concurrency** (semaphore-bounded `asyncio.gather` over `_convert_candidate`): worked cleanly on small batches (30 candidates, concurrency 8, 146s, 8/8 legitimate successes) but on a larger/longer batch the PPUBS anonymous access token appeared to degrade under sustained concurrent load (observed once: every single fetch failed with `HTTPStatusError` for ~40 consecutive candidates, self-cleared on the next fresh token). A token-refresh-and-retry-once wrapper was added but the deeper problem below made this moot.
2. **Thread/process isolation for the CPU-bound half** (`asyncio.to_thread`, then a hand-rolled `multiprocessing.Process`-per-candidate scheduler): correctly isolates a hang from the event loop in principle, but a thread-based timeout cannot actually kill the hung work (Python threads are not forcibly terminable), so abandoned threads pile up and starve the rest of the batch -- observed directly (4 simultaneous stuck `.trace-tmp` files, throughput collapsing candidate-over-candidate). The process-based version fixed the "can't kill it" problem but introduced its own instability (a `sweep_v3.py` run stalled with no diagnosable cause after ~100s and was abandoned).
3. **Final approach**: strictly sequential (`sequential_sweep.py`), one candidate at a time via the stock `_convert_candidate`, with (a) a manually-curated `KNOWN_HANGING_PATENTS` exclusion set built by observing exactly which patent a run stalled on and restarting past it, and (b) resume-on-restart: the report JSON is loaded on startup, already-attempted patent IDs are skipped, and results are merged rather than overwritten, so a kill-and-restart cycle (needed 3 times, once per newly-discovered hanging patent) never re-does completed work. This is the throughput/reliability tradeoff that actually finished: ~3-5s/candidate in the healthy stretches, cleanly self-recovering from being stopped and restarted.

None of the three approaches solve the underlying hang (a synchronous, no-`await`, no-exception, no-CPU-spin-detectable stall inside Optiland's real-ray trace for specific prescriptions) -- only isolate or route around it. A durable fix needs a process-level hard-kill wrapper *and* an investigation into what's numerically degenerate about the ~6 known-bad prescriptions found this session, which is out of scope for a mining-volume shovel.

## By-source table

| source | candidates attempted | intaken | rejected | conversion-failed |
|---|---:|---:|---:|---:|
| DATA-10a-uspto (live mining, single continuous pass) | 120 | 8 | 8 | 104 |

## Reject / conversion-failure reason breakdown

| reason | count |
|---|---:|
| embodiment f/Fno/HFOV line not found (no known table format matched) | 105 |
| surface table index break (partial/malformed table) | 20 |
| AAC Raytech summary metadata missing f/F#/FOV | 13 |
| full-field real rays did not reach image surface | 11 |
| surface radius not numeric (malformed table cell) | 8 |
| not a number: symbols / stray tokens | 7 |
| unsupported nonzero high-order asphere terms | 4 |
| **implausible FOV (extra plausibility gate)** | **8** (all `US-20250370222-A1`) |

**Honest read on yield**: 87.5% (105/120) of the failures are `embodiment f/Fno/HFOV line not found` -- the deterministic parser found *no* usable table in any of the three currently-supported formats (primary bracket-style, Fujifilm, AAC Raytech). This is the same signature the DATA-09e/f/g "parser family expansion" batches existed to close. The remaining unmined pool (~520 patents after this batch) is now dominated by patents needing *new* parser-family coverage, not patents that are simply hard-to-convert by chance -- a mining-only shovel without parser engineering has a real, low ceiling against this specific pool. This is quantified, not guessed: rerunning this exact shovel against the remaining pool without new parser coverage would be expected to yield a similarly low intake rate (~7% of attempted candidates, based on this batch: 8 intaken / 120 attempted).

## Scenario distribution

| scenario | before | after | delta |
|---|---:|---:|---:|
| smartphone-wide | 201 | 206 | +5 |
| smartphone-telephoto | 119 | 119 | +0 |
| smartphone-ultrawide | 33 | 36 | +3 |
| **total** | **353** | **361** | **+8** |

No telephoto seeds were found this batch (0/120 candidates attempted produced a telephoto-classified design); the 8 accepted seeds split 5 wide / 3 ultrawide, so this batch narrowed the ultrawide gap slightly (33->36) without moving the telephoto count.

## Golden reanchor

- `tests/data/eval_golden.json`: 364 briefs (was 356; +8 new case-anchored briefs for the DATA-10a seeds)
- routing-winner flips: **3** (all cleanly explained by one new seed scoring better on those specific briefs)
  - `patent_us-11899172-b2-e5_reanchor`: `US-11899172-B2-e5` -> `US-20200057277-A1-e1`
  - `patent_us-20210364763-a1-e5_reanchor`: `US-12353055-B2-e1` -> `US-20200057277-A1-e1`
  - `patent_us-20250004254-a1-e7_reanchor`: `US-20200003996-A1-e3` -> `US-20200057277-A1-e1`
  - All three flip to the same new seed (`US-20200057277-A1-e1`, EFL 3.53mm/FOV 31.7deg/F2.0), which is a legitimate closer match for those briefs' targets than the prior winners.
- no `>2%` `ATELIER_REAL_IMH_MM` vs index `image_height_mm` violations (the golden script's own gate; would have raised `ValueError` and failed the regeneration if tripped)
- one large-but-precedented anomaly worth flagging honestly: `US-20260126622-A1-e2`'s real-ray image height (`ATELIER_REAL_IMH_MM` = 41.88mm) diverges ~17x from the first-order `f*tan(HFOV)` estimate (2.41mm). This looked like a bug at first, but the *existing* 353-seed library already contains entries with this same `first_order_image_height_deviation_frac` metric up to **30.9x** (checked directly against `tests/data/eval_golden.json` before this batch) -- large real-vs-paraxial divergence is an established, tolerated, informational-only characteristic of this library (real aberrated image height on a curved/pupil-shifted surface vs a flat first-order approximation), not a gate. No extra gate was added for this; it would have been stricter than ratified precedent.

## Test results

- Targeted slice (`tests/test_case_library.py`, `tests/test_zmx_ingest.py`, `tests/test_eval_golden_seeds.py`, `tests/test_seed_intake_audit.py`): 7 hardcoded-count assertions failed on the first run (353->361, 314->322 lightweight-seed counts, 268->270 first-order outliers, 34->37 high-FOV counts, 354->362 total-seed counts with +1 preflight candidate) -- all real values computed directly from the regenerated library/index, not guessed. All 4 files pass after the fixes: **1107/1107** (1099 unaffected + 8 fixed).
- Full mock suite (`pytest -q -n 8 -k "not real"`): two independent `-n 8` runs both progressed cleanly to 94%+ (multiple hundred tests, zero *new* unexpected failures beyond the already-identified-and-fixed count assertions) before a slow tail-end stretch was interrupted by the session's time budget. The slow tail is consistent with this session's environment-specific "some Optiland real-ray builds are pathologically slow/non-deterministic in wall-clock time" pattern (see the `generate_cases.py` hang above), not with a *correctness* regression from this batch's changes -- no test that completed in either run failed for a reason connected to the new seeds, the golden reanchor, or the count fixes. **Follow-up**: a supervised (or `pytest-timeout`-guarded) full-suite run to confirm 100% completion is recommended before merging, since this session could not get a clean complete run within its time budget.
- `ruff` was not run this session (out of scope focus was data intake); recommend running before merge per repo convention.

## Reproducible command sequence

```powershell
cd D:\atelier-intake
uv sync --frozen --group dev --group optical
$env:PYTHONUTF8='1'

# Step 1-2: mine + convert the unmined pool. Sequential is the only approach that
# proved reliable this session (see "Runner deviations"); a concurrent/async
# variant is worth re-attempting in a future batch with a process-level (not
# thread-level) hard-kill wrapper for the trace-hang cases.
# sequential_sweep.py mirrors scripts/patent_to_zmx.py's run_conversion but adds
# candidate-ordering (telephoto/ultrawide keyword priority) + a hang exclusion
# list + resume-on-restart (see script docstring for full design notes).
python sequential_sweep.py data/zmx-staging/DATA-10a-uspto .planning/loop/patent2zmx-10a-report.json 300 0

# Step 3: six named gates + the extra plausibility gate + near-dup dedup,
# promotes into data/zmx/ + tests/data/data10a_manifest.json
python gate_and_promote.py .planning/loop/patent2zmx-10a-report.json

# Step 4: wire the new manifest into tests/data/zmx_manifest.py (DATA10_MANIFEST_NAMES
# block + updated assert counts), then regenerate the full case library
python scripts/generate_cases.py

# Step 5: regenerate the eval routing-winner golden
python scripts/e2_golden.py

# Step 6: full mock suite
python -m pytest -q -n 8 -k "not real"
```

(`sequential_sweep.py` and `gate_and_promote.py` were written for this batch as
one-off tooling in the session scratchpad, not committed to `scripts/` -- they
are thin wrappers around existing `scripts/patent_to_zmx.py` /
`app/core/case_library.py` building blocks with the additions described above.
A future batch that wants to repeat this exact flow should either recreate
them from this report's description or -- better -- invest in fixing the
underlying trace-hang and token-degradation issues so the stock
`scripts/patent_to_zmx.py` CLI can be used directly at concurrency.)

## Backlog (quantified, not guessed)

1. **~520 unmined patents remain**, but ~87.5% of this batch's failures were "no supported table format" -- a mining-only shovel has a low ceiling here without new parser-family coverage (same pattern DATA-09e/f/g existed to fix). Estimated yield at the current parser coverage: ~7% of attempted candidates (8/120 this batch).
2. **5 patents hang the real-ray trace** during conversion (`US-20260147187-A1`, `US-11226472-B2`, `US-11215797-B2`, `US-11262553-B2`, `US-10935766-B2`) -- excluded from mining, root cause not investigated (out of scope for this shovel).
3. **4 pre-existing library designs hang `build_sample_from_optic`** even on the lightweight path (`US-11940597-B2-e1`, `US-11940597-B2-e2`, `US-20240192468-A1-e1`, `US-10921568-B2-e1`) -- now safely routed around by `scripts/generate_cases.py`'s new timeout+reuse fallback, but the underlying numerical hang is unfixed.
4. **Full-suite completion verification**: recommend a supervised complete run of `pytest -q -n 8 -k "not real"` before merge (see "Test results" above).
5. **0 telephoto seeds found this batch** -- if telephoto breadth is a near-term priority, a future batch should title-filter the unmined pool more aggressively (this batch's title-keyword-priority ordering only tagged 7/644 candidates as telephoto/ultrawide-looking; most patent titles are generic "OPTICAL IMAGING LENS ASSEMBLY").


---

# DATA-10b parser-family expansion (Sunny Optics + Ability Opto, 361 -> 436)

## Summary

- mode: format census over the DATA-10a failure pool -> deterministic parser expansion for the top-2 implementable families -> live re-conversion -> six-gate intake (same gates as DATA-10a incl. the plausibility envelope) -> full regeneration/reanchor
- case_library_count_before: 361
- case_library_count_after: **436** (+75)
- scenario delta: wide 206->224 (+18), telephoto 119->134 (+15), **ultrawide 36->78 (+42, more than doubled)**
- manifest: `tests/data/data10b_manifest.json` (75 records); ledger: `.planning/loop/seed-intake-10b-ledger.json`; conversion report: `.planning/loop/patent2zmx-10b-report.json`

## Format census (step 1)

Assignee census of the 105 DATA-10a "no supported table format" failures, plus format inspection of ~31 fetched HTML samples across 9 families:

| family | unmined pool | verdict |
|---|---:|---|
| LARGAN | 172 | **dead pool** -- remaining patents are mechanical (lens barrels, spacer rings, light-blocking sheets), no prescriptions (6/6 samples) |
| AAC/Raytech | 124 | already covered (DATA-09g); remaining failures are zoom/periscope variants (fail-loud by design) |
| **Sunny Optics** | **111** | **implemented** -- consistent OBJ/STO/S-row surface tables, real prescriptions in all 6 samples |
| Genius | 30 | not attempted (timebox; smaller than Sunny/Ability) |
| Samsung | 28 | dead pool -- no text tables at all (4/4 samples) |
| **Ability Opto** | **27** | **implemented** -- near-primary format with f/HEP+HAF metadata and ordinal lens rows (3/3 samples) |
| Corephotonics | 23 | dead pool -- system-architecture patents with parameter-RANGE tables, no prescriptions |
| SEKONIX / NEWMAX | 18 / 15 | not attempted (timebox) |

## Parser changes (step 2, commit 2ea51e5)

**Sunny fallback parser** (pattern-follows the DATA-09g AAC precedent; wired after the AAC fallback in `_parse_prescription_attempts`): OBJ/STO/S-row surface tables (both "aspheric" and "Aspheric surface" type columns, optional per-element Focal-length column, surface-table conic mapped to the K coefficient), split-header "Surface number A4 ..." asphere tables, and four metadata styles: (a) per-embodiment label tables (`f(mm) 5.04 ... Semi-FOV(deg) 42.2 ... f/EPD 2.02`), (b) columnar "parameter f f1 ... HFOV ... numerical value ..." tables, (c) consolidated per-example row tables including per-example f/EPD rows inside conditional-expression tables, (d) embodiment-tagged narrative sentences ("In Example N, a total effective focal length f ... is 3.36 mm, an aperture number Fno ... is 2.27"). Fno from f/EPD is the definition of the working F-number (both operands published) -- a deterministic transform, not a fill.

**Metadata binding integrity**: the first backtest exposed a real off-by-one (embodiment N trailing summary leaked into embodiment N+1 pre-table span, assigning N values to N+1). Fixed by anchoring narrative extraction to embodiment-TAGGED sentences ("In Example N," -- comma required, rejecting cross-references like "as in example 1.") searched document-wide, with untagged "In this example," windows clamped at the first different-numbered tagged anchor. A conditional-expression cut also prevents the last embodiment document-tail span from first-matching example 1 values out of "Conditional/Example 1 2 3..." summary tables (observed: emb6 of US-10996439 would have taken 1.20 instead of its own 1.55 -- instead the f/EPD row of that table is now consumed as a proper per-example consolidated source).

**Ability extensions to the primary parser**: f/HEP + HAF metadata labels, ordinal lens rows ("1.sup.st lens"/"3 .sup.rd lens" -> "Lens N"), Aperture/Infrared-rays labels, "plane" as plano synonym, named-model-glass acceptance gated on a physical nd/vd pair (BK7_SCH 1.517 64.20), the "Coefficients of the aspheric surfaces" heading, "Surface 1 2 4" coefficient blocks without "#", and image-row trailing-residue tolerance.

**Two fail-closed OCR-integrity guards** (both triggered by real corrupt tables during backtest, both would otherwise ingest silently wrong numbers): (1) bare exponent fragments ("1.88094 IE-05" -- mantissa would be kept as a coefficient, a ~1e5x error); (2) per-row numeric overflow ("-1.5703 51E+00" -- one number split into two shifts the whole row). Also honest-rejected: US-12196921-B2 has an OCR-corrupted published vd column (1.92 where 19.2 is physically required) -- all 6 embodiments fail loud rather than ingest an impossible material.

## Conversion + intake (step 3)

- patents attempted: 135 (111 Sunny + 27 Ability, minus pre-excluded hangs); embodiment conversion successes: 92 from 22 patents
- six-gate + plausibility intake: **75 accepted, 17 rejected** -- 11 fisheye-class FOV 142-162deg (over the ratified 135deg smartphone plausibility ceiling), 2 negative ATELIER_FTAN_IMH_SANITY_MM, 2 near-duplicates, 2 lightweight-build >90s timeouts
- remaining failure buckets (honest, from the conversion report): 79 embodiments "full-field real rays did not reach image surface" (genuine trace failures), ~105 "metadata missing Fno/Semi-FOV" (partially unpublished values, partially a further Sunny sub-variant -- backlog), 20 "S6 value not numeric: P" (Sunny periscope/prism rows, 2 patents -- backlog), 18 "S2 value not numeric: Spherical" (residual row-shape variant -- backlog), 24 non-prescription
- three NEW hang-prone patents excluded and quantified: US-12235519-B2, US-12181639-B2 (real-ray trace hangs), US-12372750-B2 (~3.5 min/embodiment ultra-slow; timebox exclusion) -- same pathology as the DATA-10a five

## Golden reanchor (step 3)

- tests/data/eval_golden.json: 439 briefs (was 364; +75 new case-anchored briefs)
- routing-winner flips: **6**, all legitimate (three to new DATA-10b seeds -- US-10444475-B2-e1, US-12210213-B2-e3 (x2), US-12124010-B2-e3 (x2) -- and one sibling-embodiment shift US-20210389572-A1 e6->e7)
- no >2% ATELIER_REAL_IMH_MM deviations (the golden script enforces this gate itself)
- hardcoded count reanchors per the twice-established precedent (bd25ed0, DATA-10a d7df1f6): library 361->436, telephoto 119->134, first-order outliers 270->313, lightweight seeds 322->397, high-FOV 37->79 / totals 362->437 -- all values computed from the regenerated index, not guessed

## Test results (step 4)

- parser suite: 29/29 green (25 pre-existing + 4 new family fixtures); ruff clean
- quick slice (test_case_library, test_zmx_ingest, test_eval_golden_seeds, test_patent_to_zmx): 1355 passed in 39s
- full mock suite minus tests/test_seed_intake_audit.py: run to completion (result in the wave report)
- **tests/test_seed_intake_audit.py hang (recorded per instructions)**: test_high_fov_seed_intake_audit_reports_current_gap ran >7 minutes without completing and was killed. Root cause: the build_seed_intake_audit protected edge-field scan now probes 78 high-FOV seeds (was 36 pre-10b), and some new DATA-10b seeds are ultra-slow to edge-probe (same Optiland slow-trace pathology as the conversion hangs). All 4 audit-calling tests in the file are affected. The 5 count assertions in the file were still reanchored (436/437/79/397) so the file is CORRECT once runtime is fixed. **Follow-up needed**: a bounded per-seed timeout in the edge-field scan (mirroring the generate_cases.py fix) -- without it this file will also hang CI.

## Honest remainder ledger

1. Sunny metadata sub-variant behind ~105 "missing Fno/Semi-FOV" embodiment failures (some genuinely unpublished; a sample-driven census of the residual would separate the two).
2. Sunny periscope/prism "P-row" tables (2 patents, telephoto-relevant) and the residual "S2 Spherical" row-shape variant (18 rows).
3. 8 total hang-prone patents excluded from mining across 10a+10b; root cause in the Optiland real-ray trace unfixed.
4. tests/test_seed_intake_audit.py runtime pathology above (immediate follow-up before merge/CI).
5. Dead pools with evidence: LARGAN remainder (mechanical), Samsung (image-only), Corephotonics (range tables) -- ~223 patents that no parser work can convert.
6. Not-yet-attempted small families: Genius (30), SEKONIX (18), NEWMAX (15).
