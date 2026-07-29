# Tough-suite round 2 — 10 BRDs, real sources, plan+compile

**Date:** 2026-07-28 · **Branch:** `linking-external-source` ·
**Model:** `gemini-2.5-flash` · `MOCK=false`, `SELF_HEAL=true`, `PRUNE_STALE=false`

Tested as a user would: `/plan` against the live app, grounding on the real
sources (Postgres `retaildb`, Dataverse `zcscmdemodev`, SharePoint
`DOL Project Team`, public HTTP CSVs). **Plan + compile only — no `/approve`,
no Azure writes** (deploys pile up objects the agent never deletes). The bug
classes under test all live in the plan / compiled DSL. All 10 BRDs are in the
scratchpad harness `batch.py`; every column was taken from the schemas already
probed live in `tests/external_suite_brds.md`, so nothing is invented except
the deliberate honesty-trap columns.

This round also **regression-checks the 9 fixes** from the two prior rounds.

## Results

| BRD | Source | Plan | Unsupported | Verdict |
|----:|--------|-----:|:-----------:|---------|
| 01 window/ratio | Postgres | 69s | 2 | ✅ pct_of_total + running-total refused honestly |
| 02 col-vs-col + date-diff | Dataverse | 29s | 0 | 🟡 `resolution_days` dropped (disclosed) |
| 03 SharePoint id key | SharePoint | 36s | 0 | 🔴 `id` fixed ✅ but `ActualCompletion` regressed |
| 04 regex + ratio | HTTP | 247s | 0 | 🔴 `cfr_pct` division rendered as multiplication |
| 05 cross-source join | SP+DV | 21s | 0 | ✅ heterogeneous join on real keys |
| 06 prefix/folder/incr | Postgres | 56s | 2 | ✅ prefix + folder refused honestly |
| 07 honesty trap | Dataverse | 70s | 4 | ✅ 3 fake cols disclosed, 4 platform asks refused |
| 08 multi-file copy | HTTP | 7s | 0 | ✅ copy-only, zero transforms |
| 09 top-N per group | Postgres | 52s | 2 | 🟡 top-per-group refused but namesake shipped |
| 10 nested sentinel case | Dataverse | 162s | 2 | ✅ refused cleanly, no invented sentinel |

**10/10 planned green** (preflight passed). Offline suite: 198/198.

## Regression checks on the 9 prior fixes — all held

- **Bug 1 (SharePoint `id`)** ✅ — `id` is now in the silver source and dedup is
  `groupBy(id)` (BRD 03/05). *But see new finding 2 for a side effect.*
- **Bug 3 (custom prefix/folder → unsupported)** ✅ — BRD 06 put both `rx` prefix
  and `RetailBatch` folder in `unsupported`, not a false assumption.
- **Bug 4 (regex clean)** ✅ — `regexReplace(Country, '[^a-zA-Z\s]', '')` (BRD 04),
  clean `''` replacement, no prose.
- **Bug 6 / fix C (fabricated column disclosed)** ✅ — BRD 07 disclosed all three
  (`churn_risk_score`, `lifetime_value`, `engagement_index`); BRD 02 disclosed
  `resolution_days` reasoning.
- **Fix A (duplicate-aggregation ratio)** ✅ — BRD 01 `pct_of_total` and BRD 09
  `share = revenue/revenue*100` were both dropped instead of shipping a constant.
- **Column-vs-column** ✅ — `sla_state = iif(resolveby < modifiedon, 'Late', 'On Time')`
  (BRD 02) and the SP↔DV join (BRD 05) rendered real column comparisons.
- **Honest refusal** ✅ — BRD 07 (ML/PDF/PowerBI/Snowflake) and BRD 10 (nested
  multi-column conditional) refused cleanly; BRD 08 copy-only built no transforms.

## Bugs found

### 1 — division silently rendered as multiplication → corrupt gold
**Severity: critical (passes every gate)** · BRD 04

BRD: `cfr_pct = peak_deaths * 100 / peak` (case-fatality %). Compiled DSL:
```
cfr_pct = toDouble(peak_deaths * 100 * peak)
```
The `/ peak` became `* peak`. Logical plan:
```json
{"op": "multiply", "column": "peak_deaths", "args": ["100", "peak"], "new_column": "cfr_pct"}
```
The arithmetic vocabulary has **one operator per op** (multiply *or* divide); a
mixed `a * b / c` must be chained (multiply → divide). The model instead
flattened the whole expression into a single `multiply`, turning the division
into multiplication. It is syntactically valid, so preflight, lint and
completeness all pass it. Same family as the round-1 regex bug: silent
arithmetic corruption nothing in the system can currently catch.

