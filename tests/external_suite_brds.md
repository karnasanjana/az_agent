# External-source suite — 10 BRDs, bug hunt

Goal: find real bugs a user hits when building pipelines. Every BRD uses an
**external source** (no pre-seeded s-landing data) and only columns verified
live on 2026-07-24:

- **Dataverse** `https://zcscmdemodev.crm.dynamics.com` — account(4), contact(43),
  incident(3), systemuser(233), team(71)
- **SharePoint** `netorgft1612603.sharepoint.com` `/sites/DOLCaseManagement`,
  list `DOL Project Team`
- **Postgres** `localhost:5432/retaildb` — customers, products, orders, order_items
- **HTTP** public CSVs on raw.githubusercontent.com (all 200 OK)

---

## BRD 1 — Dataverse contact directory (baseline)

Build a medallion pipeline in Azure Data Factory for our contact directory.

Source — the `contact` table in Dataverse at
`https://zcscmdemodev.crm.dynamics.com`.

Bronze: land the `contact` table as-is in the `bronze` container, one folder for
the table.

Silver (write as Delta): keep `contactid`, `fullname`, `firstname`, `lastname`,
`emailaddress1`, `jobtitle`, `address1_city`, `createdon`. Trim `fullname`,
`firstname`, `lastname` and `jobtitle`; lowercase `emailaddress1`; cast
`createdon` to timestamp; drop rows with a missing `contactid`; dedup on
`contactid`.

Gold (write as Delta):
- Contacts by city: group by `address1_city`, count contacts as `contact_count`,
  sorted by `contact_count` descending.
- Contacts by job title: group by `jobtitle`, count contacts as `contact_count`,
  sorted by `contact_count` descending.

Chain bronze → silver → gold in a master pipeline; a failed stage stops the run.
Manual trigger.

---

## BRD 2 — Dataverse account 360 (3-way join, bands, top N)

We need an account health mart in Azure Data Factory.

Sources — three Dataverse tables at `https://zcscmdemodev.crm.dynamics.com`:
`account`, `contact`, and `systemuser`.

Bronze: land all three tables as-is into `bronze`, one folder per table.

Silver (Delta):
- Accounts: keep `accountid`, `name`, `accountnumber`, `address1_city`,
  `address1_country`, `revenue`, `numberofemployees`, `industrycodename`,
  `createdon`, `statecode`. Trim `name` and `address1_city`; cast `revenue` to
  decimal and `numberofemployees` to integer; cast `createdon` to timestamp;
  drop rows missing `accountid`; dedup on `accountid`.
- Contacts: keep `contactid`, `fullname`, `emailaddress1`, `jobtitle`,
  `address1_city`, `createdon`. Trim `fullname`; lowercase `emailaddress1`;
  drop rows missing `contactid`; dedup on `contactid`.
- Users: keep `systemuserid`, `fullname`, `internalemailaddress`, `jobtitle`,
  `isdisabled`, `businessunitidname`. Trim `fullname`; lowercase
  `internalemailaddress`; drop rows missing `systemuserid`; dedup on
  `systemuserid`.

Gold (Delta):
- Account size bands: from silver accounts, derive `size_band` as `Enterprise`
  when `numberofemployees` is 1000 or more, `Mid-Market` when it is 100 or more,
  otherwise `SMB`. Group by `size_band` and `address1_country`, sum `revenue` as
  `total_revenue`, count accounts as `account_count`, and compute
  `revenue_per_account = total_revenue / account_count`. Sort by `total_revenue`
  descending.
- Revenue by city: group silver accounts by `address1_city`, sum `revenue` as
  `total_revenue`, average `numberofemployees` as `avg_headcount`. Keep only the
  top 10 cities by `total_revenue`.
- Contact coverage by city: join silver contacts to silver accounts on
  `address1_city`, group by `address1_city`, count contacts as `contact_count`
  and count distinct accounts as `account_count`, sorted by `contact_count`
  descending.

Chain bronze → silver → gold in a master pipeline. Manual trigger.

---

## BRD 3 — Dataverse case SLA analytics (timestamps, bands, post-agg filter)

Build a support-case SLA mart in Azure Data Factory.

Sources — `incident` and `account` from Dataverse at
`https://zcscmdemodev.crm.dynamics.com`.

Bronze: land both tables as-is into `bronze`, one folder each.

Silver (Delta):
- Cases: keep `incidentid`, `ticketnumber`, `title`, `customeridname`,
  `prioritycodename`, `casetypecodename`, `caseorigincodename`, `createdon`,
  `resolveby`, `statecode`, `accountid`. Trim `title` and `customeridname`; cast
  `createdon` and `resolveby` to timestamp; cast `statecode` to integer; drop
  rows missing `incidentid`; dedup on `incidentid`.
- Accounts: keep `accountid`, `name`, `address1_country`, `industrycodename`.
  Trim `name`; drop rows missing `accountid`; dedup on `accountid`.

