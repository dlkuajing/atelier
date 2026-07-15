---
quick_id: 260715-patent-local-pool-replay
status: active
owner: Codex
base: d2e6a2d
---

# Frozen local-pool replay and structured failure census

## Goal

Freeze the 619 recomputed raw roots that have no formal artifact and replay every one through a
resumable, deterministic, evidence-preserving pipeline. Produce the first complete current-format
census from retained USPTO full text and isolated embodiment conversion, so the saturation ledger
can select parser/full-text work by measured bucket size rather than historical reports.

This quick does not promote staging ZMX to the formal library and does not claim saturation. A
converted staging candidate remains non-terminal until existing quality, traceability, physical,
dedupe, routing, and provenance gates close.

## Frozen cohort contract

1. Derive membership from the tracked saturation snapshot and its authoritative input hashes:
   every root with a raw USPTO record and no formal case ID, exactly once.
2. Store canonical publication/root/source/pool-line identities and bind the cohort to the
   saturation snapshot SHA-256, pool concat SHA-256, and formal case-index SHA-256.
3. Refuse replay if live pool or case-index bytes drift from the frozen manifest.
4. The historical `convert-cursor.json` is evidence only; it cannot select or exclude this cohort.

## Replay contract

1. Add a command with `freeze`, `run`, `audit`, and `report` operations.
2. `run` processes roots in frozen order, skips only roots with a strict current result file, and
   atomically writes one result per root before advancing the recomputable cursor.
3. Retain exact parser-input HTML in the raw patent lake. Record every PPUBS source-bucket attempt,
   HTTP status/exception class, chosen bucket, content hash, and retry identity without logging the
   anonymous access token.
4. Parse every disclosed embodiment. Each parse outcome and conversion receipt uses structured
   codes; generic `failed`, `unknown`, silent skip, and free-text-only outcomes are forbidden in
   new replay artifacts.
5. Send every parsed prescription through the process-isolated converter from quick
   `260715-patent-conversion-hard-timeout`.
6. A successful staging conversion is recorded as `converted_pending_intake`, not `intaken`.
   Terminal statuses use only the canonical ten-value saturation enum and only when evidence
   proves the classification. Ambiguous parser/source results remain explicit non-terminal work
   items that make replay audit fail.
7. Preserve raw lake, attempt evidence, replay results, frozen manifest, cursor/summary, and report
   as separate layers. No raw fetch can directly mutate formal cases, formal ZMX, or routing goldens.

## Source and safety gates

- Use the existing anonymous official USPTO PPUBS session endpoint; no credential is required or
  printed. Respect its existing 429 backoff and add a bounded inter-root delay.
- Do not run CODE V. Confirm zero CODE V inventory before and after every replay command.
- Do not modify scoring rulers, redlines, route scorer, or physical thresholds.
- Do not infer, repair, midpoint-fill, or LLM-generate any optical number.
- Network/HTTP failures cannot become `confirmed_no_prescription`; future/unpublished metadata
  cannot become `fulltext_unavailable` without source evidence.

## Verification contract

- Unit tests cover exact 619-root freeze membership, input-drift refusal, deterministic manifest
  bytes, resume after interruption, corrupt/duplicate result refusal, source-attempt evidence,
  structured non-terminal handling, and summary/audit recomputation.
- A small official PPUBS canary retains HTML and produces a structured result without CODE V.
- `PYTHONUTF8=1` targeted patent regression and Ruff pass.
- `git diff --check` passes.
- The quick remains active until the entire frozen cohort has a strict replay result and the
  measured largest remaining bucket is written to STATE/decisions. Parent saturation remains
  incomplete even if replay produces new staging candidates.

## Runtime checkpoint (2026-07-15)

- Frozen manifest: 619 roots / 619 publications, cohort SHA-256
  `e809823c709de93f49eb9b2103c4ebcdd9cf7e34d88f45a4953aaa21fd7bb42b`.
- Current replay checkpoint: 128/619 roots, 0 corrupt results. This is an intermediate checkpoint,
  not replay completion or saturation.
- Current root states: parser review 94, mixed non-terminal 27, source retry 3, all-terminal 3,
  all-converted-pending-intake 1.
- Current item states: parser review 322, terminal receipt 171, converted-pending-intake 48,
  patent-budget retry 1.
- Parser signatures are recomputed from strict result detail. Current largest measured signatures
  are AAC Raytech summary metadata missing (63) and Sunny metadata missing (63); the full cohort
  must finish before selecting the final largest parser bucket.
- Official PPUBS canary retained HTML and no CODE V process existed before or after replay.
- Real-pool failures drove two fail-closed fixes: retained source attempts now survive document
  parser exceptions; explicit optical infinity/plano radius is deterministically encoded as the
  existing ZMX plane radius 0. Other non-finite DTO inputs remain non-terminal.
- Each embodiment retains its process hard timeout. Replay additionally has a 180-second cumulative
  patent budget; unlaunched parsed embodiments become explicit
  `conversion_retry_required.patent_budget_exhausted` items.
