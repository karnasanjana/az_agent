"""Typed Pydantic v2 contract for an ADF medallion pipeline.

This is the ONE source of truth the whole system agrees on. The LLM (via
Pydantic AI) must return a validated ``PipelineSpec`` instance; the deterministic
builder, review, preflight, graph, and deployer all consume the same object.
Nothing downstream parses free text.

The spec is BRD-driven and source-agnostic: HTTP file, Azure Blob/ADLS, and a
generic REST/CSV endpoint are all expressible. Bronze is always a Copy Activity
(no transformation); Silver/Gold are Mapping Data Flows.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Annotated, Literal

# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class AuthKind(str, Enum):
    anonymous = "anonymous"
    managed_identity = "managed_identity"


class DatasetKind(str, Enum):
    delimited_text = "DelimitedText"  # CSV
    parquet = "Parquet"
    json = "Json"
    rest_resource = "RestResource"
    binary = "Binary"                 # byte-for-byte copy of any file type
    azure_sql_table = "AzureSqlTable"  # table in an Azure SQL Database source
    delta = "Delta"                    # Delta Lake table — data flows only (inline),
                                       # never a Copy source/sink or an ADF dataset resource


class TransformKind(str, Enum):
    select = "select"
    cast = "cast"
    derived = "derived"
    filter = "filter"
    aggregate = "aggregate"
    sort = "sort"
    window = "window"
    join = "join"  # combine the current stream with another source stream


class TriggerKind(str, Enum):
    manual = "manual"
    schedule = "schedule"


class MedallionLayer(str, Enum):
    bronze = "bronze"
    silver = "silver"
    gold = "gold"


# --------------------------------------------------------------------------- #
# Sources (discriminated by ``kind``)
# --------------------------------------------------------------------------- #


class HttpSource(BaseModel):
    """Anonymous HTTP(S) file source (e.g. Johns Hopkins CSSE daily CSVs)."""

    kind: Literal["http"] = "http"
    base_url: str
    relative_url_template: str = Field(
        ...,
        description="Relative path, optionally with a {date} / @{dataset().date} token.",
    )
    file_pattern: Optional[str] = None  # e.g. MM-DD-YYYY.csv
    auth: AuthKind = AuthKind.anonymous


class BlobSource(BaseModel):
    """Azure Blob / ADLS Gen2 source, reached with Managed Identity."""

    kind: Literal["blob"] = "blob"
    account_url: str  # https://<acct>.dfs.core.windows.net
    container: str
    path: Optional[str] = None
    auth: AuthKind = AuthKind.managed_identity


class RestSource(BaseModel):
    """Generic REST / CSV-over-HTTP endpoint."""

    kind: Literal["rest"] = "rest"
    base_url: str
    relative_url: Optional[str] = None
    method: str = "GET"
    response_format: str = "json"  # json | csv
    auth: AuthKind = AuthKind.anonymous


class SqlSource(BaseModel):
    """Azure SQL Database source, reached with Managed Identity (no passwords)."""

    kind: Literal["sql"] = "sql"
    server: str    # logical server name or full host (<name>.database.windows.net)
    database: str
    auth: AuthKind = AuthKind.managed_identity


Source = Annotated[
    Union[HttpSource, BlobSource, RestSource, SqlSource], Field(discriminator="kind")
]


# --------------------------------------------------------------------------- #
# Storage / linked services / datasets
# --------------------------------------------------------------------------- #


class StorageAccount(BaseModel):
    """ADLS Gen2 account reached with Managed Identity (no keys)."""

    account_name: str
    account_url: Optional[str] = None  # https://<acct>.dfs.core.windows.net
    containers: List[str] = Field(default_factory=lambda: ["bronze", "silver", "gold"])
    auth: AuthKind = AuthKind.managed_identity


class LinkedService(BaseModel):
    name: str
    type: str  # HttpServer | AzureBlobFS | RestService | AzureSqlDatabase
    auth: AuthKind
    url: Optional[str] = None          # HttpServer / RestService
    account_url: Optional[str] = None  # AzureBlobFS
    server: Optional[str] = None       # AzureSqlDatabase
    database: Optional[str] = None     # AzureSqlDatabase


class Column(BaseModel):
    name: str
    type: str = "string"  # string | integer | timestamp | double | boolean | ...


class DatasetLocation(BaseModel):
    container: str
    folder: Optional[str] = None
    file_name: Optional[str] = None


class Dataset(BaseModel):
    name: str
    kind: DatasetKind
    linked_service: str
    location: Optional[DatasetLocation] = None
    # CSV/JSON/REST over HTTP uses a relative URL instead of a store location.
    relative_url: Optional[str] = None
    # AzureSqlTable only: the source table.
    schema_name: Optional[str] = None  # e.g. dbo
    table_name: Optional[str] = None
    parameters: List[str] = Field(default_factory=list)
    columns: List[Column] = Field(default_factory=list)
    first_row_as_header: bool = True


# --------------------------------------------------------------------------- #
# Data flow transforms
# --------------------------------------------------------------------------- #


class DerivedColumn(BaseModel):
    name: str
    expression: str  # Mapping-Data-Flow expression, e.g. toInteger(Confirmed)


class SortKey(BaseModel):
    column: str
    order: str = "desc"  # asc | desc


# LLMs emit two expression idioms ADF's data-flow DSL rejects at runtime
# (DF-DSL-001 / DF-FN-0015). Normalize them at validation instead of burning a
# ~5-minute self-heal attempt on each:
#   * pipeline-style interpolation:  @{col}      ->  col   ({col} kept when the
#     name needs escaping; stream@{col} -> stream@col for join conditions)
#   * SQL null tests:                col != null ->  !isNull(col)
#                                    col == null ->  isNull(col)
_STREAM_AT_BRACE = re.compile(r"(?<=\w)@\{(\w+)\}")
_AT_BRACE = re.compile(r"@\{([^}]+)\}")
_NULL_NE = re.compile(r"(\w+|\{[^}]+\})\s*!=\s*null\b", re.IGNORECASE)
_NULL_EQ = re.compile(r"(\w+|\{[^}]+\})\s*==\s*null\b", re.IGNORECASE)
# One non-nested ternary spanning the whole expression. ADF's data-flow language
# has NO `?:` operator (DF-EXPR-010) — only iif().
_TERNARY = re.compile(r"^([^?:]+)\?([^?:]+):([^?:]+)$")
# LLM-invented '@stream@column' qualifier (e.g. '@bronzeorders@order_status').
# The leading '@' is never valid DSL; the 'stream@' qualifier itself is only
# valid inside JOIN conditions — everywhere else columns are referenced bare.
_AT_STREAM_AT = re.compile(r"@(\w+)@")

# Bare identifiers in a data-flow expression that are column references: not
# followed by '(' (those are function calls like trim/isNull/toTimestamp) and
# not boolean/null literals. Quoted string literals are stripped before scanning.
_EXPR_IDENT = re.compile(r"\b[A-Za-z_]\w*\b(?!\s*\()")
_EXPR_LITERALS = {"true", "false", "null"}
_QUOTED_LITERAL = re.compile(r"'[^']*'")


def _normalize_df_expression(s: "str | None", keep_stream_qualifier: bool = False) -> "str | None":
    if not s:
        return s
    s = _AT_STREAM_AT.sub(r"\1@" if keep_stream_qualifier else "", s)
    s = _STREAM_AT_BRACE.sub(r"@\1", s)
    s = _AT_BRACE.sub(
        lambda m: m.group(1) if re.fullmatch(r"\w+", m.group(1)) else "{" + m.group(1) + "}",
        s,
    )
    s = _NULL_NE.sub(r"!isNull(\1)", s)
    s = _NULL_EQ.sub(r"isNull(\1)", s)
    m = _TERNARY.match(s.strip())
    if m:
        cond, a, b = (g.strip() for g in m.groups())
        if a.lower() == "true" and b.lower() == "false":
            s = cond
        elif a.lower() == "false" and b.lower() == "true":
            s = f"!({cond})"
        else:
            s = f"iif({cond}, {a}, {b})"
    return s


class Transform(BaseModel):
    """A single Mapping-Data-Flow transformation, producing a named stream."""

    kind: TransformKind
    name: str  # output stream name (e.g. 'CastTypes')
    columns: List[DerivedColumn] = Field(default_factory=list)  # cast/derived/aggregate
    condition: Optional[str] = None  # filter / window; also the JOIN condition
    group_by: List[str] = Field(default_factory=list)  # aggregate
    order_by: List[SortKey] = Field(default_factory=list)  # sort
    # join-only: the OTHER stream to join the current stream with, and the join type.
    # `condition` carries the join expression, e.g. "orders@order_id == items@order_id".
    right_stream: Optional[str] = None
    join_type: str = "inner"  # inner | left_outer | right_outer | full_outer | cross

    @model_validator(mode="after")
    def _normalize_expressions(self) -> "Transform":
        # Joins keep the stream@column qualifier (required to disambiguate the
        # two sides); every other transform references columns bare.
        is_join = self.kind == TransformKind.join
        self.condition = _normalize_df_expression(self.condition, keep_stream_qualifier=is_join)
        for c in self.columns:
            c.expression = _normalize_df_expression(c.expression) or c.expression
        self.group_by = [_normalize_df_expression(g) or g for g in self.group_by]
        return self


class DataFlowEndpoint(BaseModel):
    stream_name: str
    dataset: str
    # Per-source schema (needed for the extra sources of a multi-source/join flow;
    # the primary source keeps using DataFlow.source_columns for back-compat).
    columns: List[Column] = Field(default_factory=list)


def _referenced_columns(transforms: List["Transform"]) -> List[str]:
    """Column names the transforms CONSUME from the source (filter conditions,
    derive/cast/aggregate expressions, group-by keys, sort keys) in first-use
    order. A name produced by an EARLIER transform (a derived/aggregate output
    like `order_count = count(order_id)`) is not a source column — skip it. A
    transform consuming the same name it produces (order_status = trim(order_status))
    still counts: the input read happens before the overwrite."""
    seen: "dict[str, None]" = {}  # insertion-ordered set
    produced: set = set()

    def scan(s: "str | None") -> None:
        if not s:
            return
        for m in _EXPR_IDENT.finditer(_QUOTED_LITERAL.sub("", s)):
            name = m.group(0)
            if name.lower() not in _EXPR_LITERALS and name not in produced:
                seen.setdefault(name)

    for t in transforms:
        scan(t.condition)
        for c in t.columns:
            scan(c.expression)
        for g in t.group_by:
            scan(g)
        for k in t.order_by:
            scan(k.column)
        produced.update(c.name for c in t.columns)
    return list(seen)


class DataFlow(BaseModel):
    name: str
    # silver | gold when the pipeline follows the medallion pattern; None for a
    # non-medallion transformation flow (the builder treats both the same).
    layer: Optional[MedallionLayer] = None
    source: DataFlowEndpoint
    sink: DataFlowEndpoint
    source_columns: List[Column] = Field(default_factory=list)
    # Extra input sources for a multi-source flow (e.g. a Gold join of several Silver
    # datasets). Empty for the common single-source Silver/Gold flow. Each is referenced
    # by its stream_name from a `join` transform's `right_stream`.
    additional_sources: List[DataFlowEndpoint] = Field(default_factory=list)
    transforms: List[Transform] = Field(default_factory=list)
    compute_cores: int = 8  # smallest General Purpose tier

    @model_validator(mode="after")
    def _sanitize_stream_names(self) -> "DataFlow":
        """ADF Mapping-Data-Flow STREAM names (source/sink stream_name, transform
        names) allow ONLY alphanumerics and must start with a letter — unlike the
        ls_/ds_/df_/pl_ resource names, underscores are rejected with 'Provided
        name contains invalid characters'. LLMs emit snake_case anyway, so fix it
        deterministically here and rewrite every reference (right_stream, join
        conditions, expressions using stream@column) to match."""

        def clean(n: str) -> str:
            c = re.sub(r"[^A-Za-z0-9]", "", n or "")
            if c and not c[0].isalpha():
                c = "s" + c
            return c or "Stream"

        rename: dict = {}
        for ep in (self.source, self.sink, *self.additional_sources):
            new = clean(ep.stream_name)
            if new != ep.stream_name:
                rename[ep.stream_name] = new
                ep.stream_name = new
        for t in self.transforms:
            new = clean(t.name)
            if new != t.name:
                rename[t.name] = new
                t.name = new
        if rename:
            pattern = re.compile(
                "|".join(
                    rf"\b{re.escape(k)}\b"
                    for k in sorted(rename, key=len, reverse=True)
                )
            )

            def sub(s: "str | None") -> "str | None":
                return pattern.sub(lambda m: rename[m.group(0)], s) if s else s

            for t in self.transforms:
                if t.right_stream:
                    t.right_stream = rename.get(t.right_stream, clean(t.right_stream))
                t.condition = sub(t.condition)
                for c in t.columns:
                    c.expression = sub(c.expression) or c.expression
        return self

    @model_validator(mode="after")
    def _drop_noop_transforms(self) -> "DataFlow":
        """The LLM emits placeholder transforms with no working parts — e.g. a
        trailing select named 'selectallforsilver' with columns: [], meant as
        'keep everything'. The builder renders that as `select(mapColumn())`,
        which maps NOTHING into the sink; an empty derive/filter/sort is equally
        broken DSL. A contentless transform is a pass-through in intent, so drop
        it — the chain reconnects around it (transforms are a linear chain; only
        additional-source stream names can be a join's right_stream)."""

        def noop(t: Transform) -> bool:
            if t.kind in (TransformKind.cast, TransformKind.derived, TransformKind.select):
                return not t.columns
            if t.kind == TransformKind.aggregate:
                return not t.columns and not t.group_by
            if t.kind in (TransformKind.filter, TransformKind.window):
                return not t.condition
            if t.kind == TransformKind.sort:
                return not t.order_by
            return False  # joins are validated by cross_reference_errors

        self.transforms = [t for t in self.transforms if not noop(t)]
        return self

    @model_validator(mode="after")
    def _infer_source_columns(self) -> "DataFlow":
        """The LLM sometimes omits the source schema entirely (source_columns,
        source.columns AND every dataset column list come back empty). The builder
        then renders `source(output(), allowSchemaDrift: true, ...)` — every real
        column counts as schema DRIFT, and each expression referencing one fails at
        runtime with DF-EXPR-010 'Column X used in expression is unavailable or
        invalid' (a ~5-minute feedback loop per attempt). Recover deterministically:
        declare the columns the transforms actually consume in the source projection,
        as strings — the flow's own cast transforms handle typing. Single-source
        flows only: with joins a bare column can't be attributed to one source."""
        if self.additional_sources:
            return self
        if not self.source_columns and self.source.columns:
            # The LLM filled the per-endpoint schema instead of source_columns —
            # the builder reads only source_columns for the primary source.
            self.source_columns = list(self.source.columns)
        if not self.source_columns:
            self.source_columns = [
                Column(name=n) for n in _referenced_columns(self.transforms)
            ]
        return self


# --------------------------------------------------------------------------- #
# Pipelines & triggers
# --------------------------------------------------------------------------- #


class Activity(BaseModel):
    name: str
    type: str  # Copy | ExecuteDataFlow | ExecutePipeline
    layer: Optional[MedallionLayer] = None  # set on the Bronze Copy activity
    # Copy
    source_dataset: Optional[str] = None
    sink_dataset: Optional[str] = None
    # ExecuteDataFlow
    data_flow: Optional[str] = None
    # ExecutePipeline
    invoked_pipeline: Optional[str] = None
    # chaining
    depends_on: List[str] = Field(
        default_factory=list,
        description="Activity names this one depends on (Succeeded condition).",
    )


class PipelineDef(BaseModel):
    name: str
    parameters: List[str] = Field(default_factory=list)
    activities: List[Activity] = Field(default_factory=list)


class Trigger(BaseModel):
    name: str
    kind: TriggerKind
    pipeline: str
    frequency: Optional[str] = None  # schedule: Day | Hour | ...
    interval: Optional[int] = None
    start_time: Optional[str] = None


# --------------------------------------------------------------------------- #
# Top-level spec
# --------------------------------------------------------------------------- #

_PREFIXES = {
    "linked_services": "ls_",
    "datasets": "ds_",
    "dataflows": "df_",
    "pipelines": "pl_",
}


class PipelineSpec(BaseModel):
    """Complete, validated description of a medallion pipeline."""

    name: str = "medallion_pipeline"
    source: Optional[Source] = None
    storage: Optional[StorageAccount] = None
    linked_services: List[LinkedService] = Field(default_factory=list)
    datasets: List[Dataset] = Field(default_factory=list)
    dataflows: List[DataFlow] = Field(default_factory=list)
    pipelines: List[PipelineDef] = Field(default_factory=list)
    triggers: List[Trigger] = Field(default_factory=list)

    # If the BRD is ambiguous, the parser fills this instead of inventing
    # components. A non-empty list means "needs human clarification".
    # RESERVED FOR GENUINE BLOCKERS ONLY — if the agent can make a sensible
    # assumption it does so and records it in `assumptions`, it does NOT ask here.
    clarifications: List[str] = Field(default_factory=list)

    # Plan-first architect: decisions the agent made on its own to build a complete
    # plan without pestering the user (e.g. "dedup key not stated -> used
    # (Country_Region, Last_Update)"). Surfaced in the plan for the user to accept or
    # override via chat. These NEVER block approval.
    assumptions: List[str] = Field(default_factory=list)

    # Optional enhancements the agent proposes but did NOT build (e.g. "add a daily
    # schedule trigger?", "consider partitioning silver by date"). Advisory only —
    # only include when it would genuinely change the pipeline, never as filler.
    suggestions: List[str] = Field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Robust coercion for LLM output
    # ------------------------------------------------------------------ #

    @field_validator("source", mode="before")
    @classmethod
    def _coerce_source(cls, v):
        """LLMs sometimes serialize the discriminated `source` union as a JSON
        string instead of a nested object — accept and decode it."""
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except Exception:  # noqa: BLE001 — leave it for normal validation
                return v
        return v

    @model_validator(mode="after")
    def _harmonize_copy_kinds(self) -> "PipelineSpec":
        """ADF rejects a Copy where exactly one side is Binary
        (BinaryUnsupportedDatasetType: 'Binary dataSet can only be copied to
        binary dataSet'). The LLM does this when a BRD says "byte-for-byte":
        it marks the sink Binary but leaves the CSV source DelimitedText — which
        also breaks downstream data flows (they can't read Binary). Coerce the
        Binary side to the other side's kind; a format-preserving Copy of the
        same kind is byte-equivalent for our purposes."""
        kinds = {ds.name: ds for ds in self.datasets}
        for pl in self.pipelines:
            for act in pl.activities:
                if act.type != "Copy":
                    continue
                src = kinds.get(act.source_dataset or "")
                snk = kinds.get(act.sink_dataset or "")
                if src is None or snk is None or src.kind == snk.kind:
                    continue
                if src.kind == DatasetKind.binary:
                    src.kind = snk.kind
                elif snk.kind == DatasetKind.binary:
                    snk.kind = src.kind
        return self

    # ------------------------------------------------------------------ #
    # Naming
    # ------------------------------------------------------------------ #

    def naming_violations(self) -> List[str]:
        """Return ls_/ds_/df_/pl_ prefix violations (empty == clean)."""
        issues: List[str] = []
        groups = {
            "linked_services": self.linked_services,
            "datasets": self.datasets,
            "dataflows": self.dataflows,
            "pipelines": self.pipelines,
        }
        for field, items in groups.items():
            prefix = _PREFIXES[field]
            for item in items:
                if not item.name.startswith(prefix):
                    issues.append(f"{field}: '{item.name}' must start with '{prefix}'")
        return issues

    # ------------------------------------------------------------------ #
    # Cross-reference integrity (used by pre-flight, not at construction)
    # ------------------------------------------------------------------ #

    def cross_reference_errors(self) -> List[str]:
        errors: List[str] = []
        ls_names = {ls.name for ls in self.linked_services}
        ds_names = {ds.name for ds in self.datasets}
        df_names = {df.name for df in self.dataflows}
        pl_names = {pl.name for pl in self.pipelines}

        for ds in self.datasets:
            if ds.linked_service not in ls_names:
                errors.append(
                    f"dataset '{ds.name}' references unknown linked service "
                    f"'{ds.linked_service}'"
                )

        for df in self.dataflows:
            if df.source.dataset not in ds_names:
                errors.append(
                    f"dataflow '{df.name}' source references unknown dataset "
                    f"'{df.source.dataset}'"
                )
            if df.sink.dataset not in ds_names:
                errors.append(
                    f"dataflow '{df.name}' sink references unknown dataset "
                    f"'{df.sink.dataset}'"
                )
            for extra in df.additional_sources:
                if extra.dataset not in ds_names:
                    errors.append(
                        f"dataflow '{df.name}' additional source references unknown "
                        f"dataset '{extra.dataset}'"
                    )

        for pl in self.pipelines:
            for act in pl.activities:
                if act.type == "Copy":
                    for ref, kind in ((act.source_dataset, "source"), (act.sink_dataset, "sink")):
                        if ref is None or ref not in ds_names:
                            errors.append(
                                f"pipeline '{pl.name}' activity '{act.name}' Copy {kind} "
                                f"dataset '{ref}' not found"
                            )
                elif act.type == "ExecuteDataFlow":
                    if act.data_flow not in df_names:
                        errors.append(
                            f"pipeline '{pl.name}' activity '{act.name}' references unknown "
                            f"data flow '{act.data_flow}'"
                        )
                elif act.type == "ExecutePipeline":
                    if act.invoked_pipeline not in pl_names:
                        errors.append(
                            f"pipeline '{pl.name}' activity '{act.name}' invokes unknown "
                            f"pipeline '{act.invoked_pipeline}'"
                        )
                # NOTE: unknown depends_on names are NOT flagged. The LLM sometimes
                # points a child-pipeline activity at an activity in a SIBLING child
                # pipeline (cross-pipeline dependency). ADF has no such concept and the
                # builder deterministically DROPS any depends_on not present in the same
                # pipeline (see build_pipeline: `[d for d in depends_on if d in kept]`).
                # So a dangling dep is self-healing, not a blocker — don't fail pre-flight
                # on it.

        for tr in self.triggers:
            if tr.pipeline not in pl_names:
                errors.append(f"trigger '{tr.name}' references unknown pipeline '{tr.pipeline}'")

        return errors

    # Naming and cross-reference integrity are enforced by pre-flight (which
    # blocks approval), not as a hard parse-time failure — a single off-by-one
    # name from the LLM should surface as a fixable pre-flight finding, not make
    # the whole parse fail and burn retries.

    def is_buildable(self) -> bool:
        """True when the spec has enough structure to build SOMETHING reviewable:
        at least one pipeline with at least one activity, and at least one dataset.
        Used to decide whether open clarifications should block the plan (an
        unbuildable spec) or ride along as answerable notes (a buildable one)."""
        has_activity = any(pl.activities for pl in self.pipelines)
        return bool(self.datasets) and has_activity


def validate_naming(spec: PipelineSpec) -> List[str]:
    """Module-level helper mirroring ``PipelineSpec.naming_violations``."""
    return spec.naming_violations()
