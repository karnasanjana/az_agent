---
name: adf-storage-and-linked-services
description: Azure storage choices (Blob vs ADLS Gen2) and linked-service rules for ADF.
---

# Storage & Linked Services

## Blob vs ADLS Gen2 (critical)

- **ADLS Gen2** = a storage account with **Hierarchical Namespace (HNS) ON**. It
  exposes the `.dfs.core.windows.net` endpoint and uses `AzureBlobFS`.
- **Plain Blob** = HNS **OFF**. It uses the `.blob.core.windows.net` endpoint and
  `AzureBlobStorage`.
- These are NOT interchangeable: a non-HNS account will FAIL on the `.dfs` endpoint.
  Match the endpoint to the account. If unsure, plain Blob works for medallion
  copy + data flows.

## Linked services — Managed Identity only

NEVER emit account keys, SAS tokens, or connection strings. Use Managed Identity.

- HTTP source: `HttpServer`, `authenticationType: Anonymous`.
- Storage: one linked service per account. The deterministic builder decides the
  concrete type (`AzureBlobStorage` vs `AzureBlobFS`) from the configured storage
  mode — you just declare a storage linked service (`ls_...`) with the account URL.

## RBAC the pipeline needs at run time

- The **ADF managed identity** needs **Storage Blob Data Contributor** on the
  storage account (it runs the Copy/Data Flow reads & writes).
- The deploying user needs Data Factory Contributor on the factory.
