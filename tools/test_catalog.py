"""Offline check for the ER catalog reader — no ER backend, no network.
Run: python tools/test_catalog.py"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

_STUB = {
    "source_id": "retail-postgres",
    "schema_version": 4,
    "database_name": "retaildb",
    "tables": [
        {"schema_name": "public", "table_name": "orders", "columns": [
            {"name": "order_id", "data_type": "bigint"},
            {"name": "total", "data_type": "numeric(18,2)"},   # ER strips precision -> "numeric"
            {"name": "placed_at", "data_type": "timestamp without time zone"},
            {"name": "note", "data_type": "varchar"},
        ]},
        {"schema_name": "sales", "table_name": "orders", "columns": [  # same name, other schema
            {"name": "sale_id", "data_type": "int"},
        ]},
    ],
}


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "retail-postgres.json"), "w", encoding="utf-8") as fh:
            json.dump(_STUB, fh)
        os.environ["ER_CATALOG_URL"] = d

        schema = catalog.fetch("retail-postgres")
        assert schema and schema["schema_version"] == 4, "fetch failed"
        assert catalog.fetch("missing") is None, "absent source must be None"

        # bare table name -> matches public.orders; types mapped to grounding vocab
        cols = catalog.columns(schema, "orders")
        by = {c["name"]: c["type"] for c in cols}
        assert by == {"order_id": "long", "total": "decimal",
                      "placed_at": "timestamp", "note": "string"}, by

        # schema-qualified picks the right same-named table
        assert catalog.columns(schema, "sales.orders") == [{"name": "sale_id", "type": "integer"}]
        assert catalog.columns(schema, "public.orders")[0]["name"] == "order_id"

        # unknown table -> [] (grounding then falls back to live probe)
        assert catalog.columns(schema, "customers") == []

        # unknown data_type -> string, never crashes
        assert catalog._map("some_weird_type") == "string"

    print("ok")


if __name__ == "__main__":
    main()
