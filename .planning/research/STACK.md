# Stack Research

**Domain:** CODE V automation (Python↔Windows COM/batch) + local-demo web frontend for FastAPI backend
**Researched:** 2026-07-03
**Confidence:** MEDIUM (CODE V specifics) / HIGH (frontend stack)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| CODE V sequence files (`.seq`) + Macro-PLUS | CODE V 2026 (whatever 主公 installs) | Deep-engine automation: define lens, run optimization, export results, all in one batch script | This is the **documented, supported** batch mechanism (`IN` command reads `.seq` in command mode; Macro-PLUS is CODE V's built-in scripting language for exactly this). It matches the project's own architecture decision (macro batch, not interactive API) and avoids COM's per-call overhead — the same class of problem that already killed Zemax ZOS-API for this project (10s→118s). Confidence: MEDIUM — public docs are thin (Synopsys/Keysight gates full reference behind licensed portal `docs.keysight.com/codev*`), but every independent source (community tool `autov`, John Loomis's CODE V teaching notes, LinkedIn Synopsys OSG posts) converges on sequence-file batch as the standard automation idiom, not COM. |
| `subprocess.run()` (Python stdlib) | 3.12 | Invoke CODE V executable with a generated `.seq` file, capture stdout/stderr, enforce timeout | Simplest, most robust invocation surface for "generate script → run headless → parse output" pattern. No COM apartment-threading headaches, no dependency on CODE V being GUI-launched first. Aligns with PROJECT.md's explicit rejection of interactive-API-style engines. |
| pywin32 (`win32com.client`) | 308+ | **Fallback/optional**: attach to a running CODE V COM server if 主公's license only exposes interactive automation, or for live status polling during long optimizations | CODE V does expose a COM interface (Synopsys "CODE V Macros and COM" training page confirms this exists) but public documentation on its Python usage is essentially absent — the pattern would mirror generic `win32com.client.Dispatch`/`GetActiveObject` used for Excel/Office automation. Treat as **secondary path**, only if batch-mode round-tripping proves insufficient (e.g., need mid-run progress callbacks). Confidence: LOW — no verified Python+CODE V COM code sample found; must be spiked against the real license, not assumed. |
| FastAPI (existing) + Jinja2 templates | Jinja2 3.1+ | Serve minimal server-rendered shell pages for the demo frontend | Backend is already FastAPI; adding Jinja2 avoids introducing a second toolchain (Node build pipeline) just to render a few demo screens. Matches project's local-only, single-command-launch constraint. |
| htmx | 2.0.x (CDN `<script>` tag, no build step) | Client-side interactivity: form submit → partial page swap, polling/SSE-driven live updates, without writing custom JS | 2026 consensus (multiple independent sources incl. dev.to, Medium HTMX/FastAPI dashboard writeups) is that for CRUD-plus-realtime-updates dashboards driven by a Python backend, htmx eliminates the React/Vite/npm toolchain entirely — critical here because this is a **single demo machine**, not a maintained product frontend. 14KB min, no bundler, no `npm install` step to break on the demo laptop. Confidence: MEDIUM (WebSearch-verified across multiple sources, no official htmx+FastAPI joint doc, but pattern is well-trodden). |
| Plotly.js (CDN, not npm) | 2.35+ | Render MTF curves (log-scale, multi-field-angle overlay), before/after CODE V optimization comparison charts | Handles scientific/log-axis multi-series line charts out of the box (native support for tan/sag MTF pairs per field), has legend toggling and hover-readout for free — valuable for the "expert credibility" narrative where a designer wants to read exact MTF values off the curve. Its documented weakness (perf degrading >10k points, WebGL context limit ~8 charts/page) is a non-issue here: MTF curves are a few hundred points across ≤5 field points, and the demo shows one design at a time. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sse-starlette` | 2.1+ | Server-Sent Events endpoint for streaming Wizard LLM tokens + long-running CODE V batch progress to the browser | FastAPI has no built-in SSE helper; this library wraps `StreamingResponse` with proper `text/event-stream` framing, reconnect (`Last-Event-ID`), and heartbeat — reinventing this by hand is a common source of dropped-connection bugs. Use for both LLM streaming and CODE V "optimization running..." progress ticks. |
| `htmx-sse` extension | bundled with htmx via CDN (`htmx.org/dist/ext/sse.js`) | Wire SSE endpoint directly into DOM swaps (`hx-ext="sse"`, `sse-swap`) | Pairs with `sse-starlette`; lets the CODE V progress bar / LLM token stream update DOM without hand-written `EventSource` JS. |
| Alpine.js | 3.14+ (CDN) | Small islands of client-only state (toggle panels, slider inputs, tab switching) that don't need a server round-trip | Use where htmx's server-swap model is overkill (e.g., toggling between "fast path" and "CODE V deep" result tabs). Keeps total JS footprint under ~30KB combined with htmx — no bundler still required. |
| Pico.css or Tailwind (CDN build) | Pico 2.x / Tailwind CDN | Baseline visual polish without a design system build step | Pico.css: classless, looks respectable with zero class-naming effort — lowest friction for a demo. Tailwind CDN (`cdn.tailwindcss.com`) if finer control over decision-maker-facing polish is needed; accept the CDN's dev-mode performance warning since this never ships to production. |
| `python-docx` / `weasyprint` (optional) | — | If the demo needs a "leave-behind" PDF/exec-summary export of the design report | Only pull in if a phase explicitly requires exportable deliverables beyond the live browser demo; not needed for the walkthrough itself. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| A single `scripts/run_demo.ps1` (or `.bat` per project's Windows-script rules) | One-command launch of `uvicorn` + browser open | Must follow AGENTS.md Windows-script rules: pure English, CRLF line endings, `cd /d "%~dp0"` at top if `.bat`. Given project already has Windows-only constraints, prefer PowerShell (`.ps1`) over `.bat` for readability, but either satisfies "single command" requirement. |
| CODE V presence probe (custom, Python) | Runtime-detect CODE V install at startup, decide fast-path-only vs dual-engine mode | Not a third-party tool — must be hand-rolled: check registry key or known install path (`%CODEV%` env var / `C:\CODEV\...`) and probe executable launch. This is the "pluggable engine interface + runtime detection" the project's Active requirements already call for; no existing library does this for a niche commercial EDA tool. |

## Installation

```bash
# Backend additions (uv, existing project convention)
uv add sse-starlette jinja2

