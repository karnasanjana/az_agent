# az_agent — Quality Review & Road to User-Ready

*Written 2026-07-06, from evidence in `artifacts/*/heals.json`, the run history, and the current code.*

---

## Part 1 — Honest quality review: where the application actually is

### What every real failure had in common

| Run | What failed | Root cause | Caught where |
|---|---|---|---|
| `f94767f74536`, `1b822b893e71` | Copy to bronze | BRD named a storage account that doesn't exist (`retailstorage123456`) | **Azure runtime** (~5 min) |
| `1b822b893e71` | Self-heal itself | Heal mis-targeted: copy activity failed, heal patched `df_customers_silver` (unrelated dataflow) — burned all retries | never caught |
| `fe4102f4960d` | Silver dataflow | `aggregate( ) ~> aggdedupeorderitems` — model emitted an aggregate with nothing in it, builder rendered empty parens → DF-DSL-001 parse error | **Azure runtime** |
| `756b3869e824` | Silver dataflow | `groupBy(customer_id)` + `customer_id = first(customer_id)` → DF-AGG-005 duplicate column; plus alias datasets dodged schema grounding (1-column projection) | **Azure runtime** |

**The single pattern: every failure was discoverable locally, and none was.**
Nothing above needed Azure to detect. An empty aggregate is visible in the generated
script text. A duplicate groupBy column is visible in the spec. A nonexistent storage
account answers a DNS query in milliseconds. The application's core defect is not
that the model makes mistakes — it's that mistakes travel 5 minutes into an Azure
run before anyone sees them, and then a mis-aimed heal loop hides the error.

### Why it "worked once with a simple BRD then kept failing"

Not luck, structural: a simple BRD (one dataset, one filter/cast) exercises spec
shapes the normalizer and builder have already been hardened against. A big BRD
(5 datasets, dedup + joins + aggregate) walks the model into spec shapes never seen
before — empty aggregates, alias datasets, groupBy collisions. Each new BRD shape
finds the next unguarded corner. That is exactly the "normalizer whack-a-mole"
leak already identified in the improvement notes. The fix is not more whack-a-mole;
it is making invalid shapes unrepresentable (AST) and catching the rest in preflight.

### Scorecard by subsystem

| Subsystem | State | Verdict |
|---|---|---|
| Parse (BRD → spec, gemini-2.5-flash) | Works; weakest link. Invents aliases, empty transforms, redundant agg columns | Needs AST + decomposition + model eval |
| Grounding | Good since location-aliasing fix; CSV-only; silent when file missing | Extend + make loud |
| Builder | Deterministic, well-commented; has collision guard now; still renders some invalid shapes (empty aggregate) | Close remaining render gaps |
| Preflight | Checks cross-refs/names only. **Does not validate dataflow scripts or Azure resources** | Biggest gap — promote to real gate |
| Deploy | Ordered, prunes, verifies counts | OK |
| Run/self-heal | Recovery rerun + stop + attempt history (new). Target picking = string match, provably wrong once | Fix targeting deterministically |
| State | `_RUNS` in-memory; server restart looks like a hang/retry loop | Persist |
| Eval | Harness exists, 3 golden BRDs, ops% metric | Right instrument — grow + wire to CI |
| UX | Plan/review/graph/approve solid; errors now readable | Minor polish |

### Is the path so far correct?

**Yes — direction validated by the evidence.** The 5-point priority list
(grounding → AST → tighter Pydantic → decomposition → eval) predicted these
failures precisely: every runtime failure was either a grounding miss or a
model-written-shape the builder trusted. Items shipped so far (grounding + alias
stamping, collision guard, recovery rerun, stop, attempt history) each closed a
real observed failure. Not wasted effort, correct order. What's wrong is only
*completeness*: the syntax layer is ~70% closed, and preflight — the cheapest,
highest-leverage gate — is still nearly empty.

---

## Part 2 — The plan

Phases ordered by (bugs it kills) ÷ (effort). Each phase has an exit test.
Phases 1–2 turn "fails at silver/gold" into "fails in 2 seconds locally or not at all."

### Phase 1 — Stop shipping invalid artifacts (1–2 days) ← do this first

**1.1 Dataflow script linter in preflight.** Deterministic checks on every
generated script — no LLM, no Azure:
- balanced parens/brackets, no empty `aggregate()`, `derive()`, `filter()`, `groupBy()`
- every stream referenced exists; exactly one sink; source streams unique
- aggregate: agg-column names ∩ groupBy = ∅ (belt-and-braces with the builder guard)
- every column referenced in expressions exists in the incoming projection
  (grounding already computes projections — reuse `_flow_output_columns`)
