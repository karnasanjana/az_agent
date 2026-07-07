# IMPLEMENTATION SPEC — LogicalPlan refactor (BRD → LogicalPlan → Compiler → PipelineSpec → ADF)

**Audience: an LLM implementer (Claude, GPT, any). Follow EXACTLY. Do not redesign,
do not rename, do not "improve". Where this spec says a field name, use that field
name. Where it gives a formula, implement that formula. If a step is impossible as
written, STOP and report the conflict — do not invent a workaround.**

---

## 0. Rules for the implementer

1. Execute steps IN ORDER. Do not start step N+1 until step N's acceptance test passes.
2. After every step run: `python -m pytest tests/ -x -q` from repo root. All green before proceeding.
3. Never delete code until Step 8 says so. Until then old and new paths coexist behind the env flag `LEGACY_PARSER` (Step 6).
4. Never edit: `agent/builder.py`, `agent/deployer.py`, `agent/validator.py`, `agent/graph.py`, `agent/review.py`, `ui.py` — except the exact edits listed in Step 6.
5. All new code: Python 3.10+, Pydantic v2, same style as existing files (module docstring explaining WHY, `from __future__ import annotations`).
6. Model access: reuse `get_model()`, `structured_output()`, `default_model_settings()` from `config.py`. Do not construct model clients directly.
7. Commit after each step with message `logical-plan step N: <what>`.

---

## 1. Context you need (read these files first, change nothing)

- `models/spec.py` — the current `PipelineSpec`. The compiler (Step 3) EMITS this type. Note `_OP_FN` (line ~214): the closed op vocabulary. Note `Transform`, `DataFlow`, `DataFlowEndpoint`, `Dataset`, `DatasetKind`, `LinkedService`, `PipelineDef`, `Activity`, `Trigger`.
- `agent/parser.py` — the current one-big-call parser. Will become legacy.
- `app.py` lines ~186–350 — `/plan`, `/chat`, `_store_and_respond`. Step 6 rewires these.
- `agent/preflight.py`, `agent/lint.py` — validators. Untouched; frozen after Step 8.
- `agent/grounding.py` — `ground_spec(spec)` stamps real column schemas. Called unchanged after compile.

Current flow: `parse_brd(text)` → `PipelineSpec` (LLM invents names/wiring/datasets — source of all failures).
Target flow: `extract_plan(text)` → `LogicalPlan` (business logic only) → `compile_plan(plan)` → `PipelineSpec` (all names/wiring deterministic) → existing builder/preflight/deploy unchanged.

---

## 2. Step 1 — `models/logical.py` (new file)

Create `models/logical.py` with EXACTLY these models. Copy the op-vocabulary sets from `models/spec.py` by importing them (do not duplicate): `from models.spec import _OP_FN, _OP_IDENTITY, _norm_op`.