# No npm install needed — htmx, Alpine.js, Plotly.js, Pico.css/Tailwind
# are all loaded via CDN <script>/<link> tags in the Jinja2 template.
# This is a deliberate choice: zero Node toolchain on the demo machine.

# Optional, only if COM fallback path is spiked:
uv add pywin32
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| Sequence-file batch automation | CODE V COM interface (interactive) | If a specific workflow needs mid-optimization callbacks/live variable inspection that batch mode can't express — spike this only after batch mode proves insufficient, since COM's per-call latency is the exact failure mode that already disqualified Zemax ZOS-API for this project. |
| `subprocess.run()` invocation | pywin32 COM `Dispatch`/`GetActiveObject` | If CODE V's license/install genuinely requires a running GUI session to automate against (some EDA tools do) — verify against 主公's actual license terms once installed, don't assume. |
| htmx + Jinja2 + CDN JS | React/Vite/TypeScript SPA | If this frontend is expected to evolve into a maintained multi-page product beyond the demo milestone, or needs complex client-side state (undo/redo, offline caching). PROJECT.md scope is explicitly "local demo, single milestone, decision-maker narrative" — React's build toolchain adds real risk (npm install breaking on a demo machine with no internet) for no payoff here. |
| Plotly.js for MTF charts | uPlot / Chart.js | If chart volume grows to real-time streaming of thousands of points per frame (e.g., live ray-trace animation) — uPlot's canvas rendering beats Plotly's SVG/WebGL there. Not the case for static/before-after MTF curves. |
| Server-rendered SVG (already produced by Optiland backend) displayed via `<img>`/inline `<svg>` | Client-side ray-tracing re-render in JS (e.g., three.js, custom canvas) | Only if the demo needs interactive 3D rotation of the lens layout — no such requirement in PROJECT.md. The backend already generates SVG layouts; re-rendering client-side would duplicate logic and risk visual drift from the backend's ground-truth geometry. Serve the backend's SVG directly. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| ZOS-API (Zemax OpticStudio interactive API) | Already measured and rejected by 主公: 10s→118s blowup from per-call COM overhead on real cases. Confirms the general risk class for *any* interactive-API-style engine automation. | CODE V sequence-file batch mode (all computation happens inside one CODE V process invocation, no per-call marshaling) |
| React/Vue/Svelte SPA with npm build pipeline | Adds a Node toolchain dependency and build step to a project whose explicit constraint is "single command, reliable reproduction on a demo machine." A broken `npm install` on the demo day is a real risk this project cannot afford (演示彩排 is the milestone's acceptance bar). | htmx + Jinja2 + CDN-loaded JS libraries — zero build step, works offline once CDN assets are cached or vendored locally |
| Plotly.js npm package + Webpack/Vite bundling | Same build-toolchain risk as above, and unnecessary — Plotly.js CDN bundle is self-contained. | `<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>` (or vendor the file locally to remove internet dependency entirely on demo day — recommended given "reliable reproduction" constraint) |
| Assuming CODE V CLI flags/`.lis` output format from training data | Synopsys/Keysight gate the authoritative Macro-PLUS and command reference behind a licensed docs portal (`docs.keysight.com/codev...`); public web search could not surface exact executable flags or output-parsing conventions. Stating these as fact would be an unverified claim. | Treat CODE V invocation mechanics (exact exe name, CLI flags, `.lis`/output buffer format) as a **required spike** once 主公 finishes the CODE V install — read the actual local Macro-PLUS Reference Manual and Command Reference shipped with the install before writing the automation layer. |

## Stack Patterns by Variant

**If CODE V license only permits interactive (GUI-attached) automation:**
- Fall back to pywin32 COM `GetActiveObject("CodeV.Application")`-style attach (exact ProgID unverified — confirm from installed COM registration)
- Still generate `.seq`/macro content programmatically, just execute via COM's macro-run method instead of a bare subprocess call
- Because: the project's runtime-detection/pluggable-engine design already anticipates degraded modes; this is one more branch of that same interface, not a new architecture

**If demo machine has no reliable internet during rehearsal/showtime:**
- Vendor htmx, Alpine.js, Plotly.js, and Pico.css/Tailwind as local static files under `app/static/vendor/` instead of CDN `<script src>` tags
- Because: PROJECT.md's "一键启动：单命令拉起后端 + 前端，演示机可靠复现" requirement means a CDN outage or hotel wifi on-site must not be able to break the demo

**If the demo needs to show live token-by-token LLM output during natural-language intake:**
- Use `sse-starlette` + `htmx-sse` extension for that stream; keep CODE V's (much longer, minutes-scale) optimization progress on a separate SSE endpoint or simple polling, since the two have very different latency profiles and coupling them into one stream risks the LLM's fast stream getting head-of-line blocked behind slow CODE V ticks

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| Python 3.12 (existing) | pywin32 308+ | pywin32 requires Windows-only install; guard import behind `platform.system() == "Windows"` so CI (Linux) and non-Windows dev machines don't break — matches existing project pattern of runtime engine detection/degradation. |
| `sse-starlette` | FastAPI 0.115.0+ (existing) | No known incompatibility; sse-starlette targets Starlette's `StreamingResponse`, which FastAPI wraps directly. |
| htmx 2.x | Any server framework returning HTML fragments | Version 2.x dropped IE11 support and reorganized some extensions (`sse` is now a separate extension file, not bundled in core) — make sure to load `ext/sse.js` explicitly, not assume it's in `htmx.min.js`. |
| Plotly.js 2.35+ | Any modern evergreen browser | No Python-side dependency; purely a `<script>` tag. If backend needs to *generate* static Plotly figures server-side instead of client-side JSON, `plotly` Python package (`uv add plotly`) is a separate, optional path — not needed if MTF data is just JSON-fed to client-side Plotly.js. |

## Sources

- WebSearch: "Synopsys CODE V Python COM automation win32com" — MEDIUM confidence, confirms COM interface exists (Synopsys "CODE V Macros and COM" training page) but no verified Python code sample
- WebSearch + WebFetch: `github.com/BrianJKoopman/autov` — MEDIUM confidence, independent real-world confirmation that sequence-file generation + command-line/terminal invocation (not COM) is the practitioner's actual automation pattern for CODE V
- WebFetch: `johnloomis.org/eop601/codev/auto/cv_auto1.html` (CODE V teaching notes, University-affiliated) — MEDIUM confidence on `.seq` file semantics (`IN` command, CTRL-C behavior inside `.seq` execution), confirms sequence files are the batch execution unit
- WebSearch: CODE V Macro-PLUS Reference Manual existence (`docs.keysight.com/codev202503/...Macro-PLUS.pdf`) — confirms authoritative reference exists but is gated behind licensed docs portal; **not fetchable without login**, flagged as required reading once 主公 installs CODE V
- WebSearch: "htmx vs React vs Svelte ... 2026" (multiple independent blog/dev.to sources) — MEDIUM confidence, consistent convergence on htmx+Python backend for CRUD/dashboard-style demos without heavy client state
- WebSearch: "plotly.js vs uPlot vs Chart.js MTF curve" (SciChart, StackShare, DigitalOcean comparisons) — MEDIUM confidence, consistent on Plotly.js scientific-chart strengths and its documented large-dataset weakness (irrelevant at MTF-curve data scale)
- Project-internal: `D:\atelier\.planning\PROJECT.md` Key Decisions table — HIGH confidence, authoritative for already-made architecture calls (macro-batch over interactive API, Optiland fast + CODE V deep dual-engine, local-service-not-desktop-app)

---
*Stack research for: CODE V automation + local demo frontend*
*Researched: 2026-07-03*
