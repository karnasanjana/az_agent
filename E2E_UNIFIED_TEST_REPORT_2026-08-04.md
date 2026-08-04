# Unified App — E2E Test Report (2026-08-04)

Tester: Claude (acting as an end-user e2e tester). Branch: `linking-er`.
Target: **live Azure** (`MOCK=false`), factory `azure-datalake-adf`, RG `Azure-data-lake`,
storage `adls`. LLM fixed at `gemini-2.5-flash`. `SELF_HEAL=true`, `PLAN_REVIEW=false`.

## What was tested

Two flows, six external sources, 20 medium→tough BRD cases + the ER connect/talk path.

- **Flow 2 (BRD-direct):** `POST /plan` → (refine `/chat`) → `/approve` → poll `/status`,
  driven over HTTP against `:8000`. Fully exercised for all 20 cases.
- **Flow 1 (connect → ER diagram → talk-to-data → build):** driven over HTTP against the
  ER backend `:8010` + the catalog seam into `:8000`.

## Environment / setup findings (before any case ran)

| # | Finding | Severity | Notes |
|---|---------|----------|-------|
| E1 | **ER backend (:8010) was not running** at session start, though `ER_CATALOG_URL` pointed at it and the ER frontend (:3000) was up against a dead backend. | Med | Started it manually. In a real unified deploy this must be supervised (docker-compose does this; a bare `uvicorn app.py` for :8000 does not). |
| E2 | **`FERNET_KEY` is absent from `.env`.** ER schema extraction (`/api/*/start`) encrypts pending creds with it and **500s** without it (health + `/test` + `/databases` still work, so it looks healthy until you extract). | **High** | Had to generate an ephemeral Fernet key and restart. docker-compose expects `${FERNET_KEY}` from the shell/compose env — it is not in the app `.env`, so a `.env`-only bring-up silently loses extraction. |
| E3 | **`GOOGLE_APPLICATION_CREDENTIALS` is empty and no `gcp-sa.json` exists.** Diagram storage is GCS-backed, so **saving/sharing a diagram fails**, which means the **catalog seam** (`catalog_source_id` grounding Flow-1 → pipeline) cannot be exercised end-to-end. | **High** | The catalog endpoint *does* fail gracefully (404 "share the diagram first"), and `/plan` falls back to env grounding — so Flow 2 is unaffected. But the headline Flow-1→Flow-2 handoff is blocked without a GCS key. Also blocks BigQuery/GCS *app-seeding* at deploy time. |
| E4 | **No native `sqlserver` source in the pipeline compiler.** `SourceFormat` = {dataverse, postgres, bigquery, gcs, sharepoint}. SQL Server can be *connected* in the ER UI but Flow-2 has **no SQL Server mover**. | Med | Cross-component gap: the connect UI offers SQL Server, the pipeline builder can't natively ingest it. See case Q1. |

## Flow 1 — connect → extract → talk-to-data (ER backend :8010)

**Connect feasibility (honest scope):** only **Postgres** and **SQL Server** use direct
credentials; the other four (**Dataverse, SharePoint, BigQuery, GCS**) require a live OAuth
`access_token` minted by the browser (MSAL / Google OAuth) — **not drivable headless**, so
their connect→extract path can only be validated through the actual frontend. SQL Server
needs a reachable server (none available). **Postgres (local) is the one fully testable path.**

| Step | Source | Result |
|------|--------|--------|
| `/api/postgres/test` | Postgres | ✅ 200 "Connection successful" |
| `/api/postgres/databases` | Postgres | ✅ 200 — `retaildb`, 33 tables |
| `/api/postgres/start` + SSE `/stream` | Postgres | ✅ (after E2 fix) — **33 tables extracted** with full columns (type, nullability, PK, identity), indexes, is_view. FKs in a separate `foreign_keys` block. |
| `/api/chat/message` (talk-to-data) | Postgres | ⚠️ **partial** — see F1/F2 below |
| `/api/catalog/{token}` (seam) | — | ✅ graceful 404 (no shared diagram; blocked by E3), `/plan` falls back to env grounding |

