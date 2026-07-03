# Architecture Research

**Domain:** Dual-engine optical design demo — fast in-process compute engine (Optiland) + slow offline batch engine (CODE V via macro/.seq automation), single-machine local deployment (Windows demo box), FastAPI backend + new local web frontend with progress streaming
**Researched:** 2026-07-03
**Confidence:** MEDIUM-HIGH (patterns are well-established industrial practice; CODE V-specific automation details are MEDIUM — Synopsys/Keysight docs are not indexable by generic web search, findings rely on secondary/community sources)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Local Web Frontend (browser, localhost)                │
│   Wizard form → Design view (SVG/MTF) → "Send to CODE V" → Job progress   │
│   SSE client (EventSource) subscribes to /api/codev/jobs/{id}/stream      │
└───────────────────────────────┬────────────────────────────────────────--┘
                                 │ HTTP + SSE
┌────────────────────────────────▼───────────────────────────────────────--┐
│                       FastAPI Backend (existing, extended)                │
│  ┌──────────────┬──────────────┬──────────────┬────────────────────────┐ │
│  │  /optical    │  /wizard     │  /rag        │  /codev  (NEW)         │ │
│  │  (existing,  │  (existing)  │  (existing)  │  submit / status /     │ │
│  │   fast path) │              │              │  stream(SSE) / result  │ │
│  └──────────────┴──────────────┴──────────────┴───────────┬────────────┘ │
│                                                              │             │
│  ┌───────────────────────────────────────────────────────▼────────────┐  │
│  │                Compute Engine Abstraction (NEW)                    │  │
│  │  ┌────────────────────┐        ┌──────────────────────────────┐   │  │
│  │  │  FastEngine         │        │  DeepEngine                  │   │  │
│  │  │  (Optiland,         │        │  (CodeVEngine: subprocess    │   │  │
│  │  │   in-process,       │        │   batch driver; NullEngine:  │   │  │
│  │  │   sub-second)       │        │   degrade when absent)       │   │  │
│  │  └────────────────────┘        └──────────────┬───────────────┘   │  │
│  │           EngineRegistry.detect() at startup — capability probe    │  │
│  └───────────────────────────────────────────────┼────────────────────┘  │
│                                                    │                       │
│  ┌─────────────────────────────────────────────▼─────────────────────┐  │
│  │              Job Layer (NEW) — in-process asyncio, no queue broker  │  │
│  │  JobStore (in-memory dict, id→JobRecord)                            │  │
│  │  JobRunner: asyncio.create_task → run_in_executor(subprocess driver)│  │
│  │  Progress: driver polls .seq log tail / stdout → pushes to asyncio  │  │
│  │  Queue per job_id → SSE generator drains queue                      │  │
│  └──────────────────────────────┬──────────────────────────────────────┘ │
│                                  │                                        │
│  ┌───────────────────────────────▼─────────────────────────────────────┐│
│  │          CODE V Job Artifacts Pipeline (NEW)                        ││
│  │  1. .seq macro generator (from LensAssembly → CODE V command text)  ││
│  │  2. subprocess launch: codev -batch job.seq  (working dir = job dir)││
│  │  3. Output parser: .seq log / exported .zmx / .txt results          ││
│  │  4. Result → ZMX writer (canonical anchor format)                   ││
│  │  5. Validation gate (existing image_quality_floor + parameter_guards)││
│  │  6. Ingest into case_library (existing zmx_ingest.py pipeline)      ││
│  └───────────────────────────────────────────────────────────────────--┘│
└────────────────────────────────────────────────────────────────────────--┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │  CODE V (Windows GUI app, │
                    │  licensed, batch-launched)│
                    │  reads .seq, writes .zmx/ │
                    │  log files to job dir     │
                    └──────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Engine Abstraction (`ComputeEngine` ABC) | Uniform interface for "trace/optimize/evaluate a lens" regardless of backend | Python `abc.ABC` + `Protocol` fallback; `FastEngine(Optiland)`, `DeepEngine(CodeV)`, `NullDeepEngine` (degrades) |