```python
"""LogicalPlan: the ONLY thing the LLM produces. Business intent, zero ADF.

No resource names, no linked services, no containers, no DSL, no JSON schema.
The deterministic compiler (agent/compiler.py) turns this into a PipelineSpec.
Anything the model cannot express goes in `unsupported` — loud, never silent.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.spec import _OP_FN, _OP_IDENTITY, _norm_op


class SourceFormat(str, Enum):
    csv = "csv"
    parquet = "parquet"
    json = "json"
    sql_table = "sql_table"
    http_csv = "http_csv"      # CSV fetched from a public HTTP(S) URL


class OutputFormat(str, Enum):
    delta = "delta"
    csv = "csv"
    parquet = "parquet"


class LogicalColumn(BaseModel):
    name: str
    type: str = "string"       # string|integer|long|double|decimal(p,s)|boolean|date|timestamp


class LogicalSource(BaseModel):
    """One business entity to ingest. `entity` is snake_case business name
    (e.g. 'orders', 'customers') — NEVER an ADF resource name."""
    entity: str
    format: SourceFormat
    # storage-resident source (format csv/parquet/json):
    container: Optional[str] = None
    folder: Optional[str] = None
    file_name: Optional[str] = None
    # http source (format http_csv):
    http_url: Optional[str] = None      # full URL to the file
    # sql source (format sql_table):
    server: Optional[str] = None
    database: Optional[str] = None
    schema_name: Optional[str] = None
    table_name: Optional[str] = None
    columns: List[LogicalColumn] = Field(default_factory=list)  # optional; grounding overrides

    @field_validator("entity")
    @classmethod
    def _snake(cls, v: str) -> str:
        import re
        s = re.sub(r"[^a-z0-9_]", "_", v.strip().lower())
        s = re.sub(r"_+", "_", s).strip("_")
        if not s:
            raise ValueError("entity name empty after normalization")
        return s

    @model_validator(mode="after")
    def _location_complete(self) -> "LogicalSource":
        if self.format == SourceFormat.http_csv and not self.http_url:
            raise ValueError(f"source '{self.entity}': http_csv needs http_url")
        if self.format == SourceFormat.sql_table and not (self.server and self.database and self.table_name):
            raise ValueError(f"source '{self.entity}': sql_table needs server, database, table_name")
        if self.format in (SourceFormat.csv, SourceFormat.parquet, SourceFormat.json) and not self.file_name and not self.folder:
            raise ValueError(f"source '{self.entity}': storage source needs file_name (or folder)")
        return self


class CleaningOp(BaseModel):
    """One column operation. `op` MUST be in the closed vocabulary."""
    op: str                     # any key of _OP_FN, or identity
    column: str                 # input column
    args: List[str] = Field(default_factory=list)   # literals (formats etc.)
    new_column: Optional[str] = None  # output name; None = replace column in place

    @field_validator("op")
    @classmethod
    def _known(cls, v: str) -> str:
        key = _norm_op(v)
        if key not in _OP_FN and key not in _OP_IDENTITY:
            raise ValueError(
                f"unknown op '{v}'. Allowed: {', '.join(sorted(_OP_FN))}, identity"
            )
        return v


class FilterRule(BaseModel):
    op: str                     # not_null | null | eq | ne | gt | ge | lt | le
    column: str
    value: Optional[str] = None

    @field_validator("op")
    @classmethod
    def _known(cls, v: str) -> str:
        if _norm_op(v) not in {"notnull", "null", "eq", "ne", "gt", "ge", "lt", "le",
                               "isnull", "isnotnull", "notempty", "exists", "missing"}:
            raise ValueError(f"unknown filter op '{v}'")
        return v


class EntityTransform(BaseModel):
    """Silver-layer cleaning for one entity. Absent entity = copy-only (no silver flow)."""
    entity: str
    casts: List[LogicalColumn] = Field(default_factory=list)     # target types
    cleaning: List[CleaningOp] = Field(default_factory=list)     # trim/upper/replace...
    filters: List[FilterRule] = Field(default_factory=list)      # AND-ed
    dedup_keys: List[str] = Field(default_factory=list)          # non-empty => dedup


class JoinPlan(BaseModel):
    left_entity: str
    right_entity: str
    left_keys: List[str]
    right_keys: List[str]
    type: str = "inner"        # inner | left | right | full

    @model_validator(mode="after")
    def _keys(self) -> "JoinPlan":
        if not self.left_keys or len(self.left_keys) != len(self.right_keys):
            raise ValueError(
                f"join {self.left_entity}->{self.right_entity}: left_keys and "
                "right_keys must be non-empty and same length"
            )
        return self


class AggregationPlan(BaseModel):
    name: str                   # output column name
    op: str                     # sum|avg|min|max|count|count_distinct|first
    column: str

    @field_validator("op")
    @classmethod
    def _known(cls, v: str) -> str:
        if _norm_op(v) not in {"sum", "avg", "mean", "min", "max", "count",
                               "countdistinct", "first"}:
            raise ValueError(f"unknown aggregation op '{v}'")
        return v


class SortPlan(BaseModel):
    column: str
    order: str = "desc"         # asc | desc


class OutputPlan(BaseModel):
    """One gold/business output."""
    name: str                   # snake_case business name, e.g. 'monthly_sales'
    from_entities: List[str]
    joins: List[JoinPlan] = Field(default_factory=list)
    derived: List[CleaningOp] = Field(default_factory=list)   # computed BEFORE aggregation
    group_by: List[str] = Field(default_factory=list)
    aggregations: List[AggregationPlan] = Field(default_factory=list)
    filters: List[FilterRule] = Field(default_factory=list)   # applied BEFORE aggregation
    sort: List[SortPlan] = Field(default_factory=list)
    top_n: Optional[int] = None
    columns: List[str] = Field(default_factory=list)          # final projection; [] = all
    format: OutputFormat = OutputFormat.delta

    @field_validator("name")
    @classmethod
    def _snake(cls, v: str) -> str:
        import re
        s = re.sub(r"[^a-z0-9_]", "_", v.strip().lower())
        s = re.sub(r"_+", "_", s).strip("_")
        if not s:
            raise ValueError("output name empty after normalization")
        return s


class SchedulePlan(BaseModel):
    frequency: str = "Day"      # Day | Hour | Minute | Week | Month
    interval: int = 1
    start_time: Optional[str] = None


class LogicalPlan(BaseModel):
    """Complete business description of the pipeline. NO ADF concepts."""
    project: str = "pipeline"   # short snake_case project name for the master pipeline
    sources: List[LogicalSource]
    transforms: List[EntityTransform] = Field(default_factory=list)
    outputs: List[OutputPlan] = Field(default_factory=list)
    schedule: Optional[SchedulePlan] = None
    # Requirements the model recognized but this system cannot build.
    # LOUD capability contract: each is one plain-English line, e.g.
    # "file-existence validation gates (GetMetadata/IfCondition) — not supported".
    unsupported: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    clarifications: List[str] = Field(default_factory=list)

    @field_validator("project")
    @classmethod
    def _snake(cls, v: str) -> str:
        import re
        s = re.sub(r"[^a-z0-9_]", "_", (v or "pipeline").strip().lower())
        s = re.sub(r"_+", "_", s).strip("_")
        return s or "pipeline"
```

