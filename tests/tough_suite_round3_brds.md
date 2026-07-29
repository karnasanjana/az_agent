# Tough-suite round 3 — 9 BRDs, harder shapes + regression of the 2026-07-29 fixes

Every BRD uses an **external source** and only columns verified live in
`tests/external_suite_brds.md`, except the deliberate honesty-trap columns.
Paste any one into the app's BRD box (or POST to `/plan`) to test like a user.

Sources: Dataverse `https://zcscmdemodev.crm.dynamics.com` (account, contact,
incident, systemuser) · SharePoint `DOL Project Team` on
`https://netorgft1612603.sharepoint.com/sites/DOLCaseManagement` · Postgres
`localhost:5432/retaildb` (customers, products, orders, order_items) · public
HTTP CSVs.

What each one is hunting:

| # | Source | Hunts |
|--:|--------|-------|
| 01 | Postgres | mixed `a*b/c` arithmetic — regress P0 divide-folds-to-multiply |
| 02 | Dataverse | column-vs-column in a **filter** — regress P1 quoted-column-literal |
| 03 | SharePoint | column null in first item (`ActualCompletion`) + `_`-system fields — regress P1 |
| 04 | Postgres | 4-table many-way join graph + derived line totals |
| 05 | SP + Dataverse | heterogeneous cross-source join on a name key |
| 06 | Postgres | incremental + custom containers + prefix + folder + daily schedule together |
| 07 | Dataverse | deep 3-level nested conditional + honesty trap (fake col + 5 platform asks) |
| 08 | HTTP | regex clean + IN/LIKE/BETWEEN filters + mixed-arithmetic CFR ratio |
| 09 | Postgres | **underspecified** BRD — should ask, not hallucinate |

---

## BRD 01 — Postgres retail ratios (mixed arithmetic everywhere)

Build a retail margin mart in Azure Data Factory.

Sources — `orders`, `order_items`, `products` from PostgreSQL, server
`localhost`, database `retaildb`, schema `public`.

Bronze: land each table as-is into `bronze`, one folder per table.

Silver (Delta):
- Orders: keep `order_id`, `customer_id`, `order_date`, `total_amount`; cast
  `order_date` to date and `total_amount` to decimal; drop rows missing
  `order_id`; dedup on `order_id`.
- Order items: keep `order_item_id`, `order_id`, `product_id`, `quantity`,
  `unit_price`; cast `quantity` to integer and `unit_price` to decimal; drop
  rows missing `order_item_id`; dedup on `order_item_id`. Derive
  `line_total = quantity * unit_price`.
- Products: keep `product_id`, `product_name`, `category`, `price`; trim
  `product_name`; cast `price` to decimal; drop rows missing `product_id`;
  dedup on `product_id`.

Gold (Delta):
- Category performance: join order items to products on `product_id`, group by
  `category`, sum `line_total` as `revenue`, sum `quantity` as `units`, and
  compute `avg_unit_revenue = revenue * 1 / units` and
  `revenue_share_pct = revenue * 100 / revenue`. Sort by `revenue` descending.
- Order economics: from silver order items, group by `order_id`, sum
  `line_total` as `order_revenue`, sum `quantity` as `order_units`, and compute
  `avg_line_value = order_revenue / order_units` and
  `blended = order_revenue * 100 / order_units`. Sort by `order_revenue`
  descending, top 20.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 02 — Dataverse SLA with column-vs-column filters

Build a support-case SLA mart in Azure Data Factory.

Sources — `incident` and `account` from Dataverse at
`https://zcscmdemodev.crm.dynamics.com`.

Bronze: land both as-is into `bronze`, one folder each.

Silver (Delta):
- Cases: keep `incidentid`, `ticketnumber`, `title`, `customeridname`,
  `prioritycodename`, `createdon`, `modifiedon`, `resolveby`, `statecode`,
  `accountid`. Trim `title` and `customeridname`; cast `createdon`,
  `modifiedon` and `resolveby` to timestamp; cast `statecode` to integer; drop
  rows missing `incidentid`; dedup on `incidentid`. Keep only rows where
  `resolveby` is earlier than `modifiedon`. Derive `sla_state` as `Late` when
  `resolveby` is earlier than `createdon`, otherwise `On Time`.
