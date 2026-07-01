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

from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_validator
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


class TransformKind(str, Enum):
    select = "select"
    cast = "cast"
    derived = "derived"
    filter = "filter"
    aggregate = "aggregate"
    sort = "sort"
    window = "window"


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


Source = Annotated[Union[HttpSource, BlobSource, RestSource], Field(discriminator="kind")]


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
    type: str  # HttpServer | AzureBlobFS | RestService
    auth: AuthKind
    url: Optional[str] = None          # HttpServer / RestService
    account_url: Optional[str] = None  # AzureBlobFS


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


class Transform(BaseModel):
    """A single Mapping-Data-Flow transformation, producing a named stream."""

    kind: TransformKind
    name: str  # output stream name (e.g. 'CastTypes')
    columns: List[DerivedColumn] = Field(default_factory=list)  # cast/derived/aggregate
    condition: Optional[str] = None  # filter / window
    group_by: List[str] = Field(default_factory=list)  # aggregate
    order_by: List[SortKey] = Field(default_factory=list)  # sort


class DataFlowEndpoint(BaseModel):
    stream_name: str
    dataset: str


class DataFlow(BaseModel):
    name: str
    layer: MedallionLayer  # silver | gold (bronze is a Copy Activity, not a data flow)
    source: DataFlowEndpoint
    sink: DataFlowEndpoint
    source_columns: List[Column] = Field(default_factory=list)
    transforms: List[Transform] = Field(default_factory=list)
    compute_cores: int = 8  # smallest General Purpose tier


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
    clarifications: List[str] = Field(default_factory=list)

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

        for pl in self.pipelines:
            act_names = {a.name for a in pl.activities}
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
                for dep in act.depends_on:
                    if dep not in act_names:
                        errors.append(
                            f"pipeline '{pl.name}' activity '{act.name}' depends on unknown "
                            f"activity '{dep}'"
                        )

        for tr in self.triggers:
            if tr.pipeline not in pl_names:
                errors.append(f"trigger '{tr.name}' references unknown pipeline '{tr.pipeline}'")

        return errors

    # Naming and cross-reference integrity are enforced by pre-flight (which
    # blocks approval), not as a hard parse-time failure — a single off-by-one
    # name from the LLM should surface as a fixable pre-flight finding, not make
    # the whole parse fail and burn retries.


def validate_naming(spec: PipelineSpec) -> List[str]:
    """Module-level helper mirroring ``PipelineSpec.naming_violations``."""
    return spec.naming_violations()