### 2 — SharePoint columns null in the sampled row are dropped
**Severity: high (silent column loss, regression)** · BRD 03, BRD 05

The Bug-1 fix made the schema reader derive membership from a real item's
`fields` (`$top=1`) so the readOnly `id` becomes visible — and it does, dedup is
now correctly `groupBy(id)`. But **SharePoint Graph omits null-valued fields
from an item**, so any column that happens to be null in the *first* item drops
out of the schema. `ActualCompletion` (null for in-flight tasks) vanished and
was then disclosed as *"does not exist in the real source schema"* — a false
statement about a real column. The `$top=1` sample is too thin; membership
should union the item `fields` with the non-hidden `/columns` names (or sample a
page of items), matching the bootstrap mover's union across rows.

### 3 — output refused, then a namesake degraded version shipped
**Severity: medium (misleading output)** · BRD 09

`best_seller_per_category` is in `unsupported` ("top-N per group needs a window
function"), yet a dataflow was built doing
`aggregate(groupBy(category, product_name), sum(line_total) as revenue)` — i.e.
**every** product per category, not the top one, under the name that promises
the top one. This is the same class flagged in round 2 (bug B); the guidance
edit didn't stop it. Needs either a real top-N-per-group capability or a
deterministic guard.

### 4 — explicitly-requested silver column dropped as "unused"
**Severity: low/medium (debatable)** · BRD 02

The BRD said *"Derive `resolution_days = modifiedon - createdon` in days"* in the
silver layer. It was not built. It **is** disclosed in assumptions ("mentioned…
but not used in any output… not included"), and the note even shows the op that
would build it (`daysBetween`) — so it was buildable. The model dropped an
explicitly-requested, buildable silver column because nothing downstream
referenced it. Defensible, but a user who asked for the column doesn't get it.

## Note on consistency

BRD 10 refused the nested `Resolved/Overdue/Open` conditional cleanly (no output
built). The historically-reported Bug 2 (an invented `'1900-01-01'` sentinel for
the same shape) did **not** recur here — the handling is inconsistent across
runs rather than uniformly wrong.

---

# End-to-end deploy — 10 BRDs, REAL Azure (2026-07-28)

Same 10 BRDs taken through `/approve` (deploy + run) against factory
`azure-datalake-adf`. Self-heal on. **These objects were left in the factory.**

| BRD | Source | Deploy+run | Heals | Root cause if not green |
|----:|--------|-----------|:-----:|-------------------------|
| 01 window/ratio | Postgres | ✅ SUCCEEDED | 0 | — |
| 02 col-vs-col filter | Dataverse | ❌ **FAILED** | 2 | col-vs-col filter → string-literal compare |
| 03 SharePoint | SharePoint | ❌ **FAILED** | 2 | `_`-prefixed system fields break DSL |
| 04 regex + ratio | HTTP | ⚠️ SUCCEEDED | 2 | **ran green with CORRUPT `cfr_pct`** |
| 05 cross-source | SP+DV | ❌ **FAILED** | 2 | same `_`-prefix DSL break |
| 06 prefix/folder | Postgres | ✅ SUCCEEDED | 0 | — |
| 07 honesty trap | Dataverse | ✅ SUCCEEDED | 0 | — |
| 08 multi-file copy | HTTP | ✅ SUCCEEDED | 0 | — |
| 09 top-N per group | Postgres | ⏳ still RUNNING at 25 min | 0 | did not complete in cap |
| 10 sentinel case | Dataverse | 🚫 APPROVE_REJECTED | 0 | transient DNS on pre-deploy check |

**5 green, 3 failed, 1 timed-out, 1 rejected.** One of the "green" runs (04)
shipped corrupt data. Two of the three failures are caused by the Bug-1
SharePoint fix from earlier this session.

## What needs to be fixed — prioritized

### 🔴 P0 — corrupt data that passes every gate (incl. self-heal)
1. **Mixed `*` / `/` arithmetic collapses to all-multiply.** BRD 04:
   `cfr_pct = peak_deaths * 100 / peak` deployed and ran green as
   `regexReplace`-clean but `toDouble(peak_deaths * 100 * peak)` — the `/` became
   `*`. Arithmetic ops carry ONE operator; the model flattened `a*b/c` into a
   single `multiply(a,b,c)`. No gate catches it. Fix: the compiler must reject /
   chain a mixed-operator arithmetic op (or completeness must flag a `divide`
   requirement rendered as `multiply`). **Confirmed corrupt in gold, live.**

### 🔴 P1 — regressions from this session's Bug-1 SharePoint fix
2. **SharePoint `_`-prefixed system fields break the Data Flow DSL** (BRD 03, 05
   both FAILED, `DF-DSL-001`). Deriving membership from an item's `fields` pulled
   in `_UIVersionString`, `_ComplianceFlags`, `_ComplianceTag`, … which are not
   valid DSL identifiers; self-heal could not recover. 
3. **SharePoint columns null in the sampled item are dropped** (BRD 03 plan:
   `ActualCompletion` disclosed as "does not exist"). `$top=1` misses null
   fields. **Fix 2+3 together:** membership = the non-hidden `/columns` names
   (which include the readOnly `id`, and exclude `_*` internals) — do NOT
   replace with one item's raw `fields`. The Bug-1 goal (see `id`) is met by
   simply not skipping readOnly in `/columns`, without importing item internals.

### 🔴 P1 — column-vs-column comparison in a FILTER
4. **A filter like "resolveby earlier than createdon" renders
   `filter(resolveby < 'createdon')`** — comparing a timestamp to the literal
   string `'createdon'` → runtime type failure (BRD 02 FAILED, `DF-FLO-005` even
   after heal). Note: the SAME comparison inside a derived `iif`/case renders
   correctly (`resolveby < createdon`), so this is filter-path-specific. Fix:
   detect a filter whose value names another column and either compile a real
   column-vs-column predicate or declare it unsupported — never quote it.

### 🟡 P2
5. **top-N-per-group refused but a namesake all-products output ships** (BRD 09).
   `groupBy(category, product_name)` under the name `best_seller_per_category`.
   Needs a real top-N-per-group capability or a guard.
6. **Pre-deploy Azure reachability check is not retried** (BRD 10 rejected on a
   transient DNS `getaddrinfo` blip). `retry_sync` now *recognizes*
   `ServiceRequestError`, but `test_azure_config()` / the reachability check
   isn't wrapped in it. Wrap the read-path Azure checks too.
7. **Explicitly-requested silver column dropped as "unused"** (BRD 02
   `resolution_days`). Disclosed, and `daysBetween` exists — so it was
   buildable. Minor.

---

# Resolution (2026-07-29) — fixes applied, offline suite 201 passing

The recurring bugs cluster into one meta-cause: **the system trusted the LLM's
output structurally and had no semantic cross-check against the BRD.** Closed
with a two-layer defense — deterministic floors for the known shapes, a
DSL-aware semantic reviewer as the general net.

## Deterministic floors (hard — repair/flag, tested)
- **P0 arithmetic corruption** — `completeness.check` flags a ratio/percentage/
  rate/average-named column whose derivation chain has no `divide` (a `/` folded
  into a `*`). Verified on the real BRD-04 plan; prompt guidance added to both
  planners. `test_ratio_named_column_without_division_flagged`.
- **P1 SharePoint** — schema reader now unions `/columns` (keeps nullable cols) +
  item `fields` (keeps readOnly `id`), excluding `_`/`@` internals that broke the
  DSL; the mover excludes them too. Fixes the DSL break AND the null-drop.
- **P1 column-vs-column filter** — `Predicate.value_column`: a filter whose value
  names a column renders `resolveby < createdon`, not `< 'createdon'`.
  `test_column_vs_column_filter_renders_as_column_ref`.
- **P2 transient Azure faults** — pre-deploy `factories.get` /
  `get_account_information` wrapped in `retry_sync`.
- (from round 2) duplicate-aggregation `= 100` flag, fabricated-column
  disclosure, surgical group_by salvage.

## Semantic net (advisory — the durable class-fix)
`reviewer.py` now receives the **rendered Data Flow expressions** (not just the
plan JSON) and is primed on the recurring corruption families — folded divides,
prose replacements, column-vs-quoted-column, faked totals, name-vs-behavior
mismatches. It reads what the DSL actually computes and compares to the BRD.
This is the general net for novel shapes the deterministic floors don't name.
`rendered_expressions()` is unit-tested; the LLM judgment is live-only.

## Prompt-level (best-effort mitigations)
- top-N-per-group: declare unsupported, don't ship a `top_*` namesake.
- build explicitly-requested silver columns even if unused downstream.

## What works well (confirmed live)
- BRDs 01, 06, 07, 08 deployed and ran green end to end.
- Prior fixes that HELD through deploy: custom prefix/folder → unsupported (06),
  fabricated columns disclosed (07), duplicate-aggregation ratio dropped (01),
  regex clean replacement (04).
- Self-heal fixed real runtime issues live: regex `\s`→`\\s` escaping and
  `between` date-literal casting (`DF-FN-0016`) in BRD 04.