**F1 — talk-to-data 500 on missing `alias` (bug).** Asking *"Which 5 customers placed the most
orders?"* → **HTTP 500**. Root cause in backend log:
`Failed to parse query step: 1 validation error for QueryStep — alias Field required`.
The advisor LLM sometimes emits a query step without the required `alias`; the code logs the
parse failure but the request still 500s instead of degrading (retry / drop the step / ask).
A single malformed step takes down the whole answer. **This is the one clear code bug found.**

**F2 — talk-to-data classified a data question as `type=schema`.** *"What is the total revenue
per product category?"* → 200 but `type=schema`: it explained the join and generated correct
SQL but **did not execute** it against Postgres, so no rows came back. Borderline (not a crash),
but a user asking for a number gets prose + SQL, not the number.

## Flow 2 — BRD-direct pipeline build (:8000), all 20 cases

_(plan-phase results; live-deploy subset in the next section)_

**Headline: 20/20 cases produced a buildable, preflight-passing plan; 0 failed checks; 0 HTTP
errors.** The honesty/scoping behavior was correct throughout — unsupported asks flagged, a
nonexistent column dropped, and the underspecified BRD asked questions instead of inventing.

| Case | Source | Preflight | Unsup | Clar | Notes |
|------|--------|-----------|-------|------|-------|
| P1_pg_retail | Postgres | PASS | 0 | 0 | clean |
| P2_pg_4table | Postgres | PASS | 0 | 0 | clean |
| P3_pg_incr | Postgres | PASS | 4 | 0 | incremental/window asks flagged unsupported |
| P4_pg_kitchen | Postgres | PASS | 0 | 0 | kitchen-sink (joins+ratios+bands+filters) clean |
| B1_bq_sales | BigQuery | PASS | 0 | 0 | 3-table BQ, joins + top-N |
| B2_bq_lite | BigQuery | PASS | 0 | 0 | clean |
| D1_dv_crm | Dataverse | PASS | 0 | 0 | grounded on live Dataverse metadata |
| D2_dv_360 | Dataverse | PASS | 0 | 0 | 3-way join, bands, top-N |
| D3_dv_bands | Dataverse | PASS | 5 | 0 | deep-nest + honesty trap; 5 unsupported flagged |
| S1_sp_tracker | SharePoint | PASS | 1 | 0 | SharePoint native source recognized |
| S2_sp_flags | SharePoint | PASS | 0 | 0 | derived flags + date bands |
| G1_gcs_leads | GCS | PASS | 0 | 0 | plan builds; missing-CSV only caught at deploy |
| Q1_sql_orders | SQL Server | PASS | 0 | 0 | built on **assumed/unverified** columns |
| X1_cross_sp_dv | SP×DV | PASS | 0 | 0 | heterogeneous cross-source join |
| X2_cross_t3 | SP×DV | PASS | 0 | 0 | cross-source, business-unit work mix |
| X3_honesty | Dataverse | PASS | 6 | 0 | **dropped nonexistent column** + flagged 5 out-of-scope asks |
| X4_underspec | Postgres | PASS | 1 | **2** | **asked 2 clarifying Qs instead of inventing** ✅ |
| X5_dv_sla | Dataverse | PASS | 1 | 0 | post-agg pct filter flagged |
| X6_pg_ratios | Postgres | PASS | 0 | 0 | mixed arithmetic everywhere |
| X7_pg_basket | Postgres | PASS | 0 | 0 | 4-table many-way join basket mart |

## Live Azure deploys (representative subset)

Deployed to the real factory `azure-datalake-adf` via `/approve` → polled `/status` to terminal.