- Delta sink not fed by Copy (already guarded — move the error into preflight report)

Would have caught: DF-DSL-001 (`fe4102f4960d`), DF-AGG-005 (`756b3869e824`). Exit
test: both bad specs (kept in `artifacts/`) fail preflight with a pointed message.

**1.2 Builder: refuse to render empty/degenerate transforms.** Empty aggregate →
build error naming the transform (or drop it with a note if group_by empty AND
columns empty). Same for empty derive/select. Symmetric with the collision guard.

**1.3 Resource preflight (the storage-account class).** Before approval, in
preflight with real backend:
- resolve every linked-service endpoint (DNS or `az storage account show`)
- check landing files exist (grounding already reads them — surface "0 of 5
  landing files found" as a **blocking** check, not a silent skip)
- verify factory/resource-group reachable with current credential

Would have caught: both `retailstorage123456` runs at plan time. Exit test: BRD
with fake account → preflight FAILS in seconds, approve button disabled.

### Phase 2 — Make self-heal trustworthy (1–2 days)

**2.1 Deterministic heal targeting.** Replace `_pick_target` string matching:
parse the failed activity name from the ADF error → look up which pipeline JSON
contains that activity → map ExecuteDataFlow → its dataflow, Copy → its datasets
+ linked service. All in the artifacts on disk; zero guessing. Evidence:
`1b822b893e71` burned every retry patching a dataflow when a copy activity failed.
Exit test: replay that run's error string → targeting returns the copy pipeline,
not `df_customers_silver`.

**2.2 Heal validation gate.** A healed artifact must pass the Phase-1 linter
before redeploy; if the heal output fails lint, retry the heal with the lint
error appended (same feedback loop as parse-time Pydantic retries).

**2.3 No-progress detection.** Same artifact + same error class twice → stop,
surface both attempts, don't burn the third retry. (Stop button + attempt
history already shipped.)

### Phase 3 — Kill the remaining model-written syntax (2–4 days)

**3.1 Finish the expression AST (priority item 2).** `op` enum exists and is
partially adopted (`ops%` in the eval). Close it: expressions become
`{op, column, args}` only; builder renders all DSL; raw `expression` strings
demoted to a fallback the eval counts against the model, then removed. Invalid
syntax becomes unrepresentable — this ends the whack-a-mole permanently.

**3.2 Tighten Pydantic (priority item 3).** `aggregate`: `group_by` or `columns`
non-empty; `filter`: condition/predicates required; `join`: right_stream +
condition required; alias detection: two DelimitedText/Delta datasets with the
same location → validation error telling the model to reuse the existing one
(pydantic-ai feeds it back, model retries in seconds).

**3.3 Decompose generation (priority item 4).** One call: skeleton (layers,
datasets, pipeline chain). Then one small call per dataflow: "here is the REAL
grounded schema of your source; emit transforms as ops." Narrow prompts are the
proven way to make a small model behave; also makes each call independently retryable.

### Phase 3.5 — Coverage: the "any BRD should pass" strategy (parallel track)

"Any BRD" has to be engineered honestly. ADF's full surface is ~100 connectors ×
~40 activity types × 3 trigger families; no closed spec covers it all at once, and
an open one (LLM emits raw ADF JSON) re-opens every syntax leak just closed. The
achievable contract — and the one users actually need — is:

> **Every BRD gets either a correct pipeline or an explicit "this needs X, which
> isn't supported yet" at PLAN time. Never a silently degraded pipeline.**

Today that contract is broken: `_SUPPORTED_ACTIVITIES` is only
`{Copy, ExecuteDataFlow, ExecutePipeline}` and everything else is **silently
dropped** (builder.py:640-648). The retail BRD's VALIDATION section (file exists,
not empty, block downstream) vanished without a note. That silent-drop is why "any
BRD" feels broken — the app pretends to accept requirements it discards.

**3.5.1 Capability contract (hours, do with Phase 1).** Silent drops become loud:
any unsupported activity/feature in the spec → a blocking preflight line
("BRD requires file-validation activities — not supported yet") + an assumption
in the review. User decides: proceed degraded or stop. Trust restored immediately.

**3.5.2 Coverage tier 1 (days): the medallion 95%.**
- `GetMetadata` + `IfCondition`/`Validation` activities — file-exists / not-empty
  gates (asked for by the current BRD)
