# Dataverse test BRD — CRM contacts / accounts / cases medallion

Source of truth: the Dynamics 365 environment `zcscmdemodev.crm.dynamics.com`.
Every column below was verified to hold real data (contacts 43 rows, accounts 4,
incidents/cases 3). Use this to test the Dataverse → bronze → silver → gold flow.

> **How to test manually today:** the production Dataverse Copy activity is not
> wired into the compiler yet (see docs/dataverse-source-wiring.md), so the
> planner treats these tables as **landing** files (`ds_landing_contacts →
> ds_bronze_contacts`). Seed the `landing` container with the bootstrap injector,
> then the generated plan runs the whole way (landing → bronze → silver → gold):
>
>     python tools/inject_to_bronze.py dataverse contacts   --container landing --real
>     python tools/inject_to_bronze.py dataverse accounts   --container landing --real
>     python tools/inject_to_bronze.py dataverse incidents  --container landing --real
>
> (drop `--real` to write to mock_tenant/ instead of the live lake). The injector
> writes `landing/<entity>/<entity>.csv` — if the plan's landing dataset expects a
> different path, match it to what preflight shows.

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
