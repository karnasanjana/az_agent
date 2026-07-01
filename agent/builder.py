"""Deterministic builder: PipelineSpec -> ADF ARM JSON + Data Flow script DSL.

No LLM, no cloud. Given a validated ``PipelineSpec`` this produces the exact
artifact JSON the Deployer feeds to ``create_or_update``, plus the Mapping Data
Flow script DSL embedded in each Silver/Gold data flow.

Layer rules (enforced here):
  * BRONZE  = a Copy Activity only (source -> bronze), byte-for-byte, NO script.
  * SILVER  = MappingDataFlow with a script (cast/null/filter/dedup/audit -> Parquet).
  * GOLD    = MappingDataFlow with a script (aggregate/derive/sort).
  * pl_master_pipeline chains them with dependsOn:[Succeeded].
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from models.spec import (
    DataFlow,
    Dataset,
    DatasetKind,
    LinkedService,
    PipelineDef,
    PipelineSpec,
    Transform,
    TransformKind,
    Trigger,
    TriggerKind,
)

# --------------------------------------------------------------------------- #
# Linked services
# --------------------------------------------------------------------------- #


def _blob_mode() -> bool:
    """True when targeting plain Azure Blob (no HNS) instead of ADLS Gen2."""
    from config import storage_kind

    return storage_kind() == "blob"


def _to_blob_endpoint(account_url: "str | None") -> "str | None":
    """Rewrite a .dfs URL the LLM produced to the .blob endpoint for blob mode."""
    if not account_url:
        return account_url
    return account_url.replace(".dfs.core.windows.net", ".blob.core.windows.net")


def _storage_endpoint(spec_account_url: "str | None") -> "str | None":
    """The storage endpoint the linked service should target.

    The deploy target is the storage account configured in the environment
    (ADLS_ACCOUNT_NAME), so prefer that over whatever account name the BRD/LLM
    happened to mention — otherwise the deployed pipeline would point at a
    non-existent account. Falls back to the spec's URL when no env is set."""
    account = os.environ.get("ADLS_ACCOUNT_NAME")
    if account:
        from config import blob_endpoint, dfs_endpoint

        return blob_endpoint(account) if _blob_mode() else dfs_endpoint(account)
    return _to_blob_endpoint(spec_account_url) if _blob_mode() else spec_account_url


# Every Azure storage linked-service label the LLM might emit. They all collapse to
# ONE deploy target whose concrete type is decided by STORAGE_KIND, not the label.
_AZURE_STORAGE_TYPES = {
    "AzureBlobFS",
    "AzureBlobStorage",
    "AzureDataLakeStorageGen2",
    "AzureDataLakeStore",
    "AzureStorage",
}


def _canonical_storage_ls(spec: PipelineSpec) -> LinkedService:
    """The single storage linked service every storage-backed dataset must share.

    The LLM often emits several storage linked services with inconsistent names
    (ls_adls, ls_blob_<acct>, ...) and points different datasets at different ones —
    some at a name that never gets created ("invalid reference ..."), some at an
    AzureBlobFS (.dfs) endpoint that a non-HNS Blob account rejects with the
    SoftDelete/BlobStorageEvents 409. Collapsing to ONE storage linked service,
    built per STORAGE_KIND, removes both failure modes. Prefer the first storage LS
    the spec declared (keeps its name stable across reruns); synthesize one only when
    the spec declared none but still has storage datasets."""
    from models.spec import AuthKind

    storage = [ls for ls in spec.linked_services if ls.type in _AZURE_STORAGE_TYPES]
    if storage:
        return storage[0]
    ls_type = "AzureBlobStorage" if _blob_mode() else "AzureBlobFS"
    return LinkedService(name="ls_storage", type=ls_type, auth=AuthKind.managed_identity)


def build_linked_service(ls: LinkedService) -> Dict[str, Any]:
    if ls.type == "HttpServer":
        return {
            "type": "HttpServer",
            "typeProperties": {
                "url": ls.url,
                "enableServerCertificateValidation": True,
                "authenticationType": "Anonymous",
            },
        }
    if ls.type == "RestService":
        return {
            "type": "RestService",
            "typeProperties": {
                "url": ls.url,
                "enableServerCertificateValidation": True,
                "authenticationType": "Anonymous",
            },
        }
    if ls.type in {
        "AzureBlobFS",
        "AzureBlobStorage",
        "AzureDataLakeStorageGen2",
        "AzureDataLakeStore",
        "AzureStorage",
    }:
        # Any Azure storage linked service the LLM names maps to the SAME deploy
        # target; the concrete type (AzureBlobStorage vs AzureBlobFS) is decided by
        # STORAGE_KIND, not the label.
        # Managed Identity: no key / SAS / connection string. The endpoint targets
        # the configured deploy account, not whatever the BRD named.
        endpoint = _storage_endpoint(ls.account_url)
        if _blob_mode():
            # Plain Blob storage (no HNS): AzureBlobStorage + blob serviceEndpoint.
            return {
                "type": "AzureBlobStorage",
                "typeProperties": {
                    "serviceEndpoint": endpoint,
                    "accountKind": "StorageV2",
                },
            }
        return {
            "type": "AzureBlobFS",
            "typeProperties": {"url": endpoint},
        }
    raise ValueError(f"Unsupported linked service type: {ls.type}")


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #

import datetime as _dt

# Build-time date used as a safe default for date-like parameters, so a run never
# fails with "No value provided for Parameter ..." when the master forwards nothing.
_BUILD_DATE = _dt.date.today().strftime("%Y-%m-%d")


def _param_default(name: str) -> str:
    return _BUILD_DATE if "date" in name.lower() else ""


def _param_defs(names: List[str]) -> Dict[str, Any]:
    """Parameter definitions with a defaultValue for every parameter. Defaults make
    pipelines/datasets runnable even when the LLM names parameters inconsistently
    across layers or the master doesn't thread a value down."""
    return {p: {"type": "String", "defaultValue": _param_default(p)} for p in names}


# --------------------------------------------------------------------------- #
# Datasets
# --------------------------------------------------------------------------- #


def _dataset_parameters(ds: Dataset) -> Dict[str, Any]:
    return _param_defs(list(ds.parameters))


def _adls_location(ds: Dataset) -> Dict[str, Any]:
    loc = ds.location
    if _blob_mode():
        # Plain Blob: AzureBlobStorageLocation uses 'container' (not 'fileSystem').
        store: Dict[str, Any] = {
            "type": "AzureBlobStorageLocation",
            "container": loc.container if loc else None,
        }
    else:
        store = {"type": "AzureBlobFSLocation", "fileSystem": loc.container if loc else None}
    if loc and loc.folder:
        store["folderPath"] = loc.folder
    if loc and loc.file_name:
        store["fileName"] = loc.file_name
    return store


def build_dataset(ds: Dataset) -> Dict[str, Any]:
    ls_ref = {"referenceName": ds.linked_service, "type": "LinkedServiceReference"}
    schema = [{"name": c.name, "type": c.type} for c in ds.columns]

    # REST endpoint
    if ds.kind == DatasetKind.rest_resource:
        return {
            "type": "RestResource",
            "linkedServiceName": ls_ref,
            "parameters": _dataset_parameters(ds),
            "typeProperties": {"relativeUrl": ds.relative_url or ""},
            "schema": schema,
        }

    # JSON (over HTTP or in ADLS)
    if ds.kind == DatasetKind.json:
        location = (
            {"type": "HttpServerLocation", "relativeUrl": ds.relative_url}
            if ds.relative_url is not None
            else _adls_location(ds)
        )
        return {
            "type": "Json",
            "linkedServiceName": ls_ref,
            "parameters": _dataset_parameters(ds),
            "typeProperties": {"location": location},
            "schema": schema,
        }

    # Parquet (ADLS only)
    if ds.kind == DatasetKind.parquet:
        return {
            "type": "Parquet",
            "linkedServiceName": ls_ref,
            "parameters": _dataset_parameters(ds),
            "typeProperties": {"location": _adls_location(ds), "compressionCodec": "snappy"},
            "schema": schema,
        }

    # DelimitedText (CSV) — over HTTP (relative_url) or in ADLS (location)
    location = (
        {"type": "HttpServerLocation", "relativeUrl": ds.relative_url}
        if ds.relative_url is not None
        else _adls_location(ds)
    )
    return {
        "type": "DelimitedText",
        "linkedServiceName": ls_ref,
        "parameters": _dataset_parameters(ds),
        "typeProperties": {
            "location": location,
            "columnDelimiter": ",",
            "firstRowAsHeader": ds.first_row_as_header,
            "quoteChar": '"',
            "escapeChar": "\\",
        },
        "schema": schema,
    }


# Copy source/sink type per dataset kind.
_COPY_SOURCE_TYPE = {
    DatasetKind.delimited_text: "DelimitedTextSource",
    DatasetKind.parquet: "ParquetSource",
    DatasetKind.json: "JsonSource",
    DatasetKind.rest_resource: "RestSource",
}
_COPY_SINK_TYPE = {
    DatasetKind.delimited_text: "DelimitedTextSink",
    DatasetKind.parquet: "ParquetSink",
    DatasetKind.json: "JsonSink",
    DatasetKind.rest_resource: "RestSink",
}


