---
quick_id: 260715-patent-conversion-hard-timeout
status: complete
owner: Codex
base: b3e9591
---

# Patent conversion process isolation and hard timeout

## Goal

Make every patent embodiment conversion independently terminable and auditable. A malformed
prescription or a hanging Optiland trace must be unable to block a batch, and every retry must
retain enough immutable evidence to reproduce what ran and why it stopped.

This shovel hardens execution only. It does not claim that any root or embodiment has reached a
terminal saturation status, and it does not relax an existing optical quality or physical gate.

## Scope

1. Add a generic patent-conversion subprocess runner that:
   - serializes one deterministic embodiment request per attempt;
   - derives a stable request identity from canonical request bytes;
   - assigns a monotonic retry identity without overwriting earlier attempts;
   - starts a dedicated worker process and enforces a wall-clock hard timeout;
   - terminates the whole worker process tree, then performs a bounded reap;
   - retains request, response, stdout, stderr, candidate ZMX, and a structured receipt;
   - publishes the candidate ZMX only after worker success and parent-side validation.
2. Add a worker entry point that reconstructs the existing deterministic
   `PatentPrescription`, calls the existing ZMX writer and Optiland validation path, and emits
   a strict machine-readable result. No optical number is inferred or repaired.
3. Route the production conversion loop through the subprocess boundary. A timeout becomes the
   canonical `trace_timeout` outcome/reason; process/trace failures remain fail-closed and do
   not publish a formal candidate.
4. Retain the exact fetched HTML text used by parsing, together with source bucket, content hash,
   and patent identity, in a raw-input layer separate from candidate/formal ZMX artifacts.
5. Add focused tests for successful execution, hard timeout and process-tree kill evidence,
   bounded reap, stable retry identity, corrupt/missing worker response, and raw-input retention.
6. Update STATE and decisions with recomputable verification evidence.
7. Close the verification incident exposed by the first full-suite run: for every test not
   explicitly marked `real_machine`, install a subprocess-boundary guard that rejects CODE V
   executables before process creation. The guard itself must be covered without launching any
   real executable. A marker selection alone is not an adequate safety boundary.

## Explicit non-goals

- Do not run CODE V or `codevm`.
- Do not modify scoring, redline, routing, or physical acceptance thresholds.
- Do not assign `[EXPERT]` conclusions or production/yield claims.
- Do not convert legacy free-text failures into terminal saturation outcomes without evidence.
- Do not yet expand external source discovery; that follows local-pool execution hardening.

## Process contract

- Windows workers use a new process group and `taskkill /F /T /PID` on timeout, with a direct
  kill fallback. POSIX workers use a new session and kill the process group.
- Pipes are binary; raw stdout/stderr are retained. Diagnostic tails are decoded lossily only
  for the structured receipt, so locale-specific output cannot break cleanup.
- Cleanup itself has a short upper bound. A failed tree-kill or reap remains explicit evidence.
- Success requires: worker exit code zero, strict response schema, matching request identity,
  candidate file present, parent-side normalized ZMX load, and finite EFL.
- Attempts are append-only. A retry for identical canonical input shares a request identity but
  receives a new attempt number and directory.
- The raw source document is content-addressed and never stored in the formal seed directory.

## Verification contract

- `PYTHONUTF8=1 uv run pytest` passes for new process-runner tests and all patent-conversion
  regressions.
- `PYTHONUTF8=1 uv run ruff check` passes for all changed Python files.
- A real fixture embodiment crosses the subprocess boundary and produces a loadable ZMX.
- A deliberately sleeping worker is terminated within the configured bound and leaves a
  `trace_timeout` receipt plus request/log evidence, with no published candidate.
- Repeating the same request produces the same request hash and a distinct retry identity.
- A non-`real_machine` test attempting `codev.exe`, `cvcommand.exe`, `codevm.exe`, or
  `cvgui.exe` through `subprocess` is rejected before launch, while ordinary Python child
  processes remain available to process-isolation tests.
- `git diff --check` passes.

## Verification incident

The first host full-suite attempt was invalid: even with `-m "not real_machine"`, an unmarked
path launched `D:/CODEV115/codev.exe`, which detached `cvgui.exe`/`codevm.exe`. The pytest tree
was terminated immediately. Read-only evidence in `D:/CVUSER/codev.rec` contained only startup
(`LEN NEW`) followed by `EXI Y`; no business macro or optical command was recorded. The detached
processes exited externally before work resumed. No further host-wide regression may run until
the test subprocess guard above is installed and proven.

## Follow-on

After this quick is complete, freeze and replay the 619 uncovered local roots through the
isolated runner. The saturation ledger, not a fixed design count, selects the largest next
failure bucket for parser/full-text work.

## Completion evidence

- A real sleeping Python worker was process-tree terminated after the configured 0.2-second
  timeout and reaped; request, stdout, stderr, kill/reap details, and a `trace_timeout` receipt
  remained, with no published candidate.
- A real patent fixture crossed the worker boundary twice: both attempts produced loadable ZMX,
  shared the same canonical request SHA-256, and used distinct append-only retry identities.
- Missing worker responses fail closed as `trace_failed.worker_response_invalid`; Windows GBK
  `taskkill` output remains diagnostic bytes and cannot crash cleanup.
- Exact parser-input HTML is content-addressed separately from staging/formal ZMX and bound into
  every post-fetch attempt by path and SHA-256.
- The non-`real_machine` subprocess guard rejects four CODE V executable forms before process
  creation while continuing to permit the Python patent worker.
- `PYTHONUTF8=1` patent/process/guard regression: 77 passed.
- Ruff for all changed Python files: pass. `git diff --check`: pass.
- A guarded 2738-test host sweep produced no test failure or CODE V process but exceeded its
  704-second outer limit. It is recorded as timeout, not pass; complete CI remains a PR gate.

The quick is complete because process isolation, evidence retention, and its safety tests satisfy
this shovel's contract. The parent saturation objective remains active and incomplete.
