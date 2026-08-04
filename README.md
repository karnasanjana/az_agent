# BRD → ADF Medallion Agent

A production web app that turns a data engineer's **Business Requirements Document**
into a deployed **Azure Data Factory** medallion pipeline (Bronze → Silver → Gold),
shows the generated pipelines for review, and on approval **builds and runs them for
real** in your Azure subscription — with live Bronze→Silver→Gold run status streamed
back. ADF only (no Databricks/Synapse/Fabric). Nothing touches your tenant before
approval.

```
BRD in  →  agent GENERATES pipelines  →  SHOW user (JSON + Data Flow scripts + visual
governance plan)  →  user APPROVES  →  agent CONNECTS TO AZURE, BUILDS + RUNS
for real  →  live run status streamed back.
```

It is **BRD-driven and not hardcoded to one dataset**. A COVID-19 (Johns Hopkins)
BRD ships as the working example, but the agent builds any medallion pipeline its BRD
describes. Sources supported: HTTP/HTTPS file (anonymous), Azure Blob/ADLS, and a
generic REST/CSV endpoint.

## How the layers map (this is the contract)

| Layer  | ADF object | Transformation | Review shows |
| ------ | ---------- | -------------- | ------------ |
| **Bronze** | **Copy Activity only** | none — byte-for-byte raw landing, idempotent overwrite | Copy Activity JSON labelled *"raw landing, no transformation"* — **no script section (its absence is correct)** |
| **Silver** | **Mapping Data Flow** | cast, null handling, filter, dedup, audit columns → Parquet | Data Flow JSON **+ script** |
| **Gold**   | **Mapping Data Flow** | aggregations, derived KPIs (safe division via `iif`), sort | Data Flow JSON **+ script** |

`pl_master_pipeline` chains Bronze → Silver → Gold with `dependsOn: [Succeeded]`, so a
failed Bronze halts downstream work. Naming prefixes `ls_/ds_/df_/pl_` are enforced.

## Design choice that de-risks the hard part

Claude is **never** asked to free-form-write ADF JSON. The LLM reasons in exactly two
places:

1. **Parse** the BRD into a **typed, validated `PipelineSpec`** (Pydantic AI — schema
   enforced, no `json.loads`, no fence-stripping).
2. *(Optional, off by default)* **Self-heal** a failed artifact.

The deterministic `builder.py` turns the typed spec into deployable ADF JSON and the
Data Flow script DSL. So Data Flow JSON generation is reliable **by construction** —
Claude fills structured transform fields; code emits the JSON. (`tests/smoke_test.py`
is the spike that proves this offline.)

**v1 is fail-loud.** On a failed run the error is surfaced in the UI; the Claude
self-heal retry loop is enabled by default and can be disabled with `SELF_HEAL=false`.
failure modes.

## Three-phase validation plan

```
Local dry-run          Azure smoke test        Azure data test
──────────────         ────────────────        ───────────────
JSON valid?      →     Did it deploy?    →     Did data land?
Spec correct?          Did it run?             Are rows correct?
Naming ok?             No SDK errors?          Is it idempotent?
seconds, no deps       ~2 min, Azure access    ~5 min, Azure + data
MOCK=true / smoke_test  small BRD on real ADF   full COVID BRD end-to-end
```

## Project layout

```
models/spec.py      PipelineSpec + sub-models (Http/Blob/Rest sources, Dataset,
                    Transform, DataFlow, Trigger, PipelineDef) + validate_naming()
                    + cross_reference_errors()
config.py           Foundry/Claude client + Azure config + RETRY_CAP + MOCK flag (lazy)
agent/parser.py     Pydantic AI agent: BRD text -> validated PipelineSpec
agent/builder.py    PipelineSpec -> ADF JSON + Data Flow script DSL (pure, offline)
agent/review.py     render() / render_text() - basic execution flow and governance plan
agent/preflight.py  validate() — offline safety guard; blocks approval on failure
agent/deployer.py   provision_containers() + deploy_artifacts() (Azure or MOCK), idempotent
agent/validator.py  execute() — live run + per-layer status; fail-loud; self-heal default-on
ui.py               single-page UI (inline HTML/CSS/JS, no external deps)
app.py              FastAPI: /plan /preview /approve /status /
samples.py          shipped COVID BRD + sample spec
tests/smoke_test.py offline spike / local dry-run
Dockerfile, docker-compose.yml
```

## Azure prerequisites (for the real build + run)

1. An **Azure subscription** and a **resource group**.
2. An **Azure Data Factory** instance in that resource group.
3. An **ADLS Gen2 storage account** with **hierarchical namespace enabled**.
4. An **identity** the app runs as (Managed Identity when hosted in Azure, or a
   service principal locally) with:
   - **Data Factory Contributor** on the resource group (to create_or_update ADF objects), and
   - **Storage Blob Data Contributor** on the storage account (to create containers / write data).
   The **ADF's own Managed Identity** also needs **Storage Blob Data Contributor** on the
   account so the pipelines can read/write data at run time.
