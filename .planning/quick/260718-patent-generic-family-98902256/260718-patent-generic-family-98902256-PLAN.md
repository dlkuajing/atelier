# Quick Plan: Patent generic family 98902256 / US-20260063880-A1

**Status:** Complete — family shovel closed; parent/global saturation remains incomplete
**Date:** 2026-07-18
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `98902256`
- Distinct root / publication: `US-20260063880` / `US-20260063880-A1`
- Application: `19/304678`
- Title: `PLASTIC OPTICAL FOLDING ELEMENT, IMAGING LENS MODULE AND ELECTRONIC DEVICE`
- Applicant / assignee: `LARGAN PRECISION CO., LTD.`
- Inventors in normalized source front matter: `HSU; Shih-Jung`; `FAN; Chen-Wei`
- Filing / publication: `2025-08-20` / `2026-03-05`
- Provisional priority observed in source: `63/687,363` (`2024-08-27`)
- Raw HTML: `data/patent-lake/uspto-ppubs-html/US-PGPUB/adc36ef0434e925c/US-20260063880-A1.html`
- Raw SHA-256: `adc36ef0434e925c8098a9f57f2621a0828321c00a696058443fc4f2ac0a22d1`
- Normalized text SHA-256: `142e7fd688eb9ef226bf092d482c6c3a1aa7859bdd518ecc9a7546915e70ae6c`
- Existing replay attempt: `attempt-0001`, terminal state `parser_review_required`, detail `PatentParseError: embodiment f/Fno/HFOV line not found`; no conversion artifact.
- Entry marker scan: 54 occurrences of `embodiment`, no detected EFL / Fno / full or half field-angle markers, and four HTML tables. Marker counts are routing signals only, not a terminal classification.

## Objective

Independently reconcile the retained official publication source and all document items for this family, determine whether exact reconstructible optical prescriptions exist, encode only evidence-supported terminal classifications or conversions, and close the family with deterministic replay/audit evidence while preserving the global saturation ledger invariants.

## Work plan

- [x] Freeze the current 85-family generic residual census and record the exact entry snapshot.
- [x] Reconcile bibliographic identity, family/application lineage, claims, description, tables, equations, figures, and every disclosed embodiment directly from the retained source.
- [x] Establish the complete document-item inventory and distinguish reconstructible sequential optical prescriptions from folding-element/material/film architecture, metadata-only gaps, or other terminal evidence classes.
- [x] Add the narrowest exact classifier/conversion support and focused regression tests; do not change generic heuristics or scoring/redline criteria.
- [x] Produce repeated replay attempts and demonstrate semantic determinism plus retained-source/evidence integrity.
- [x] Refresh only live shared-ledger pointers required by deterministic tests, preserving historical snapshots.
- [x] Run focused and full patent tests, guard tests, compile/Ruff, JSON/evidence/terminal/contamination audits, corruption audit, CODE V process inventory, primary-repository cleanliness check, and worktree diff review.
- [x] Update STATE and decisions evidence, mark this quick complete, and commit this family shovel atomically before selecting the next residual family.

## Safety constraints

- Never start, control, or terminate CODE V; inventory must remain zero.
- Original retained source only. Any PDF page rasterization is evidence inspection only: no enhancement, inferred geometry, or image-based optical prescription reconstruction.
- No borrowing of prescription facts or classifications from other Largan families.
- The global patent saturation goal remains incomplete after this family closes.

## Result

The exact A1 source binds application `19/304678`, provisional `63/687,363`, one related-
application paragraph, Background 2-3, Summary 4-7, drawing paragraphs 8-36, detailed
paragraphs 37-103, 27 claims in six independent subject groups, 28 declared figures, four
flattened coating/geometry tables, 18 MathML inequalities and six source items. Items 1-4 are
plastic folding-element/reflection-film architectures; items 5-6 are multi-camera electronic-
device wrappers. The tables publish reflection-film layer materials/thicknesses and mechanical
dimensions, but no item publishes an ordered optical radius/spacing/material/index/Abbe/conic/
asphere/stop prescription or required system metadata. The sole focal-length phrase is generic
device zoom language. All six therefore become distinct `confirmed_no_prescription` terminals;
there is no worker, request, receipt, fingerprint, candidate/ZMX, formal intake or CODE V use.

The retained 1,604,370-byte official PDF has 37 image-only pages, 25 drawing sheets on pages
2-26 and one raster per page. The canonical decoded raster set is
`72c5771436731298b746bcadee420bbb43d1803bf4003ef1e8948a159566717a`; the full contact sheet
and nine original-resolution pages, including all three table pages, were reviewed without
enhancement, geometry measurement or numeric derivation. Attempts 2/3 are semantic-equal after
excluding only `result_attempt`, at
`f242fdcfa5f3cff34cee642b1ce424c44a4459fb9eeb3a5d6d69f4351d4e4f4d`.

Generic residual moves 85->84; result set is
`43f504d428bcb42f3f7c579cd304097d2588f6385824c68b79145949615182da`, summary is
`6f044e937b7bc3538722bcf2b33b42154e1779608b4315500c53e0b1cf3d7b5c`, report is
`53ea450fd54cf47f13f9a76acfd98851c14bc8e4a5f9fd83910fd406a184622b`, and both after
censuses are byte-identical at
`3b2bb775aebc38892d8ebef80c230c284ed843fcd501e36fe49cb934943b0e91`. Strict audit passes
619/619 with corrupt=0. Focused tests pass 7/7; the first complete file sweep exposed only four
live shared-pointer assertions (664 passed), targeted repair passes 4/4, and the final complete
file sweep passes 668/668. Remaining patent tests pass 94/94 and the no-real-CODE-V guard passes
5/5. Compile, Ruff, 51 changed JSON files, 68 evidence manifests/849 path-hash references,
18-null/6-empty-coverage terminal invariants and four-scope formal-contamination checks pass.
All 38 prior shared summary/report references were refreshed; historical result-set snapshots were
preserved except the two test-proven live pointers. Deterministic ordering selects Family
`97524399`, root `US-20260147219`, publication `US-20260147219-A1`, next. Parent/global patent
saturation remains active and incomplete.