- Accounts: keep `accountid`, `name`, `address1_country`. Trim `name`; drop
  rows missing `accountid`; dedup on `accountid`.

Gold (Delta):
- Breaches by priority: from silver cases, group by `prioritycodename` and
  `sla_state`, count cases as `case_count`, sorted by `case_count` descending.
- Breaches by country: join silver cases to silver accounts on `accountid`,
  keep only rows where `resolveby` is earlier than `createdon`, group by
  `address1_country`, count cases as `breach_count`, sorted by `breach_count`
  descending.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 03 — SharePoint tracker using a column that is null in most rows

Build a project-tracking medallion pipeline in Azure Data Factory.

Source — the SharePoint list `DOL Project Team` on site
`https://netorgft1612603.sharepoint.com/sites/DOLCaseManagement`.

Bronze: land the list as-is in `bronze`, one folder for the list.

Silver (Delta): keep `id`, `Title`, `TeamMemberResponsible`, `Status`,
`ItemType`, `StartDate`, `ExpectedCompletion`, `ActualCompletion`, `Notes`.
Trim `Title`, `TeamMemberResponsible` and `Notes`; cast `StartDate`,
`ExpectedCompletion` and `ActualCompletion` to timestamp; drop rows missing
`id`; dedup on `id`. Where `Notes` is blank, default it to `No notes`.

Gold (Delta):
- Completion state: derive `completion_state` as `Done` when `ActualCompletion`
  is not null, otherwise `Open`. Group by `Status` and `completion_state`,
  count items as `item_count`, sorted by `item_count` descending.
- Owner workload: group by `TeamMemberResponsible`, count items as
  `item_count`, sorted by `item_count` descending, top 10.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 04 — Postgres 4-table basket mart (many-way joins)

Build a retail basket mart in Azure Data Factory.

Sources — `customers`, `products`, `orders`, `order_items` from PostgreSQL,
server `localhost`, database `retaildb`, schema `public`.

Bronze: land each table as-is into `bronze`, one folder per table.

Silver (Delta):
- Customers: keep `customer_id`, `first_name`, `last_name`, `email`, `city`;
  trim `first_name`, `last_name`, `city`; lowercase `email`; drop rows missing
  `customer_id`; dedup on `customer_id`.
- Products: keep `product_id`, `product_name`, `category`, `price`; trim
  `product_name`; cast `price` to decimal; drop rows missing `product_id`;
  dedup on `product_id`.
- Orders: keep `order_id`, `customer_id`, `order_date`, `total_amount`; cast
  `order_date` to date and `total_amount` to decimal; drop rows missing
  `order_id`; dedup on `order_id`.
- Order items: keep `order_item_id`, `order_id`, `product_id`, `quantity`,
  `unit_price`; cast `quantity` to integer and `unit_price` to decimal; derive
  `line_total = quantity * unit_price`; drop rows missing `order_item_id`;
  dedup on `order_item_id`.

Gold (Delta):
- Basket detail: join order items to orders on `order_id`, to products on
  `product_id`, and to customers on `customer_id`; group by `city` and
  `category`, sum `line_total` as `revenue`, sum `quantity` as `units`, sorted
  by `revenue` descending.
- Customer category spend: join order items to orders on `order_id`, to
  customers on `customer_id`, and to products on `product_id`; group by
  `customer_id`, `email` and `category`, sum `line_total` as `spend`, top 25 by
  `spend`.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 05 — Cross-source SharePoint tasks × Dataverse staff

We want project work alongside the staff directory in one mart.

Sources — TWO systems:
- The SharePoint list `DOL Project Team` on site
  `https://netorgft1612603.sharepoint.com/sites/DOLCaseManagement`.
- The `systemuser` table in Dataverse at `https://zcscmdemodev.crm.dynamics.com`.

Bronze: land both into `bronze`, one folder per entity.

Silver (Delta):
- Tasks: from the SharePoint list keep `id`, `Title`, `TeamMemberResponsible`,
  `Status`, `ItemType`; trim `Title` and `TeamMemberResponsible`; drop rows
  missing `id`; dedup on `id`.