| EngineRegistry | Detect available engines at process startup, expose `registry.deep_available` | Probe: check CODE V install path / license env var / `codev.exe --version` subprocess call with short timeout; cache result in app state, not per-request |
| Job Layer (JobStore + JobRunner) | Own lifecycle of a long-running CODE V job: queued → running → parsing → done/error | In-memory dict keyed by UUID; `asyncio.create_task` wrapping `loop.run_in_executor(None, blocking_subprocess_fn)`; no external broker needed at single-user demo scale |
| SSE Progress Channel | Push job progress lines to the one browser tab watching it | `asyncio.Queue` per job; FastAPI `StreamingResponse(media_type="text/event-stream")` generator awaits queue, yields `data: {...}\n\n` |
| .seq Macro Generator | Translate `LensAssembly` (existing Pydantic schema) into CODE V Macro-PLUS command sequence | Template-based string generation (Jinja2 or f-strings), not a DSL compiler — CODE V macro syntax is small and stable for this use case |
| Subprocess Driver | Launch CODE V in batch mode, supervise process, enforce timeout, capture output | `subprocess.Popen` with explicit `cwd`, `creationflags=CREATE_NO_WINDOW` optional, hard timeout + `taskkill /F /T /PID` escalation on Windows |
| Output Parser | Turn CODE V's exported files/log into structured result + ZMX | Small parser module mirroring `zmx_ingest.py` conventions; fails loud on unexpected format (no silent guessing, per project's "ground truth" ethos) |
| Result → ZMX writer | Guarantee CODE V output re-enters the system through the *same* anchor format as everything else | Reuse/extend `zmx_ingest.py`; CODE V should be made to *export* ZMX directly if supported, avoiding a bespoke bridge format |
| Validation Gate | Reject CODE V results that don't meet quality floor before they touch the case library | Reuse existing `image_quality_floor.py` + `parameter_guards.py` — same gate fast path uses, no special-casing deep engine |
| Case Library Ingest | Same 39-case JSON index mechanism, extended with CODE V-verified entries | Existing `case_library.py` / `zmx_ingest.py`, no new data model |

## Recommended Project Structure

```
app/
├── core/
│   ├── engines/                     # NEW — pluggable compute engine layer
│   │   ├── base.py                  # ComputeEngine ABC/Protocol, EngineCapabilities dataclass
│   │   ├── fast_engine.py           # Wraps existing optical_engine.py (Optiland)
│   │   ├── deep_engine.py           # CodeVEngine: subprocess batch driver
│   │   ├── null_engine.py           # Degrades gracefully when CODE V absent
│   │   └── registry.py              # detect_engines() at startup, app.state.engines
│   ├── codev/                       # NEW — CODE V-specific job machinery
│   │   ├── seq_generator.py         # LensAssembly -> .seq macro text
│   │   ├── subprocess_driver.py     # Popen lifecycle, timeout, taskkill escalation
│   │   ├── output_parser.py         # .seq log / exported files -> structured result
│   │   └── zmx_bridge.py            # CODE V result -> canonical ZMX (feeds zmx_ingest.py)
│   ├── jobs/                        # NEW — generic long-running job layer
│   │   ├── models.py                # JobRecord, JobStatus enum (queued/running/done/error)
│   │   ├── store.py                 # In-memory JobStore (dict + asyncio.Lock)
│   │   └── runner.py                # create_job(), run_in_executor wrapper, progress queue
│   ├── optical_engine.py            # existing — becomes the FastEngine backend
│   ├── zmx_ingest.py                # existing — CODE V results feed through here unchanged
│   ├── image_quality_floor.py       # existing — reused as validation gate for CODE V output
│   └── parameter_guards.py          # existing — reused, no special path for deep engine
├── api/
│   ├── optical.py                   # existing, unchanged (fast path)
│   ├── wizard.py                    # existing, unchanged
│   ├── rag.py                       # existing, unchanged
│   └── codev.py                     # NEW — POST /submit, GET /status/{id}, GET /stream/{id} (SSE)
└── data/
    └── codev_jobs/                  # NEW — per-job working directories (.seq in, .zmx/.log out)
        └── {job_id}/

frontend/                            # NEW — local web UI (separate from lumira Next.js frontend)
├── src/
│   ├── views/                       # Wizard → Design → CODE-V-progress → Comparison narrative
│   └── lib/sse-client.ts            # EventSource wrapper, reconnect-on-drop handling
└── (build output served by FastAPI StaticFiles, or run via separate dev server + one-command launcher)

scripts/
└── launch_demo.(bat|ps1)            # NEW — one-command: start backend (uvicorn) + frontend, open browser
```

