# Dataverse test BRD — CRM contacts / accounts / cases medallion

Source of truth: the Dynamics 365 environment `zcscmdemodev.crm.dynamics.com`.
Every column below was verified to hold real data (contacts 43 rows, accounts 4,
incidents/cases 3). Use this to test the Dataverse → bronze → silver → gold flow.

> **How this runs:** the native Dataverse source IS wired into the compiler now,
> so the planner emits a real `ls_dataverse_*` linked service + `ds_dataverse_<ent>`
> Copy → bronze, and grounds each entity against the live Dataverse metadata at plan
> time (contacts 340 cols, accounts 243, incidents 166). No manual seeding needed —
> ADF's Copy pulls the rows via the AAD service principal in `SOURCE_*` env.
>
> (Do NOT add a "treat these as landing files" note here — it steers the planner
> away from the native connector and back to unchecked landing CSVs.)

---

## BRD — CRM analytics medallion (Dataverse source)

Build a medallion pipeline in Azure Data Factory for our CRM reporting.

Sources — three tables from our Dataverse environment
`https://zcscmdemodev.crm.dynamics.com`:
- `contacts`
- `accounts`
- `incidents` (support cases)

Bronze: fetch each table from Dataverse and land it as-is in the `bronze`
container, one folder per table.

Silver (write as Delta):
- Contacts: keep `contactid`, `fullname`, `firstname`, `emailaddress1`,
  `jobtitle`, `address1_city`, `address1_postalcode`, `adx_organizationname`,
  `createdon`, `modifiedon`, `statecode`. Trim `fullname` and `address1_city`,
  lowercase `emailaddress1`, cast `createdon` and `modifiedon` to timestamp,
  remove rows with a missing `contactid`, dedup on `contactid`, and keep only
  active contacts (`statecode` = 0).
- Accounts: keep `accountid`, `name`, `openrevenue`, `opendeals`,
  `territorycode`, `customersizecode`, `statecode`, `modifiedon`. Trim `name`,
  cast `openrevenue` to decimal and `opendeals` to integer, cast `modifiedon`
  to timestamp, remove rows with a missing `accountid`, dedup on `accountid`,
  keep only active accounts (`statecode` = 0).
- Cases: keep `incidentid`, `ticketnumber`, `title`, `prioritycode`,
  `severitycode`, `caseorigincode`, `caseage`, `createdon`, `statecode`. Trim
  `title`, cast `createdon` to timestamp and `caseage` to integer, remove rows
  with a missing `incidentid`, dedup on `incidentid`, keep only active cases
  (`statecode` = 0).

Gold (write as Delta):
- Contacts by city: count of contacts per `address1_city`, sorted by count
  descending.
- Contacts by organization: count of contacts per `adx_organizationname`.
- Cases by priority: count of cases and average `caseage` per `prioritycode`.
- Cases by origin: count of cases per `caseorigincode`.

Chain bronze -> silver -> gold in a master pipeline; a failed stage stops the
run. Manual trigger.
