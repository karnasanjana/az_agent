# BRD → Azure Data Factory Medallion Agent

**POC documentation** — overview, design rationale, architecture, capabilities, validation
evidence, deployment/operations, future scope, and leadership summary.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Overview](#2-overview)
3. [Design Rationale — why the LLM never touches Azure directly](#3-design-rationale--why-the-llm-never-touches-azure-directly)
4. [Architecture](#4-architecture)
5. [HTTP Surface](#5-http-surface)
6. [Request Lifecycle](#6-request-lifecycle)
7. [Capabilities](#7-capabilities)
8. [Source Coverage](#8-source-coverage)
9. [The BRD Corpus](#9-the-brd-corpus)
10. [Limitations and Unsupported Scope](#10-limitations-and-unsupported-scope)
11. [Container and Naming Rules](#11-container-and-naming-rules)
12. [Safety, Governance, and Approval Controls](#12-safety-governance-and-approval-controls)
13. [Validation Evidence](#13-validation-evidence)
14. [Deployment and Operations](#14-deployment-and-operations)
15. [Operational Workflow](#15-operational-workflow)
16. [Future Scope](#16-future-scope)
17. [Production Readiness](#17-production-readiness)
18. [Appendix: Code Map and Branch Map](#18-appendix-code-map-and-branch-map)

---

## 1. Executive Summary

This is a proof-of-concept web application that converts a Business Requirements Document (BRD)
into a running Azure Data Factory (ADF) medallion pipeline. It generates ADF artifacts, presents
them for human review, blocks unsafe plans through offline pre-flight validation, and only
deploys and runs the pipeline after explicit approval.

The core value proposition is shortening the path from business requirements to reviewable,
deployable ADF pipelines while keeping a human in the approval loop at every tenant-changing step.

The central engineering finding of this POC is a negative result turned into a design:
**giving a language model direct Azure access does not work.** Several approaches were attempted —
direct tenant access, free-form ADF JSON generation, template-filling forms, and fully agentic
tool loops. Each hallucinated resources, invented columns, or emitted ADF JSON that was
syntactically plausible and operationally wrong. The architecture that works constrains the model
to a typed, validated plan and hands every Azure interaction to deterministic code. Section 3
documents this in full, because it is the most transferable lesson in the project.

| Decision area | POC finding | Leadership interpretation |
| --- | --- | --- |
| Deployability | 9/10 hard BRDs, then 5/5 external-source BRDs, succeeded end to end in live Azure | Good POC signal; ready for controlled beta-style use |
| Safety | Pre-flight blocked invalid transforms before deploy, every time | Safe failure beats silent wrong deployment |
| Design approach | Constrained plan + deterministic compiler beat every free-form/agentic variant tried | The reliability comes from the architecture, not the model |
| Source breadth | Azure Blob/ADLS, HTTP, Dataverse, Postgres, BigQuery, SharePoint proven live | Not Azure-only in practice; external sources land in bronze |
| Cleanup | App-created ADF resources and containers can be listed and removed | Tenant can be restored after test runs |
| Runtime speed | Planning is seconds; ADF Mapping Data Flow execution is minutes | Azure runtime, not the agent, is the slow portion |

## 2. Overview

### The problem

A data engineer receives a BRD ("land these CSVs, clean them like this, produce this aggregated
mart") and then spends hours hand-building ADF linked services, datasets, mapping data flows,
pipelines, and triggers — plus the container provisioning, naming conventions, and monitoring
around them.

### What the app does

It turns a BRD directly into a **deployed, running** ADF medallion pipeline:

```
BRD in → agent GENERATES the full plan and every ADF object
       → SHOWS the user everything (JSON, Data Flow scripts, governance plan)
       → user APPROVES
       → agent CONNECTS TO AZURE, provisions containers, deploys, RUNS for real
       → live Bronze → Silver → Gold run status streamed back
```

It is a single FastAPI web app with an inline UI: paste or upload a BRD, click
**Generate pipelines**, review, click **Approve → build & run**, watch the run. ADF only — no
Databricks, Synapse, or Fabric. **Nothing touches the Azure tenant before approval.**

### The medallion contract

| Layer | ADF object | Transformation |
| --- | --- | --- |
| **Bronze** | Copy Activity only | none — byte-for-byte raw landing, idempotent overwrite |
| **Silver** | Mapping Data Flow | casts, null handling, filters, dedup, cleaning ops — typically Delta/Parquet |
| **Gold** | Mapping Data Flow | joins, derived measures, aggregations, KPI buckets, sort |

A master pipeline chains the layers with `dependsOn: [Succeeded]`, so a failed Bronze halts
everything downstream. Naming prefixes (`ls_/ds_/df_/pl_`) are enforced by code.

## 3. Design Rationale — why the LLM never touches Azure directly

This section exists because it is the most important finding of the POC, and because the
approaches that failed are the ones most people try first.

### What was tried, and why each was abandoned

**Attempt 1 — Give the agent direct Azure access and let it work.**
The intuitive approach: hand the model credentials and an instruction, let it create resources.
It hallucinated. It referenced storage accounts that did not exist, invented column names that
were not in the source files, and — most dangerously — created real objects in the tenant while
reasoning about a plan that was subtly wrong. A hallucination in a chat window is a bad answer.
A hallucination with tenant write access is a bad answer that has already happened. This was
abandoned early and permanently: **the model has never had, and will never have, direct write
access to the Azure tenant.**

**Attempt 2 — Ask the model to write ADF JSON directly.**
ADF JSON is verbose, deeply nested, and full of fields where a plausible-looking value is
invalid. The model produced JSON that parsed cleanly and failed at runtime: invalid `recreate`
mode on Delta sinks, `limit()` calls in the Data Flow DSL (a function that does not exist),
column names with spaces that break the DSL, type mismatches in joins and coalesce. Each failure
was discovered in Azure, minutes into a Data Flow run, after real objects had been deployed. The
feedback loop was too slow and too expensive, and every fix was a per-case patch that did not
generalize.

**Attempt 3 — A template/form-filling approach.**
Constrain the model to filling slots in pre-written ADF templates. This removed the JSON syntax
problem but replaced it with a rigidity problem: real BRDs do not fit a fixed template. Any BRD
that needed a shape the template did not anticipate either failed or, worse, got quietly bent
into the nearest template that did fit. The templates were eventually deleted; the Microsoft
gallery JSON they came from is now used only as reference material for the compiler, never as
something the model fills in.

**Attempt 4 — Fully agentic tool loops.**
Give the model a broad set of tools and let it drive. This is retained in a constrained form —
`PLAN_MODE=tools` builds the plan through validated tool calls — but only because every tool call
is validated on the spot and rejected with a precise error when wrong. The unconstrained version,
where tools could reach Azure, reintroduced the Attempt 1 problem with extra steps. The lesson:
agentic loops are safe exactly to the degree their tools are validated, and no further.

### What actually works

The LLM is **never asked to free-form-write ADF JSON**, and never given tenant write access. It
reasons in a narrow, checkable space:

1. **BRD → `LogicalPlan`** — a typed, Pydantic-validated plan written in business vocabulary
   (entities, casts, filters, joins, aggregations). Every field is validated against a **closed
   operation vocabulary**; an operation the compiler cannot render is rejected at parse time,
   not discovered in production.
2. **`LogicalPlan` → ADF JSON** — a deterministic compiler (`agent/compiler.py` +
   `agent/builder.py`) emits the Data Flow script DSL and deployable JSON. Same plan in, same
   JSON out, every time — correct **by construction**, provable offline.

The division of labor is the whole point. The model does the one thing it is genuinely good at:
reading ambiguous business prose and mapping it to structured intent. Deterministic code does
everything that must be exactly right: JSON generation, naming, cross-references, type checking,
Azure API calls.

Everything else is guard rails: a completeness checker that repairs gaps, a triage step that
turns unsupported asks into honest refusals with suggested alternatives, schema **grounding**
that reads real file headers so column types come from data rather than guesses, an offline
**pre-flight** gate that blocks approval of unsafe plans, a deploy-time source-file gate, and an
optional self-heal loop for runtime failures.

### The consequence: hallucination becomes a caught error, not an outage

Every failure mode from the failed attempts now has a specific catcher:

| Hallucination | Where it is caught | Result |
| --- | --- | --- |
| Invented source entity the BRD never mentioned | `invented_sources` check, plan phase | Rejected, model re-prompted |
| Invented column that the source does not have | Grounding (real file/table headers) | Column dropped, reported in assumptions |
| Operation outside the vocabulary (SCD2, pivot, alerts) | Pydantic parse + triage | Listed as unsupported with an alternative |
| Invalid ADF construct (`recreate`, `limit()`) | Compiler never emits it | Structurally impossible |
| Type-invalid expression (`upper()` on an integer) | Type checker, pre-flight | Approval blocked, nothing deployed |
| Missing source file | Deploy-time source gate | Approve aborts, nothing created |
| Runtime ADF failure | Self-heal + learned lessons | Repaired and retried, or fails loud |

The app also learns from its own failures: runtime incidents are distilled into generic rules in
`skills/99-learned-lessons.md` that every future planning prompt loads — fixes accumulate as
knowledge, not per-case patches.

## 4. Architecture

The architecture separates **reasoning** (LLM, narrow and checkable) from **deterministic
artifact generation** (compiler/builder). This is the design choice Section 3 argues for.

### Module map

```
app.py                 FastAPI app + run store; every endpoint lives here
ui.py                  single-page UI (inline HTML/CSS/JS, no external deps)
config.py              lazy config: LLM provider client, Azure credentials, MOCK flag

models/logical.py      LogicalPlan — the typed plan the LLM fills (business
                        vocabulary: sources, transforms, outputs, pipelines,
                        containers, schedule, naming, folders)
models/spec.py         PipelineSpec — the ADF-shaped spec the compiler emits;
                        closed op vocabulary + naming + cross-reference checks

agent/ingest.py         BRD file/text intake (extract_brd_text)
agent/extractor.py      LLM call: BRD text → LogicalPlan (extract_plan / refine_plan)
agent/plantools.py      tool-agent planning mode: LLM builds the plan through
                         validated tool calls (PlanSession in planhandlers.py)
agent/completeness.py   offline plan checker/repairer (check, align_plan,
                         normalize_source_locations, infer_object_prefix)
agent/triage.py         unsupported asks → refusal + closest-alternative
                         suggestion; residual problems → chat questions
agent/compiler.py       deterministic: LogicalPlan → PipelineSpec
agent/builder.py        deterministic: PipelineSpec → ADF JSON + Data Flow
                         script DSL (pure, offline)
agent/grounding.py      reads real source schemas (file headers or table
                         metadata, read-only) to ground column names/types
agent/knowledge.py      ADF knowledge base for heal/lint/triage grounding
agent/preflight.py      offline safety gate: validate() — blocks approval on failure
agent/reviewer.py       LLM review pass over the built plan (findings, not edits)
agent/review.py         render()/render_text() — governance plan for the audit record
agent/plancache.py      identical BRD + mode + model → cached plan, zero LLM calls
agent/plandiff.py       human-readable diff between plan revisions (chat edits)
agent/deployer.py       provision_containers() + deploy_artifacts() (Azure or MOCK)
agent/validator.py      execute() — real run + per-layer status; self-heal loop
agent/skills.py         loads skills/*.md into every planning prompt
agent/lint.py, typecheck.py, retry.py   expression lint, type checking, LLM retry

tools/                  external-source connectors, schema readers, catalog reader
compilers/              per-source compile seam
knowledge/              ADF reference knowledge (grounding for heal/lint/triage)
ER-Diagram/             (linking-er) schema extraction + ER diagram app,
                         frontend + backend, catalog provider
```

### Where things live at runtime

- `artifacts/<run_id>/` — every generated ADF JSON object for a run (the audit trail of exactly
  what was deployed).
- `artifacts/.plan_cache/` — the plan cache.
- `artifacts/lesson_candidates.jsonl` + `skills/99-learned-lessons.md` — the learning loop.
- Run state is in-memory (`app._RUNS`) — a server restart forgets in-flight runs (known POC
  limitation; a DB swap fixes it).

## 5. HTTP Surface

| Endpoint | Purpose |
| --- | --- |
| `POST /plan` | BRD text/file → full plan + pre-flight + review. **No Azure writes.** |
| `POST /chat` | answer clarification questions / request plan edits; same conversation |
| `GET /preview/{run_id}` (+ `/text`, `/markdown`) | review JSON / governance plan |
| `POST /approve` | the gate: deploy + run for real (or MOCK) |
| `GET /status/{run_id}` | live deploy + Bronze→Silver→Gold run state |
| `POST /stop/{run_id}` | cancel an in-flight run |
| `GET/POST /azure-config`, `POST /azure-config/test` | runtime Azure target config + connectivity test |
| `GET /health`, `GET /` | health probe, the UI |

## 6. Request Lifecycle

### Phase 1 — `POST /plan` (generate, nothing deployed)

Every step is timed; the response carries a `timings` block plus `llm_calls`.

1. **Ingest** — `agent.ingest.extract_brd_text` normalizes the pasted text or uploaded file.
2. **Plan cache** — `agent.plancache`: identical BRD + same plan mode + same model returns the
   cached plan with zero LLM calls.
3. **Extract (the only mandatory LLM step)** — depending on `PLAN_MODE`:
   - `auto` (default): one LLM call via `agent.extractor.extract_plan` produces a `LogicalPlan`;
     repairs/refinements use the tool agent.
   - `tools`: the LLM never emits a whole plan — it builds one incrementally through validated
     tool calls (`upsert_source`, `upsert_transform`, `upsert_output`, `set_containers`,
     `set_schedule`, …) against a `PlanSession`; every call is validated on the spot and bad
     calls are rejected with the error fed back to the model.
   - `oneshot`: legacy — whole plan re-emitted each repair round.

   Pydantic validation is schema-enforced by the agent framework: no `json.loads`, no
   markdown-fence stripping.
4. **Completeness repair** — `agent.completeness.check` + `align_plan`: offline detectors find
   gaps (an output referencing an entity nobody ingests, a source missing its container, a
   declared output with no data path) and either fix them mechanically or send the plan back to
   the model with precise problem strings. `infer_object_prefix` / `normalize_object_prefix`
   enforce the prefix rules (prefix once, never `s-s-bronze`). `invented_sources` rejects sources
   the BRD never mentioned.
5. **Triage** — `agent.triage`: asks the BRD cannot express in the closed vocabulary (SCD Type 2,
   Teams alerts, pivots, …) are moved to an explicit `unsupported` list with a closest-supported
   `suggestion` each — the runnable remainder still builds. Problems the repair loop could not fix
   become plain chat questions (`NEEDS_CLARIFICATION`) instead of a 422.
6. **Compile** — `agent.compiler.compile_plan`: deterministic `LogicalPlan → PipelineSpec`; then
   `agent.builder` emits per-object ADF JSON (linked services, datasets, data flows, pipelines,
   triggers) and the Data Flow script DSL into `artifacts/<run_id>/`.
7. **Grounding** — `agent.grounding.ground_logical_plan` (when `GROUND_PLAN=true`): reads real
   source schemas — the first 64 KB of a file, or table metadata for an external source, always
   read-only — and replaces guessed column names/types with real ones, then recompiles. On
   `linking-er`, grounding is **catalog-first**: if the source's schema was already extracted and
   reviewed in the ER Diagram app, the reviewed schema is used and noted as
   "grounded from catalog v*N*"; otherwise it live-probes. Unreadable sources are skipped, not fatal.
8. **Pre-flight** — `agent.preflight.validate`: offline gate — spec valid, naming enforced,
   cross-references resolve, JSON well-formed, Bronze Copy present, Silver/Gold scripts present,
   type checks pass. Failures loop back through repair; if still failing, approval stays disabled.
9. **Review** — `agent.reviewer` (LLM findings on the built plan) + `agent.review.render` (the
   governance plan). The response returns `run_id`, summary, pre-flight result, clarifications,
   unsupported list + suggestions, and the full review.

`POST /chat` (`refine_plan`) continues the same conversation: the user answers a clarification or
asks for a change; the plan is edited through the same validated path, re-compiled,
re-preflighted, and `agent.plandiff.diff` shows the user exactly what changed.

### Phase 2 — `POST /approve` (build and run for real)

Hard gate: a prior preview **and** a green pre-flight are required, otherwise the request is
rejected.

1. **Source-file gate** — before anything is created, every storage source blob is checked to
   exist; a missing file aborts with a precise `BlobNotFound` message and **nothing is deployed**.
2. **Provision containers** — `agent.deployer.provision_containers`: creates only the layer
   containers the approved plan needs (idempotent).
3. **Deploy** — `agent.deployer.deploy_artifacts`: `create_or_update` on every artifact in
   dependency order (linked services → datasets → data flows → pipelines → triggers). Re-running
   produces no duplicates. Stale agent-created objects from earlier runs are **reported, never
   deleted** (`PRUNE_STALE=false` is the default; the agent never deletes from the tenant).
4. **Run** — `agent.validator.execute`: `create_run` on the master pipeline, then polls ADF,
   mapping activity states to per-layer Bronze/Silver/Gold status with ADF run IDs. Status
   streams to the UI via `GET /status`.
5. **Self-heal (default on)** — on a runtime failure, `heal_artifact` gives the LLM the failed
   artifact + the exact ADF error + schema context; the healed artifact is linted, redeployed,
   and the run retried up to a capped number of times. Every heal is logged and feeds the
   learned-lessons loop. `SELF_HEAL=false` switches to fail-loud.

With `MOCK=true` the same flow writes to `mock_tenant/` and simulates the run — the UI shows a
MOCK banner; no Azure account needed.

## 7. Capabilities

The planning model works against a **closed operation vocabulary** (`models/logical.py` +
`models/spec.py`). Anything inside the vocabulary compiles deterministically to ADF; anything
outside it is surfaced as an explicit `unsupported` item with a suggested closest alternative —
never silently dropped, never invented.

### Sink formats

- **Delta** (with correct overwrite semantics — `truncate`/`overwrite` only; the invalid
  `recreate` mode is guarded against), **Parquet**, **CSV**
- Mixed formats across gold outputs in one run (e.g. one Delta + one CSV mart)

### Silver transformations (per entity)

- **Casts**: string, integer, long, double, decimal(p,s), boolean, date, timestamp — including
  timestamps with spaces/odd headers (aliased safely for the Data Flow DSL)
- **Cleaning ops**: trim, upper, lower, proper-case, replace, regex replace,
  remove-special-characters, blank-to-default, coalesce, substring, length, round, abs, floor,
  ceil, concat
- **Date parts**: year, month, day, day-of-week, day-of-year, week, quarter, hour, minute, second
- **Arithmetic derived columns**: add/subtract/multiply/divide over columns and literals,
  chainable (e.g. `line_revenue = quantity * list_price * (1 - discount)`), with safe division
  rendered via `iif`
- **Conditional values** (`case` op): ordered when/then branches + otherwise — used for KPI
  buckets and tier labels ('Platinum'/'Gold'/…)
- **Filters** (AND-ed): null / not-null, =, ≠, >, ≥, <, ≤, IN / NOT IN, BETWEEN, LIKE / NOT LIKE,
  regex match
- **Deduplication** on any key set
- Audit columns on the silver layer

### Gold outputs

- **Joins**: inner, left, right, outer, cross — including multi-entity join chains (6-way joins
  proven in benchmarks), and heterogeneous cross-source joins (e.g. SharePoint × Dataverse)
- **Group-by + aggregations**: sum, avg, min, max, count, count distinct, first
- **Pre-aggregation filters** and **post-aggregation derived columns** (including case buckets
  over aggregated measures)
- **Sort** ascending/descending; **top-N** (rendered as rank + filter — the Data Flow DSL has no
  `limit()`)
- Multiple gold outputs per run (8-output gold layers proven)

### Orchestration and packaging

- Master pipeline chaining Bronze → Silver → Gold with `dependsOn: [Succeeded]`; **BRD-named
  multi-pipeline structures** (e.g. `s_PL_Landing_To_Bronze` / `s_PL_Bronze_To_Silver` /
  `s_PL_Silver_To_Gold` chained under `s_PL_Master` via ExecutePipeline)
- **Schedules** (e.g. daily at 02:00 UTC). "Run manually / on demand" is the default and correctly
  treated as *not* a schedule
- **Custom layer containers** when explicitly named (`warehouse-raw` / `warehouse-clean` /
  `warehouse-reporting`); defaults `bronze`/`silver`/`gold` otherwise; only the containers the run
  needs are created
- **Object naming prefixes** on request (`s-` → `s-bronze`, applied exactly once; source
  containers like `s-landing` are never mistaken for a prefix request)
- **ADF Studio folder grouping** (opt-in): everything a project creates grouped under a named root
  folder with per-entity subfolders, so the whole project can be found and deleted at once
- Optional per-source "verify file exists / is non-empty before loading" validation activities
- Naming convention `ls_/ds_/df_/pl_` enforced by code

### Behavior at the boundary (this is a feature, not a gap)

- **Ambiguous BRD** → the app asks plain-language clarification questions in chat and builds
  nothing it would have to invent
- **Unsupported ask** → listed explicitly with a closest-supported suggestion, while the runnable
  remainder of the BRD still deploys
- **Nonexistent column** → dropped and reported in assumptions, not invented
- **Unsafe plan** → pre-flight blocks the approve button; a missing source file blocks at the
  deploy gate with a precise error before anything is created

## 8. Source Coverage

The `SourceFormat` vocabulary in `models/logical.py`. External (non-Azure) sources land in bronze
via a native ADF Copy or an app-side seed, then follow the identical silver/gold path.

| Source | Status | Notes |
| --- | --- | --- |
| **Azure Blob / ADLS Gen2** (csv, text, parquet, json, binary) | Proven, most exercised | The primary path; every storage suite runs on it |
| **Anonymous HTTP CSV** | Proven end-to-end | Public URL pulled into landing, full medallion built on it |
| **Postgres** | Proven live e2e | Local, Cloud SQL, or Azure DB for PostgreSQL; schema-grounded |
| **Dataverse / Dynamics 365** | Proven live e2e | Native Dataverse Copy; grounded on live entity metadata; needs an Application User grant in the environment |
| **BigQuery** | Proven live e2e | Keyless ADC app-seed of a BQ table into bronze |
| **SharePoint Online lists** | Plans natively; deploy needs a seeded bronze blob | Graph app-only auth; `Sites.Selected` requires a per-site grant |
| **GCS** | Plans; deploy seeds from the bucket | Object existence currently surfaces at runtime, not the approve gate |
| **SQL table metadata** (`sql_table`) | Plans and emits a real SQL Copy | Least schema-grounded path; builds on assumed columns unless grounded |

Credentials never come from BRD text. External connectivity is configured through environment
variables, managed identity, or service principal credentials.

## 9. The BRD Corpus

Every BRD the agent has been tested against is catalogued in
[docs/BRD_CORPUS.md](BRD_CORPUS.md) — which suite, which branch, and what each was designed to
prove. Summary:

| Suite | BRDs | Branch | Focus |
| --- | --- | --- | --- |
| `tests/gold_silver_brds.md` | 14 | all | Silver/gold op coverage; BRDs 11–14 are prescriptive (exact ADF object names) |
| `tests/heldout_brds.md` | 5 | all | Fresh unseen BRDs, frozen code, no manual repair |
| `tests/stress_brds.md` | 10 | all | One BRD per untested dimension, incl. ambiguity and refusal traps |
| `tests/external_suite_brds.md` | 10 | external branches | Dataverse, SharePoint, Postgres, HTTP, cross-source |
| `tests/tough_suite_round3_brds.md` | 10 | external branches | Harder shapes + regression of earlier fixes |
| Per-source BRDs (`dataverse`, `gcp`, `sharepoint`, `postgres`) | 4 | external branches | Single-source medallions |

The corpus deliberately spans four BRD shapes: **descriptive** (business prose, agent infers
names), **prescriptive** (BRD names every ADF object — the bike-store 8-output analytics BRD is
canonical), **trap** (correct answer is a question or a refusal, not a pipeline), and
**external-source** (bronze pulls from a non-Azure system).

## 10. Limitations and Unsupported Scope

### Not supported (refused honestly, with suggestions)

- **SCD Type 2 / dimension history** — out of the vocabulary; alternative offered (e.g. plain
  overwrite dimension)
- **Alerts/notifications** (Teams, email, webhooks on failure)
- **Pivot / unpivot** transformations
- **Databricks, Synapse, Fabric** — ADF only, by design
- **Real-time / streaming** — batch medallion only
- **Free-form custom Data Flow expressions from the BRD** — only the closed vocabulary compiles;
  this is the safety property, not a gap
- **Private/authenticated HTTP sources** — HTTP sources are anonymous public URLs only
- **Key/SAS/connection-string auth for Azure** — deliberately absent; Managed Identity / service
  principal only

### Known POC limitations (engineering debt, not design)

- **Run store is in-memory** (`app._RUNS`) — a server restart forgets in-flight runs; the deployed
  ADF objects and the `artifacts/` audit trail are unaffected. Swap for a DB to survive restarts.
- **The approve gate pre-checks Azure landing blobs but not GCS object existence or SQL Server
  reachability** — those two fail at runtime after real objects are created. Honest failure, but
  later than it should be.
- **SharePoint seeding path mismatch** — the bronze seeder and the compiler's expected landing
  path disagree, so SharePoint deploys need manual seeding at the compiler's path.
- **SQL Server has no first-class `SourceFormat`** — it plans and emits a real SQL Copy, but
  without schema grounding, so it builds on assumed columns.
- **The self-heal loop requires LLM access at run time** (disable with `SELF_HEAL=false` for
  fail-loud behavior).
- Type inference on ungrounded sources is best-effort; grounding removes most of this risk.

## 11. Container and Naming Rules

Container behavior was a major test focus. The product does not hardcode every run to one
container scheme; it follows the BRD: defaults when unnamed, exact custom containers when named,
prefixes only when explicitly requested.

| BRD wording | Expected behavior | Example |
| --- | --- | --- |
| No custom containers named | Create/use default medallion containers | `bronze`, `silver`, `gold` |
| Custom containers named | Use those names exactly | `warehouse-raw`, `warehouse-clean`, `warehouse-reporting` |
| Source is in `s-landing` | Treat `s-landing` as existing input, not a prefix | Source container remains `s-landing` |
| Everything created must start with `s-` | Prefix created objects/containers exactly once | `s-bronze`, `s-silver`, `s-gold` (never `s-s-bronze`) |
| "Bronze raw" | Raw means unchanged copy, not a container literally named `raw` | Bronze output still defaults to `bronze` unless `raw` is explicitly named |

## 12. Safety, Governance, and Approval Controls

The app is designed to avoid silent tenant changes. Planning and review never deploy anything.
Approval requires a passing pre-flight, and unsupported requirements require explicit
acknowledgement before deployment.

| Control | Purpose |
| --- | --- |
| No Azure writes during `/plan` | Lets users inspect the generated plan safely before any tenant change |
| LLM has no tenant credentials | The model cannot create, modify, or delete anything — only deterministic code calls Azure |
| Pre-flight gate | Blocks invalid specs, broken references, bad naming, bad expressions, unsupported activity types |
| Preview and governance plan | Creates an approval record with generated objects and pipeline logic |
| Unsupported acknowledgement | Prevents known-incomplete requirements from deploying silently |
| Managed identity / service principal auth | Avoids account keys, SAS tokens, hardcoded credentials |
| Never delete | `PRUNE_STALE=false` default: stale objects are reported, a human deletes |
| Cleanup capability | Artifact records can be used to remove app-created ADF objects and generated containers |

The app does not accept raw secrets from BRD text; BRDs describe the logical source only.
User-provided secrets inside BRD text are treated as a security anti-pattern.

## 13. Validation Evidence

Two kinds of evidence: a fast **offline unit suite** (no Azure, no LLM) and repeated **end-to-end
benchmark suites** where full BRDs were pushed through `/plan → /approve → real Azure deploy →
real ADF run → /status` against a live subscription. Benchmark rule for every suite: run the BRDs
**as written** — no code edits, no BRD rewording mid-run; the app's built-in repair/self-heal runs
normally and the result is recorded honestly.

### Headline numbers

| Suite | BRDs | Result | Environment |
| --- | --- | --- | --- |
| Offline unit tests (`pytest tests -q`) | 192 tests / 30 modules | **192 passed**, ~27 s | local, no Azure/LLM |
| Final hard suite | 10 | **9/10 ran green**; 1 blocked *safely* by pre-flight | real Azure |
| Held-out suite — frozen code, fresh unseen BRDs | 5 | **5/5 PASS** | real Azure |
| Stress suite — one BRD per untested dimension | 10 | **10/10** end-to-end | real Azure |
| Tough all-aspects suite | 8 | **6/8 first pass**; 2 blocked pre-deploy by the source-file gate, both green on rerun → 8/8 | real Azure |
| Folder-grouping E2E | 2 | **2/2** incl. ADF-tree folder verification | real Azure |
| **Unified E2E (2026-08-04, `linking-er`)** | 20 plans + 8 deploys | **20/20 plans passed pre-flight**; **5/5 "should-work" deploys SUCCEEDED** | real Azure, 6 source types |

Across all end-to-end suites, **zero silent failures**: every non-green outcome was a validation
gate stopping an unsafe or un-runnable deploy, with a precise error message.

### What each suite proves

**Offline unit suite (192 tests).** Covers the deterministic core with no network: compiler
output, Data Flow IR, container/prefix rules (including the `s-s-bronze` double-prefix
regression), ADF folder stamping, naming prefixes, completeness repair, invented-source
rejection, triage, type checking, semantic guards, plan diff, plan cache, plan-tool validation,
LLM retry logic, learned-lessons distillation. Reproduce: `python -m pytest tests -q` (~27 s).

**Final hard suite — 9/10.** Ten varied medallion BRDs (multi-entity joins, custom containers,
explicit `s-` prefixes, unsupported asks mixed into runnable work). The one failure: the generated
transform attempted `upper()` on a column source inference had treated as integer — **pre-flight
blocked approval and nothing was deployed**. That is the design working: a safe failure rather
than a bad deploy.

**Held-out suite — 5/5 (the "usable by others" measurement).** Code frozen, five brand-new BRDs
the system had never seen, no manual repair allowed. All five passed — including a copy-only
scheduled ingest from a public URL that deployed and ran end-to-end. The beta-usability bar (≥4/5)
cleared.

**Stress suite — 10/10.** One BRD per previously untested dimension: HTTP source with a full
medallion; a 6-way join at scale; copy-only multi-file; text/binary formats; IN/BETWEEN/LIKE/regex
filters; regex cleaning ops; a deliberately **ambiguous BRD that must ask a question instead of
building** (it did); an **unsupported-heavy BRD that must refuse** (it did); custom containers plus
a named deploy target; and a messy, informally-worded BRD.

**Tough all-aspects suite — 8/8 (6 first-pass + 2 after data upload).** Every supported feature
dimension at once, plus traps — negative prefix wording, unsupported asks (Teams alerts, SCD
Type 2) mixed with runnable work, columns with spaces, BRD-named pipeline structures, mixed gold
formats, external HTTP pull, ADF folders combined with a naming prefix, post-aggregation tier
bucketing. The two first-pass blocks were the **deploy-time source-file gate working as designed**:
the named landing blobs did not exist, approve aborted with an exact `BlobNotFound` per file, and
nothing was created; both ran fully green on rerun after upload.

**Unified E2E, 2026-08-04 (`linking-er`) — the broadest run.** 20 medium-to-tough BRDs across six
source types (Postgres, BigQuery, Dataverse, SharePoint, GCS, SQL Server) plus cross-source joins,
driven entirely over the app's own HTTP APIs as a user would.

- **20/20 produced a buildable, pre-flight-passing plan.** Zero failed checks, zero HTTP errors.
- **Honesty behavior was correct throughout**: unsupported asks flagged with alternatives, a
  nonexistent column dropped and reported, and the underspecified BRD **asked two clarifying
  questions instead of inventing**.
- **Live deploys: 5 SUCCEEDED / 1 gate-blocked / 1 runtime error / 1 correct terminal failure.**
  All five "should-work" cases (Postgres ×2, Dataverse, BigQuery, cross-source SharePoint ×
  Dataverse) ran green end-to-end on live Azure.
- **Self-heal behaved correctly in all three modes**: it *recovered* two real live-Azure Data Flow
  failures in one attempt each (runs then went green), *gave up cleanly* where the source was
  fundamentally unavailable (a fictional SQL host: two attempts, then a clean terminal failure, no
  runaway), and *stayed out of the way* on clean runs (zero heals).
- **Stale handling confirmed**: the deploy report listed 68 stale objects with `pruned: []` — it
  reports, never deletes.

### What was verified beyond "the run went green"

- **Data landed correctly**: raw byte-for-byte file in bronze, cleaned/deduped Parquet/Delta in
  silver, aggregated marts with derived KPIs in gold — checked in the ADLS containers and ADF
  Monitor.
- **Idempotency**: re-approving the same run creates no duplicate objects; bronze overwrites; the
  run repeats cleanly.
- **Safety**: the agent never deleted anything from the tenant; stale objects were reported only.
- **Plan-phase performance**: every `/plan` response carries per-phase timings + LLM call counts;
  the plan cache gives identical BRDs a zero-LLM-call replan; warm grounding dropped from ~8 s to
  ~12 ms via memoized clients.

### Honest failure catalog (found by the benchmarks, all fixed)

- Invalid `recreate` mode on Delta sinks (only truncate/overwrite are valid) — the dominant early
  failure; fixed and guarded.
- `limit()` in the Data Flow DSL does not exist — top-N is now compiled as rank + filter.
- Column names with spaces break the Data Flow DSL / Delta sinks — now aliased automatically.
- Type mismatches in coalesce/joins/comparisons (ADF errors DF-DT-001, DF-FN-0015, DF-EXPR-010) —
  now caught by the type checker and encoded as learned lessons.
- A source with an omitted container silently defaulted to `landing` and hit the deploy gate —
  sources now always carry the BRD-named container.

## 14. Deployment and Operations

### What the app itself is

One Python FastAPI process (`uvicorn app:app`), single-page UI served inline, no database, no
Docker required. State per generated plan lives in `artifacts/<run_id>/` on disk (the audit trail)
and in memory (`app._RUNS`) for run status.

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload        # open http://127.0.0.1:8000
```

On `linking-er` the unified app additionally runs the ER Diagram backend and frontend;
`docker-compose` supervises all of them together.

### Azure prerequisites (for the real build + run)

1. Azure subscription + resource group
2. An **Azure Data Factory** instance in that resource group
3. An **ADLS Gen2 storage account** with hierarchical namespace enabled
4. An identity the app runs as (Managed Identity in Azure, or service principal / `az login`
   locally) with **Data Factory Contributor** on the resource group and **Storage Blob Data
   Contributor** on the storage account. The ADF's own Managed Identity also needs **Storage Blob
   Data Contributor** so pipelines can read/write data at run time.
5. An LLM endpoint for the plan phase

**No storage keys, SAS tokens, or connection strings anywhere** — identity auth only. Secrets come
from env vars / Key Vault, never code.

### Behavior flags (defaults shown)

| Flag | Default | Meaning |
| --- | --- | --- |
| `MOCK` | `false` | `true` = full dry-run: deploys to `mock_tenant/`, simulates the run, UI shows a MOCK banner. Demo without an Azure account. |
| `SELF_HEAL` | `true` | LLM repairs a failed artifact at run time (capped retries, every heal logged). `false` = fail loud. |
| `PRUNE_STALE` | `false` | The agent **never deletes** tenant objects. Stale objects are reported only. |
| `PLAN_MODE` | `auto` | `auto` = one LLM call + tool-agent repairs; `tools` = every edit via validated tool calls; `oneshot` = legacy. |
| `PLAN_CACHE` | `true` | Identical BRD + mode + model → cached plan, zero LLM calls. |
| `GROUND_PLAN` | `true` | `/plan` reads real source schemas (read-only) to ground columns. `false` = fully offline plan phase. |
| `ER_CATALOG_URL` / `CATALOG_SOURCE_ID` | unset | Catalog-first grounding from a reviewed ER diagram; unset = live-probe as before. |
| `CATALOG_DRIFT_CHECK` | `0` | Also live-probe a catalog-grounded source and flag drift as an advisory note. |

### Operational safety guarantees

- **Nothing is created in the tenant before explicit approval.** `/plan`, `/chat`, `/preview` are
  read-only toward Azure (grounding reads schemas only).
- **Approval is gated**: a prior preview *and* a green pre-flight are required.
- **Deploy-time source gate**: Azure source blobs are checked to exist before any object is
  created; a missing file aborts the whole approve.
- **Idempotent deploys**: `create_or_update` everywhere; re-approving never duplicates objects.
- **No deletes, ever**: cleanup lists are report-only by default.
- **Fail loud, visibly**: run failures surface the exact ADF activity error with run IDs;
  self-heals are logged and auditable, and repeated incidents are distilled into
  `skills/99-learned-lessons.md`.

### Verifying a run (operator checklist)

1. **UI live status**: Bronze → Silver → Gold with ADF run IDs.
2. **ADF Monitor** (portal → Data Factory → Monitor → Pipeline runs): master run + child activities.
3. **ADLS containers**: bronze raw file (byte-for-byte), silver cleaned Delta/Parquet, gold
   aggregated marts with derived KPIs.
4. **Idempotency**: re-approve → no duplicates, clean repeat.

## 15. Operational Workflow

| Step | Operator action | System output |
| --- | --- | --- |
| 1 | Start app with configured environment | Local UI available |
| 2 | Paste/upload BRD | Run ID, plan summary, assumptions, unsupported items |
| 3 | Review generated artifacts | ADF JSON, dataflow scripts, governance review |
| 4 | Resolve clarifications or unsupported acknowledgements | Plan becomes approvable or remains blocked |
| 5 | Approve | Containers and ADF objects are created/updated |
| 6 | Monitor | Live status with ADF run IDs and per-activity outcomes |
| 7 | Clean up if needed | Artifact-listed resources can be deleted safely, preserving source containers |

### Stage summary

| Stage | What happens | Azure writes? |
| --- | --- | --- |
| Plan | BRD parsed into a typed logical plan; schemas read for grounding | No |
| Compile | Logical plan converted deterministically into ADF-ready spec and artifacts | No |
| Pre-flight | Artifacts checked for naming, references, JSON validity, wiring, expression types | No |
| Review | User sees objects, scripts, governance plan, unsupported items, assumptions | No |
| Approve | App provisions containers, creates/updates ADF objects, starts a run | Yes |
| Monitor | App polls Azure run status and reports per-activity state | Read/status only |

### Performance notes

Planning is fast — often seconds per BRD. The slow portion is Azure runtime: ADF pipeline startup,
Mapping Data Flow cluster warm-up, deployment/provisioning, and queue behavior. For fast
evaluation, separate plan/pre-flight score from deployability score and full runtime score.

| Measurement type | What it proves | Expected speed |
| --- | --- | --- |
| Plan/pre-flight | Agent reasoning and safety gates | Seconds to under a minute per BRD |
| Deployability | ADF artifacts can be provisioned | Minutes depending on Azure |
| Runtime | ADF pipelines execute with real data | Slowest; dataflow spin-up dominates |

## 16. Future Scope

The POC proves the BRD → pipeline path. The next phase closes the loop on the two ends: where the
schema comes from, and where the source credentials come from.

### 16.1 ER Diagram → pipeline builder (the catalog seam)

Today the agent grounds a plan by probing the source itself. That works, but it means the schema
the pipeline is built on is whatever the agent happened to read at plan time — never reviewed by a
human, never versioned.

The direction is a **catalog seam** between the ER Diagram application and the pipeline builder,
with a clean division of ownership: **ER owns schema truth, the agent consumes it.**

```
ER app:  connect → extract → review → SHARE diagram  ──►  share token = source_id
                                                            │
agent /plan:  grounding reads GET {ER_CATALOG_URL}/catalog/{source_id}
              catalog hit  → ground from the reviewed schema  ("from catalog v4")
              catalog miss → live-probe the source            ("from PostgreSQL")
```

An engineer connects a source in the ER app, extracts its schema, sees it as an ER diagram with
real relationships, corrects anything wrong, and shares it. The agent then builds the pipeline
against *that reviewed schema* — so the schema that built the pipeline is the schema a human
approved, and it carries a version number.

**Status:** built and HTTP round-trip proven. The contract is the ER app's existing
`DatabaseSchema` JSON plus `source_id` and `schema_version`; no new auth or storage — it reuses the
ER app's existing share token. It is fully opt-in: unset the env vars and grounding behaves exactly
as before. Optional `CATALOG_DRIFT_CHECK=1` also live-probes and raises a loud advisory note if the
real source has drifted from the reviewed catalog (added/removed columns, type changes) — advisory
only; it never blocks a deploy.

**What is left:** the full Flow-1 → Flow-2 handoff (diagram → grounded pipeline) has not yet been
demonstrated end to end because diagram storage is GCS-backed and needed credentials were missing
in the test environment. The endpoint degrades gracefully (404 → live-probe fallback), so nothing
is blocked; the demonstration is what remains. Multi-source per run is also deferred — currently
one `CATALOG_SOURCE_ID` at a time.

### 16.2 User-side source connection

Today external source credentials come from environment variables set by whoever runs the app.
That does not scale past a demo: every new source is a config change and a restart.

The direction is a **user-side connect flow** — the user picks their source type in the UI,
authenticates as themselves, and the app uses that grant for schema extraction and pipeline
construction. The ER application already implements this for schema extraction; extending it to
the pipeline builder is the work.

| Source | Connect mechanism | Current state |
| --- | --- | --- |
| **PostgreSQL** | Direct credentials | Working — connect, list databases, extract 33-table schemas |
| **SQL Server** | Direct credentials | Connect + extract work; **no native mover in the pipeline compiler yet** — the gap to close first |
| **BigQuery / GCP** | Google OAuth token minted in the browser | Connect implemented; pipeline side proven live via keyless ADC |
| **GCS** | Google OAuth token | Connect implemented; deploy-time object pre-check still needed |
| **Dataverse / Dynamics 365** | MSAL OAuth; app needs an Application User in the environment | Proven live end-to-end |
| **SharePoint Online** | MSAL OAuth; Graph `Sites.Selected` per-site grant | Connect built; pipeline seeding path needs alignment |

Four of the six (Dataverse, SharePoint, BigQuery, GCS) require a live OAuth token minted by the
browser, which is why their connect path can only be validated through the real frontend and not
headlessly — a testing constraint worth planning around rather than a defect.

**Prioritized next steps for this track:**

1. **First-class `sqlserver` source** in the logical model with schema grounding, matching the
   other five. Today SQL Server can be connected in the UI but the pipeline builder has no native
   mover, and it plans on assumed columns.
2. **Source-liveness pre-checks at the approve gate** for GCS object existence and SQL
   reachability, so those refuse at the gate like Azure blobs already do, instead of failing after
   real objects are created.
3. **Align the SharePoint bronze seeding path** with the compiler's expected landing path so
   SharePoint deploys without manual intervention.
4. **Demonstrate the Flow-1 → Flow-2 handoff end to end** once diagram storage credentials are in
   place.
5. **Per-user credential storage** (Key Vault-backed) so a connected source persists for that user
   rather than living in process env vars.

### 16.3 Other tracks

| Area | Current limitation | Next step |
| --- | --- | --- |
| Run store | In-memory app run state | Durable DB — needed for production and restart resilience |
| Secrets | No BRD-supplied secrets accepted | Key Vault / managed identity design for authenticated sources |
| Talk-to-data | Advisor can 500 on a malformed LLM query step; sometimes explains instead of executing | Degrade gracefully per step; execute when a concrete aggregate is requested |
| Unsupported platforms | No Databricks, Event Hub streaming, Teams alerts, notebooks | Keep as explicit unsupported, or build connectors later |
| Runtime speed | ADF Data Flow runs are slow | Smaller smoke tests; separate plan/deploy/runtime scoring |
| Benchmark purity | Manual code/BRD edits distort scores | Keep code and BRDs frozen; let app repair run naturally |

## 17. Production Readiness

This POC is credible for controlled internal evaluation and beta-style use with data engineers
reviewing every plan before approval. It is **not yet** a fully autonomous production deployment
system.

| Readiness question | Answer |
| --- | --- |
| Can it deploy real ADF pipelines? | Yes, demonstrated end to end across six source types |
| Can it support custom container conventions? | Yes, verified |
| Can it honor a prescriptive BRD that names every ADF object? | Yes — the bike-store 8-output BRD is the proof case |
| Can it avoid writing to Azure before review? | Yes, `/plan` is read-only except schema reads |
| Can it safely block bad generated logic? | Yes, pre-flight blocked invalid transforms in every suite where they occurred |
| Can the LLM damage the tenant? | No — it has no tenant credentials; only deterministic code calls Azure |
| Can it replace a data engineer today? | No; it accelerates generation and review but needs human approval |
| Is Docker needed? | Not for the agent alone; `docker-compose` is used for the unified `linking-er` app |

### Benchmark interpretation note

A fair benchmark freezes code and BRD text, allows the app's built-in repair/self-heal behavior to
operate, and records the final status. Manual code edits during a run should not be counted as app
success. Pre-flight failures are **not** deployment failures — they are safe, non-deployable
outcomes that should be counted honestly and investigated afterward.

## 18. Appendix: Code Map and Branch Map

| File/folder | Why it matters |
| --- | --- |
| `README.md` | Operator setup, workflow, supported behavior, test status |
| `app.py` | API and web app orchestration |
| `ui.py` | Browser UI |
| `config.py` | LLM and Azure configuration |
| `models/` | Typed logical and ADF spec models — the closed vocabulary |
| `agent/` | Planning, compilation, building, pre-flight, deployment, validation |
| `compilers/` | Per-source compile seam |
| `tools/` | External-source connectors, schema readers, catalog reader |
| `knowledge/` | ADF reference knowledge for heal/lint/triage grounding |
| `skills/` | Rules and lessons that guide planning and repair |
| `tests/` | Unit tests, regression tests, BRD benchmark suites |
| `docs/BRD_CORPUS.md` | Index of every BRD suite, branch, and what it proves |
| `artifacts/` | Generated run artifacts and summaries; audit and cleanup |
| `ER-Diagram/` | (`linking-er`) schema extraction + ER diagram app; the catalog provider |

### Branch map

| Branch | Purpose | Relationship |
| --- | --- | --- |
| `main` | Stable baseline for the BRD-to-ADF agent and its passing BRD test set | Base branch for the feature branches below |
| `brd-passed-version` | Historical checkpoint of the BRD-tested version; won a live bake-off against `main` | Local branch currently matches `main` |
| `linking-external-source` | Adds and tests external sources: Dataverse, Postgres, BigQuery/GCS, SharePoint tooling | Ahead of `main`; included in `linking-er` |
| `linking-er` | Unified application: ADF agent + external sources + redesigned UI + catalog seam + `ER-Diagram/` frontend/backend | Built on `linking-external-source`; the integration branch for the complete app |

Use `main` for agent-only changes and `linking-er` for work that depends on the unified ER
Diagram/catalog application. Do not commit `.env`, cloud credentials, service-account JSON,
generated artifacts, or tenant output.
