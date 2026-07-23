# GCP Backend — Implementation Plan

**Status:** planned, not implemented.
**Goal:** emit runnable GCP data pipelines from the *existing* `LogicalPlan`, reusing
open-source engines (dlt + dbt + Airflow) instead of building a pipeline engine or
repeating the ADF live-run trial-and-error.

---

## 0. The single fact this plan rests on

`models/logical.py` `LogicalPlan` is **platform-neutral** — its docstring: *"Business
intent, zero ADF. No resource names, no linked services, no containers, no DSL."*
`agent/compiler.py` `compile_plan()` is the **only** code that turns it into ADF.

Therefore GCP support is **additive**, not a rewrite:

```
BRD → LLM → LogicalPlan ─┬─→ compile_plan()      → ADF JSON      (today, untouched)
                         └─→ compile_plan_gcp()   → dlt+dbt+DAG   (new)
```

Everything upstream of the compiler — parser, extractor, grounding, gates
(completeness, typecheck, reviewer), the LLM, `LogicalPlan` itself — is **unchanged**.

---

## 1. What we reuse from open source (never rebuild)

| Project | Repo | We reuse | Deletes which ADF pain |
|---|---|---|---|
| **dlt** | github.com/dlt-hub/dlt | source→BigQuery connectors (GCS, SQL, REST/HTTP), auto schema, incremental, retries, load state | Copy activity + landing/bronze datasets + linked services |
| **dbt-core + dbt-bigquery** | github.com/dbt-labs/dbt-core | SQL compiler + runner, ref/dependency graph, offline `dbt compile`, incremental `MERGE`, tests | ExecuteDataFlow, stream naming, dedupJoinColumns, derived-column batching |
| **Apache Airflow** | github.com/apache/airflow | scheduler + orchestrator, DAG dependency engine, retries, backfill | ADF pipeline chain, ExecutePipeline, Triggers |
| **Google DataflowTemplates** (optional) | github.com/GoogleCloudPlatform/DataflowTemplates | pre-built ingest jobs if dlt falls short | — |

### Why this ends the ADF trial-and-error

ADF validated **only in Azure** — DF-ARG-005, `left_outer` rejected, Delta-unsafe
column names — discovered by live runs + heal loops. dbt/dlt validate **offline**:

- `dbt compile` / `dbt parse` — validates every SQL model, ref graph, column reference on the laptop, no BigQuery.
- `dlt` schema is inspectable / dry-runnable locally.
- `python dag.py` — import-checks the whole DAG offline.

Heal loop shrinks from *deploy → read Azure error → repair → redeploy* to
*compile locally → read error → fix*.

---

## 2. Compiler design (mirror of `compile_plan`)

Same input, same contract, same loop order — different renderer.

```python
# compilers/gcp.py
def compile_plan_gcp(plan: LogicalPlan) -> GcpBundle: ...

class GcpBundle(BaseModel):
    files: dict[str, str]        # relative path -> file contents (pure, no cloud)
    assumptions: list[str]       # threaded through, same as PipelineSpec
    clarifications: list[str]
    unsupported: list[str]
```

The compiler stays **pure** (no LLM, no cloud) exactly like `compile_plan`. A deployer
writes `files` to disk and runs the tools (§5).

### Emitted layout (the "spec" is a folder)

```
ingest/pipeline.py                    # dlt: all sources -> BigQuery bronze
dbt/dbt_project.yml
dbt/models/sources.yml                # bronze tables declared as dbt sources
dbt/models/silver/silver_<entity>.sql
dbt/models/gold/gold_<output>.sql
orchestration/dag.py                  # Airflow: dlt run + dbt run, scheduled
```

### The four render passes (one per `LogicalPlan` section)

**1. `_render_ingest(plan.sources)` → `ingest/pipeline.py`**
One dlt resource per source, sink = bronze BigQuery dataset.

| `SourceFormat` | dlt source |
|---|---|
| csv / parquet / json / text / binary | `filesystem` (GCS) |
| http_csv | `requests` reader |
| sql_table | `sql_database` |
| dataverse | small REST resource (reuse `tools/list_dataverse.py`) |

`plan.containers.bronze` → bronze BigQuery dataset name. `LogicalColumn.type` →
BigQuery type via a map (`integer→INT64`, `double→FLOAT64`, `decimal(p,s)→NUMERIC`,
`timestamp→TIMESTAMP`, …).

**2. `_render_silver(xf, source_cols)` → one SQL model per `EntityTransform`**
Port of `_silver_transforms`:

```sql
-- silver_orders.sql
SELECT
  CAST(order_id AS INT64)   AS order_id,       -- xf.casts
  TRIM(customer_name)       AS customer_name,  -- xf.cleaning
  COALESCE(discount, 0)     AS discount
FROM {{ source('bronze','orders') }}
WHERE order_total IS NOT NULL                  -- xf.filters
QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY 1) = 1  -- xf.dedup_keys
```

**3. `_render_gold(out)` → one SQL model per `OutputPlan`**
Port of `_gold_transforms`. SQL removes the ADF-only machinery (dedupJoinColumns,
stream qualifiers, batched derived transforms):