5. A **Claude on Azure AI Foundry** deployment (Anthropic-compatible endpoint).

No storage account keys, SAS tokens, or connection strings anywhere — Managed Identity
/ service principal only.

## Configuration (environment variables)

Foundry / Claude (needed for `/plan`):

```bash
export FOUNDRY_BASE_URL="https://<resource>.services.ai.azure.com/anthropic"
export FOUNDRY_API_KEY="<key>"          # never hardcoded; env or Key Vault only
export CLAUDE_MODEL="claude-opus-4-8"    # default if unset
```

Azure (needed for `/approve`, unless `MOCK=true`):

```bash
export AZURE_SUBSCRIPTION_ID="..."
export AZURE_RESOURCE_GROUP="..."
export ADF_FACTORY_NAME="..."
export ADLS_ACCOUNT_NAME="covidlake"
# ADLS_ACCOUNT_URL defaults to https://<account>.dfs.core.windows.net
# AZURE_LOCATION defaults to eastus
```

Auth — either `az login` (local dev) **or** a service principal:

```bash
export AZURE_CLIENT_ID="..."
export AZURE_TENANT_ID="..."
export AZURE_CLIENT_SECRET="..."
```

Flags:

```bash
export MOCK=false        # true = local dry-run, writes to mock_tenant/, simulates the run
export SELF_HEAL=true    # default; set false to disable the self-heal retry loop
export PRUNE_STALE=false # true = delete agent-created objects not in this run.
                         # OFF by default: the agent NEVER deletes from your tenant.
                         # When off, stale objects are reported, never removed.
```

Plan-phase performance:

```bash
export PLAN_MODE=auto    # auto (default) = one LLM call to generate, tool agent for
                         #   repairs/refines — fastest path that stays correctable
                         # tools   = every edit via validated tool calls (most robust,
                         #   most model turns)
                         # oneshot = whole plan re-emitted each round (legacy)
export PLAN_CACHE=true   # identical BRD + same mode + same model -> reuse the cached
                         # plan, zero LLM calls (artifacts/.plan_cache/). Set false
                         # when evaluating a model/prompt change.
export GROUND_PLAN=true  # /plan READS source file headers (first 64 KB) to ground
                         # column schemas. Read-only — nothing is created in your
                         # tenant before approval. Set false for a fully offline plan
                         # phase; grounding then runs at /approve, before the deploy.
```

Every `/plan` and `/chat` response carries a `timings` block — per-phase wall-clock
(`extract`, `repair_completeness`, `triage_unsupported`, `compile`, `grounding`,
`repair_preflight`) plus `llm_calls` — so a slow or chatty run is measurable.

## Branches and development workflow

The repository currently uses the following branches. Branch descriptions are based
on their current commit history; update this table when a branch is repurposed.

| Branch | Purpose | Relationship |
| --- | --- | --- |
| `main` | Stable baseline for the BRD-to-ADF agent and its passing BRD test set. | Base branch for the feature branches below. |
| `brd-passed-version` | Historical checkpoint for the BRD-tested version. | The local branch currently matches `main`; `origin/brd-passed-version` still points to the earlier "7 brd passed" checkpoint. |
| `linking-external-source` | Adds and tests external sources, including Dataverse, Postgres, BigQuery/GCP, GCS, and SharePoint-related source tooling. | Three commits ahead of `main`; included in `linking-er`. |
| `linking-er` | Unified application branch: combines the ADF agent, external-source support, redesigned UI, schema catalog seam, and the `ER-Diagram/` frontend/backend. | Built on `linking-external-source`; this is the integration branch for the complete app. |

Typical workflow:

```bash
git fetch origin
git switch main
git pull --ff-only
git switch -c feature/<short-name>

# After making and testing the change:
git add <files>
git commit -m "Describe the change"
git push -u origin feature/<short-name>
```

Open a pull request into the branch your work extends. Use `main` for agent-only
changes and `linking-er` for work that depends on the unified ER Diagram/catalog
application. Do not commit `.env`, cloud credentials, service-account JSON, generated
artifacts, or tenant output.

## Setup

### Prerequisites

- Git, Python 3.11+, and `pip`.
- Node.js 18+ and npm for the ER Diagram frontend.
- ODBC Driver 18 for SQL Server when extracting SQL Server/Azure SQL schemas.
- Docker Desktop with Compose if using the recommended all-in-one setup.
- Cloud credentials only for the source systems and real Azure deployment paths you
  intend to use. `MOCK=true` keeps ADF deployment local.

Clone the repository and select the branch you want to run:

```bash
git clone https://github.com/sanjanakarna/az_agent.git
cd az_agent
git switch linking-er       # complete integrated app
# git switch main           # agent-only stable baseline
```

### Option 1: Docker Compose (complete application)