**Acceptance (write `tests/test_logical.py`):**
1. A valid plan (2 csv sources, 1 transform with dedup, 1 output with a join + 2 aggregations) validates.
2. `CleaningOp(op="partitionBy", column="x")` raises (unknown op).
3. `JoinPlan(left_entity="a", right_entity="b", left_keys=[], right_keys=[])` raises.
4. `LogicalSource(entity="Orders Data!", format="csv", file_name="o.csv")` → entity == `"orders_data"`.

---

## 3. Step 2 — `agent/compiler.py` (new file)

Create `agent/compiler.py`. One public function:

```python
def compile_plan(plan: LogicalPlan) -> PipelineSpec:
```

Deterministic. No LLM. No I/O except `os.environ.get("ADLS_ACCOUNT_NAME", "")`.

### 3.1 Naming formulas (EXACT — no deviation)

| Object | Name |
|---|---|
| Storage linked service | `ls_storage` |
| HTTP linked service | `ls_http_{host}` where host = url host, non-alnum → `_` |
| SQL linked service | `ls_sql_{server}` where server = first label of server host, non-alnum → `_` |
| Landing dataset (external source) | `ds_landing_{entity}` |
| Bronze dataset | `ds_bronze_{entity}` |
| Silver dataset | `ds_silver_{entity}` |
| Gold dataset | `ds_gold_{output.name}` |
| Silver data flow | `df_silver_{entity}` |
| Gold data flow | `df_gold_{output.name}` |
| Ingest pipeline | `pl_ingest_{entity}` |
| Silver pipeline | `pl_silver_{entity}` |
| Gold pipeline | `pl_gold_{output.name}` |
| Master pipeline | `pl_master_{plan.project}` |
| Trigger | `tr_schedule_{plan.project}` |
| Copy activity | `copy_{entity}` |
| ExecuteDataFlow activity | `flow_{dataflow name without df_ prefix}` |
| ExecutePipeline activity (in master) | `run_{child pipeline name without pl_ prefix}` |
| Stream names in flows | source `src{Entity}` (entity CamelCase, alnum only), sink `sink{Entity}`; transform streams see 3.4 |