# --------------------------------------------------------------------------- #
# Data flow script DSL (Silver / Gold only)
# --------------------------------------------------------------------------- #


def _transform_dsl(input_stream: str, t: Transform) -> str:
    """Render one transformation line: '<in> <op>(...) ~> <name>'."""
    if t.kind in (TransformKind.cast, TransformKind.derived):
        assigns = ",\n        ".join(f"{c.name} = {c.expression}" for c in t.columns)
        return f"{input_stream} derive({assigns}) ~> {t.name}"

    if t.kind == TransformKind.filter:
        return f"{input_stream} filter({t.condition}) ~> {t.name}"

    if t.kind == TransformKind.aggregate:
        group = ", ".join(t.group_by)
        aggs = ",\n        ".join(f"{c.name} = {c.expression}" for c in t.columns)
        return f"{input_stream} aggregate(groupBy({group}),\n        {aggs}) ~> {t.name}"

    if t.kind == TransformKind.sort:
        keys = ", ".join(f"{k.order}({k.column})" for k in t.order_by)
        return f"{input_stream} sort({keys}) ~> {t.name}"

    if t.kind == TransformKind.select:
        cols = ", ".join(f"{c.name} = {c.expression}" for c in t.columns)
        return f"{input_stream} select(mapColumn({cols})) ~> {t.name}"

    if t.kind == TransformKind.window:
        return f"{input_stream} window({t.condition or ''}) ~> {t.name}"

    raise ValueError(f"Unsupported transform kind: {t.kind}")


def build_dataflow_script(df: DataFlow) -> str:
    """Produce the full ADF Mapping Data Flow script:

        source(...) ~> Src
        Src derive/filter/aggregate/sort ... ~> ...
        Last sink(...) ~> Sink
    """
    schema = ",\n    ".join(f"{c.name} as {c.type}" for c in df.source_columns)
    body = f"\n    {schema}\n  " if schema else ""
    lines: List[str] = [
        f"source(output({body}),",
        "  allowSchemaDrift: true,",
        "  validateSchema: false,",
        f"  ignoreNoFilesFound: false) ~> {df.source.stream_name}",
    ]

    current = df.source.stream_name
    for t in df.transforms:
        lines.append(_transform_dsl(current, t))
        current = t.name

    lines.append(
        f"{current} sink(allowSchemaDrift: true,\n"
        "  validateSchema: false,\n"
        "  skipDuplicateMapInputs: true,\n"
        "  skipDuplicateMapOutputs: true) ~> "
        f"{df.sink.stream_name}"
    )
    return "\n".join(lines)


def build_dataflow(df: DataFlow) -> Dict[str, Any]:
    return {
        "type": "MappingDataFlow",
        "typeProperties": {
            "sources": [
                {
                    "name": df.source.stream_name,
                    "dataset": {"referenceName": df.source.dataset, "type": "DatasetReference"},
                }
            ],
            "sinks": [
                {
                    "name": df.sink.stream_name,
                    "dataset": {"referenceName": df.sink.dataset, "type": "DatasetReference"},
                }
            ],
            "transformations": [{"name": t.name} for t in df.transforms],
            "scriptLines": build_dataflow_script(df).split("\n"),
        },
    }


# --------------------------------------------------------------------------- #
# Pipelines
# --------------------------------------------------------------------------- #


def _depends_on(names: List[str]) -> List[Dict[str, Any]]:
    return [{"activity": n, "dependencyConditions": ["Succeeded"]} for n in names]


def _source_read_settings(ds: Dataset) -> "Dict[str, Any] | None":
    """Wildcard read settings for a Copy SOURCE whose dataset has no concrete file
    name — without this ADF rejects the Copy with FormatBasedDatasetMissingFileName.
    Returns None when the dataset already resolves to a file (concrete name or an
    HTTP relativeUrl), or for REST sources. Set only on the source side, so sinks
    are unaffected."""
    if ds.relative_url is not None:  # HTTP file: relativeUrl already names it
        return None
    if ds.kind == DatasetKind.rest_resource:
        return None
    loc = ds.location
    if loc and loc.file_name:  # concrete file name present
        return None
    settings: Dict[str, Any] = {
        "type": "AzureBlobStorageReadSettings" if _blob_mode() else "AzureBlobFSReadSettings",
        "recursive": True,
        "wildcardFileName": "*",
    }
    if loc and loc.folder:
        settings["wildcardFolderPath"] = loc.folder
    return settings


