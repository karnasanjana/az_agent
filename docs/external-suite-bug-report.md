# External-source e2e test report — 10 BRDs, real Azure

**Date:** 2026-07-24 · **Branch:** `linking-external-source` @ `fe56772` ·
**Model:** `gemini-2.5-flash` · `MOCK=false`, `SELF_HEAL=true`, `PRUNE_STALE=false`

Tested as a user would: `/plan` → `/preview` → `/approve` → poll `/status`, against
the real ADF factory `azure-datalake-adf` and storage `azurejaydeltalake`.
No hand-seeded data — every BRD names an external source and the **app** connects
and ingests. BRDs are in [`tests/external_suite_brds.md`](../tests/external_suite_brds.md);
all column names were probed live first, so nothing in them is invented.

**No fixes were applied.** This is an observation report.

## Results

| BRD | Source | Verdict | Plan | Deploy+run | Heals |
|----:|--------|---------|-----:|-----------:|------:|
| 1 | Dataverse `contact` | ✅ SUCCEEDED | 20s | 725s | 0 |
| 2 | Dataverse 3-way join | ✅ SUCCEEDED | 27s | 356s | 0 |
| 3 | Dataverse case SLA | ✅ SUCCEEDED | 112s | 135s | 0 |
| 4 | SharePoint list | ⚠️ SUCCEEDED after heal | 213s | 215s | 1 |
| 5 | SharePoint + Dataverse | ✅ SUCCEEDED | 147s | 145s | 0 |
| 6 | Postgres 4-table | ✅ SUCCEEDED | 18s | 517s | 0 |
| 7 | Postgres + prefix/folder | ✅ SUCCEEDED | 60s | 117s | 0 |
| 8 | HTTP COVID CSV | ⚠️ SUCCEEDED after heal | 22s | 256s | 1 |
| 9 | HTTP multi-file copy | ❌ ERROR | 8s | 46s | 0 |
| 10 | Honesty trap | ✅ SUCCEEDED | 92s | 159s | 0 |

**9/10 deployed and ran green in Azure.** Total 12 min planning, 44 min deploy+run.
Offline suite: 194/194 pass.

## What worked well

- **Cross-source join (BRD 5)** — a SharePoint list joined to a Dataverse table in one
  data flow, `TeamMemberResponsible == fullname`. Two unrelated external systems, one mart.
- **Honest refusal (BRD 3)** — `pct_of_total = case_count * 100 / case_count` was correctly
  diagnosed as needing a window function, declared unsupported, everything else built,
  with a real workaround suggested.
- **Honest refusal (BRD 10)** — all five platform-level asks (ML scoring, Databricks+Airflow,
  email PDF, Power BI, Snowflake) refused; the buildable core still shipped.
- **Postgres (BRD 6)** — flawless. 4 gold outputs, a 3-way join, `toDouble`-wrapped
  arithmetic. The `seeded` stale-bronze guard from `fe56772` holds up live.
- **Entity-set resolution** — `contact` → `contacts` auto-resolved from Dataverse metadata.
- **Self-heal** — rescued both runtime failures (BRD 4, BRD 8) without user involvement.
- **Learned-lessons loop** — distilled BRD 4's failure into two reusable rules in
  `skills/99-learned-lessons.md` on its own.

## Bugs found

The build engine is strong. **Five of the six bugs are the same failure mode: the
pipeline it builds is fine, but the report it gives you about that pipeline overstates
what it did.** A user who trusts the plan summary is misled.

---

### Bug 1 — SharePoint `id` invisible → silent dedup on the wrong key → data loss
**Severity: high (silent data loss)** · BRD 4, BRD 5