Copy `.env.example` to `.env`, fill in the values required for your chosen LLM and
data sources, and keep `MOCK=true` for a local ADF dry run. The ER backend also needs
`FERNET_KEY`, `GEMINI_API_KEY`, `GCS_BUCKET`, and `GCS_PROJECT`; set
`GCP_SA_KEY_FILE` to the host path of its GCP service-account key when GCS persistence
is enabled.

```bash
docker compose up --build
```

Then open:

- Unified ER Diagram frontend: `http://localhost:3000`
- ER Diagram backend and Swagger: `http://localhost:8010/docs`
- BRD-to-ADF agent: `http://localhost:8000`

Stop the stack with `docker compose down`.

### Option 2: Run each service locally

Agent API/UI (from the repository root):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app:app --reload --port 8000
```

ER Diagram backend (in a second terminal):

```powershell
cd ER-Diagram\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Configure FERNET_KEY and the source/storage credentials in the environment.
uvicorn app.main:app --reload --port 8010
```

ER Diagram frontend (in a third terminal):

```powershell
cd ER-Diagram\frontend
npm install
Copy-Item .env.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8010 and configure Auth/MSAL as needed.
npm run dev
```

For bash/zsh, activate Python environments with `source .venv/bin/activate` and copy
environment templates with `cp` instead of `Copy-Item`.

### Verify the setup

```bash
python tests/smoke_test.py
python -m pytest
cd ER-Diagram/frontend && npm run lint && npm run build
```

Some integration tests require real source credentials or Azure access. Start with
the smoke test and `MOCK=true`; enable external integrations one at a time.

## Phase 1 — Local dry-run (no Azure, no Foundry)

```bash
python tests/smoke_test.py
```

Runs pre-flight on the shipped COVID BRD and prints the Bronze Copy Activity JSON
(no script), the Silver/Gold Data Flow scripts + deployable JSON, and the master
`dependsOn` chain. To exercise the full deploy+run UI offline, start the app with
`MOCK=true` — `/approve` writes to `mock_tenant/` and simulates the Bronze→Silver→Gold
run. The UI shows a **MOCK** banner.

## Phase 2 & 3 — Real end-to-end build + run (a data engineer's walkthrough)

1. Complete the Azure prerequisites and export the env vars above (`MOCK=false`).
2. `uvicorn app:app --reload` and open `http://127.0.0.1:8000`.
3. **Paste or upload your BRD** -> **Generate pipelines**.
4. Review:
   - **Pre-flight** must be green (spec valid, naming, cross-refs resolve, JSON well-formed,
     Bronze Copy present, Silver/Gold scripts present). If it fails, fix the BRD and regenerate
     — approval stays disabled.
   - **Governance plan**: expand the plain-text plan for the audit/approval record.
   - **All objects**: every linked service / dataset / data flow / pipeline / trigger JSON.
5. **Approve — build & run.** The app connects to Azure, creates the bronze/silver/gold
   containers, `create_or_update`s every object, then triggers `pl_master_pipeline`.
6. Watch **live status**: Bronze → Silver → Gold with ADF run IDs and any error message.
7. **Verify outputs:**
   - **ADF Monitor** (portal → your Data Factory → Monitor → Pipeline runs): see the
     `pl_master_pipeline` run and the child Bronze/Silver/Gold runs.
   - **ADLS containers** (portal → storage account → Containers, or Storage Explorer):
     - `bronze/` — the raw landed file (byte-for-byte copy),
     - `silver/` — cleaned/deduped **Parquet**,
     - `gold/` — aggregated **CSV** with the derived KPI.
8. **Idempotency:** re-run `/approve` (or POST again) — no duplicate objects, Bronze
   overwrites, the run repeats cleanly.

## API

| Method & path | Purpose |
| --- | --- |
| `POST /plan` (form: `brd` text or `file` upload) | parse + build + pre-flight; returns run_id, summary, preflight, clarifications, review, governance plan. **No Azure writes.** |
| `GET /preview/{run_id}` | review JSON (all three layers) |
| `GET /preview/{run_id}/text` | plain-text governance plan |
| `POST /approve` (`{run_id}`) | **gate**: requires prior preview AND passing pre-flight, then deploys + runs (Azure or MOCK) |
| `GET /status/{run_id}` | live deploy + Bronze→Silver→Gold run state + run IDs + errors |
| `GET /` | the UI |

## Notes / what's intentionally scoped

- **Ambiguity → clarifications.** If the BRD is unclear, the parser returns a
  `clarifications` list and builds nothing — it never invents components.
- **Run store is in-memory** (`app._RUNS`); swap for a DB to survive restarts.
- **Self-heal is enabled by default**; set `SELF_HEAL=false` to fail loud without retries.
- **MOCK is for development only** and clearly labelled in the UI; real Azure is the
  default, primary path.
- **Manual trigger** is created as an artifact but exercised via `create_run` on demand
  (manual runs aren't ARM trigger resources).