```sql
-- gold_monthly_sales.sql
SELECT o.month, SUM(o.total) AS revenue          -- group_by + aggregations
FROM {{ ref('silver_orders') }} o
JOIN {{ ref('silver_customers') }} c ON o.cust_id = c.id   -- joins (_JOIN_TYPE map)
GROUP BY o.month
HAVING SUM(o.total) > 1000                        -- post-agg filters
ORDER BY revenue DESC                             -- sort
LIMIT 10                                          -- top_n
```

Mapping of `OutputPlan` fields → SQL clauses:
`joins`→JOIN, `derived`→computed cols, `filters`(pre)→WHERE, `group_by`+`aggregations`
→GROUP BY, `filters`(on agg names)→HAVING, `post_agg_derived`→outer SELECT, `sort`
→ORDER BY, `top_n`→LIMIT, `columns`→final SELECT list.

**4. `_render_dag(plan.pipelines, plan.schedule)` → `orchestration/dag.py`**
`LogicalPipeline.invokes` + existing `depends_on` logic → Airflow task dependencies.
`SchedulePlan.frequency/interval` → `schedule_interval`. Empty `plan.pipelines` →
one linear DAG (same fallback as `compile_plan`'s single-pipeline branch).

---

## 3. The only genuinely new module

```python
# compilers/sql_expr.py — the SQL twin of models/spec.py's ADF DSL renderer
```

`models/spec.py` renders ops to ADF DSL (`toInteger`, `iif`, `&&`). GCP renders the
**same op vocabulary** to BigQuery SQL:

| op | ADF DSL (today) | BigQuery SQL (new) |
|---|---|---|
| cast integer | `toInteger(x)` | `CAST(x AS INT64)` |
| case | `iif(c, a, b)` | `CASE WHEN c THEN a ELSE b END` |
| coalesce | `coalesce(x, 0)` | `COALESCE(x, 0)` |
| join inner/left/full | `inner`/`left`/`outer` | `JOIN`/`LEFT JOIN`/`FULL JOIN` |
| sum / avg / countdistinct | agg DSL | `SUM` / `AVG` / `COUNT(DISTINCT …)` |

~One lookup table + a small expression walker. This is the real new work; everything
else is templating.

---

## 4. What stays ours (already built, kept 100%)

- **BRD → `LogicalPlan`** — LLM + grounding + gates. No OSS tool reads a BRD. Platform-neutral, unchanged.
- Gates run on `LogicalPlan` (pre-compiler), so completeness / typecheck / reviewer work for GCP for free.

---

## 5. Deploy step (where gcloud-mcp / cloud-run-mcp fit)

Deploy layer only — **not** authoring. After `compile_plan_gcp` writes the bundle:

1. `dlt pipeline` run → load sources into bronze BigQuery.
2. `dbt run` → build silver + gold models.
3. Drop `dag.py` into Cloud Composer (or run Airflow) for scheduling.

MCP servers (gcloud-mcp, cloud-run-mcp) are optional convenience for the agent to
execute these gcloud/deploy commands — they do **not** author pipelines.

---

## 6. Build order

1. `compilers/sql_expr.py` — op → BigQuery SQL table + walker. Unit-tested offline (no cloud).
2. `compilers/gcp.py` — `compile_plan_gcp` + 4 renderers + `GcpBundle`. Compile a sample `LogicalPlan` → assert the folder + SQL strings offline.
3. Jinja templates for `dbt_project.yml`, `sources.yml`, `dag.py`.
4. GCP heal loop — run `dbt compile` on the emitted models, feed errors back (offline analog of the ADF heal loop).
5. Deployer — `dlt` + `dbt run` + Composer upload.

**Net new code:** `compilers/gcp.py` (≈ size of `compile_plan` minus quirk handling) +
`compilers/sql_expr.py` + templates. Everything else is reuse.

---

## 7. Honest risks / open decisions

- **New target = new (smaller) quirk list.** BigQuery/dbt bring their own: dataset naming, incremental `MERGE`, dbt `ref()` ordering. Fewer and gentler than ADF's, but budget a heal loop.
- **dlt schema inference vs grounding.** Decide: feed dlt the grounded schema (more control, more code) or let dlt infer (less code). Default: feed the grounded schema — matches today's explicit-columns behaviour.
- **Orchestration is the least 1:1.** Airflow's operator/dependency model isn't identical to ADF ExecutePipeline; the `depends_on` port needs real DAG testing, not just rendering.
- **Two backends to maintain.** Every new op = two renderers (ADF DSL + SQL). Ongoing tax.
- **`dbt compile` proves valid, not correct.** Right join keys / aggregations still need a test run — but offline and fast, unlike ADF's live-only validation.
- **Incremental load** (`load_mode incremental`) → dbt incremental models. Mechanical; map when hit.

---

## 8. What would break this plan (checked, not found)

A `LogicalPlan` field that secretly encodes ADF semantics would force a rewrite.
Reviewed `models/logical.py` — none found. `LogicalPlan` carries only business intent,
so the second backend is genuinely additive.