[`tools/source_schema.py:252`](../tools/source_schema.py#L252) skips every `readOnly`
column. SharePoint marks `ID` readOnly, so the planner never sees it — even though `id`
**is** present in the bronze CSV.

Two derivations of "what columns exist" disagree:

| | columns | has `id`? |
|---|---:|---|
| `sharepoint_list_schema()` (planner grounds on this) | 10 | ✗ |
| `_pull_sharepoint()` (writes the bronze CSV) | 24 | ✓ |

Both BRDs said *"drop rows missing `id`; dedup on `id`"*. Result: `dedup on Title`.
Two tasks sharing a title silently lose a row. In BRD 4 it at least flagged the missing
`id` in `unsupported`; **in BRD 5 `unsupported` was empty — the primary key was
substituted with zero disclosure.**

The docstring at [`agent/grounding.py:313`](../agent/grounding.py#L313) states the
intended invariant — *"same readers the bootstrap mover uses"* — which for SharePoint
is false.

*Verified fix (tested, then reverted):* derive membership from a real item's `fields`
and use `/columns` only for types. Makes the two agree exactly (24 = 24, `id` present).

---

### Bug 2 — a requirement declared unsupported was still emitted, broken
**Severity: high (silently wrong output)** · BRD 4

`completion_state` needs `ExpectedCompletion < StartDate` — column-vs-column plus a
null check. `CaseBranch` ([`models/logical.py:225`](../models/logical.py#L225)) only
tests one column against a *literal*, so the model's diagnosis that it can't be built
was **correct**. But it declared it unsupported *and shipped it anyway*:

```
completion_state = iif(ActualCompletion > '1900-01-01T00:00:00Z', 'Done', 'In Flight')
```

An invented sentinel date, and the `Overdue` bucket the BRD asked for silently vanishes.
It also crashed in Azure (`DF-FN-0016`) and cost a heal cycle. Refusing a requirement and
shipping a degraded version of it should be mutually exclusive.

---

### Bug 3 — unsupported features reported as satisfied assumptions
**Severity: high (false assurance)** · BRD 7

BRD asked to prefix every object with `rt` and group them in an ADF folder
`RetailIncremental`. Neither exists in this codebase (`object_prefix`, `adf_folder`,
`load_mode` appear nowhere on any branch). Deployed reality:

```
object_prefix = None    adf_folder = None
datasets: ds_bronze_orders, ds_silver_orders, ...   (no rt)
pipeline folders: all None
```

Instead of `unsupported`, the user was told:

> *"The ADF compiler will apply the 'rt' prefix to all generated objects and place them
> in a Data Factory folder named 'RetailIncremental'."*

**Root cause:** [`agent/extractor.py:172-175`](../agent/extractor.py#L172-L175) tells the
model that naming conventions are *"ADF implementation details the compiler owns"* and to
record them in `assumptions`. The model obeyed; the compiler has no such capability.

*(Incremental load was handled correctly — `incremental merge` is on the unsupported list
at line 177 and was declared honestly. Not a bug.)*

---

### Bug 4 — regex replacement value hallucinated → silent data corruption
**Severity: critical (corrupt data in gold, passes every gate)** · BRD 8

BRD: *"strip any character that is not a letter or a space from `Country`"*.
Deployed to Azure and executed successfully:

```
regexReplace(Country, '[^A-Za-z0-9 ]', 'alphanumeric_space')
```

The third argument is the **replacement value**. The model wrote a *description of the
character class* there instead of `''`. Effect:

- `Cote d'Ivoire` → `Cote dalphanumeric_spaceIvoire`
- `Timor-Leste` → `Timoralphanumeric_spaceLeste`

It is syntactically valid, so preflight, lint, deploy, runtime and self-heal all pass it.
Nothing in the system can currently catch this class of error.
(Secondary: `[^A-Za-z0-9 ]` also keeps digits, which the BRD didn't ask for.)

---

### Bug 5 — no retry on transient Azure faults; succeeded deploy reported as ERROR
**Severity: medium (spurious failure, misleading state)** · BRD 9

```
ServiceResponseError: ('Connection aborted.',
  ConnectionResetError(10054, 'An existing connection was forcibly closed...'))
```

The deploy had **already succeeded** — all 10 objects and the `reference` container were
created. The reset hit afterwards, so the user sees a red ERROR for a pipeline that is
fully deployed in their factory.

`agent/retry.py` exists and is wired to **LLM** calls
([`agent/validator.py:458`](../agent/validator.py#L458)), but no Azure SDK call in
`deployer.py` / `validator.py` is wrapped. Reusing `retry_sync` on those calls is the
obvious fix.

---

### Bug 6 — non-existent column silently dropped, then reported as ingested
**Severity: medium (false assurance)** · BRD 10

The BRD asked to keep `customer_health_score`, which does not exist in Dataverse
`account` (0 of 243 columns). Grounding correctly stripped it from the build — the
source-schema gate works, and it appears in **no** dataset or dataflow.

But it was never listed in `unsupported`. Instead the user was told:

> *"The customer_health_score is already a source column and will be ingested as-is."*

Build correct; report false. Same family as Bugs 2, 3.

---

## Suggested priority

1. **Bug 4** — corrupt data that passes every gate. A lint rule rejecting a
   `regexReplace` replacement argument that looks like prose would catch it.
2. **Bug 1** — silent data loss, and the fix is small and verified.
3. **Bugs 2 / 3 / 6** — one shared rule: *anything not actually built belongs in
   `unsupported`, and nothing in `assumptions` may claim a capability the compiler
   lacks.* Fixing the `extractor.py` guidance addresses all three.
4. **Bug 5** — wrap Azure SDK calls in the existing `retry_sync`.

## Tenant side-effects

9 BRDs' objects were deployed and left in place (`PRUNE_STALE=false` — the agent never
deletes). Containers created: `bronze`, `silver`, `gold`, `retail-raw`, `retail-clean`,
`retail-mart`, `reference`. The factory now reports 27 pipelines / 47 dataflows /
13 triggers, including stale objects from earlier sessions that the deploy reported but
did not remove. Cleanup is yours to do.
