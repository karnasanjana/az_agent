"""Compiler: LogicalPlan -> PipelineSpec. Deterministic, no LLM, no cloud.

This is where the search-space collapse pays off. The model produced only
business intent (entities, ops, joins, outputs); here CODE assigns every ADF
name, wires the medallion layers, reuses datasets across boundaries, chains the
master pipeline, and renders every expression from structured ops. Nothing is
invented — same LogicalPlan in always yields the same PipelineSpec out.

Because the compiler owns naming/wiring/references, the whole class of
spec.py `_repair_*` validators (layer sinks, linked-service refs, container
names, copy-kind harmonization) has no input to repair: their failure
conditions are unreachable from this path.

Naming formulas are fixed (see IMPLEMENTATION_SPEC.md section 3.1). Stream names
are pre-cleaned to ADF's alphanumeric rule so spec.py `_sanitize_stream_names`
is a no-op on compiler output.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from models.logical import (
    AggregationPlan,
    CleaningOp,
    EntityTransform,
    FilterRule,
    LogicalColumn,
    LogicalPlan,
    LogicalSource,
    OutputPlan,
    SourceFormat,
)
from models.spec import (
    Activity,
    AuthKind,
    Column,
    DataFlow,
    DataFlowEndpoint,
    Dataset,
    DatasetKind,
    DatasetLocation,
    DerivedColumn,
    LinkedService,
    MedallionLayer,
    PipelineDef,
    PipelineSpec,
    Predicate,
    SortKey,
    StorageAccount,
    Transform,
    TransformKind,
    Trigger,
    TriggerKind,
    _norm_op,
)

STORAGE_LS = "ls_storage"


# --------------------------------------------------------------------------- #
# Name helpers
# --------------------------------------------------------------------------- #


def _camel(entity: str) -> str:
    """orders -> Orders, order_items -> OrderItems (alnum, starts with a letter)."""
    parts = re.split(r"[^A-Za-z0-9]+", entity)
    camel = "".join(p[:1].upper() + p[1:] for p in parts if p)
    if camel and not camel[0].isalpha():
        camel = "s" + camel
    return camel or "Stream"


def _host_token(url: str) -> str:
    host = urlparse(url).netloc or url
    return re.sub(r"[^a-z0-9]", "_", host.lower()).strip("_") or "host"


def _server_token(server: str) -> str:
    label = (server or "").split(".")[0]
    return re.sub(r"[^a-z0-9]", "_", label.lower()).strip("_") or "sql"


# LogicalColumn.type -> ADF data-flow cast function.
def _cast_expression(col: LogicalColumn) -> str:
    t = (col.type or "string").strip().lower()
    m = re.fullmatch(r"decimal\((\d+)\s*,\s*(\d+)\)", t)
    if m:
        return f"toDecimal({col.name}, {m.group(1)}, {m.group(2)})"
    fn = {
        "integer": "toInteger",
        "int": "toInteger",
        "long": "toLong",
        "bigint": "toLong",
        "double": "toDouble",
        "float": "toDouble",
        "decimal": "toDecimal",
        "boolean": "toBoolean",
        "bool": "toBoolean",
        "date": "toDate",
        "timestamp": "toTimestamp",
        "datetime": "toTimestamp",
        "string": "toString",
    }.get(t, "toString")
    return f"{fn}({col.name})"


_DS_KIND_BY_FORMAT = {
    SourceFormat.csv: DatasetKind.delimited_text,
    SourceFormat.parquet: DatasetKind.parquet,
    SourceFormat.json: DatasetKind.json,
    SourceFormat.http_csv: DatasetKind.delimited_text,
    SourceFormat.sql_table: DatasetKind.azure_sql_table,
}


# --------------------------------------------------------------------------- #
# Compiler
# --------------------------------------------------------------------------- #


def compile_plan(plan: LogicalPlan) -> PipelineSpec:
    project = plan.project
    src_by_entity: Dict[str, LogicalSource] = {s.entity: s for s in plan.sources}
    xf_by_entity: Dict[str, EntityTransform] = {t.entity: t for t in plan.transforms}

    linked_services: List[LinkedService] = []
    datasets: List[Dataset] = []
    dataflows: List[DataFlow] = []
    pipelines: List[PipelineDef] = []
    triggers: List[Trigger] = []
    assumptions: List[str] = list(plan.assumptions)

    # ------------------------------------------------------------------ #
    # Linked services
    # ------------------------------------------------------------------ #
    storage_type = "AzureBlobFS"
    linked_services.append(
        LinkedService(name=STORAGE_LS, type=storage_type, auth=AuthKind.managed_identity)
    )

    http_ls: Dict[str, str] = {}  # host token -> ls name
    sql_ls: Dict[str, str] = {}  # server token -> ls name
    for s in plan.sources:
        if s.format == SourceFormat.http_csv and s.http_url:
            tok = _host_token(s.http_url)
            if tok not in http_ls:
                name = f"ls_http_{tok}"
                http_ls[tok] = name
                parsed = urlparse(s.http_url)
                base = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else s.http_url
                linked_services.append(
                    LinkedService(name=name, type="HttpServer", auth=AuthKind.anonymous, url=base)
                )
        elif s.format == SourceFormat.sql_table and s.server:
            tok = _server_token(s.server)
            if tok not in sql_ls:
                name = f"ls_sql_{tok}"
                sql_ls[tok] = name
                linked_services.append(
                    LinkedService(
                        name=name,
                        type="AzureSqlDatabase",
                        auth=AuthKind.managed_identity,
                        server=s.server,
                        database=s.database,
                    )
                )

    # ------------------------------------------------------------------ #
    # Ingest (landing -> bronze Copy) per source
    # ------------------------------------------------------------------ #
    used_landing_container = False
    bronze_ds: Dict[str, str] = {}  # entity -> bronze dataset name

    for s in plan.sources:
        ent = s.entity
        kind = _DS_KIND_BY_FORMAT[s.format]
        cols = [Column(name=c.name, type=c.type) for c in s.columns]

        landing_name = f"ds_landing_{ent}"
        bronze_name = f"ds_bronze_{ent}"
        bronze_ds[ent] = bronze_name

        if s.format in (SourceFormat.csv, SourceFormat.parquet, SourceFormat.json):
            container = s.container or "landing"
            if container == "landing":
                used_landing_container = True
            landing = Dataset(
                name=landing_name,
                kind=kind,
                linked_service=STORAGE_LS,
                location=DatasetLocation(
                    container=container, folder=s.folder, file_name=s.file_name
                ),
                columns=cols,
            )
            bronze_file = s.file_name or f"{ent}.csv"
        elif s.format == SourceFormat.http_csv:
            path = urlparse(s.http_url).path.lstrip("/")
            landing = Dataset(
                name=landing_name,
                kind=DatasetKind.delimited_text,
                linked_service=http_ls[_host_token(s.http_url)],
                relative_url=path,
                columns=cols,
            )
            bronze_file = f"{ent}.csv"
        else:  # sql_table
            landing = Dataset(
                name=landing_name,
                kind=DatasetKind.azure_sql_table,
                linked_service=sql_ls[_server_token(s.server)],
                schema_name=s.schema_name,
                table_name=s.table_name,
                columns=cols,
            )
            bronze_file = f"{ent}.csv"

        bronze_kind = (
            kind if s.format in (SourceFormat.csv, SourceFormat.parquet, SourceFormat.json)
            else DatasetKind.delimited_text
        )
        bronze = Dataset(
            name=bronze_name,
            kind=bronze_kind,
            linked_service=STORAGE_LS,
            location=DatasetLocation(container="bronze", folder=ent, file_name=bronze_file),
            columns=cols,
        )
        datasets.extend([landing, bronze])

        pipelines.append(
            PipelineDef(
                name=f"pl_ingest_{ent}",
                activities=[
                    Activity(
                        name=f"copy_{ent}",
                        type="Copy",
                        layer=MedallionLayer.bronze,
                        source_dataset=landing_name,
                        sink_dataset=bronze_name,
                    )
                ],
            )
        )

    # ------------------------------------------------------------------ #
    # Silver flows per transform
    # ------------------------------------------------------------------ #
    silver_ds: Dict[str, str] = {}  # entity -> silver dataset name

    for xf in plan.transforms:
        ent = xf.entity
        if ent not in src_by_entity:
            assumptions.append(f"transform for '{ent}' skipped: no matching source")
            continue
        camel = _camel(ent)
        silver_name = f"ds_silver_{ent}"
        silver_ds[ent] = silver_name
        datasets.append(
            Dataset(
                name=silver_name,
                kind=DatasetKind.delta,
                linked_service=STORAGE_LS,
                location=DatasetLocation(container="silver", folder=ent),
            )
        )

        transforms = _silver_transforms(xf)
        src_cols = [Column(name=c.name, type=c.type) for c in src_by_entity[ent].columns]
        dataflows.append(
            DataFlow(
                name=f"df_silver_{ent}",
                layer=MedallionLayer.silver,
                source=DataFlowEndpoint(stream_name=f"src{camel}", dataset=bronze_ds[ent]),
                sink=DataFlowEndpoint(stream_name=f"sink{camel}", dataset=silver_name),
                source_columns=src_cols,
                transforms=transforms,
            )
        )
        pipelines.append(
            PipelineDef(
                name=f"pl_silver_{ent}",
                activities=[
                    Activity(
                        name=f"flow_silver_{ent}",
                        type="ExecuteDataFlow",
                        layer=MedallionLayer.silver,
                        data_flow=f"df_silver_{ent}",
                    )
                ],
            )
        )

    # Pass-through silver for entities a gold output reads while a silver layer
    # exists elsewhere. Without this, gold reads bronze for those entities while
    # a silver layer exists — the "gold skips silver" medallion break preflight
    # blocks (medallion_wiring). A transform-less silver flow copies bronze ->
    # silver Delta, keeping every gold source on the silver layer.
    if silver_ds:
        gold_entities = {
            e for out in plan.outputs for e in out.from_entities if e in src_by_entity
        }
        for ent in sorted(gold_entities - set(silver_ds)):
            camel = _camel(ent)
            silver_name = f"ds_silver_{ent}"
            silver_ds[ent] = silver_name
            datasets.append(
                Dataset(
                    name=silver_name,
                    kind=DatasetKind.delta,
                    linked_service=STORAGE_LS,
                    location=DatasetLocation(container="silver", folder=ent),
                )
            )
            src_cols = [Column(name=c.name, type=c.type) for c in src_by_entity[ent].columns]
            dataflows.append(
                DataFlow(
                    name=f"df_silver_{ent}",
                    layer=MedallionLayer.silver,
                    source=DataFlowEndpoint(stream_name=f"src{camel}", dataset=bronze_ds[ent]),
                    sink=DataFlowEndpoint(stream_name=f"sink{camel}", dataset=silver_name),
                    source_columns=src_cols,
                    transforms=[],
                )
            )
            pipelines.append(
                PipelineDef(
                    name=f"pl_silver_{ent}",
                    activities=[
                        Activity(
                            name=f"flow_silver_{ent}",
                            type="ExecuteDataFlow",
                            layer=MedallionLayer.silver,
                            data_flow=f"df_silver_{ent}",
                        )
                    ],
                )
            )
            assumptions.append(
                f"'{ent}' feeds a gold output but had no cleaning — added a "
                f"pass-through silver flow so gold reads the silver layer"
            )

    def best_dataset(entity: str) -> str:
        """Silver dataset if a silver flow exists for the entity, else bronze."""
        return silver_ds.get(entity) or bronze_ds[entity]

    # ------------------------------------------------------------------ #
    # Gold flows per output
    # ------------------------------------------------------------------ #
    for out in plan.outputs:
        entities = [e for e in out.from_entities if e in src_by_entity]
        if not entities:
            assumptions.append(f"output '{out.name}' skipped: no known source entities")
            continue
        gold_name = f"ds_gold_{out.name}"
        gold_kind = {
            "delta": DatasetKind.delta,
            "csv": DatasetKind.delimited_text,
            "parquet": DatasetKind.parquet,
        }[out.format.value]
        gold_loc = DatasetLocation(
            container="gold",
            folder=out.name,
            file_name=f"{out.name}.csv" if out.format.value == "csv" else None,
        )
        datasets.append(
            Dataset(name=gold_name, kind=gold_kind, linked_service=STORAGE_LS, location=gold_loc)
        )

        first = entities[0]
        source_ep = DataFlowEndpoint(stream_name=f"src{_camel(first)}", dataset=best_dataset(first))
        additional = [
            DataFlowEndpoint(stream_name=f"src{_camel(e)}", dataset=best_dataset(e))
            for e in entities[1:]
        ]
        transforms = _gold_transforms(out)
        dataflows.append(
            DataFlow(
                name=f"df_gold_{out.name}",
                layer=MedallionLayer.gold,
                source=source_ep,
                sink=DataFlowEndpoint(stream_name=f"sink{_camel(out.name)}", dataset=gold_name),
                additional_sources=additional,
                transforms=transforms,
            )
        )
        pipelines.append(
            PipelineDef(
                name=f"pl_gold_{out.name}",
                activities=[
                    Activity(
                        name=f"flow_gold_{out.name}",
                        type="ExecuteDataFlow",
                        layer=MedallionLayer.gold,
                        data_flow=f"df_gold_{out.name}",
                    )
                ],
            )
        )

    # ------------------------------------------------------------------ #
    # Master pipeline + trigger
    # ------------------------------------------------------------------ #
    master_acts: List[Activity] = []

    def _run_act(child: str, depends: List[str]) -> Activity:
        return Activity(
            name=f"run_{child[len('pl_'):]}",
            type="ExecutePipeline",
            invoked_pipeline=child,
            depends_on=depends,
        )

    for s in plan.sources:
        master_acts.append(_run_act(f"pl_ingest_{s.entity}", []))
    # Every silver entity (explicit transform OR pass-through), in source order,
    # so the master invokes the pass-through silver flows too.
    for s in plan.sources:
        if s.entity in silver_ds:
            master_acts.append(
                _run_act(f"pl_silver_{s.entity}", [f"run_ingest_{s.entity}"])
            )
    for out in plan.outputs:
        entities = [e for e in out.from_entities if e in src_by_entity]
        if not entities:
            continue
        deps = [
            f"run_silver_{e}" if e in silver_ds else f"run_ingest_{e}" for e in entities
        ]
        master_acts.append(_run_act(f"pl_gold_{out.name}", deps))

    master_name = f"pl_master_{project}"
    pipelines.append(PipelineDef(name=master_name, activities=master_acts))

    if plan.schedule:
        triggers.append(
            Trigger(
                name=f"tr_schedule_{project}",
                kind=TriggerKind.schedule,
                pipeline=master_name,
                frequency=plan.schedule.frequency,
                interval=plan.schedule.interval,
                start_time=plan.schedule.start_time,
            )
        )

    # ------------------------------------------------------------------ #
    # Storage + assumptions + capability contract
    # ------------------------------------------------------------------ #
    containers = ["bronze", "silver", "gold"]
    if used_landing_container:
        containers = ["landing"] + containers
    account = os.environ.get("ADLS_ACCOUNT_NAME", "storage")

    for line in plan.unsupported:
        assumptions.append(f"NOT BUILT (unsupported): {line}")

    return PipelineSpec(
        name=project,
        storage=StorageAccount(account_name=account, containers=containers),
        linked_services=linked_services,
        datasets=datasets,
        dataflows=dataflows,
        pipelines=pipelines,
        triggers=triggers,
        assumptions=assumptions,
        clarifications=list(plan.clarifications),
    )


# --------------------------------------------------------------------------- #
# Transform builders
# --------------------------------------------------------------------------- #


def _clean_col(op: CleaningOp) -> DerivedColumn:
    return DerivedColumn(
        name=op.new_column or op.column, op=op.op, column=op.column, args=list(op.args)
    )


def _predicate(f: FilterRule) -> Predicate:
    return Predicate(op=f.op, column=f.column, value=f.value)


def _silver_transforms(xf: EntityTransform) -> List[Transform]:
    transforms: List[Transform] = []
    if xf.casts:
        transforms.append(
            Transform(
                kind=TransformKind.cast,
                name="castTypes",
                columns=[
                    DerivedColumn(name=c.name, expression=_cast_expression(c)) for c in xf.casts
                ],
            )
        )
    if xf.cleaning:
        transforms.append(
            Transform(
                kind=TransformKind.derived,
                name="cleanColumns",
                columns=[_clean_col(op) for op in xf.cleaning],
            )
        )
    if xf.filters:
        transforms.append(
            Transform(
                kind=TransformKind.filter,
                name="filterRows",
                predicates=[_predicate(f) for f in xf.filters],
            )
        )
    if xf.dedup_keys:
        # columns=[] -> builder emits each(match(!in([keys], name)), $$ = first($$)),
        # preserving every non-key column via schema drift (no schema needed here).
        transforms.append(
            Transform(
                kind=TransformKind.aggregate,
                name="dedupRows",
                group_by=list(xf.dedup_keys),
                columns=[],
            )
        )
    return transforms


_JOIN_TYPE = {
    "inner": "inner",
    "left": "left_outer",
    "right": "right_outer",
    "full": "full_outer",
}


def _gold_transforms(out: OutputPlan) -> List[Transform]:
    transforms: List[Transform] = []

    for i, j in enumerate(out.joins):
        left_stream = f"src{_camel(j.left_entity)}"
        right_stream = f"src{_camel(j.right_entity)}"
        cond = " && ".join(
            f"{left_stream}@{lk} == {right_stream}@{rk}"
            for lk, rk in zip(j.left_keys, j.right_keys)
        )
        transforms.append(
            Transform(
                kind=TransformKind.join,
                name=f"join{i + 1}",
                right_stream=right_stream,
                join_type=_JOIN_TYPE.get(j.type, "inner"),
                condition=cond,
            )
        )

    if out.derived:
        transforms.append(
            Transform(
                kind=TransformKind.derived,
                name="deriveColumns",
                columns=[_clean_col(op) for op in out.derived],
            )
        )
    if out.filters:
        transforms.append(
            Transform(
                kind=TransformKind.filter,
                name="filterRows",
                predicates=[_predicate(f) for f in out.filters],
            )
        )
    if out.group_by or out.aggregations:
        group_names = set(out.group_by)
        for a in out.aggregations:
            if a.name in group_names:
                raise ValueError(
                    f"output {out.name}: aggregation '{a.name}' duplicates a group_by column"
                )
        transforms.append(
            Transform(
                kind=TransformKind.aggregate,
                name="aggregateRows",
                group_by=list(out.group_by),
                columns=[
                    DerivedColumn(name=a.name, op=a.op, column=a.column)
                    for a in out.aggregations
                ],
            )
        )
    if out.sort:
        transforms.append(
            Transform(
                kind=TransformKind.sort,
                name="sortRows",
                order_by=[SortKey(column=s.column, order=s.order) for s in out.sort],
            )
        )
    if out.top_n is not None:
        transforms.append(
            Transform(kind=TransformKind.limit, name="limitRows", take=out.top_n)
        )
    if out.columns:
        transforms.append(
            Transform(
                kind=TransformKind.select,
                name="selectFinal",
                columns=[DerivedColumn(name=c) for c in out.columns],
            )
        )
    return transforms
