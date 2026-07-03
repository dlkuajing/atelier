# Pitfalls Research

**Domain:** Synopsys CODE V macro-batch automation + Zemax/CODE V format interop + live customer-demo delivery of long-running optical compute
**Researched:** 2026-07-03
**Confidence:** MEDIUM

CODE V itself is a closed, low-documentation-footprint commercial tool; there is no public API reference site or open issue tracker (unlike Zemax's community forum). Findings below combine: (1) verified facts from Synopsys's own licensing docs and third-party interop tooling docs (HIGH/MEDIUM confidence), (2) direct extrapolation from this project's own already-proven ZMX ingest bugs (E1-01/E1-02, documented in CONCERNS.md) applied to the CODE V round-trip case, since those are the same class of failure on the same file format (HIGH confidence — this is not speculation, it is pattern continuation of bugs already caught once), and (3) general demo/live-engineering-software delivery wisdom (MEDIUM confidence, cross-industry not optics-specific).

**Where CODE V-specific behavior could not be verified via public docs** (no official public API reference exists for Macro-PLUS command-line error codes), findings are flagged LOW and the mitigation is "verify empirically against your own installed CODE V version during the ZMX-interop spike" — which the project has already scheduled as its first Active requirement.

---

## Critical Pitfalls

### Pitfall 1: License checkout failure mid-batch silently corrupts or truncates results

**What goes wrong:**
CODE V uses Synopsys Common Licensing (SCL), built on FlexNet/FlexLM. A macro-batch run that processes N designs in one `.seq` invocation can lose its license checkout partway through (server hiccup, another seat grabbing a floating license, VPN drop if the license server is remote) even though the run started successfully. Depending on how the macro is written, a mid-run license failure can (a) hard-abort the whole `.seq`, losing all not-yet-flushed results, or (b) — worse — cause the macro interpreter to continue past the failed command silently, producing a results file that looks complete but contains stale/default values for the failed step.

**Why it happens:**
FlexNet license failures are asynchronous relative to the macro's control flow: CODE V's macro engine was designed for interactive engineer-at-keyboard use, not unattended batch pipelines. Batch mode is documented to "automatically continue as long as good progress is being made" (per CODE V automatic-design docs) — this "keep going" behavior is a feature for optimization robustness but a landmine for license-outage detection, because "made progress" and "silently used cached/last-good values after a checkout failure" can look identical from outside the process.

**How to avoid:**
- Never trust CODE V's own exit code alone as a completeness signal. After every batch run, verify output artifact count == expected count (N designs in → N result files out), not just "process exited 0."
- Add an explicit license-checkout self-test macro command at the start of the `.seq` (checkout a token, verify success, release) before the real batch work begins — fail fast rather than discovering the failure mid-batch.
- Wrap the CODE V subprocess call with a wall-clock timeout AND a result-file freshness check (mtime) — a hung license wait can look like a slow-but-alive process.
- Treat every batch invocation as needing per-item output validation (checksums / key-metric sanity bounds), not just "did the .seq finish."

**Warning signs:**
- Batch run completes faster than expected for its item count (early truncation).
- Output files for later items in the batch are byte-identical to earlier items (stale-cache symptom).
- Intermittent failures that correlate with time-of-day or other concurrent CODE V seat usage on the license server.

**Phase to address:**
Phase implementing the CODE V engine adapter / pluggable engine interface — before it's trusted as a data source for the demo's "CODE V deep-optimization" narrative.

---

### Pitfall 2: ZMX → CODE V → ZMX round-trip silently degrades exactly the surfaces this project already knows are fragile

**What goes wrong:**
This project's own history (CONCERNS.md) shows two real, already-shipped bugs from ZMX ingest alone: XASPHERE coefficient off-by-one (E1-01, 407µm RMS silent corruption) and glass-catalog placeholder fallback (E1-02, 18% EFL drift) — both undetected by the existing EFL<2% gate until deliberately investigated. A CODE V round-trip adds a second, independent conversion boundary (Zemax-format-writer inside CODE V, or a third-party converter) on top of Optiland's own ZMX reader. Each hop is a separate opportunity for the same class of failure: extended-asphere terms silently truncated or reordered, glass name resolved to a different (numerically close but not identical) dispersion curve, and vignetting factors (VDX/VDY) lost or reinterpreted on non-focal surfaces (the exact bug class fixed in E1-02).

**Why it happens:**
Optical file formats have no single canonical spec; format converters between vendors are known to be reverse-engineered and incomplete ("virtually impossible to convert ALL features... due to divergent program philosophies... lack of documentation," per OpTaliX's own conversion-tooling documentation). Independently verified: research literature comparing CODE V, OSLO, and Zemax explicitly documents that refractive-index/dispersion data for the same-named plastic materials (PC, PMMA, etc.) **do not agree** across these three programs — i.e., glass-name string equality does not imply optical equivalence, which is structurally the same failure mode as this project's own E1-02 bug, just at a different layer (cross-vendor catalog divergence vs. Optiland's incomplete catalog).

**How to avoid:**
- Do not assume "round-trips through CODE V and comes back as valid ZMX" implies numerical fidelity. Require the ZMX-interop spike (already scheduled as Active requirement #2) to explicitly diff: EFL, RMS spot/MTF at 0/0.7/1.0 field, and per-surface glass nd/vd values, pre- vs post-round-trip — not just "file parses."
- For glass materials specifically: resolve by (nd, vd, or full dispersion formula) numeric comparison, not by name string match, when validating round-trip fidelity. Treat name equality as a hint, not proof.
- For XASPHERE / extended-asphere surfaces: explicitly count polynomial terms before and after round-trip; a term-count mismatch is a silent-truncation signal, exactly like E1-01.
- For vignetting: explicitly assert VDX/VDY survive round-trip on every non-trivial (non-1.0 field) case, reusing the same regression pattern that caught E1-02.
- Reuse (don't rewrite) the existing `test_load_efl_within_2pct` gate infrastructure as the acceptance bar for CODE V round-trip, extended with the per-surface glass/asphere-term diffs above — this is the same gate, applied one hop further out.

**Warning signs:**
- EFL passes the <2% gate but off-axis MTF/RMS at the edge field degrades unexpectedly after CODE V round-trip (this is precisely how E1-01 hid for a while — the aggregate metric passed while per-surface data was wrong).
- Glass names in the round-tripped ZMX match the original string but nd/vd differ by more than datasheet tolerance.
- Any smartphone-lens case with Japanese resins or CDGM glass (already known fragile in Optiland's own catalog per E1-02) is a priority stress-test target for the CODE V round trip, since it is already known these are the exact materials most likely to be catalog-incomplete on the Optiland side — CODE V's catalog completeness for these same materials is unverified and should not be assumed better.

**Phase to address:**
The ZMX-interop spike (Active requirement: "ZMX ↔ Code V 互通验证"), which the project has already correctly sequenced first. This pitfall is the reason that sequencing is correct — do not let CODE V engine integration proceed past spike-validation into the demo-facing "deep optimization result" narrative until this gate passes.

---

### Pitfall 3: CODE V macro output format is not a stable machine-readable contract across versions/settings

**What goes wrong:**
CODE V's native output channel for macro/batch runs is designed for a human reading a text buffer/log (interactive command-mode transcript), not a stable structured data format for programmatic parsing. Column widths, significant-digit formatting, and even which fields are printed can shift based on CODE V version, active lens units, or output-mode settings (e.g., number of decimal places on MTF/RMS values, whether wavelength headers are printed). A parser hand-tuned against one CODE V installation's output can silently misparse (or crash on index-out-of-range) against a different version or configuration.

**Why it happens:**
CODE V predates structured-output conventions (JSON etc.) common in modern tooling; its scripting layer (Macro-PLUS) was built for interactive optical engineers, and output formatting is oriented toward readability in a terminal/log window, not toward parser stability guarantees.

**How to avoid:**
- Prefer any structured/machine-oriented output primitives CODE V's Macro-PLUS exposes (buffer variables written to a delimited file by the macro itself, rather than parsing the interactive command-log text) — write the macro to explicitly emit values you control the format of (e.g., `WRITE` a fixed-format line per metric) rather than scraping default command output.
- Pin and record the exact CODE V version used during the spike; treat any future CODE V version bump the same way Optiland version bumps are already treated in this project (AbbeMaterial polynomial-vs-buchdahl footgun) — as requiring a full re-validation of the parsing/acceptance gate, not an assumed-compatible upgrade.
- Add a canary/smoke macro that, before any real batch, runs a known-answer trivial case (e.g., a stock singlet) and asserts the parsed output matches expected values exactly — this catches both license/execution failures (Pitfall 1) and output-format drift in one gate.

**Warning signs:**
- Parser code with fragile fixed-column-offset string slicing against CODE V log output.
- No version pin recorded anywhere for the CODE V installation used in development vs. the demo machine.
- Any "off by one field" or NaN-from-parse-failure symptom appearing only on the demo machine and not the dev machine (classic version-drift signature).

**Phase to address:**
CODE V engine adapter implementation phase — output parsing should be built defensively from day one, not retrofitted after the first parse failure on a different machine.

---

### Pitfall 4: Demo depends on a resource (license seat, network, background batch) that is invisible until it fails live

**What goes wrong:**
The project's own constraints explicitly note the demo machine is local/offline-capable for the fast (Optiland) path, but CODE V licensing is inherently a separate dependency: FlexNet licensing normally requires either (a) a reachable license server (network-dependent, and license servers are frequently on corporate VPNs that are exactly the kind of network a traveling demo laptop loses access to), or (b) a node-locked/standalone license file tied to that specific machine. If the demo relies on live CODE V computation to show the "deep optimization" narrative and the license check fails in front of the customer (Wi-Fi drop, VPN timeout, license server maintenance window, floating-license seat contention with someone back at the office), the single most differentiated part of the pitch (the thing distinguishing this from a generic Optiland-only demo) is the part most likely to visibly break live.

**Why it happens:**
Optical CAD tools were built for engineers at a workstation on a stable corporate network, not for portable sales/demo scenarios. Floating licenses in particular introduce a failure mode invisible during solo rehearsal (works fine when no one else is using a seat) that appears only in production timing (someone else checks out the last seat while you're mid-demo).

**How to avoid:**
- Use a node-locked license file for the specific demo machine if Synopsys licensing supports it, eliminating network/server dependency entirely for demo day. If only floating licenses are available, this is a real constraint to escalate, not silently accept.
- **Never compute CODE V's deep-optimization result live during the demo.** Pre-compute and cache the CODE V-optimized result for every case in the demo script ahead of time; the live demo replays/displays the cached artifact ("cross-validated by CODE V" claim is about provenance of the design, not about live recomputation). This is consistent with the project's own stated constraint that CODE V is explicitly an offline/background layer, not an online interactive path — the same principle should extend to demo-day risk management, not just runtime latency.
- Build an explicit fallback narrative path: if CODE V-backed results are for any reason unavailable (license, hardware failure, etc.), the demo degrades to Optiland-only results with an honest framing ("CODE V cross-validation available in full engagement"), rather than a hard failure with no recovery script.
- Rehearse the exact failure: unplug network mid-flow during a dry run and confirm the app/demo script does not hang or crash, but degrades visibly and gracefully.

**Warning signs:**
- No rehearsal has ever been done with network disconnected or with license server unreachable.
- The demo's narrative script has no defined behavior for "CODE V result not available" — i.e., the happy path is the only path anyone has tested.
- Reliance on a shared/floating license without checking whether other users in the org might be using a seat during the demo's likely time window.

**Phase to address:**
Demo-rehearsal phase (Active requirement: "完整演示彩排"), but the pre-computation/caching architecture decision must be made in the CODE V integration phase, not retrofitted the day before a demo.

---

### Pitfall 5: Windows subprocess/COM automation of CODE V hangs invisibly instead of failing loudly

**What goes wrong:**
Automating a GUI-capable Windows application (whether via COM, a spawned executable in "batch"/command-line mode, or a scripted `.seq` invocation) risks the automated process silently blocking on a modal dialog, a license-prompt popup, or an interactive confirmation that never appears in a truly headless/unattended context but can appear if any part of the invocation path is not fully suppressed (e.g., a first-run EULA dialog, an update-check popup, a "save changes?" prompt if a previous session didn't exit cleanly). Because there is no visible terminal for a GUI app waiting on a dialog, the calling Python process simply sees the child process as "still running" with an open-ended wall-clock time, which is indistinguishable from a legitimately long-running optimization.

**Why it happens:**
CODE V, like most Windows CAD-class engineering tools, was not primarily designed for unattended headless invocation; the safest command-line entry points that guarantee no GUI/dialog surface are the ones documented for batch usage, but any deviation (wrong working directory causing a "file not found, choose one?" style prompt, prior crash leaving a lock/temp file, running from a directory the app doesn't have write access to) can reintroduce a GUI wait state.

**How to avoid:**
- Always invoke via the documented pure-batch/command-line entry point (not by automating a launched GUI window via COM/window-message injection), and validate on a clean machine state that the invocation truly returns no window handle.
- Wrap every CODE V subprocess call with a hard timeout (not just a "hope it exits" wait), and treat timeout as a first-class error path with diagnostic capture (was there a window? check via a Windows API window-enumeration check for the CODE V process id) rather than an indefinite hang.
- Run automated batch invocations under a clean, dedicated working directory with known write permissions, and clear any stale temp/lock files from prior runs before starting — matching this project's general "clean worktree" discipline but applied to CODE V's own scratch files.
- Test unattended invocation cold — i.e., first run after a reboot, with no prior interactive CODE V session ever having run "accept license terms" clicks on that machine — since first-run dialogs are the most common hidden-GUI-wait trap.

**Warning signs:**
- Subprocess call hangs past expected duration with no CPU usage from the CODE V process (idle-waiting-on-input signature, vs. legitimately busy optimization which should show CPU load).
- Works when run from an interactive desktop session but fails/hangs differently when run non-interactively (e.g., via a scheduled task or service account with no desktop session) — a classic hidden-modal-dialog tell.
- Any first-time setup step (license acceptance, catalog path configuration) that was done manually once and never scripted/verified reproducible.

**Phase to address:**
CODE V engine adapter implementation phase; specifically the "one-click launch" / demo-machine reproducibility requirement (Active requirement: "一键启动").

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Parse CODE V's interactive log-text output directly instead of building explicit structured-output macro commands | Faster to get first result working | Silent breakage on CODE V version/config drift (Pitfall 3); fragile to any format change | Never for anything demo-facing; acceptable only for a disposable spike/throwaway probe script |
| Trust process exit code 0 as "batch succeeded" | Simple, no extra validation code | Masks license mid-batch failures (Pitfall 1) and silent truncation | Never — always add output-artifact-count / freshness validation |
| Compute CODE V deep-optimization result live during customer demo | Feels more "real" / impressive if it works | Single point of live-demo failure tied to license/network (Pitfall 4) | Never for customer-facing demo; fine for internal dev/debug sessions |
| Assume ZMX round-trip through CODE V preserves fidelity because the file "parses fine" | Skips building per-surface diff tooling | Repeats E1-01/E1-02-class silent corruption one layer further out | Never — always validate with EFL/RMS/glass/asphere-term diffs before trusting CODE V-sourced ZMX in the case library |
| Use a shared/floating CODE V license for demo day | No extra licensing cost/setup | Seat-contention failure risk during the exact demo window | Never for a high-stakes customer demo; acceptable for internal batch/dev work only |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| CODE V macro-batch (.seq) | Assuming license failure aborts cleanly and visibly | Add explicit license self-test at .seq start; validate output artifact count post-run, not just exit code |
| CODE V → ZMX export | Trusting glass name string equality as proof of optical equivalence | Diff resolved nd/vd (or full dispersion formula) numerically, not by name, matching the E1-02 lesson already learned inside this project |
| CODE V → ZMX export | Assuming extended-asphere terms round-trip completely | Count/compare polynomial term-by-term pre/post, matching the E1-01 lesson already learned inside this project |
| Pluggable engine interface (Optiland fast / CODE V deep) | Building the interface assuming both engines expose equivalent structured output | Design the interface around Optiland's stable structured API as the contract; treat CODE V adapter as a translation layer that must defensively validate/coerce, since CODE V's native output is not natively structured |
| Windows subprocess automation | Automating via GUI window / COM object model that can present modal dialogs | Use the pure command-line batch entry point; validate with clean-machine cold-start test; enforce hard timeouts with diagnostic capture |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Treating CODE V batch runs as "background, unlimited time" with no upper bound | Demo prep/CI runs stall indefinitely with no clear signal of stuck vs. slow | Always wrap with hard timeout + CPU-activity heartbeat check | First time a license/dialog hang occurs unattended (Pitfall 5) |
| Re-running full CODE V optimization batch on every case-library change instead of caching results keyed by case content-hash | Batch turnaround grows linearly with library size (already growing toward ~100 cases per CONCERNS.md scaling note) | Cache CODE V results keyed by input ZMX hash; only recompute changed/new cases | Once case library reaches the ~50-100 case range the project already anticipates by EOY |
| Parsing CODE V log output with fixed-offset string slicing at scale | Silent misparse across many cases only surfaces on aggregate statistics, not per-case | Structured macro output (WRITE to delimited file) + explicit per-case validation, not aggregate-only gates (same class of trap as the EFL<2% gate not catching E1-01) | As soon as batch size exceeds what a human can spot-check case-by-case |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Embedding CODE V license server hostname/port or credentials in committed macro/config files | License server details leaked in a public-facing or shared repo | Keep license server config in `.env` / local machine config, matching this project's existing `.env`-only secrets discipline (per AGENTS.md) |
| Running CODE V subprocess with elevated/admin privileges "just to make automation work" | Broader attack surface if the automation script itself has a bug or the macro file is compromised | Run with least-privilege account sufficient for license checkout + file I/O only |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Presenting a live-computing spinner for CODE V-backed "deep optimization" during customer demo | If it hangs (license/network), the audience watches a stalled progress bar in real time — worse than not showing it at all | Pre-cache CODE V results; present them as "already-computed cross-validation," with the option to explain the offline compute workflow narratively rather than performing it live |
| No visible distinction in the UI between "fast Optiland result" and "CODE V deep-validated result" | Technical audience (engineers) may distrust the credibility claim if they can't tell which numbers came from which engine | Explicitly badge/label results by originating engine, consistent with the project's own two-engine architecture decision |
| Silent engine downgrade (CODE V unavailable → falls back to Optiland-only) with no user-visible indication | Decision-maker audience may believe they're seeing a CODE V-validated result when they are not — directly undermines the "professional credibility" north star | Any fallback must be visibly and explicitly flagged in the demo UI/report, never silent |

## "Looks Done But Isn't" Checklist

- [ ] **CODE V batch integration:** Often missing per-item output validation — verify artifact count matches input count, not just process exit code
- [ ] **ZMX↔CODE V round trip:** Often missing per-surface glass/asphere numeric diffs — verify nd/vd and polynomial term counts match pre/post, not just that the file parses and EFL gate passes
- [ ] **Demo one-click launch:** Often missing a true cold-start test (fresh reboot, no prior manual license-acceptance clicks) — verify on a genuinely clean machine state, not just the dev machine that's been run many times already
- [ ] **Demo fallback path:** Often missing an actual rehearsed failure scenario — verify by deliberately disconnecting network / blocking the license server during a dry run and confirming graceful degradation, not just designing the fallback on paper
- [ ] **CODE V output parsing:** Often missing a version pin / canary smoke-test — verify a known-answer trivial case parses to exact expected values before trusting real-case output

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|-----------------|
| License failure mid-batch discovered after the fact | LOW | Re-run the batch from the point of the last validated artifact; add the self-test gate (Pitfall 1) so it doesn't recur |
| ZMX round-trip fidelity loss discovered in case library | MEDIUM | Reuse the exact remediation pattern already proven for E1-01/E1-02: isolate affected cases, patch the specific conversion boundary, re-validate via extended EFL/glass/asphere-term gate, do not silently drop affected cases |
| Demo-day live CODE V failure with no fallback prepared | HIGH (in the moment) | Pivot to Optiland-only narrative honestly, framed as "full CODE V cross-validation shown in follow-up engagement"; this is a live-recovery script that should be pre-written, not improvised |
| CODE V output-parser breaks after a CODE V version update | MEDIUM | Re-run the canary/smoke known-answer case first to isolate parser vs. numerical drift; treat exactly like the existing Optiland-version-bump re-validation discipline already documented in this project (AbbeMaterial polynomial-vs-buchdahl footgun) |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|---------------|
| License checkout failure mid-batch | CODE V engine adapter phase | Self-test macro at .seq start; output artifact count == input count check on every batch run |
| ZMX↔CODE V round-trip fidelity loss | ZMX-interop spike (already first in Active requirements) | Extended acceptance gate: EFL<2% (existing) + per-surface glass nd/vd diff + asphere term-count diff + vignetting VDX/VDY survival check |
| CODE V output format instability | CODE V engine adapter phase | Canary known-answer smoke test on every CODE V version/environment; structured WRITE-based output instead of log scraping |
| Live demo dependency on license/network | CODE V integration phase (architecture) + demo rehearsal phase (validation) | Pre-computed/cached CODE V results for all demo cases; rehearsal with network/license deliberately disabled |
| Windows headless automation hangs | CODE V engine adapter phase + one-click-launch requirement | Cold-start test on genuinely clean machine state; hard timeout + CPU-activity heartbeat on every subprocess call |

## Sources

- Synopsys — CODE V Installation Guide (confirms Windows-only distribution, licensing setup) — https://www.synopsys.com/content/dam/synopsys/optical-solutions/documents/installation-guide/code-v-installation-guide.pdf [MEDIUM]
- Synopsys — Licensing QuickStart / Choosing Licensing Options for CODE V, LightTools, LucidDrive — confirms Synopsys Common Licensing built on FlexNet/FlexLM — https://www.synopsys.com/optical-solutions/support/choosing-license-option.html [HIGH]
- Synopsys — FlexNet Publisher 2024 R2 License Administration Guide — https://www.synopsys.com/content/dam/synopsys/support/documents/licensing/enduser.pdf [MEDIUM]
- CODE V Macro-PLUS Reference Manual (Keysight-hosted mirror) — confirms Macro-PLUS scripting layer exists as the automation surface — https://docs.keysight.com/codev202503/files/936663277/936663308/1/1743761631000/Macro-PLUS.pdf [MEDIUM]
- John Loomis — CODE V Automatic Design notes — confirms batch-mode "continue on progress" behavior and CTRL-C/.seq interaction differences — https://johnloomis.org/eop601/codev/auto/cv_auto1.html [MEDIUM]
- OpTaliX file-conversion documentation (via Optenso) — confirms cross-vendor conversion incompleteness, coordinate-break/decenter dummy-surface workarounds, reverse-engineered format handling — https://www.optenso.com/fileconv/fileconv.html [MEDIUM]
- ResearchGate — "Dispersion models in CODE V, OSLO, and ZEMAX for polycarbonate (PC), acrylic (PMMA)..." — directly confirms cross-vendor glass-name/dispersion-data disagreement for common optical plastics — https://www.researchgate.net/figure/Dispersion-models-in-CODE-V-OSLO-and-ZEMAX-for-polycarbonate-PC-acrylic-PMMA-and_fig1_335513208 [MEDIUM — single academic source, but directly on-point and consistent with this project's own independently-discovered E1-02 bug]
- Reprise / Walnut.io / general SaaS demo-reliability blogs — cross-industry live-demo failure/recovery best practices (offline-capable infra, rehearsal discipline, fallback scripting) — https://www.reprise.com/resources/blog/the-art-of-failing-forward-demo-lessons-learned , https://www.walnut.io/blog/product-demos/top-5-product-demo-fails/ [MEDIUM — not optics-specific, general applicability]
- This project's own `.planning/codebase/CONCERNS.md` (E1-01 XASPHERE bug, E1-02 glass-catalog bug, AbbeMaterial polynomial/buchdahl footgun) — used as HIGH-confidence pattern-continuation evidence for CODE V round-trip risk, since these are proven failure modes on the exact same file format one layer removed [HIGH — internal, already validated]

---
*Pitfalls research for: CODE V macro-batch automation, live optical-design customer demo, Zemax/CODE V format interop*
*Researched: 2026-07-03*
