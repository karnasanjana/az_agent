---
name: adf-medallion-structure
description: How to lay out a Bronze/Silver/Gold medallion pipeline in Azure Data Factory.
---

# ADF Medallion Structure

A medallion pipeline has three layers, built with two ADF mechanisms only:

- **Bronze** = a **Copy activity** that lands the raw source byte-for-byte into the
  bronze container. NO transformation, NO data flow, NO script. One Copy per source
  file (or a wildcard read when copying a whole folder).
- **Silver** = a **Mapping Data Flow** (`layer="silver"`) that cleans/standardises:
  cast types, trim, dedup, drop nulls, add audit columns. Writes Parquet to silver.
- **Gold** = a **Mapping Data Flow** (`layer="gold"`) that aggregates into
  business-ready outputs. Writes CSV (or Parquet) to gold.

## Orchestration

- One child pipeline per layer (e.g. `pl_landing_to_bronze`, `pl_bronze_to_silver`,
  `pl_silver_to_gold`).
- One **master pipeline** (`pl_..._master`) whose activities are all
  `ExecutePipeline`, chaining the children Bronze → Silver → Gold with
  `dependsOn` using the **Succeeded** condition, so a failed Bronze halts Silver.
- The master deploys LAST; a child pipeline must exist before the master references it.

## Naming (lowercase prefixes, mandatory)

`ls_` linked services · `ds_` datasets · `df_` data flows · `pl_` pipelines.
A BRD that says "PL_Retail_Master" becomes `pl_retail_master`.