- Staff: from `systemuser` keep `systemuserid`, `fullname`, `jobtitle`,
  `internalemailaddress`, `isdisabled`, `businessunitidname`; trim `fullname`
  and `jobtitle`; lowercase `internalemailaddress`; drop rows missing
  `systemuserid`; dedup on `systemuserid`. Keep only rows where `isdisabled` is
  false.

Gold (Delta):
- Task load by staff: join tasks to staff on task `TeamMemberResponsible`
  equals staff `fullname`; group by `fullname` and `jobtitle`, count tasks as
  `task_count`, sorted by `task_count` descending.
- Work mix by business unit: join tasks to staff on `TeamMemberResponsible`
  equals `fullname`; group by `businessunitidname` and `ItemType`, count tasks
  as `task_count`.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 06 — Postgres incremental with custom containers, prefix, folder, schedule

Build an incremental retail load in Azure Data Factory.

Sources — `orders` and `customers` from PostgreSQL, server `localhost`,
database `retaildb`, schema `public`.

Use our own container names: land raw data in `retail-raw`, cleaned data in
`retail-clean`, reporting data in `retail-mart`. Prefix every ADF object with
`rt3` so they sort together, and group them into a Data Factory folder called
`RetailR3`.

Bronze: load both tables incrementally into `retail-raw` — only rows changed
since the last run, using `order_date` for orders and `created_date` for
customers. One folder per table.

Silver (Delta, into `retail-clean`):
- Orders: keep `order_id`, `customer_id`, `order_date`, `total_amount`; cast
  `order_date` to date and `total_amount` to decimal; drop rows missing
  `order_id`; dedup on `order_id`.
- Customers: keep `customer_id`, `first_name`, `last_name`, `email`, `city`,
  `created_date`; trim `first_name`, `last_name`, `city`; lowercase `email`;
  cast `created_date` to date; drop rows missing `customer_id`; dedup on
  `customer_id`.

Gold (Delta, into `retail-mart`):
- Daily revenue: group silver orders by `order_date`, sum `total_amount` as
  `revenue`, count orders as `order_count`, sorted by `order_date` descending.
- Revenue by city: join silver orders to silver customers on `customer_id`,
  group by `city`, sum `total_amount` as `revenue`, sorted by `revenue`
  descending.

Chain bronze → silver → gold. Run it every day at 03:00 UTC.

---

## BRD 07 — Dataverse account bands (deep nesting + honesty trap)

Build a customer intelligence platform on Azure.

Sources — `account` and `contact` from Dataverse at
`https://zcscmdemodev.crm.dynamics.com`.

Bronze: land both into `bronze`, one folder each.

Silver (Delta):
- Accounts: keep `accountid`, `name`, `revenue`, `numberofemployees`,
  `address1_country`, `industrycodename`, and `growth_potential_score`. Trim
  `name`; cast `revenue` to decimal and `numberofemployees` to integer; drop
  rows missing `accountid`; dedup on `accountid`. Derive `segment` as
  `Strategic` when `numberofemployees` is 1000 or more, otherwise `Enterprise`
  when `numberofemployees` is 250 or more, otherwise `Mid-Market` when
  `numberofemployees` is 50 or more, otherwise `SMB`.
- Contacts: keep `contactid`, `fullname`, `emailaddress1`, `jobtitle`. Trim
  `fullname`; lowercase `emailaddress1`; drop rows missing `contactid`; dedup
  on `contactid`.

Gold (Delta):
- Revenue by segment: group silver accounts by `segment` and
  `address1_country`, sum `revenue` as `total_revenue`, count accounts as
  `account_count`, compute `revenue_per_account = total_revenue / account_count`,
  sorted by `total_revenue` descending.

Also please:
- Train a machine-learning model to predict account churn nightly.
- Run the silver transforms in a Databricks notebook orchestrated by Airflow.
- Email the sales team a PDF whenever revenue drops week over week.
- Publish the gold tables to a Power BI dashboard and auto-refresh it.
- Also write the gold layer to Snowflake.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 08 — HTTP COVID CSV (regex + IN/LIKE/BETWEEN + CFR ratio)

