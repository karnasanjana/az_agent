# GCP test BRD — sales analytics medallion (BigQuery)

Source of truth: Google BigQuery, project `gemini-for-zion`, dataset
`omniquery_demo` (the project you have access to). Columns below are the REAL
BigQuery schema, read with
`python tools/source_schema.py bigquery omniquery_demo.<table>`.

> **GCS bucket:** you asked for a bucket source too, but there are **no CSV files
> in any bucket you have access to** (they hold docs/PDFs/staging artifacts, not
> tabular CSV). Since a GCS source lands as CSV in bronze, there's no real GCS
> data to wire — this BRD is BigQuery-only. Drop a CSV into a bucket and I'll add
> it as a second source.
>
> **How this runs:** with no `GOOGLE_APPLICATION_CREDENTIALS` set, ADF has no
> service-account key, so these are **app-seeded** — the agent pulls each table
> into `bronze/<entity>/<entity>.csv` at deploy time using KEYLESS gcloud auth. No
> ADF Copy is emitted. Set an SA key env later to switch to ADF's own BigQuery
> Copy — same BRD, no changes.

---

## BRD — Sales analytics medallion (BigQuery source)

Build a medallion pipeline in Azure Data Factory for sales and customer
reporting from BigQuery.

Sources — three BigQuery tables in project `gemini-for-zion`, dataset
`omniquery_demo`:
- `customers`
- `products`
- `orders`

Bronze: load each table as-is into the `bronze` container, one folder per table.

Silver (write as Delta):
- Customers: keep `id`, `name`, `email`, `industry`, `mrr`, `created_date`,
  `account_manager`. Trim `name`; lowercase `email`; cast `mrr` to decimal and
  `created_date` to date; remove rows with a missing `id`; dedup on `id`.
- Products: keep `id`, `name`, `category`, `price`, `active`. Trim `name`; cast
  `price` to decimal; remove rows with a missing `id`; dedup on `id`; keep only
  active products (`active` = true).
- Orders: keep `id`, `customer_id`, `product_id`, `order_date`, `quantity`,
  `total`, `status`. Cast `order_date` to date, `quantity` to integer, `total` to
  decimal; lowercase `status`; remove rows with a missing `id`; dedup on `id`.

Gold (write as Delta):
- Revenue by customer: join `orders` to `customers` on `orders.customer_id =
  customers.id`, group by customer `name`, sum `total` as `revenue` and count
  orders as `order_count`, sorted by `revenue` descending, top 10.
- Revenue by category: join `orders` to `products` on `orders.product_id =
  products.id`, group by `category`, sum `total` as `revenue`, sorted by
  `revenue` descending.
- Orders by status: from orders, group by `status`, count orders as
  `order_count` and sum `total` as `revenue`.

Chain bronze → silver → gold in a master pipeline; a failed stage stops the run.
Manual trigger.