### 3.2 Linked services + storage

- Always emit ONE `LinkedService(name="ls_storage", type="AzureBlobFS", auth=managed_identity, account_url=None)`. (builder.py resolves the real endpoint from `ADLS_ACCOUNT_NAME` env — see `_storage_endpoint`; passing None is correct.)
- Per distinct `http_url` host: `LinkedService(name=..., type="HttpServer", auth=anonymous, url="{scheme}://{host}")`.
- Per distinct sql server: `LinkedService(name=..., type="AzureSqlDatabase", auth=managed_identity, server=..., database=...)`.
- `spec.storage = StorageAccount(account_name=os.environ.get("ADLS_ACCOUNT_NAME", "storage"), containers=[...])` where containers = `["bronze", "silver", "gold"]` plus `"landing"` if any storage-resident source is used as landing.

### 3.3 Datasets + ingest (bronze)

For each `LogicalSource`:

- **storage csv/parquet/json**: landing dataset `ds_landing_{entity}` = `Dataset(kind=DelimitedText|Parquet|Json, linked_service="ls_storage", location=DatasetLocation(container=source.container or "landing", folder=source.folder, file_name=source.file_name))`. Bronze dataset `ds_bronze_{entity}` = same kind, `location=DatasetLocation(container="bronze", folder=entity, file_name=source.file_name)`.
- **http_csv**: landing dataset `ds_landing_{entity}` = `Dataset(kind=DelimitedText, linked_service=<http ls>, relative_url=<url path part>)`. Bronze as above with kind DelimitedText, file_name=`{entity}.csv`.
- **sql_table**: landing dataset = `Dataset(kind=AzureSqlTable, linked_service=<sql ls>, schema_name=..., table_name=...)`. Bronze = DelimitedText, container bronze, folder entity, file_name `{entity}.csv`.
- If `source.columns` present, copy to BOTH landing and bronze `columns` as `Column(name, type)`.
- Ingest pipeline `pl_ingest_{entity}` with ONE `Activity(name=f"copy_{entity}", type="Copy", layer=bronze, source_dataset=ds_landing_..., sink_dataset=ds_bronze_...)`.

### 3.4 Silver flows

For each `EntityTransform` whose entity exists in sources (skip + record in `assumptions` if not):

- Sink: `ds_silver_{entity}` = `Dataset(kind=Delta, linked_service="ls_storage", location=DatasetLocation(container="silver", folder=entity))`.
- `DataFlow(name=f"df_silver_{entity}", layer=silver, source=DataFlowEndpoint(stream_name=f"src{Camel}", dataset=bronze_ds_name), sink=DataFlowEndpoint(stream_name=f"sink{Camel}", dataset=silver_ds_name), source_columns=<source.columns or []>)`.
- Transforms IN THIS ORDER (skip empty ones), stream names EXACTLY:
  1. casts → `Transform(kind=cast, name="castTypes", columns=[DerivedColumn(name=c.name, expression=f"to{TypeCamel}({c.name})")...])` — map type→fn: integer→toInteger, long→toLong, double→toDouble, decimal(..)→`toDecimal({name}, p, s)`, boolean→toBoolean, date→`toDate({name})`, timestamp→`toTimestamp({name})`, string→toString.
  2. cleaning → `Transform(kind=derived, name="cleanColumns", columns=[DerivedColumn(name=op.new_column or op.column, op=op.op, column=op.column, args=op.args)...])`.
  3. filters → `Transform(kind=filter, name="filterRows", predicates=[Predicate(op=f.op, column=f.column, value=f.value)...])`.
  4. dedup_keys → `Transform(kind=aggregate, name="dedupRows", group_by=dedup_keys, columns=[DerivedColumn(name=c, op="first", column=c) for c in <all known non-key columns>])`. Known columns = source.columns names + new_columns added by cleaning, minus dedup_keys. If no columns known (empty schema), still emit the aggregate with `columns=[]` and RELY on grounding+`_infer_source_columns`; add to `plan.assumptions`: `"dedup for {entity}: non-key columns unknown until grounding"` — grounding runs later and `agent/grounding.py` fills schemas. **Compiler must then post-fill**: after `ground_spec()` in app.py the flow is re-checked (Step 6 wiring handles ordering; nothing extra here).
  5. Silver pipeline `pl_silver_{entity}` with ONE `Activity(name=f"flow_silver_{entity}", type="ExecuteDataFlow", layer=silver, data_flow=df_name)`.