Gold (Delta):
- SLA by priority: from silver cases, derive `sla_bucket` as `Breached` when
  `resolveby` is earlier than `createdon`, otherwise `Within SLA`. Group by
  `prioritycodename` and `sla_bucket`, count cases as `case_count`, sorted by
  `case_count` descending.
- Cases by account country: join silver cases to silver accounts on `accountid`,
  group by `address1_country` and `casetypecodename`, count cases as
  `case_count`. Only keep groups with a `case_count` of 2 or more.
- Case origin mix: group silver cases by `caseorigincodename`, count cases as
  `case_count`, and compute `pct_of_total = case_count * 100 / case_count`.
  Sort by `case_count` descending.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 4 — SharePoint project tracker (derived flags, date bands)

Build a project-tracking medallion pipeline in Azure Data Factory.

Source — the SharePoint list `DOL Project Team` on site
`https://netorgft1612603.sharepoint.com/sites/DOLCaseManagement`.

Bronze: land the list as-is in the `bronze` container, one folder for the list.

Silver (Delta): keep `id`, `Title`, `TeamMemberResponsible`, `Status`,
`ItemType`, `StartDate`, `ExpectedCompletion`, `ActualCompletion`, `Notes`.
Trim `Title`, `TeamMemberResponsible` and `Notes`; cast `StartDate`,
`ExpectedCompletion` and `ActualCompletion` to timestamp; drop rows with a
missing `id`; dedup on `id`. Where `Notes` is blank, default it to `No notes`.

Gold (Delta):
- Delivery status: derive `completion_state` as `Done` when `ActualCompletion`
  is not null, `Overdue` when `ActualCompletion` is null and `ExpectedCompletion`
  is earlier than `StartDate`, otherwise `In Flight`. Group by `Status` and
  `completion_state`, count items as `item_count`, sorted by `item_count`
  descending.
- Owner workload: group by `TeamMemberResponsible`, count items as `item_count`,
  sorted by `item_count` descending, top 10.
- Work type mix: group by `ItemType`, count items as `item_count`.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 5 — Cross-source: SharePoint tasks + Dataverse users (heterogeneous join)

We want to see project work alongside the staff directory in one mart.

Sources — TWO different systems:
- The SharePoint list `DOL Project Team` on site
  `https://netorgft1612603.sharepoint.com/sites/DOLCaseManagement`.
- The `systemuser` table in Dataverse at `https://zcscmdemodev.crm.dynamics.com`.

Bronze: land both into the `bronze` container, one folder per entity.

Silver (Delta):
- Tasks: from the SharePoint list keep `id`, `Title`, `TeamMemberResponsible`,
  `Status`, `ItemType`, `StartDate`, `ExpectedCompletion`. Trim `Title` and
  `TeamMemberResponsible`; cast `StartDate` and `ExpectedCompletion` to
  timestamp; drop rows missing `id`; dedup on `id`.
- Staff: from `systemuser` keep `systemuserid`, `fullname`, `jobtitle`,
  `internalemailaddress`, `isdisabled`, `businessunitidname`. Trim `fullname`
  and `jobtitle`; lowercase `internalemailaddress`; drop rows missing
  `systemuserid`; dedup on `systemuserid`. Keep only rows where `isdisabled` is
  false.

Gold (Delta):
- Task load by staff member: join silver tasks to silver staff on task
  `TeamMemberResponsible` equals staff `fullname`. Group by `fullname` and
  `jobtitle`, count tasks as `task_count`, sorted by `task_count` descending.
- Unassigned or unknown owners: from silver tasks, group by
  `TeamMemberResponsible`, count tasks as `task_count`, and keep only groups
  where `task_count` is 1 or more, sorted by `task_count` descending.
- Work mix by business unit: join silver tasks to silver staff on
  `TeamMemberResponsible` equals `fullname`, group by `businessunitidname` and
  `ItemType`, count tasks as `task_count`.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 6 — Postgres retail medallion (4 tables, joins, arithmetic)

Build a retail sales medallion pipeline in Azure Data Factory.

Sources — four tables from PostgreSQL, server `localhost`, database `retaildb`,
schema `public`: `customers`, `products`, `orders`, `order_items`.

Bronze: load each table as-is into the `bronze` container, one folder per table.

Silver (Delta):
- Customers: keep `customer_id`, `first_name`, `last_name`, `email`, `city`,
  `created_date`. Trim `first_name`, `last_name`, `city`; lowercase `email`;
  cast `created_date` to date; drop rows missing `customer_id`; dedup on
  `customer_id`.
- Products: keep `product_id`, `product_name`, `category`, `price`. Trim
  `product_name`; cast `price` to decimal; drop rows missing `product_id`;
  dedup on `product_id`.
- Orders: keep `order_id`, `customer_id`, `order_date`, `total_amount`. Cast
  `order_date` to date and `total_amount` to decimal; drop rows missing
  `order_id`; dedup on `order_id`.
- Order items: keep `order_item_id`, `order_id`, `product_id`, `quantity`,
  `unit_price`. Cast `quantity` to integer and `unit_price` to decimal; drop
  rows missing `order_item_id`; dedup on `order_item_id`.