### Structure Rationale

- **`app/core/engines/`:** isolates the abstraction from both concrete engines; this is the seam the roadmap should build *first* — everything else (job layer, .seq generation) is a plugin behind it. Keeps `NullEngine` trivial to implement day one, so CI and other dev machines never see CODE V-shaped code paths fail.
- **`app/core/codev/`:** CODE V-specific mechanics (macro syntax, subprocess quirks, output parsing) live in one place, separate from the generic job orchestration in `app/core/jobs/`. This separation matters because `jobs/` should be reusable if a second slow engine is ever added, while `codev/` is disposable/replaceable.
- **`app/core/jobs/`:** deliberately generic and boring — in-memory store, no Celery/Redis. At single-user demo scale (one operator, one browser tab, one CODE V license seat) a broker is pure overhead and adds a failure mode with no benefit.
- **`app/data/codev_jobs/{job_id}/`:** every job gets an isolated working directory. CODE V batch runs read/write files by convention (input .seq, output .zmx/.log); collisions between concurrent jobs are avoided by directory isolation, not by locking.
- **`frontend/`:** kept as its own top-level directory, not shoehorned into `app/` — it is a genuinely separate deployable (even if launched by the same script) and will likely use a different toolchain (Vite/React or similar) than the Python backend.

## Architectural Patterns

### Pattern 1: Pluggable Engine via Abstract Interface + Startup Capability Probe

**What:** Define a `ComputeEngine` interface (Protocol or ABC) with methods like `trace()`, `optimize()`, `is_available()`. At FastAPI startup (lifespan hook), probe for CODE V (check install path / env var / try a trivial `--version` subprocess call with a short timeout) and populate `app.state.engines = EngineRegistry(fast=FastEngine(), deep=deep_engine_or_null)`. Routes read `request.app.state.engines.deep` — never import CODE V modules directly.

**When to use:** Any time a feature depends on an optional external dependency (license-gated software, GPU, OS-specific tool) that may not exist on every machine (CI, other dev machines, future deployments).

**Trade-offs:** Adds one layer of indirection over calling Optiland/CODE V directly. Pays for itself immediately here because the project's own constraint list requires CI and other dev machines to run "no CODE V" without special-casing — this pattern makes that the *default* path, not an exception.

**Example:**
```python
# app/core/engines/base.py
from abc import ABC, abstractmethod
from typing import Protocol

class DeepEngine(Protocol):
    def is_available(self) -> bool: ...
    def submit(self, lens: "LensAssembly", job_dir: Path) -> "JobHandle": ...

# app/core/engines/null_engine.py
class NullDeepEngine:
    def is_available(self) -> bool:
        return False
    def submit(self, lens, job_dir):
        raise EngineUnavailableError("CODE V not detected on this machine")

# app/core/engines/registry.py
def detect_engines() -> EngineRegistry:
    deep = CodeVEngine() if _probe_codev() else NullDeepEngine()
    return EngineRegistry(fast=FastEngine(), deep=deep)
```

### Pattern 2: In-Process Async Job Runner (no external broker) for Single-User Batch Tasks

**What:** Long-running CODE V runs are wrapped in `asyncio.create_task(run_job(job_id))`, where the blocking `subprocess.run`/`Popen.communicate` call is pushed to a thread executor via `loop.run_in_executor()`. Job state (status, progress messages, result) lives in an in-memory `JobStore` dict guarded by an `asyncio.Lock`. No Celery, no Redis, no external queue broker.