### 3.5 Gold flows

For each `OutputPlan`:

- Resolve each entity in `from_entities` to its BEST dataset: `ds_silver_{entity}` if a silver flow exists for it, else `ds_bronze_{entity}`.
- Sink: `ds_gold_{output.name}` kind by `output.format` (delta→Delta / csv→DelimitedText / parquet→Parquet), `location=DatasetLocation(container="gold", folder=output.name)`; for csv also `file_name=f"{output.name}.csv"`.
- `DataFlow(name=f"df_gold_{output.name}", layer=gold)`:
  - `source` = first entity's dataset, `stream_name=f"src{Camel(entity)}"`.
  - `additional_sources` = one `DataFlowEndpoint(stream_name=f"src{Camel(entity)}", dataset=...)` per remaining entity.
  - Join transforms: for i, j in enumerate(output.joins): `Transform(kind=join, name=f"join{i+1}", right_stream=f"src{Camel(j.right_entity)}", join_type={"inner":"inner","left":"left_outer","right":"right_outer","full":"full_outer"}[j.type], condition=" && ".join(f"{L}@{lk} == {R}@{rk}" for lk, rk in zip(j.left_keys, j.right_keys)))` where `L` = stream carrying the left side (`src{Camel(left_entity)}` for the first join, `join{i}` for later ones… **use the LEFT ENTITY's src stream name in the condition — ADF resolves columns by origin stream; this matches the existing builder's join rendering. Verify against `agent/builder.py`'s join handling and follow whatever the builder expects for `condition`.**)
  - derived → `Transform(kind=derived, name="deriveColumns", ...)` same mapping as 3.4.2.
  - filters → `Transform(kind=filter, name="filterRows", ...)`.
  - group_by/aggregations → `Transform(kind=aggregate, name="aggregateRows", group_by=output.group_by, columns=[DerivedColumn(name=a.name, op=a.op, column=a.column)...])`. **Guard: any `a.name` also in `group_by` → raise `ValueError(f"output {output.name}: aggregation '{a.name}' duplicates a group_by column")`** (compiler refuses; completeness check catches earlier).
  - sort → `Transform(kind=sort, name="sortRows", order_by=[SortKey(column=s.column, order=s.order)...])`.
  - top_n → `Transform(kind=limit, name="limitRows", take=output.top_n)`.
  - columns (final projection, non-empty) → `Transform(kind=select, name="selectFinal", columns=[DerivedColumn(name=c) for c in output.columns])`.
- Gold pipeline `pl_gold_{output.name}` with ONE ExecuteDataFlow activity `flow_gold_{output.name}`.

### 3.6 Master pipeline + trigger

- `pl_master_{plan.project}`: one `Activity(type="ExecutePipeline", name=f"run_{child without pl_}", invoked_pipeline=child)` per child pipeline, in order ingest → silver → gold.
- `depends_on` (activity names): each silver's activity depends on `[run_ingest_{entity}]`; each gold's activity depends on `[run_silver_{e} for e in from_entities if silver exists]`, else on the ingest runs of its entities.
- If `plan.schedule`: `Trigger(name=f"tr_schedule_{plan.project}", kind=schedule, pipeline=master_name, frequency=schedule.frequency, interval=schedule.interval, start_time=schedule.start_time)`.
- `spec.name = plan.project`; copy `plan.assumptions` → `spec.assumptions`, `plan.clarifications` → `spec.clarifications`, and every `plan.unsupported` line → `spec.assumptions` PREFIXED with `"NOT BUILT (unsupported): "`.

**Acceptance (write `tests/test_compiler.py`):**
1. Plan with 2 csv sources, 1 transform (cast+filter+dedup), 1 output (join, group_by, 2 aggs, sort, top_n) → `compile_plan` returns a PipelineSpec where: `spec.naming_violations() == []`, `spec.cross_reference_errors() == []`, exactly 1 storage linked service, dataset count == 2 landing + 2 bronze + 1 silver + 1 gold, master has 4 ExecutePipeline activities with correct depends_on.
2. Same plan compiled twice → `spec.model_dump()` identical (determinism).
3. Aggregation name duplicating group_by → `ValueError`.
4. `builder.write_artifacts(compile_plan(plan), "test_compile_run")` succeeds and `preflight.validate("test_compile_run")["passed"] is True` (run with `MOCK=true` env; clean up `artifacts/test_compile_run` after).

---

## 4. Step 3 — `agent/completeness.py` (new file)

Deterministic critic. No LLM.

```python
def check(plan: LogicalPlan) -> List[str]:
```

Return one plain-English string per problem (empty list = pass). Checks — implement ALL:

1. `plan.sources` empty → `"no sources: the plan must ingest at least one entity"`.
2. Duplicate `entity` names among sources.
3. Every `EntityTransform.entity` exists in sources.
4. Every `OutputPlan.from_entities` entity exists in sources.
5. Output with `len(from_entities) >= 2` must have joins forming a CONNECTED graph over from_entities (union-find or BFS; each join edge connects left_entity–right_entity). Not connected → `"output '{name}': entities {missing} are not connected by joins"`.
6. Every join's left_entity and right_entity ∈ from_entities.
7. `aggregations` non-empty but `group_by` empty AND output has >0 aggregations that aren't global → allowed (global agg); no check. But `group_by` non-empty with `aggregations` empty → `"output '{name}': group_by without aggregations"`.
8. Aggregation `name` ∈ `group_by` → duplicate-column error (mirror of compiler guard).
9. When a source has non-empty `columns`: every FilterRule.column, CleaningOp.column, dedup key, join key, group_by name, aggregation column referencing that entity must exist in its columns (for outputs, check against union of from_entities' columns + derived new_columns + aggregation names). Unknown → `"'{col}' is not a column of '{entity}' (has: {list})"`. When columns empty, skip (grounding fills later).
10. `top_n` set but `sort` empty → `"output '{name}': top_n without sort — say what 'top' means"`.

**Acceptance (`tests/test_completeness.py`):** one test per check above (10 tests): a minimal plan violating exactly that check yields exactly one message containing the quoted key phrase.

---

## 5. Step 4 — `agent/extractor.py` (new file)

The ONLY LLM call in the plan path. Mirrors `agent/parser.py`'s structure (agent builder + async run + history) but with `output_type=structured_output(LogicalPlan)` and this system prompt VERBATIM:

```
You are a senior data engineer. Read the user's requirements (a BRD document or
plain sentences) and produce a LogicalPlan: WHAT data exists, HOW it must be
cleaned, and WHAT business outputs are needed. You do NOT design Azure Data
Factory objects — no pipeline names, no datasets, no JSON, no ADF expressions.
A deterministic compiler builds all of that from your plan.

Rules:
- sources: one entry per business entity (file or table) named in the
  requirements. entity = short snake_case business name (orders, customers).
  Use the EXACT file names / URLs / table names the requirements give.
- transforms: one entry per entity that needs cleaning. Express EVERYTHING as
  structured ops from the closed vocabulary — casts (target types), cleaning
  ops (trim/upper/lower/replace/...), filters (not_null/eq/gt/...), dedup_keys.
  There is NO free-text expression field. If logic cannot be expressed with the
  vocabulary, put one plain-English line in `unsupported` instead.
- outputs: one entry per business output the requirements ask for. Joins list
  the key columns on both sides. Aggregations use sum/avg/min/max/count/
  count_distinct/first. "top N" = sort + top_n. Do NOT invent outputs the
  requirements never asked for.
- schedule: only when the requirements state or clearly imply one.
- unsupported: every requirement you recognized but cannot express (validation
  gates, alerting, archive/delete steps, SCD2, incremental merge, ForEach
  patterns). One short line each. NEVER silently drop a requirement.
- assumptions: every decision you made that the requirements left open
  (dedup keys chosen, date formats, join types). Short lines.
- clarifications: AT MOST 2, ONLY when a core fact is missing (e.g. no source
  location at all). Otherwise assume and record in assumptions.
- This is a conversation: on follow-up messages, return the FULL updated plan
  with the requested change applied, everything else unchanged.
```

Public API (mirror parser.py exactly):

```python
async def extract_plan(brd_text, message_history=None) -> Tuple[LogicalPlan, List[Any]]
async def refine_plan(instruction, message_history) -> Tuple[LogicalPlan, List[Any]]
def extract_plan_sync(brd_text) -> LogicalPlan
```

Agent construction: `Agent(get_model(), output_type=structured_output(LogicalPlan), system_prompt=_SYSTEM_PROMPT, retries=4, model_settings=default_model_settings())`. Do NOT load `skills/*.md` (those teach ADF DSL — irrelevant now).

**Acceptance:** `python -c "from agent.extractor import build_extractor_agent; build_extractor_agent()"` runs clean (no API call needed). Full LLM test happens in Step 7 eval.

---

## 6. Step 5+6 — wire into `app.py` with feedback loop

### 6.1 New helper in `app.py` (place above `/plan`)

```python
_MAX_PLAN_REPAIRS = 3

async def _plan_to_spec(text: str, history=None):
    """extract -> completeness -> (repair loop) -> compile. Returns
    (spec, logical_plan, messages). Raises HTTPException(422) with the
    remaining problems when the loop does not converge."""
    from agent.completeness import check
    from agent.compiler import compile_plan
    from agent.extractor import extract_plan, refine_plan

    plan, messages = await extract_plan(text, message_history=history)
    for _ in range(_MAX_PLAN_REPAIRS):
        problems = check(plan)
        if not problems:
            break
        feedback = (
            "Your plan has problems. Fix ALL of them and return the full "
            "corrected plan:\n" + "\n".join(f"- {p}" for p in problems)
        )
        plan, messages = await refine_plan(feedback, messages)
    else:
        raise HTTPException(status_code=422, detail={
            "message": "Could not produce a consistent plan from the requirements.",
            "problems": check(plan),
        })
    return compile_plan(plan), plan, messages
```

### 6.2 Rewire `/plan` and `/chat`

In `/plan` (currently calls `parse_brd`) and `/chat` (currently `refine_spec`):

```python
if os.environ.get("LEGACY_PARSER", "").lower() in {"1", "true"}:
    spec, messages = await parse_brd(text)          # old path, unchanged
else:
    spec, plan, messages = await _plan_to_spec(text)  # /chat: pass run["messages"] as history
```

Everything downstream (`ground_spec`, `write_artifacts`, `preflight.validate`, `_store_and_respond`, `_RUNS[...]`) stays byte-identical. Additionally store the logical plan for audit: after `builder.write_artifacts(...)` write `os.path.join(run_dir, "logical_plan.json")` with `plan.model_dump_json(indent=2)` (only when non-legacy path).

### 6.3 Preflight repair loop (second feedback wire)

In `/plan` and `/chat`, after `pf = preflight.validate(run_id)`: if `pf["passed"]` is False AND not legacy path, run up to 2 repair rounds:

```python
for _ in range(2):
    if pf["passed"]:
        break
    failed = [f"{c['name']}: {c['detail']}" for c in pf["checks"] if not c["passed"]]
    plan, messages = await refine_plan(
        "The compiled pipeline failed validation. Adjust the plan to fix:\n"
        + "\n".join(f"- {f}" for f in failed), messages)
    problems = check(plan)
    if problems:
        continue  # counts as a round
    spec = compile_plan(plan)
    # re-ground, rebuild, re-validate (same calls as the first pass)
    ...
```

If still failing after the loop → keep current behavior exactly (`status: "PREFLIGHT_FAILED"`, user sees checks). Never deploy a failing spec.

**Acceptance:** with `MOCK=true LEGACY_PARSER=true`, `POST /plan` behaves exactly as before (regression: run `tests/smoke_test.py`). With the new path and a stubbed extractor (monkeypatch `extract_plan` to return a fixed valid LogicalPlan), `POST /plan` returns `status="AWAITING_APPROVAL"` with passing preflight. Write this as `tests/test_plan_loop.py` (use FastAPI TestClient; monkeypatch `agent.extractor.extract_plan` / `refine_plan`).

---

## 7. Step 7 — eval as the gate

Extend `tests/eval_spec_gen.py` (keep the existing legacy scoring; ADD a logical-path mode):

1. For each golden BRD file: `extract_plan_sync` → `check` (must be []) → `compile_plan` → `write_artifacts` → `preflight.validate` (must pass) → for every dataflow script, `lint_dataflow_script` (must be []).
2. Score = fraction of BRDs passing all stages over N runs (default 3). Print per-stage failures.
3. Add the big retail BRD (`brd_retail_medallion.md`) as a golden case, plus a copy-only BRD and a single-entity BRD (reuse existing goldens where present).

**Gate rule (record in README):** no change to the extractor prompt, LogicalPlan, or compiler merges unless eval ≥ 95% over 3 runs per BRD.

**Acceptance:** `python tests/eval_spec_gen.py --logical` runs end-to-end and prints per-BRD, per-stage results. (Requires a live model key; when absent, the script must exit with a clear "no model configured" message, not a stack trace.)

---

## 8. Step 8 — deletions (ONLY after Step 7 eval passes ≥95%)

1. In `models/spec.py` DELETE these model_validators: `_repair_layer_sinks`, `_repair_linked_service_refs`, `_repair_container_names`, `_harmonize_copy_kinds`. (Compiler makes their input conditions impossible.) Keep `_normalize_df_expression` and `_sanitize_stream_names` (defense in depth for the legacy path) UNLESS `LEGACY_PARSER` support is also being removed — then delete those too along with `agent/parser.py` and the `LEGACY_PARSER` branches in app.py.
2. `agent/lint.py`: add module-docstring line: `"FROZEN: do not add rules. New failure classes are fixed in the compiler or the LogicalPlan model, never here."`
3. Delete `skills/05-dataflow-script-dsl.md` prompt-loading relevance: extractor never loads skills; leave the files on disk for reference.
4. Run full test suite + eval again. Green → commit `logical-plan step 8: delete repair layer`.

---

## 9. Explicitly OUT of scope (do not build, do not attempt)

- Multi-LLM "critic" agents — completeness.py is the critic, deterministic.
- ADF debug-session live validation — future work, separate spec.
- New activity types (GetMetadata, ForEach, Lookup…) — they go to `unsupported[]`.
- Run persistence (`_RUNS` → disk), UI changes, auth — separate specs.
- Changing `agent/validator.py` self-heal — untouched; it now only sees runtime/environment errors.

## 10. Definition of done

1. All new tests + existing tests green.
2. `MOCK=true`: retail BRD through `/plan` → `AWAITING_APPROVAL`, preflight all-pass, `logical_plan.json` in the run dir, zero raw `expression` strings in the generated spec (assert in eval: every DerivedColumn came from an op).
3. Eval ≥95% over 3 runs on all golden BRDs.
4. A BRD requesting an unsupported feature (e.g. "validate file exists before loading") produces a plan whose review shows `NOT BUILT (unsupported): ...` — visible, not silent.
5. `LEGACY_PARSER=true` still works end-to-end (rollback path) until Step 8 removes it.