def _build_context(spec: PipelineSpec) -> Dict[str, Any]:
    return {
        "dataset_kinds": {ds.name: ds.kind for ds in spec.datasets},
        "dataset_params": {ds.name: list(ds.parameters) for ds in spec.datasets},
        "pipeline_params": {pl.name: list(pl.parameters) for pl in spec.pipelines},
        "source_read_settings": {ds.name: _source_read_settings(ds) for ds in spec.datasets},
    }


def _copy_input(dataset_name: str, ctx: Dict[str, Any], pipeline_params: List[str]) -> Dict[str, Any]:
    """Build the Copy input ref. Only bind dataset params that actually exist on the
    pipeline — binding to a missing pipeline param is what produced ADF's "No value
    provided for Parameter" failure. Unbound dataset params fall back to their own
    defaultValue."""
    ref: Dict[str, Any] = {"referenceName": dataset_name, "type": "DatasetReference"}
    params = ctx["dataset_params"].get(dataset_name, [])
    bound = {p: f"@pipeline().parameters.{p}" for p in params if p in pipeline_params}
    if bound:
        ref["parameters"] = bound
    return ref


_SUPPORTED_ACTIVITIES = {"Copy", "ExecuteDataFlow", "ExecutePipeline"}


def build_pipeline(pl: PipelineDef, ctx: "Dict[str, Any] | None" = None) -> Dict[str, Any]:
    ctx = ctx or {"dataset_kinds": {}, "dataset_params": {}, "pipeline_params": {}}
    pipeline_params = list(pl.parameters)
    activities: List[Dict[str, Any]] = []

    # This ADF model supports Copy / ExecuteDataFlow / ExecutePipeline. The LLM may
    # add GetMetadata / IfCondition / Validation / Delete activities for the BRD's
    # error-handling asks — skip them rather than crash, and drop dangling dependsOn
    # references to the skipped activities so the pipeline stays valid.
    kept = {a.name for a in pl.activities if a.type in _SUPPORTED_ACTIVITIES}

    for act in pl.activities:
        if act.type not in _SUPPORTED_ACTIVITIES:
            continue
        common: Dict[str, Any] = {
            "name": act.name,
            "dependsOn": _depends_on([d for d in act.depends_on if d in kept]),
            "policy": {"timeout": "0.12:00:00", "retry": 1, "retryIntervalInSeconds": 30},
            "userProperties": [],
        }

        if act.type == "Copy":
            src_kind = ctx["dataset_kinds"].get(act.source_dataset, DatasetKind.delimited_text)
            sink_kind = ctx["dataset_kinds"].get(act.sink_dataset, DatasetKind.delimited_text)
            source_tp: Dict[str, Any] = {"type": _COPY_SOURCE_TYPE[src_kind]}
            read_settings = ctx.get("source_read_settings", {}).get(act.source_dataset)
            if read_settings:  # source dataset has no concrete file -> wildcard read
                source_tp["storeSettings"] = read_settings
            common.update(
                {
                    "type": "Copy",
                    # Bronze: byte-for-byte raw landing, idempotent overwrite.
                    "typeProperties": {
                        "source": source_tp,
                        "sink": {"type": _COPY_SINK_TYPE[sink_kind]},
                        "enableStaging": False,
                        "validateDataConsistency": False,
                    },
                    "inputs": [_copy_input(act.source_dataset, ctx, pipeline_params)],
                    "outputs": [
                        {"referenceName": act.sink_dataset, "type": "DatasetReference"}
                    ],
                }
            )
        elif act.type == "ExecuteDataFlow":
            common.update(
                {
                    "type": "ExecuteDataFlow",
                    "typeProperties": {
                        "dataflow": {"referenceName": act.data_flow, "type": "DataFlowReference"},
                        # smallest General Purpose tier (cost)
                        "compute": {"computeType": "General", "coreCount": 8},
                        "traceLevel": "Fine",
                    },
                }
            )
        elif act.type == "ExecutePipeline":
            common.update(
                {
                    "type": "ExecutePipeline",
                    "typeProperties": {
                        "pipeline": {"referenceName": act.invoked_pipeline, "type": "PipelineReference"},
                        "waitOnCompletion": True,
                    },
                }
            )
            # Forward every shared parameter down to the child pipeline (the master
            # passes its params to the children that declare the same name).
            child_params = ctx["pipeline_params"].get(act.invoked_pipeline, [])
            shared = [p for p in child_params if p in pipeline_params]
            if shared:
                common["typeProperties"]["parameters"] = {
                    p: f"@pipeline().parameters.{p}" for p in shared
                }

        activities.append(common)

    props: Dict[str, Any] = {"activities": activities}
    if pl.parameters:
        props["parameters"] = _param_defs(list(pl.parameters))
    return props