**When to use:** Single-machine, single-operator demo context where job concurrency is inherently capped at 1 (one CODE V license seat, one GUI process) and there is no requirement to survive process restarts mid-job. This is explicitly *not* the pattern for multi-tenant or horizontally-scaled deployments — the project's constraints (local demo machine, no SaaS) rule that out anyway.

**Trade-offs:** Job state is lost on backend restart — acceptable here since a restart mid-optimization means re-running the CODE V job anyway (it's idempotent, driven by the same .seq). Avoids operational burden of running Redis on a Windows demo machine and eliminates an entire class of "is the worker up?" failure modes during a live demo.

**Example:**
```python
# app/core/jobs/runner.py
async def start_job(lens: LensAssembly, engine: DeepEngine) -> str:
    job_id = str(uuid4())
    store.create(job_id)
    asyncio.create_task(_run(job_id, lens, engine))
    return job_id

async def _run(job_id: str, lens: LensAssembly, engine: DeepEngine):
    loop = asyncio.get_running_loop()
    try:
        store.update(job_id, status="running")
        result = await loop.run_in_executor(None, engine.run_blocking, lens, store.progress_cb(job_id))
        store.update(job_id, status="done", result=result)
    except Exception as e:
        store.update(job_id, status="error", error=str(e))
```

### Pattern 3: Windows Subprocess Lifecycle for a GUI-Capable Batch Tool

**What:** Launch CODE V with `subprocess.Popen(args, cwd=job_dir, creationflags=subprocess.CREATE_NO_WINDOW)` (or allow the window if CODE V's batch mode requires a visible session — verify in the spike). Enforce a hard wall-clock timeout via `Popen.wait(timeout=...)`; on `TimeoutExpired`, escalate to `taskkill /F /T /PID <pid>` (Windows lacks POSIX process groups, so a plain `.kill()` on the parent will not reliably reap children CODE V may spawn). Poll the job's log file for progress lines rather than trying to parse stdout, since GUI-mode batch tools often write real progress to a log file, not stdout.

**When to use:** Any Windows-only external GUI application driven in "headless"/batch mode from a script.

**Trade-offs:** Requires the spike (already planned as milestone step 2) to determine: (a) does CODE V's batch mode need a window at all or can it run fully hidden, (b) does it spawn helper processes that `taskkill /T` must catch, (c) what does its progress/log file actually look like. Do not guess these — they gate the subprocess driver design.

**Example:**
```python
# app/core/codev/subprocess_driver.py
def run_codev_batch(seq_path: Path, job_dir: Path, timeout_s: int, progress_cb) -> CompletedProcess:
    proc = subprocess.Popen(
        ["codev", "-batch", str(seq_path)],
        cwd=job_dir,
        creationflags=subprocess.CREATE_NO_WINDOW,  # verify in spike: may need to omit
    )
    log_path = job_dir / "codev.log"
    try:
        _tail_log_until_exit(proc, log_path, timeout_s, progress_cb)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)])
        raise CodeVTimeoutError(f"CODE V job exceeded {timeout_s}s")
    return proc
```

## Data Flow

### Request Flow (Deep Engine Path — NEW)

```
[Browser: "Send to CODE V" button, after fast-path design shown]
    ↓
POST /api/codev/submit {lens_assembly}  → validated via existing parameter_guards
    ↓
job_id = jobs.start_job(lens, engine=registry.deep)
    ↓ (immediate 202 response with job_id)
[Browser opens EventSource(/api/codev/stream/{job_id})]
    ↓
seq_generator.build(lens) → job_dir/input.seq
    ↓
subprocess_driver.run_codev_batch(...)  — runs in executor thread, tails log
    ↓ (progress lines pushed to asyncio.Queue[job_id] as they appear)
[SSE generator drains queue → `data: {...}\n\n` → EventSource.onmessage]
    ↓ (on completion)
output_parser.parse(job_dir) → structured result
    ↓
zmx_bridge.to_zmx(result) → job_dir/output.zmx
    ↓
image_quality_floor + parameter_guards validate output.zmx
    ↓ (pass)                                  ↓ (fail)
zmx_ingest.ingest(output.zmx)          job marked "error", reason surfaced to SSE stream
    ↓
case_library entry created/updated (existing mechanism)
    ↓
job marked "done", final SSE event includes before/after comparison payload
    ↓
[Browser renders optimization-before/after narrative]
```

### Fast Path (existing, unchanged)

The existing Wizard → raytrace → match request flow (documented in `.planning/codebase/ARCHITECTURE.md`) is untouched. `FastEngine` is a thin wrapper around the existing `optical_engine.py` — no behavior change, just an interface for the registry to expose it uniformly alongside `DeepEngine`.

### State Management

- **Job state:** in-memory only (`JobStore` dict), scoped to backend process lifetime — acceptable per single-operator-demo constraint; explicitly not durable across restarts.
- **Engine availability:** detected once at startup (lifespan hook), cached in `app.state` — never re-probed per-request (CODE V version-check subprocess calls are not free).
- **SSE connections:** one queue per job_id; if the browser tab reloads mid-job, a reconnect endpoint should support replaying buffered progress (store last N lines in the JobRecord, replay on reconnect) rather than only live-tailing.
- **File-system as ground truth:** each job's `job_dir` is the durable record of what happened (input .seq, output .zmx, log) — the in-memory JobStore is a cache/index over that, not the source of truth. This matches the project's existing "ZMX is the anchor format" philosophy.

## Key Abstractions

**ComputeEngine / DeepEngine (Protocol):**
- Purpose: Uniform seam so routes and the job layer never need to know if CODE V is present
- Pattern: `NullDeepEngine` returns `is_available() -> False` and raises a typed error on `submit()` — routes catch this and return a structured 503 ("deep engine unavailable"), not a crash

**JobRecord (dataclass/Pydantic):**
- Purpose: Single source of truth for one CODE V run's lifecycle
- Fields: `job_id`, `status` (queued/running/parsing/done/error), `progress: list[str]`, `result: Optional[OpticalSampleData]`, `error: Optional[str]`, `job_dir: Path`
- Pattern: Mirrors the project's existing convention of Pydantic composite payloads (`OpticalSampleData`) as the frontend contract

**EngineCapabilities:**
- Purpose: Expose *why* deep engine is unavailable (not installed vs. license expired vs. probe timeout) so the frontend can show an honest message instead of a generic "unavailable"
- Pattern: Consistent with the project's existing `ParameterGuardError` structured-violations convention — no bare strings for error states

## Scaling Considerations

This product explicitly does not scale beyond one operator on one demo machine (per PROJECT.md Constraints: "云端部署/SaaS 多租户" is out of scope). Framing scaling in terms of "users" is the wrong axis here — the real axis is **concurrent CODE V jobs** and **demo-day reliability**.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 job at a time (actual target) | In-memory JobStore + asyncio task, no broker. This is the only tier that matters for this milestone. |
| 2-3 jobs queued back-to-back (e.g. operator queues several designs before a demo) | Add a simple FIFO queue in front of the job runner so a second submit while one is running doesn't spawn a second CODE V process against the same license seat — CODE V is very likely single-instance per license. Still no external broker needed; an `asyncio.Semaphore(1)` guarding `deep_engine.submit` suffices. |
| Hypothetical multi-user / cloud (explicitly out of scope) | Would require Celery/Redis or similar, per-tenant CODE V license pooling, and is a different product — do not build toward this speculatively. |

### Scaling Priorities

1. **First real risk:** two submits racing the single CODE V license/process. Mitigate with `asyncio.Semaphore(1)` around the deep-engine submit path from day one — cheap insurance, not premature optimization.
2. **Second real risk:** SSE connection drop during a long optimization (browser refresh, network blip on localhost is rare but happens). Mitigate by buffering progress lines in the JobRecord and supporting reconnect-and-replay, not by adding infrastructure.

## Anti-Patterns

### Anti-Pattern 1: Reaching for Celery/Redis for a Single-User Local Demo

**What people do:** Default to "long-running task = Celery + Redis + message broker" because that's the canonical FastAPI answer for production SaaS.
**Why it's wrong:** Adds a Redis dependency to a Windows demo machine that must be one-command-launchable and rock-solid on demo day; introduces a new failure mode ("is the worker connected to the broker?") for zero benefit at concurrency=1.
**Do this instead:** `asyncio.create_task` + `run_in_executor` + in-memory JobStore, guarded by a semaphore if queuing is needed. Revisit only if this product ever needs multi-tenant/cloud deployment (explicitly out of scope).

### Anti-Pattern 2: Treating CODE V Subprocess Like a POSIX Child Process

**What people do:** Call `proc.terminate()` or `proc.kill()` on timeout and assume it cleans up, based on Unix habits (process groups, SIGTERM propagation).
**Why it's wrong:** Windows has no process groups; a GUI-capable application may spawn helper processes or leave a hung window that `.kill()` on the parent PID won't touch, leaving orphaned CODE V processes holding the license seat.
**Do this instead:** Use `taskkill /F /T /PID <pid>` on timeout/error, verified against actual CODE V process behavior in the spike phase.

### Anti-Pattern 3: Bespoke Result Format Instead of Routing Through ZMX

**What people do:** Parse CODE V's native output (log file, proprietary export) directly into the internal `OpticalSampleData` model, bypassing the existing ZMX ingest pipeline.
**Why it's wrong:** Creates a second, untested data path parallel to the one that already has two known historical bugs fixed in it (E1-01 XASPHERE, E1-02 vignetting) — the ZMX ingest pipeline's hard-won correctness would not apply to a new bespoke parser, and any future ZMX-anchor fix would need to be duplicated.
**Do this instead:** Make the CODE V bridge's job to produce a valid `.zmx` file and hand it to the *existing* `zmx_ingest.py`. This is explicitly the plan already stated in PROJECT.md ("Code V 产物必须回到 ZMX 走现有 ingest 流水线") — the architecture should not deviate from it even where a direct parse looks easier.

### Anti-Pattern 4: Polling for Job Status Instead of SSE Push

**What people do:** Implement `GET /api/codev/status/{id}` and have the frontend poll it every N seconds, skipping SSE because it "seems simpler."
**Why it's wrong:** CODE V global optimization runs can take minutes; polling either wastes requests at high frequency or feels laggy/dead at low frequency, undermining the demo's "optimization process visualization" narrative goal (PROJECT.md Active requirement).
**Do this instead:** SSE (`StreamingResponse` with `text/event-stream`), which is simpler than WebSockets for this one-directional server→client use case and works over a single HTTP connection without extra libraries.

## Integration Points

### External Services / Processes

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| CODE V (Windows desktop app, batch-launched) | `subprocess.Popen` with `.seq` macro file as input, working directory per job | Must be spiked first: confirm batch mode doesn't require an interactive license dialog, confirm true headless/hidden-window capability, confirm output file format for direct ZMX export vs. custom parser |
| Optiland 0.6 (existing, in-process) | Direct Python import, patched via `optiland_patches.py` | Unchanged; wrapped by `FastEngine` for interface uniformity only |
| Frontend dev/build server | Static files served by FastAPI (`StaticFiles`) or launched as separate process by the one-command launcher script | Choose static-serve-by-FastAPI for the "one command" constraint — avoids managing two long-running dev servers during a demo |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| API layer (`app/api/codev.py`) ↔ Job Layer | Direct async function calls (`await jobs.start_job(...)`) | No queue between them — job layer itself owns the async task scheduling |
| Job Layer ↔ Engine Abstraction | `engine.submit()` / `engine.run_blocking()` interface calls | Job layer never imports `CodeVEngine` directly — only the `DeepEngine` protocol via the registry, preserving graceful degradation |
| Deep Engine ↔ CODE V process | Filesystem (`.seq` in, `.zmx`/log out) + subprocess exit code | No in-memory shared state possible across the process boundary; all communication is via job_dir files, by design (mirrors how the existing ZMX pipeline already treats files as the contract) |
| CODE V bridge output ↔ existing ingest pipeline | `.zmx` file handed to `zmx_ingest.load_zmx()` (existing function) | This is the single most important boundary in the new architecture — it's what keeps CODE V from becoming a second, divergent source of truth |
| Frontend ↔ Backend | REST (submit/status) + SSE (stream) | Same-origin localhost; CORS already configured for existing routers, extend allow-list if frontend runs on a different dev port |

## Suggested Build Order (dependencies between components)

1. **ZMX↔CODE V roundtrip spike** (already planned as milestone step 2) — must come first; it validates the two riskiest unknowns (macro batch mechanics, ZMX export fidelity) before any production code is written around them.
2. **Engine abstraction + registry + NullEngine** — build this before touching CODE V integration code. It lets steps 3-5 be developed and tested on non-CODE-V machines (CI, other dev laptops) via the null path, satisfying the "no Code V → Optiland-only" degradation requirement from day one rather than retrofitting it.
3. **Job layer (generic, engine-agnostic)** — build against a fake/mock `DeepEngine` first (e.g., a `SleepEngine` that just sleeps and emits fake progress) to prove out SSE plumbing and JobStore lifecycle without waiting on real CODE V runs.
4. **CODE V subprocess driver + .seq generator + output parser + ZMX bridge** — now wire the real `CodeVEngine` into the proven job layer, using findings from the spike (step 1).
5. **Validation gate + ingest wiring** — connect CODE V output to existing `image_quality_floor.py` / `parameter_guards.py` / `zmx_ingest.py`; this is mostly reuse, low risk.
6. **Frontend build** — can start in parallel with steps 2-3 against the existing fast-path API, then wire in SSE consumption once step 3's job layer is stable.
7. **One-command launcher script** — last; depends on both backend and frontend being independently runnable and on the true CODE V invocation path being known.

## Sources

- [How to Build Background Task Processing in FastAPI](https://oneuptime.com/blog/post/2026-01-25-background-task-processing-fastapi/view) — MEDIUM confidence, corroborates BackgroundTasks limitations (no persistence, no progress tracking) vs. task-queue tradeoffs
- [Managing Background Tasks and Long-Running Operations in FastAPI | Leapcell](https://leapcell.io/blog/managing-background-tasks-and-long-running-operations-in-fastapi) — MEDIUM confidence, SSE vs polling vs WebSocket tradeoff discussion
- [FastAPI official docs — Background Tasks](https://fastapi.tiangolo.com/reference/background/) — HIGH confidence, official source confirming BackgroundTasks runs in-process, no persistence across restarts
- [Kill a Python subprocess and its children when a timeout is reached](https://alexandra-zaharia.github.io/posts/kill-subprocess-and-its-children-on-timeout-python/) — MEDIUM confidence, confirms Unix process-group techniques don't apply on Windows
- [Python subprocess official docs](https://docs.python.org/3/library/subprocess.html) — HIGH confidence, confirms `TimeoutExpired` requires manual `.kill()`, and Windows batch-file launch behavior
- [Macke's Blog: Python: Killing subprocesses on Windows](http://mackeblog.blogspot.com/2012/05/killing-subprocesses-on-windows-in.html) — LOW confidence (dated, community source), but consistent with official docs on `taskkill /F /T` need
- [Macro in CODE V: A Comprehensive Training Guide](https://manuals.plus/m/bc035b4e266b7681ea7df22abd94de5a3a7ea3d03db1c27a1ccb260e67f27a95) — LOW-MEDIUM confidence, secondary source confirming Macro-PLUS supports command-mode/batch execution; official Synopsys/Keysight CODE V documentation was not directly accessible via web search and should be verified during the spike (primary source for exact `.seq` batch invocation syntax should be the CODE V installation's own manual)
- [GitHub - ksyoung/CodeV_macros](https://github.com/ksyoung/CodeV_macros) — LOW confidence but useful as real-world example of Macro-PLUS macro structure
- `D:\atelier\.planning\codebase\ARCHITECTURE.md` — HIGH confidence, primary source for existing system structure this research extends
- `D:\atelier\.planning\PROJECT.md` — HIGH confidence, primary source for constraints (Windows-only demo, offline batch mode, ZMX anchor requirement, degradation requirement)

---
*Architecture research for: Dual-engine optical design demo (Optiland fast path + CODE V batch deep path)*
*Researched: 2026-07-03*