Gold (Delta):
- Revenue by city: join `orders` to `customers` on `customer_id`, group by
  `city`, sum `total_amount` as `revenue` and count orders as `order_count`,
  compute `avg_order_value = revenue / order_count`, sorted by `revenue`
  descending.
- Revenue by category: join `order_items` to `products` on `product_id`, derive
  `line_total = quantity * unit_price`, group by `category`, sum `line_total` as
  `revenue` and sum `quantity` as `units_sold`, sorted by `revenue` descending.
- Top customers: join `orders` to `customers` on `customer_id`, group by
  `customer_id` and `email`, sum `total_amount` as `revenue`, count orders as
  `order_count`, top 10 by `revenue`.
- Basket detail: join `order_items` to `orders` on `order_id` and to `products`
  on `product_id`, derive `line_total = quantity * unit_price`, group by
  `order_id` and `category`, sum `line_total` as `line_revenue`.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 7 — Postgres incremental + custom containers + prefixes

Build an incremental retail load in Azure Data Factory.

Sources — `orders` and `customers` from PostgreSQL, server `localhost`,
database `retaildb`, schema `public`.

Use our own container names, not the defaults: land raw data in `retail-raw`,
cleaned data in `retail-clean`, and reporting data in `retail-mart`.

Prefix every ADF object we create with `rt` so they sort together, and group the
objects into a Data Factory folder called `RetailIncremental`.

Bronze: load both tables incrementally into `retail-raw` — only pick up rows
changed since the last run, using `order_date` for orders and `created_date` for
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

Chain bronze → silver → gold. Run it every day at 02:00 UTC.

---

## BRD 8 — HTTP COVID CSV (regex clean, IN / LIKE / BETWEEN filters)

Build a COVID reporting pipeline in Azure Data Factory.

Source — the public CSV at
`https://raw.githubusercontent.com/datasets/covid-19/main/data/countries-aggregated.csv`
with columns `Date`, `Country`, `Confirmed`, `Recovered`, `Deaths`.

Bronze: copy the file as-is into the `bronze` container as
`countries_aggregated.csv`.

Silver (Delta): cast `Date` to date; cast `Confirmed`, `Recovered` and `Deaths`
to long; trim `Country`; strip any character that is not a letter or a space
from `Country`; drop rows where `Country` is missing; drop rows where
`Confirmed` is missing; dedup on `Date` and `Country`. Keep only rows where
`Date` is between 2020-03-01 and 2021-12-31. Derive
`active = Confirmed - Recovered - Deaths`.

Gold (Delta):
- Country totals: keep only rows where `Country` is one of `India`, `Brazil`,
  `Germany`, `France` or `Italy`. Group by `Country`, take the maximum
  `Confirmed` as `peak_confirmed`, the maximum `Deaths` as `peak_deaths`, and
  compute `case_fatality_pct = peak_deaths * 100 / peak_confirmed`. Sort by
  `peak_confirmed` descending.
- United nations: keep only rows where `Country` is like `United%`. Group by
  `Country` and `Date`, sum `active` as `active_cases`, sorted by `Date`
  descending, top 50.

Chain bronze → silver → gold. Manual trigger.

---

## BRD 9 — HTTP multi-file copy-only + daily schedule

We just need three public reference files landed daily. No transformations at
all — raw copies only.

Copy these into the `reference` container of our data lake, keeping the file
names:
- `https://raw.githubusercontent.com/datasets/population/main/data/population.csv`
  as `population.csv`
- `https://raw.githubusercontent.com/datasets/gdp/main/data/gdp.csv` as `gdp.csv`
- `https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv`
  as `vix_daily.csv`

Run every night at 01:30 UTC. If one file fails the whole run should fail.

---

## BRD 10 — Honesty trap (unsupported asks + a column that does not exist)

Build a customer intelligence platform on Azure.

Source — the `account` and `contact` tables in Dataverse at
`https://zcscmdemodev.crm.dynamics.com`.

Bronze: land both tables into `bronze`, one folder each.

Silver (Delta):
- Accounts: keep `accountid`, `name`, `revenue`, `numberofemployees`,
  `address1_country`, `industrycodename`, and `customer_health_score`. Trim
  `name`; cast `revenue` to decimal; drop rows missing `accountid`; dedup on
  `accountid`.
- Contacts: keep `contactid`, `fullname`, `emailaddress1`, `jobtitle`. Trim
  `fullname`; lowercase `emailaddress1`; drop rows missing `contactid`; dedup on
  `contactid`.

Gold (Delta):
- Revenue by country: group silver accounts by `address1_country`, sum `revenue`
  as `total_revenue`, count accounts as `account_count`, sorted by
  `total_revenue` descending.

Also please:
- Train a machine-learning model to predict account churn and score every
  account nightly.
- Run the silver transformations in a Databricks notebook instead of a Data
  Flow, and orchestrate it with Airflow.
- Email the sales team a PDF summary whenever revenue drops week over week.
- Publish the gold tables to a Power BI dashboard and refresh it automatically.
- Write the gold layer to Snowflake as well as the data lake.

Chain bronze → silver → gold. Manual trigger.
