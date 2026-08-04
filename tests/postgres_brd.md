Build and run a medallion pipeline in Azure Data Factory for retail sales
reporting, from the PostgreSQL retail database I've already connected and
reviewed in the diagram. Use that schema — you already know the tables, their
columns, types, keys, and relationships.

Tables: `customers`, `products`, `orders`, `order_items`.

Bronze: load each table as-is, one folder per table in the `bronze` container.

Silver (write as Delta): clean and standardize each table — trim text fields,
lowercase emails, cast dates and numbers to their proper types, drop rows missing
their primary key, and deduplicate on the primary key.

Gold (write as Delta):
- Sales by city: revenue (sum of order total) and order count per customer city,
  highest revenue first.
- Sales by category: revenue (sum of quantity x unit price) per product category,
  highest revenue first.

Chain bronze -> silver -> gold in one master pipeline; a failed stage stops the
run. Manual trigger.