| Case | Source | Approve gate | Deploy + ADF run | Heals | Outcome |
|------|--------|--------------|------------------|-------|---------|
| **P1_pg_retail** | Postgres | passed | **SUCCEEDED** — bronze Copy (local PG) → silver Delta → gold Delta; silver+gold steps green | 0 | ✅ clean e2e |
| **D1_dv_crm** | Dataverse | passed | **SUCCEEDED** — native Dataverse Copy (contacts/accounts/incidents) → silver → gold | 0 | ✅ clean e2e |
| **B2_bq_lite** | BigQuery | passed | **SUCCEEDED** — keyless `gcloud`/ADC app-seed of BQ table → bronze → silver → gold | 0 | ✅ clean e2e |
| **X1_cross_sp_dv** | SP×DV | passed | **SUCCEEDED** — heterogeneous cross-source join; `df_silver_tasks` failed first run, **self-heal repaired it**, silver+gold re-ran green | 1 | ✅ self-heal recovery |
| **P4_pg_kitchen** | Postgres | passed | **SUCCEEDED** — kitchen-sink; `df_gold_seasonal_orders` failed first run, **self-heal fixed it** → green | 1 | ✅ self-heal recovery |
| **S1_sp_tracker** | SharePoint | **409 blocked** | not deployed — gate wants `bronze/DOL Project Team.csv` (BlobNotFound); seeding via `inject_to_bronze.py` wrote a **different path** (`bronze/dol_project_team/dol_project_team.csv`) so re-approve still 409'd | — | ⛔ blocked by seeder/compiler path mismatch (BUG-3) |
| **G1_gcs_leads** | GCS | passed | **ERROR** at deploy — app-seed hit GCS `404 No such object: erdiagram/leads/leads.csv` (bucket has no CSV, as expected) | 0 | ❌ honest but **only caught at runtime**, not the gate (BUG-2) |
| **Q1_sql_orders** | SQL Server | passed | **FAILED** — emitted a real SQL Copy; `copy_customers` → `ErrorCode=SqlFailedToConnect` (host `sales-sql...` is fictional). Self-heal ran **2 attempts** then stopped cleanly | 2 | ❌ correct terminal failure; gate didn't pre-check connectivity (BUG-2) |

**Deploy verification / stale handling:** P1's `deploy_report` showed intended vs. factory counts and
**68 stale** objects with `pruned: []` — i.e. it *reports* stale objects but never deletes them,
honoring the "never delete Azure objects" rule. Confirmed working as designed.

**Self-heal:** behaved exactly right in all three modes — (a) **recovered** 2 real live-Azure
dataflow failures (X1 `df_silver_tasks`, P4 `df_gold_seasonal_orders`) in 1 attempt each and the
runs went green; (b) **gave up cleanly** where the source was fundamentally unavailable (Q1 fake
SQL host: 2 attempts → FAILED, no runaway); (c) **stayed out of the way** on clean runs (P1/D1/B2:
0 heals). This is the single strongest result of the session.

**Deploy tally: 5 SUCCEEDED / 1 ERROR / 1 FAILED / 1 gate-blocked.** All 5 "should-work" cases
(Postgres ×2, Dataverse, BigQuery, cross-source) ran **green end-to-end on live Azure**; the 3
non-successes are all correct/honest outcomes.

## Summary of bugs / issues (ranked)

