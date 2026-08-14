# BRD corpus — every BRD the agent has been tested against

One index of all BRD suites in this repository, which branch carries them, and what
each suite was designed to prove. Every BRD file is plain markdown, pasted into the
app exactly as written — no rewording mid-run.

## Where the suites live

| Suite file | Branch(es) | BRDs | What it proves |
| --- | --- | --- | --- |
| `tests/gold_silver_brds.md` | all | 14 | Silver/gold operation coverage against real `s-landing` data; BRDs 11–14 are the prescriptive kind that names exact ADF object names |
| `tests/heldout_brds.md` | all | 5 | "Usable by others" — fresh unseen BRDs against frozen code, no manual repair allowed |
| `tests/stress_brds.md` | all | 10 | One BRD per previously untested dimension (HTTP source, 6-way join, ambiguity trap, refusal trap, …) |
| `tests/external_suite_brds.md` | `linking-external-source`, `linking-er` | 10 | External sources: Dataverse, SharePoint, Postgres, HTTP, cross-source joins |
| `tests/tough_suite_round3_brds.md` | `linking-external-source`, `linking-er` | 10 | Harder shapes over external sources + regression of earlier fixes |
| `tests/dataverse_brd.md` | `linking-external-source`, `linking-er` | 1 | Single-source Dataverse CRM medallion |
| `tests/gcp_brd.md` | `linking-external-source`, `linking-er` | 1 | BigQuery sales medallion |
| `tests/sharepoint_brd.md` | `linking-external-source`, `linking-er` | 1 | SharePoint list tracker medallion |
| `tests/postgres_brd.md` | `linking-external-source`, `linking-er` | — | Postgres retail medallion (prose form) |
| `brd_retail_medallion.md` | all | 1 | The original worked example at repo root |

Historical suites referenced in run reports (`final_hard_brds.md`, `tough_all_aspects_brds.md`,
`container_regression_brds.md`, `folder_grouping_brds.md`) were consolidated into the files above
as their coverage was absorbed; their results are preserved in the POC document and in
`artifacts/*.json` run summaries.

## Branch map

| Branch | Carries | Why it exists |
| --- | --- | --- |
| `main` | Agent + storage/HTTP BRD suites | Stable baseline: BRD → ADF for Azure Blob/ADLS and public HTTP sources |
| `brd-passed-version` | Same as `main` | Historical checkpoint of the BRD-tested version; won a live bake-off against `main` |
| `linking-external-source` | `main` + Dataverse, Postgres, BigQuery, GCS, SharePoint source tooling | Adds non-Azure sources: connectors, schema readers, bronze seeding |
| `linking-er` | Everything above + `ER-Diagram/` frontend/backend, redesigned UI, catalog seam | Integration branch — the complete unified application |

## The BRD shapes that have been tested

The corpus deliberately spans four difficulty axes rather than 50 variations of the same document.

**1. Descriptive BRDs.** Business prose — "land these CSVs, clean them like this, produce this
mart." The agent infers entity names, containers, and object names. Most of
`heldout_brds.md` and `stress_brds.md`.

**2. Prescriptive BRDs.** The BRD names every ADF object it wants: `s_PL_Master`,
`s_DF_Customers_Silver`, `s_DS_Landing_CSV`, plus the exact container chain
`s-landing → s-bronze → s-silver → s-gold`. The agent must honor those names rather than
generate its own. `gold_silver_brds.md` BRDs 11–14 — the bike-store 8-output analytics BRD is
the canonical example of this shape.

**3. Trap BRDs.** BRDs whose correct answer is *not* a pipeline:
- **Ambiguity trap** (`stress_brds.md` BRD 7) — correct answer is a clarifying question.
- **Refusal trap** (`stress_brds.md` BRD 8, `external_suite_brds.md` BRD 10) — mostly unsupported
  asks; correct answer is an honest refusal list plus building the runnable remainder.
- **Nonexistent column** (`tough_suite_round3_brds.md` BRD 07) — a column the source does not
  have; correct answer is to drop it and say so, not to invent it.
- **Underspecified** (`tough_suite_round3_brds.md` BRD 09) — correct answer is to ask, not invent.

**4. External-source BRDs.** Same medallion shapes, but the bronze layer pulls from Dataverse,
SharePoint, Postgres, BigQuery, or GCS instead of an Azure container. Cross-source BRDs join
two different external systems in gold.

## Source formats the vocabulary accepts

From `models/logical.py` `SourceFormat`:

`csv`, `text`, `parquet`, `json`, `binary`, `sql_table`, `http_csv`, `dataverse`, `postgres`,
`bigquery`, `gcs`, `sharepoint`

Anything outside this list is refused at parse time with a suggested alternative — it is never
silently approximated.

## Running a suite

BRDs are pasted into the UI or posted to `/plan`. There is no suite runner in-repo by design:
the point of a benchmark run is that it goes through the same HTTP surface a user does.

```bash
uvicorn app:app --reload     # then paste the BRD at http://127.0.0.1:8000
```

Benchmark rule for every suite: run the BRDs **as written**. No code edits, no BRD rewording
mid-run. The app's built-in repair and self-heal are part of the product and are allowed to
operate; the final status is recorded honestly, including safe pre-deploy blocks.
