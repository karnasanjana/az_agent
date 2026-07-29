# Tough-suite round 3 — 9 BRDs, plan → approve → REAL Azure deploy

**Date:** 2026-07-29 · **Branch:** `linking-external-source` ·
**Model:** `gemini-2.5-flash` · `MOCK=false`, `SELF_HEAL=true`, factory
`azure-datalake-adf`. BRDs in `tests/tough_suite_round3_brds.md`. Driven like a
user: POST each BRD to `/plan`, then `/approve` (deploy + run) the green plans,
polling `/status` to a terminal state. **All 8 approvable BRDs were deployed to
the real factory — the objects were left there** (agent never deletes).

## Results

| BRD | Source | Plan | Deploy + run | Heals | Note |
|----:|--------|:----:|--------------|:-----:|------|
| 01 mixed arithmetic | Postgres | ✅ | ✅ **SUCCEEDED** (451s) | 0 | ratios compiled & ran, no corruption signal |
| 02 col-vs-col filter | Dataverse | ✅ | ❌ **FAILED** (451s) | 2 | see finding 1 + 3 |
| 03 SharePoint null col | SharePoint | ✅ | ❌ **FAILED** (616s) | 2 | see finding 1 |
| 04 4-table joins | Postgres | ✅ | ✅ **SUCCEEDED** (195s) | 0 | many-way join graph held |
| 05 cross-source SP×DV | SP+DV | ✅ | ❌ **FAILED** (466s) | 2 | see finding 1 |
| 06 incr+prefix+folder | Postgres | ✅ | ✅ **SUCCEEDED** (105s) | 0 | 3 asks refused (see finding 4) |
| 07 nesting + honesty trap | Dataverse | ✅ | 🚫 **APPROVE_REJECTED** | 0 | transient `az login` token blip |
| 08 regex + CFR ratio | HTTP | ✅ | ✅ **SUCCEEDED** (346s) | 2 | regex `\s` + `between` date-cast heals |
| 09 underspecified | Postgres | 🟡 **NEEDS_CLARIFICATION** | — | — | correctly refused to hallucinate |

**Plan: 8/9 built, 1 correctly asked. Deploy: 4 green, 3 failed, 1 auth-blip.**

## Root cause of ALL 3 failures: the running server predates the uncommitted fixes

The 2026-07-29 fixes (P1 SharePoint `_`-exclusion, P1 column-vs-column filter,
etc.) are **unstaged working-tree edits** (`git status`: `source_schema.py`,
`completeness.py`, `grounding.py`, `reviewer.py` all `M`). The FastAPI server
under test was started *before* those edits, so it imported the pre-fix modules
and never reloaded them.

Proof: the on-disk `sharepoint_list_schema` filters `_`/`@` columns
unconditionally (`tools/source_schema.py:264-274`), yet a `logical_plan.json`
the *running* server generated in this round still lists
`_UIVersionString, _ComplianceFlags, _ComplianceTag, _ComplianceTagWrittenTime,
_ComplianceTagUserId` — columns no on-disk path can return — and drops
`ActualCompletion`. The server is running stale code.

So findings 1 & 3 below are **not new bugs** — they are the *already-fixed* bugs
re-appearing because the fixes aren't loaded. **A server restart should clear
them.** Re-running the 3 failures after a restart is the real test.

## Findings

### 1 — SharePoint `_`-system columns break the Data Flow DSL (STALE fix)
**BRD 03, 05 — FAILED (`DF-DSL-001`)**. Self-heal stripped the leading
underscores twice per run but the run still failed. On-disk fix (union
`/columns` + item `fields`, exclude `_`/`@`) is correct and present — just not
loaded by the running process. `ActualCompletion` also dropped (the null-in-
sample bug the same fix addresses). **Expected to clear on restart.**

### 2 — Dataverse option-set label column does not exist as a raw column (NEW, real)
**BRD 02 — contributes to FAILED (`DF-EXPR-010`)**. The BRD groups by
`prioritycodename`. Dataverse exposes the option-set as `prioritycode` (int)
plus a *formatted-value annotation*, not a materialized `prioritycodename`
column, so it isn't in the bronze CSV. Self-heal tried to derive it from the
int code but can't map codes→labels. This is a genuine gap independent of the
stale server: grounding should either pull formatted values
(`Prefer: odata.include-annotations="*"`) or flag label-columns as unbuildable
from the raw table. Same class as the round-2 SharePoint-membership work, for
Dataverse option-sets.

### 3 — column-vs-column filter rendered as quoted literal (STALE fix)
**BRD 02 — `resolveby < 'modifiedon'`**, healed at runtime instead of compiled
right. The deterministic `Predicate.value_column` fix is on disk but not loaded.
**Expected to clear on restart.**

