# SharePoint test BRD — DOL Project Team tracker medallion

Source of truth: SharePoint Online list `DOL Project Team` on site
`https://netorgft1612603.sharepoint.com/sites/DOLCaseManagement` (13 items).
App-only Graph access is granted (`Sites.Read.All`). Columns below are the REAL
list fields, read with the SharePoint reader/mover — proven end-to-end:

    python -c "import sys;sys.path.insert(0,'tools');from inject_to_bronze import _pull_sharepoint;print(_pull_sharepoint('netorgft1612603.sharepoint.com','/sites/DOLCaseManagement','DOL Project Team')[0])"

> **Status — reader + mover proven, native source NOT wired.** `SourceFormat` has
> dataverse / postgres / bigquery / gcs but **no `sharepoint`** yet, so the planner
> can't emit a SharePoint `LogicalSource` today. To run this BRD end-to-end, either
> seed bronze first and plan the file as a storage source:
>
>     python tools/inject_to_bronze.py sharepoint netorgft1612603.sharepoint.com /sites/DOLCaseManagement "DOL Project Team" --real
>
> — or ask to wire `SourceFormat.sharepoint` (small; mirrors Dataverse: schema
> reader + app-seed via `_pull_sharepoint`, `is_app_seeded` true because Graph auth
> is app-side, not an ADF connector).

---

## BRD — DOL project tracker medallion (SharePoint source)

Build a medallion pipeline in Azure Data Factory for project-tracking reporting.

Source — the SharePoint list `DOL Project Team` on site
`https://netorgft1612603.sharepoint.com/sites/DOLCaseManagement`.

Bronze: fetch the list from SharePoint and land it as-is in the `bronze`
container, one folder for the list.

Silver (write as Delta):
- Tasks: keep `id`, `Title`, `TeamMemberResponsible`, `Status`, `ItemType`,
  `StartDate`, `ExpectedCompletion`, `Notes`. Trim `Title`,
  `TeamMemberResponsible`, and `Notes`; cast `StartDate` and `ExpectedCompletion`
  to timestamp; remove rows with a missing `id`; dedup on `id`.

Gold (write as Delta):
- Tasks by status: group by `Status`, count tasks as `task_count`, sorted by
  `task_count` descending.
- Tasks by owner: group by `TeamMemberResponsible`, count tasks as `task_count`,
  sorted by `task_count` descending.
- Tasks by type: group by `ItemType`, count tasks as `task_count`.

Chain bronze → silver → gold in a master pipeline; a failed stage stops the run.
Manual trigger.