Build a COVID reporting pipeline in Azure Data Factory.

Source — the public CSV at
`https://raw.githubusercontent.com/datasets/covid-19/main/data/countries-aggregated.csv`
with columns `Date`, `Country`, `Confirmed`, `Recovered`, `Deaths`.

Bronze: copy the file as-is into `bronze` as `countries_aggregated.csv`.

Silver (Delta): cast `Date` to date; cast `Confirmed`, `Recovered` and `Deaths`
to long; trim `Country`; strip any character that is not a letter or a space
from `Country`; drop rows where `Country` is missing; drop rows where
`Confirmed` is missing; dedup on `Date` and `Country`. Keep only rows where
`Date` is between 2020-03-01 and 2021-12-31. Derive
`active = Confirmed - Recovered - Deaths`.

Gold (Delta):
- Country fatality: keep only rows where `Country` is one of `India`, `Brazil`,
  `Germany`, `France` or `Italy`. Group by `Country`, take the maximum
  `Confirmed` as `peak_confirmed`, the maximum `Deaths` as `peak_deaths`, and
  compute `case_fatality_pct = peak_deaths * 100 / peak_confirmed`. Sort by
  `peak_confirmed` descending.
- United nations: keep only rows where `Country` is like `United%`. Group by
  `Country` and `Date`, sum `active` as `active_cases`, sorted by `Date`
  descending, top 50.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 09 — Underspecified (should ask, not invent)

We want a sales dashboard in Azure Data Factory from our retail data in
Postgres. Show revenue and top customers. Make it look nice.

(That is the whole BRD. No columns, containers, layers, tables, or trigger are
named — the agent should ask for the missing essentials rather than hallucinate
a schema.)

---

## BRD 10 — Postgres executive mart (kitchen sink: joins + ratios + bands + filters + schedule)

Build a retail executive mart in Azure Data Factory.

Sources — `customers`, `products`, `orders`, `order_items` from PostgreSQL,
server `localhost`, database `retaildb`, schema `public`.

Bronze: land each table as-is into `bronze`, one folder per table.

Silver (Delta):
- Customers: keep `customer_id`, `first_name`, `last_name`, `email`, `city`;
  trim `first_name`, `last_name`, `city`; lowercase `email`; drop rows missing
  `customer_id`; dedup on `customer_id`.
- Products: keep `product_id`, `product_name`, `category`, `price`; trim
  `product_name`; cast `price` to decimal; drop rows missing `product_id`;
  dedup on `product_id`.
- Orders: keep `order_id`, `customer_id`, `order_date`, `total_amount`; cast
  `order_date` to date and `total_amount` to decimal; drop rows missing
  `order_id`; dedup on `order_id`. Derive `value_band` as `High` when
  `total_amount` is 500 or more, otherwise `Medium` when `total_amount` is 100
  or more, otherwise `Low`.
- Order items: keep `order_item_id`, `order_id`, `product_id`, `quantity`,
  `unit_price`; cast `quantity` to integer and `unit_price` to decimal; derive
  `line_total = quantity * unit_price`; drop rows missing `order_item_id`;
  dedup on `order_item_id`.

Gold (Delta):
- Category economics: join order items to products on `product_id`, group by
  `category`, sum `line_total` as `revenue`, sum `quantity` as `units`, and
  compute `avg_revenue_per_unit = revenue / units` and
  `revenue_share_pct = revenue * 100 / revenue`. Sort by `revenue` descending.
- Value band mix: from silver orders, group by `value_band`, count orders as
  `order_count`, sum `total_amount` as `band_revenue`, sorted by `band_revenue`
  descending.
- Top customers in target cities: join orders to customers on `customer_id`,
  keep only rows where `city` is one of `New York`, `Chicago` or `Los Angeles`,
  group by `customer_id` and `email`, sum `total_amount` as `revenue`, top 10 by
  `revenue`.
- Seasonal orders: from silver orders, keep only rows where `order_date` is
  between 2023-01-01 and 2023-12-31, group by `order_date`, sum `total_amount`
  as `revenue`, count orders as `order_count`, sorted by `order_date`
  descending.

Chain bronze → silver → gold. Run it every day at 04:00 UTC.