# --------------------------------------------------------------------------- #
# Triggers
# --------------------------------------------------------------------------- #


def build_trigger(tr: Trigger) -> Dict[str, Any]:
    if tr.kind == TriggerKind.schedule:
        return {
            "type": "ScheduleTrigger",
            "typeProperties": {
                "recurrence": {
                    "frequency": tr.frequency or "Day",
                    "interval": tr.interval or 1,
                    "startTime": tr.start_time or "2024-01-01T00:00:00Z",
                    "timeZone": "UTC",
                }
            },
            "pipelines": [
                {
                    "pipelineReference": {"referenceName": tr.pipeline, "type": "PipelineReference"},
                    "parameters": {},
                }
            ],
        }
    # Manual triggers are not ARM resources — they run via create_run on demand.
    return {
        "type": "ManualTrigger",
        "pipelines": [
            {"pipelineReference": {"referenceName": tr.pipeline, "type": "PipelineReference"}}
        ],
    }


# --------------------------------------------------------------------------- #
# Whole-spec assembly + persistence
# --------------------------------------------------------------------------- #


def build_all(spec: PipelineSpec) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Return {category: {name: properties_json}} for the whole spec.

    All Azure storage linked services are collapsed into one canonical LS and every
    storage-backed dataset is repointed at it — see :func:`_canonical_storage_ls`."""
    ctx = _build_context(spec)

    storage_ls_names = {ls.name for ls in spec.linked_services if ls.type in _AZURE_STORAGE_TYPES}
    canonical = _canonical_storage_ls(spec)
    # A dataset lives in storage when it has a `location` (vs an HTTP relative_url).
    needs_storage = storage_ls_names or any(ds.location is not None for ds in spec.datasets)

    # Linked services: keep every non-storage LS (HttpServer/RestService) as-is, and
    # emit exactly ONE storage LS (the canonical one) when any storage dataset exists.
    linked: Dict[str, Any] = {
        ls.name: build_linked_service(ls)
        for ls in spec.linked_services
        if ls.type not in _AZURE_STORAGE_TYPES
    }
    if needs_storage:
        linked[canonical.name] = build_linked_service(canonical)

    def _dataset(ds: Dataset) -> Dict[str, Any]:
        built = build_dataset(ds)
        # Repoint storage-backed datasets at the one canonical storage LS so no
        # dataset can reference a missing or .dfs/.blob-mismatched linked service.
        if ds.location is not None or ds.linked_service in storage_ls_names:
            built["linkedServiceName"]["referenceName"] = canonical.name
        return built

    return {
        "linkedServices": linked,
        "datasets": {ds.name: _dataset(ds) for ds in spec.datasets},
        "dataflows": {df.name: build_dataflow(df) for df in spec.dataflows},
        "pipelines": {pl.name: build_pipeline(pl, ctx) for pl in spec.pipelines},
        "triggers": {tr.name: build_trigger(tr) for tr in spec.triggers},
    }


# Deploy order: linked services -> datasets -> data flows -> pipelines -> triggers.
DEPLOY_ORDER = ["linkedServices", "datasets", "dataflows", "pipelines", "triggers"]


def artifacts_dir(run_id: str, root: str = "artifacts") -> str:
    return os.path.join(root, run_id)


def write_artifacts(spec: PipelineSpec, run_id: str, root: str = "artifacts") -> str:
    """Write every ADF object as JSON under artifacts/<run_id>/<category>/<name>.json,
    plus readable data-flow scripts under dataflows/<name>.script and the validated
    spec as spec.json. Returns the run directory path."""
    run_dir = artifacts_dir(run_id, root)
    os.makedirs(run_dir, exist_ok=True)

    built = build_all(spec)
    for category, objects in built.items():
        cat_dir = os.path.join(run_dir, category)
        os.makedirs(cat_dir, exist_ok=True)
        for name, props in objects.items():
            with open(os.path.join(cat_dir, f"{name}.json"), "w", encoding="utf-8") as fh:
                json.dump({"name": name, "properties": props}, fh, indent=2)

    for df in spec.dataflows:
        with open(
            os.path.join(run_dir, "dataflows", f"{df.name}.script"), "w", encoding="utf-8"
        ) as fh:
            fh.write(build_dataflow_script(df))

    with open(os.path.join(run_dir, "spec.json"), "w", encoding="utf-8") as fh:
        fh.write(spec.model_dump_json(indent=2))

    return run_dir
