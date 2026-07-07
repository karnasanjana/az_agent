"""LogicalPlan: the ONLY thing the LLM produces. Business intent, zero ADF.

No resource names, no linked services, no containers, no DSL, no JSON schema.
The deterministic compiler (agent/compiler.py) turns this into a PipelineSpec.
Anything the model cannot express goes in `unsupported` — loud, never silent.

This is the search-space collapse: the model decides WHAT the business wants
(entities, cleanings, joins, outputs), and code decides everything ADF —
names, wiring, datasets, expressions. Invalid ADF syntax becomes
unrepresentable because there is no free-text expression field here; every
operation is a key of the closed op vocabulary shared with models/spec.py.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.spec import _OP_FN, _OP_IDENTITY, _norm_op


def _snake(v: str, *, field: str) -> str:
    """Normalize a business name to snake_case (letters, digits, single _)."""
    s = re.sub(r"[^a-z0-9_]", "_", (v or "").strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        raise ValueError(f"{field} empty after normalization")
    return s


class SourceFormat(str, Enum):
    csv = "csv"
    parquet = "parquet"
    json = "json"
    sql_table = "sql_table"
    http_csv = "http_csv"  # CSV fetched from a public HTTP(S) URL


class OutputFormat(str, Enum):
    delta = "delta"
    csv = "csv"
    parquet = "parquet"


class LogicalColumn(BaseModel):
    name: str
    type: str = "string"  # string|integer|long|double|decimal(p,s)|boolean|date|timestamp


class LogicalSource(BaseModel):
    """One business entity to ingest. `entity` is a snake_case business name
    (e.g. 'orders', 'customers') — NEVER an ADF resource name."""

    entity: str
    format: SourceFormat
    # storage-resident source (format csv/parquet/json):
    container: Optional[str] = None
    folder: Optional[str] = None
    file_name: Optional[str] = None
    # http source (format http_csv):
    http_url: Optional[str] = None  # full URL to the file
    # sql source (format sql_table):
    server: Optional[str] = None
    database: Optional[str] = None
    schema_name: Optional[str] = None
    table_name: Optional[str] = None
    columns: List[LogicalColumn] = Field(default_factory=list)  # optional; grounding overrides

    @field_validator("entity")
    @classmethod
    def _norm_entity(cls, v: str) -> str:
        return _snake(v, field="entity")

    @model_validator(mode="after")
    def _location_complete(self) -> "LogicalSource":
        if self.format == SourceFormat.http_csv and not self.http_url:
            raise ValueError(f"source '{self.entity}': http_csv needs http_url")
        if self.format == SourceFormat.sql_table and not (
            self.server and self.database and self.table_name
        ):
            raise ValueError(
                f"source '{self.entity}': sql_table needs server, database, table_name"
            )
        if self.format in (SourceFormat.csv, SourceFormat.parquet, SourceFormat.json) and not (
            self.file_name or self.folder
        ):
            raise ValueError(f"source '{self.entity}': storage source needs file_name (or folder)")
        return self


class CleaningOp(BaseModel):
    """One column operation. `op` MUST be in the closed vocabulary."""

    op: str  # any key of _OP_FN, or identity
    column: str  # input column
    args: List[str] = Field(default_factory=list)  # literals (formats etc.)
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


_FILTER_OPS = {
    "notnull", "null", "eq", "ne", "gt", "ge", "lt", "le",
    "isnull", "isnotnull", "notempty", "exists", "missing",
}


class FilterRule(BaseModel):
    op: str  # not_null | null | eq | ne | gt | ge | lt | le
    column: str
    value: Optional[str] = None

    @field_validator("op")
    @classmethod
    def _known(cls, v: str) -> str:
        if _norm_op(v) not in _FILTER_OPS:
            raise ValueError(f"unknown filter op '{v}'")
        return v


class EntityTransform(BaseModel):
    """Silver-layer cleaning for one entity. Absent entity = copy-only (no silver flow)."""

    entity: str
    casts: List[LogicalColumn] = Field(default_factory=list)  # target types
    cleaning: List[CleaningOp] = Field(default_factory=list)  # trim/upper/replace...
    filters: List[FilterRule] = Field(default_factory=list)  # AND-ed
    dedup_keys: List[str] = Field(default_factory=list)  # non-empty => dedup


class JoinPlan(BaseModel):
    left_entity: str
    right_entity: str
    left_keys: List[str]
    right_keys: List[str]
    type: str = "inner"  # inner | left | right | full

    @model_validator(mode="after")
    def _keys(self) -> "JoinPlan":
        if not self.left_keys or len(self.left_keys) != len(self.right_keys):
            raise ValueError(
                f"join {self.left_entity}->{self.right_entity}: left_keys and "
                "right_keys must be non-empty and same length"
            )
        return self


_AGG_OPS = {"sum", "avg", "mean", "min", "max", "count", "countdistinct", "first"}


class AggregationPlan(BaseModel):
    name: str  # output column name
    op: str  # sum|avg|min|max|count|count_distinct|first
    column: str

    @field_validator("op")
    @classmethod
    def _known(cls, v: str) -> str:
        if _norm_op(v) not in _AGG_OPS:
            raise ValueError(f"unknown aggregation op '{v}'")
        return v


class SortPlan(BaseModel):
    column: str
    order: str = "desc"  # asc | desc


class OutputPlan(BaseModel):
    """One gold/business output."""

    name: str  # snake_case business name, e.g. 'monthly_sales'
    from_entities: List[str]
    joins: List[JoinPlan] = Field(default_factory=list)
    derived: List[CleaningOp] = Field(default_factory=list)  # computed BEFORE aggregation
    group_by: List[str] = Field(default_factory=list)
    aggregations: List[AggregationPlan] = Field(default_factory=list)
    filters: List[FilterRule] = Field(default_factory=list)  # applied BEFORE aggregation
    sort: List[SortPlan] = Field(default_factory=list)
    top_n: Optional[int] = None
    columns: List[str] = Field(default_factory=list)  # final projection; [] = all
    format: OutputFormat = OutputFormat.delta

    @field_validator("name")
    @classmethod
    def _norm_name(cls, v: str) -> str:
        return _snake(v, field="output name")


class SchedulePlan(BaseModel):
    frequency: str = "Day"  # Day | Hour | Minute | Week | Month
    interval: int = 1
    start_time: Optional[str] = None


class LogicalPlan(BaseModel):
    """Complete business description of the pipeline. NO ADF concepts."""

    project: str = "pipeline"  # short snake_case name for the master pipeline
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
    def _norm_project(cls, v: str) -> str:
        s = re.sub(r"[^a-z0-9_]", "_", (v or "pipeline").strip().lower())
        s = re.sub(r"_+", "_", s).strip("_")
        return s or "pipeline"