- `Delete` activity (archive/cleanup asks)
- Parquet + JSON datasets as first-class sources (grounding included)
- Tumbling-window trigger, event (blob-created) trigger
- Copy upsert options; Delta append mode behind an explicit spec flag

**3.5.3 Coverage tier 2 (week+): common enterprise asks.**
- Azure SQL / Synapse SQL source+sink (linked service, dataset, lookup)
- REST/HTTP paginated sources
- `ForEach` + `Lookup` (metadata-driven fan-out — "process every file in folder")
- SCD2 / merge patterns in data flows (alterRow + upsert sink)

**3.5.4 The coverage flywheel.** Every rejected BRD (capability-contract hit)
is logged; the log IS the tier-3 backlog, ranked by real demand. Each new
capability lands with: spec type + builder render + linter rule + golden BRD in
the eval. Coverage grows measurably, never by silently guessing.

### Phase 4 — Survive real usage (2–3 days)

**4.1 Persist runs.** `_RUNS` → JSON sidecar per run dir (status, spec ref,
messages, preflight). On startup, rehydrate finished runs; mark in-flight ones
`INTERRUPTED` with a resume-or-abandon prompt. Kills the known
restart-looks-like-a-hang trap.

**4.2 Post-run data validation.** After Succeeded: count rows/files in silver
and gold (storage list + Delta log read). "Succeeded but gold is empty" is
today invisible — it's the valid-but-wrong class made visible. Report row counts
per layer in the UI.

**4.3 Structured logging.** One log line per run-state transition with run_id;
server.log currently useless for diagnosis (21 lines of access noise).

### Phase 5 — Prove it, then ship it (ongoing)

**5.1 Golden-BRD eval as the release gate (priority item 5).** Add the big retail
BRD (the one that failed) + every BRD that ever broke production as golden cases.
Extend `eval_spec_gen.py` scoring with the Phase-1 linter (parse → build →
preflight → **lint**). Target: ≥95% pass over 5 runs/BRD before any model or
prompt change merges. This is what makes "model-independent" a number.

**5.2 Model upgrade experiment.** With the eval in place, run the current model
(gemini-2.5-flash) vs a larger one side by side. Decide with data whether the
small model + guards is enough or the semantic layer needs a better model.
(Known: small models invent; unknown: how much it still costs after Phases 1–3.)

**5.3 Regression suite.** `tests/regressions/` — every healed artifact's
before/after pair becomes a test: bad spec in → builder+linter must reject or
correct. `heals.json` files are free test data already on disk.

### Phase 6 — User-ready packaging (when 1–5 green)

- **Auth**: the app holds subscription-level credentials — add at least a shared
  token / SSO in front before anyone else touches it.
- **Multi-user**: per-user run isolation (currently one global `_RUNS`, one .env
  deploy target). Config per run, not per process.
- **Deployment**: Dockerfile + container app; health/readiness endpoints exist.
- **Docs**: 10-minute quickstart — BRD in, pipeline out, what the approval gate
  shows, what self-heal does, where audit files live.
- **Guardrails for tenants**: cap objects per deploy, always prune-preview before
  prune, "dry-run only" mode for first-time users.

---

## Part 3 — Definition of "ready for users"

An end-to-end acceptance bar, not vibes:

1. **Fresh tenant test**: new resource group + storage + factory, upload the big
   retail BRD, approve, pipeline succeeds, gold CSV has rows — no manual touch.
2. **Sabotage test**: wrong storage account in BRD → blocked at preflight with a
   plain-English message. Missing landing file → blocked, named.
3. **Chaos test**: kill the server mid-run, restart → run state recovers, no
   phantom retry loop.
4. **Eval gate**: ≥95% parse+build+preflight+lint across golden BRDs, 5 runs each.
5. **Second user test**: someone who didn't build it goes BRD→gold using only the
   quickstart doc.

When those five pass, it is an agent users can be given.

---

## Effort summary

| Phase | Effort | Payoff |
|---|---|---|
| 1. Local gates (lint + resource preflight) | 1–2 days | Kills every observed failure class at plan time |
| 2. Trustworthy self-heal | 1–2 days | Retries stop being a slot machine |
| 3. AST + tight Pydantic + decomposition | 2–4 days | Syntax layer 100% model-proof |
| 4. Persistence + data validation | 2–3 days | Survives restarts; catches valid-but-wrong |
| 5. Eval as release gate | ongoing | "Model-independent" becomes measured |
| 6. Packaging (auth, docker, docs) | 3–5 days | Other humans can use it |

Roughly two focused weeks to the acceptance bar, with the app meaningfully more
reliable after the first two days.