| # | Sev | Where | Issue | Fix direction |
|---|-----|-------|-------|---------------|
| BUG-1 | **High** | ER `api/chat.py` talk-to-data | A malformed LLM query step (missing required `alias`) **500s the whole request** instead of degrading. Logged as `Failed to parse query step` but still crashes. | Drop/repair the bad step or retry; never let one step 500 the answer. |
| BUG-2 | **Med** | `app.py` `/approve` gate | Gate pre-checks **landing blobs** (SharePoint) but **not** GCS-object existence (G1) nor SQL reachability (Q1) — both approved then failed at runtime after creating real Azure objects. | Add a source-liveness pre-check for `gcs` app-seed (object HEAD) and `sqlserver` (connect probe) so they're refused at the gate. |
| BUG-3 | **Med** | `inject_to_bronze.py` ↔ compiler | SharePoint seed path mismatch: seeder writes `bronze/<slug>/<slug>.csv`, compiler landing dataset expects `bronze/<List Name>.csv`. Documented seed→deploy path can't satisfy the gate. | Make the seeder honor the compiler's landing path (or vice-versa) for SharePoint. |
| BUG-4 | **High (setup)** | `.env` | `FERNET_KEY` absent → ER schema extraction 500s (health/`/test`/`/databases` still pass, so it looks healthy until you extract). | Add `FERNET_KEY` to `.env(.example)`; fail fast at startup if missing. |
| BUG-5 | **High (setup)** | `.env` | `GOOGLE_APPLICATION_CREDENTIALS` empty / no `gcp-sa.json` → diagram **save/share fails**, so the **catalog seam** (Flow-1 diagram → grounded pipeline) can't run e2e. Endpoint fails gracefully (404), Flow 2 unaffected. | Provide a GCS SA key (or a non-GCS diagram store) to exercise the headline Flow-1→Flow-2 handoff. |
| BUG-6 | Low | `tools/inject_to_bronze.py` docs | Documented `... sharepoint <host> /sites/<path> ...` breaks under git-bash (POSIX path-conversion mangles `/sites/...`); needs `MSYS_NO_PATHCONV=1`. Fine in PowerShell. | Note the git-bash caveat, or read the site path in a conversion-proof way. |
| BUG-7 | Low | planner honesty (X3) | Internal contradiction: one assumption says the nonexistent column "is expected to exist… Bronze copy will fail" while another says it was "dropped, not ingested" (the latter is the real outcome). | Suppress the stale "expected to exist" assumption once the column is dropped. |
| OBS-1 | Info | SQL Server | No `SourceFormat.sqlserver` in the logical model, yet the compiler emitted a **real SQL Copy** (Q1 reached `SqlFailedToConnect`). So SQL Server likely works with a reachable server — but the plan was built on **assumed, unverified columns** (flagged in assumptions). "It's working" is half-true: it plans + attempts a real copy, but without schema grounding. | Consider a first-class `sqlserver` source + schema grounding like the other five. |
| F2 | Info | ER talk-to-data | A data question ("total revenue per category") was classified `type=schema`: it explained + generated SQL but didn't execute, so no rows returned. | Borderline; consider executing when a concrete aggregate is requested. |

## Bottom line

- **Flow 2 (BRD → pipeline) is solid.** 20/20 plans built and passed preflight; honesty/scoping
  behavior is correct; **5/5 real "should-work" deploys (Postgres ×2, Dataverse, BigQuery,
  cross-source) ran green end-to-end on live Azure** — 3 clean (0 heals) and 2 recovered by
  self-heal — and the stale/verify report behaved as designed (reports, never deletes).
- **Failure modes are honest but two land late.** SQL Server and GCS *should* be refused at the
  approve gate (missing/unreachable source) instead of failing after a real deploy (BUG-2).
- **Flow 1 (connect → ER → talk → build) is only partly exercisable in this environment.** Postgres
  connect+extract works well; talk-to-data has one 500 bug (BUG-1); the headline diagram→pipeline
  catalog handoff is blocked by missing GCS creds (BUG-5); and the other four sources' ER-connect
  need browser OAuth tokens that a headless test can't mint.
- **SharePoint** plans natively but its deploy needs a pre-seeded bronze blob whose path the seeder
  doesn't match (BUG-3) — the one source that neither auto-seeds (like Dataverse/BigQuery) nor
  seeds cleanly by hand.

_Method note: driven entirely over the app's own HTTP APIs (`:8000` az_agent, `:8010` ER backend)
as a user would; no internal function calls. Scratch drivers + per-case plan/deploy JSON are in the
session scratchpad._
