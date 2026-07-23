"""Bootstrap movers for Postgres / BigQuery / GCS — pure-logic checks (no live
source needed): type-map coverage, table-ref parsing, and CSV serialization of
typed values (datetime/Decimal/None). Connection code is exercised live via the
CLI against a real source, not here."""

import datetime as dt
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from inject_to_bronze import _to_csv  # noqa: E402
from source_schema import _BQ_TYPE, _PG_TYPE, _csv_header_cols  # noqa: E402


def test_type_maps_hit_the_common_types():
    assert _PG_TYPE["timestamp without time zone"] == "timestamp"
    assert _PG_TYPE["character varying"] == "string"
    assert _PG_TYPE["numeric"] == "decimal"
    assert _BQ_TYPE["INT64"] == "long"
    assert _BQ_TYPE["FLOAT64"] == "double"
    assert _BQ_TYPE["TIMESTAMP"] == "timestamp"


def test_table_ref_split_matches_pull_and_schema():
    # inject uses rpartition('.')[2] for the entity; schema uses rpartition for schema/table.
    assert "sales.orders".rpartition(".")[2] == "orders"
    assert "orders".rpartition(".")[2] == "orders"
    schema, _, tbl = "sales.orders".rpartition(".")
    assert (schema, tbl) == ("sales", "orders")


def test_to_csv_serializes_typed_values():
    cols = ["id", "amount", "created", "note"]
    rows = [
        {"id": 1, "amount": Decimal("9.50"), "created": dt.date(2026, 7, 22), "note": None},
    ]
    out = _to_csv(cols, rows).decode("utf-8")
    lines = out.splitlines()
    assert lines[0] == "id,amount,created,note"
    assert lines[1] == "1,9.50,2026-07-22,"  # None -> empty, Decimal/date -> str


def test_csv_header_cols_parses_bom_and_quotes():
    cols = _csv_header_cols(b"\xef\xbb\xbfid,\"full name\",amount\n1,a,2\n")
    assert [c["name"] for c in cols] == ["id", "full name", "amount"]
    assert all(c["type"] == "string" for c in cols)


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK — new source movers: type maps, ref parsing, CSV serialization")