### 4 — BRD 06 "succeeded" but is a full load, not incremental (working as designed)
Incremental watermark, the `rt3` prefix, and the `RetailR3` folder were all
declared **unsupported** and deployed (with `acknowledge_unsupported`) as a
plain full-load pipeline. Honest refusal held — flagging so the green tick isn't
mistaken for "incremental shipped".

### 5 — BRD 07 rejected on a transient credential blip (env, not code)
Pre-deploy `test_azure_config` hit `ClientAuthenticationError:
DefaultAzureCredential failed to retrieve a token` — the `az login` session
lapsed during the multi-hour run. `retry_sync` wraps `factories.get` but only
recognizes transport faults (`ServiceRequestError`), not auth token refresh.
Re-`az login` and re-approve; plan-side, BRD 07 correctly flagged all 5 platform
asks (ML / Databricks+Airflow / PDF email / Power BI / Snowflake) as unsupported.

## What held (confirmed live, green end-to-end)
- **P0 mixed arithmetic** (BRD 01, 08) — ratio/CFR flows compiled and ran with
  no corruption signal (the divide-fold guard is in the *loaded* completeness
  code; both deployed clean).
- **Many-way joins** (BRD 04) — 4-table basket + customer-category-spend green.
- **Honest refusals** — BRD 06 (prefix/folder/incremental), BRD 07 (5 platform
  asks), BRD 09 (underspecified → asked instead of inventing a schema).
- **Self-heal** fixed real runtime issues live: regex `\s`→`\\s` and `between`
  date-literal casting (BRD 08).

## Next step
Restart the server (loads the current tree), then re-run BRD 02, 03, 05 and
re-approve 07 after `az login`. Findings 1 & 3 should go green; 2 is a real
Dataverse-formatted-value gap worth a code fix.

---

# Re-run after server restart (2026-07-29, current code loaded)

Root cause of the round-1 failures confirmed: the server was running
`uvicorn app:app --port 8000` **without `--reload`**, started before the
uncommitted fixes — so it executed stale modules. Restarted on fresh code
(verified: SharePoint plan clean, no `_`-columns, `ActualCompletion` present),
then re-ran all 9 end-to-end to real Azure.

| BRD | Round 1 (stale) | Round 2 (fixed code) | Heals |
|----:|:---:|:---:|:---:|
| 01 mixed arithmetic | ✅ | ✅ SUCCEEDED | 0 |
| 02 col-vs-col filter | ❌ FAILED | ✅ **SUCCEEDED** | 1 |
| 03 SharePoint | ❌ FAILED | ✅ **SUCCEEDED** | 2 |
| 04 4-table joins | ✅ | ✅ SUCCEEDED | 0 |
| 05 cross-source | ❌ FAILED | ✅ **SUCCEEDED** | 2 |
| 06 incr+prefix+folder | ✅ | ✅ SUCCEEDED | 0 |
| 07 honesty trap | 🚫 auth blip | ✅ **SUCCEEDED** | 0 |
| 08 regex + CFR ratio | ✅ | ✅ SUCCEEDED | 2 |
| 09 underspecified | 🟡 asked | ❌ FAILED (build-and-fail) | 2 |

**8/9 green.** Every stale-code failure (02, 03, 05) and the auth-blocked 07 now
run green. The Dataverse `prioritycodename` gap (finding 2) self-healed live
(1 heal) rather than hard-blocking. **Confirms all four external sources ingest
into Azure end to end: Postgres, Dataverse, SharePoint, HTTP** — incl. the
cross-source SP×DV join (05).

## Bug found + fixed: fabricated source deploys instead of asking (BRD 09)
An underspecified BRD made the model invent the whole schema (fake server
`your_postgres_server.com`, tables `sales_orders`/`customer_details`, invented
columns). Grounding tried the live catalog, the table wasn't found so
`_external_columns` returned `[]` — and grounding **kept the model's guessed
columns**. Non-empty columns meant the "unverified schema" note never fired, so
the plan passed preflight and deployed a fabricated pipeline that died in Azure.

**Fix** (root cause, `grounding.py` + `completeness.py`):
- Grounding now **drops the guessed columns** when a live catalog read
  (postgres/dataverse/bigquery/sharepoint) returns nothing — the named
  table/list isn't there. GCS folder-only sources (no header) are left alone.
- `completeness.check` flags a **used** source of a verifiable format with no
  schema → routes to a clarification, so the plan **asks** for the real
  coordinates instead of shipping a guess.

Verified deterministically against the real DB: fake `sales_orders` → columns
cleared → clarification raised; real `orders` → grounds clean, no false
positive. Offline suite **203 passing** (2 new tests). BRDs 01/02/03 re-planned
clean with no spurious flag. (BRD 09 is non-deterministic — when the model
happens to guess the real names `orders`/`customers`, grounding verifies them
and it correctly builds; only fabricated names are now caught.)
