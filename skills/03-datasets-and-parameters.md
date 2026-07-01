---
name: adf-datasets-and-parameters
description: Dataset shapes, concrete file names, and safe parameterization in ADF.
---

# Datasets & Parameters

## Datasets must resolve to a real file

A Copy SOURCE dataset must point at an actual file (concrete `file_name` in its
location) or use a wildcard. A dataset with only a container and no file name fails
with `FormatBasedDatasetMissingFileName`. When the BRD names specific source files
(e.g. `olist_customers_dataset.csv`), put the concrete file name in the dataset's
location and create ONE dataset per distinct source file. Prefer concrete locations
over runtime file-name parameters.

## Sinks

Sink datasets do not require a file name — ADF writes generated names into the
folder. Silver sinks = Parquet; Gold sinks = CSV (or Parquet).

## One dataset per (file, layer) — reuse across boundaries

Do NOT create a separate dataset for the same file's sink and the next layer's
source. The bronze Copy's **sink** dataset IS the silver data flow's **source**
dataset; the silver sink IS the gold source. Reusing them roughly halves the dataset
count and keeps references consistent.

Expected count for N named source files: ~N landing + N bronze + N silver + only the
gold outputs the BRD names. Example: 5 files + 1 gold output (`monthly_sales`) ≈ 16
datasets. If you are emitting 30–40+, you are either inventing outputs the BRD never
asked for (extra gold aggregates, archive, logs) or duplicating source/sink datasets.

## Build only what the BRD asks for

Generate exactly the layers and outputs named in the BRD. Do NOT add archive/backup
datasets, logging/audit tables, or extra gold aggregates that the BRD does not
request. One requested gold dataset means one gold dataset and one gold data flow.

## Parameterization — keep it minimal and always defaulted

- Only parameterize when the BRD truly needs per-run paths (e.g. an execution date).
- EVERY parameter (pipeline, dataset) MUST have a `defaultValue`, or a run fails with
  "No value provided for Parameter ...".
- Keep parameter NAMES consistent across layers. If a dataset uses `execution_date`,
  the pipeline should expose `execution_date` too — mismatched names (e.g.
  `ingestion_date` on a dataset but `execution_date` on the pipeline) break binding.

## Master → child → dataset threading

The master passes its parameters down to children that declare the same name; a Copy
binds a dataset parameter only when the pipeline exposes that same parameter.
