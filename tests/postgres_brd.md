# Postgres test BRD — retail medallion (local `retaildb`)

Source of truth: the local PostgreSQL server `localhost:5432`, database `retaildb`
(env `PG_*` in `.env`). Columns below are the REAL `public.*` schema, read with
`python tools/source_schema.py postgres public.<table>`.

> **How this runs:** `localhost` is unreachable from ADF's cloud IR, so these are
> **app-seeded** — `is_app_seeded()` is true and the agent pulls each table into
> `bronze/<entity>/<entity>.csv` at deploy time (no ADF Copy). The generated
> pipeline then runs bronze → silver → gold as usual. Nothing to inject by hand.

---

## BRD — Retail sales medallion (PostgreSQL source)

Build a medallion pipeline in Azure Data Factory for retail sales reporting.

Sources — four tables from our PostgreSQL database, server `localhost`, database
`retaildb`, schema `public`:
- `customers`
- `products`
- `orders`
- `order_items`

Bronze: load each table as-is into the `bronze` container, one folder per table.

Silver (write as Delta):
- Customers: keep `customer_id`, `first_name`, `last_name`, `email`, `city`,
  `created_date`. Trim `first_name`, `last_name`, `city`; lowercase `email`; cast
  `created_date` to date; remove rows with a missing `customer_id`; dedup on
  `customer_id`.
- Products: keep `product_id`, `product_name`, `category`, `price`. Trim
  `product_name`; cast `price` to decimal; remove rows with a missing
  `product_id`; dedup on `product_id`.
- Orders: keep `order_id`, `customer_id`, `order_date`, `total_amount`. Cast
  `order_date` to date and `total_amount` to decimal; remove rows with a missing
  `order_id`; dedup on `order_id`.
- Order items: keep `order_item_id`, `order_id`, `product_id`, `quantity`,
  `unit_price`. Cast `quantity` to integer and `unit_price` to decimal; remove
  rows with a missing `order_item_id`; dedup on `order_item_id`.

Gold (write as Delta):
- Sales by city: join `orders` to `customers` on `customer_id`, group by `city`,
  sum `total_amount` as `revenue` and count orders as `order_count`, sorted by
  `revenue` descending.
- Sales by category: join `order_items` to `products` on `product_id`, compute
  `line_total = quantity * unit_price`, group by `category`, sum `line_total` as
  `revenue`, sorted by `revenue` descending.
- Top customers: join `orders` to `customers` on `customer_id`, group by
  `customer_id` and `email`, sum `total_amount` as `revenue`, top 10 by `revenue`.

Chain bronze → silver → gold in a master pipeline; a failed stage stops the run.
Manual trigger.
