"""Offline self-check for the connector contract + SQLite reference impl.
Run from the backend dir: python -m app.services.connectors.selfcheck"""
import os
import sqlite3
import tempfile

from app.services.connectors.base import WriteAttemptError, assert_read_only
from app.services.connectors.sqlite import SQLiteConnector


def _build_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, total REAL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE INDEX ix_orders_cust ON orders(customer_id);
        INSERT INTO customers VALUES (1,'Ada'),(2,'Grace');
        INSERT INTO orders VALUES (1,1,9.99),(2,2,'please update your note');
    """)
    conn.commit()
    conn.close()


def main() -> None:
    # --- guard unit checks ---
    assert_read_only("SELECT * FROM orders")
    assert_read_only("  with c as (select 1) select * from c  ")
    # value containing a write word must NOT trip the guard
    assert_read_only("SELECT * FROM orders WHERE note = 'please update'")
    for bad in ["DROP TABLE orders", "SELECT 1; DROP TABLE orders",
                "UPDATE orders SET total=0", "WITH t AS (DELETE FROM orders) SELECT 1",
                "PRAGMA writable_schema=1"]:
        try:
            assert_read_only(bad)
            raise AssertionError(f"guard let a write through: {bad!r}")
        except WriteAttemptError:
            pass

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "shop.db")
        _build_db(db)
        c = SQLiteConnector(source_id="sqlite-shop", path=db)

        schema = c.extract_schema()
        names = {t.table_name for t in schema.tables}
        assert names == {"customers", "orders"}, names
        orders = next(t for t in schema.tables if t.table_name == "orders")
        assert {col.name for col in orders.columns} == {"id", "customer_id", "total"}
        assert any(col.is_primary_key for col in orders.columns)
        assert len(schema.foreign_keys) == 1
        fk = schema.foreign_keys[0]
        assert fk.source_table == "orders" and fk.target_table == "customers", fk
        assert any(ix.name == "ix_orders_cust" for ix in orders.indexes)
        assert schema.table_count == 2

        # read-only query works and is row-capped
        res = c.run_readonly_sql("SELECT id, name FROM customers ORDER BY id", limit=1)
        assert res["row_count"] == 1 and res["rows"][0][1] == "Ada", res
        assert c.sample("main", "orders", limit=50)["row_count"] == 2

        # a write is refused BEFORE it reaches the DB
        try:
            c.run_readonly_sql("DELETE FROM orders")
            raise AssertionError("connector executed a write")
        except WriteAttemptError:
            pass

    print("ok")


if __name__ == "__main__":
    main()
