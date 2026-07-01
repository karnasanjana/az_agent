---
name: adf-activities-and-orchestration
description: Supported ADF activity types and how to chain them safely.
---

# Activities & Orchestration

## Supported activity types ONLY

This agent builds exactly three activity types:

- **Copy** — Bronze landing (source dataset → sink dataset).
- **ExecuteDataFlow** — runs a Silver/Gold Mapping Data Flow.
- **ExecutePipeline** — master invoking a child pipeline.

Do NOT emit `GetMetadata`, `IfCondition`, `Validation`, `Delete`, `Lookup`,
`ForEach`, `Switch`, `Until`, or `Wait`. They cannot be built and are dropped.

## Modelling BRD asks that aren't real activities

- "Validate file exists / handle missing or empty files" → just do the Copy; ADF
  surfaces those errors at run time. Do not add a validation activity.
- "Archive landing after gold" → a Copy to the archive container (no Delete).
- "Logging table / capture run metrics" → out of scope for pipeline activities;
  this is Azure Monitor Diagnostic Settings, configured outside the pipeline. Omit it.

## Dependencies

Chain with `dependsOn` + the **Succeeded** condition so a failed upstream stage stops
downstream work. Never reference an activity that doesn't exist in the same pipeline.

## Compute

Use the smallest General Purpose Data Flow compute (8 cores) to control cost.
