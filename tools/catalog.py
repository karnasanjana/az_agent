"""Read a source's schema from the ER-Diagram CATALOG instead of live-probing it.

The ER app extracts a source's schema (tables/columns/types), the engineer
reviews it in the ER diagram, and az_agent grounds the pipeline against THAT —
so the plan is built on a schema a human approved, not a silent re-discovery.
This is the one seam between the two agents: ER owns schema truth, az_agent
consumes it. Any miss (no catalog configured, source/table absent) returns
nothing so grounding falls back to its live probe — grounding must never block.

Catalog shape = the ER app's DatabaseSchema JSON, unchanged:
    {"source_id", "schema_version", "tables": [
        {"schema_name", "table_name", "columns": [{"name", "data_type"}]}]}

Transport (ER_CATALOG_URL):
    http(s)://host   -> GET {ER_CATALOG_URL}/catalog/{source_id}   (ER backend)
    a local dir path -> {ER_CATALOG_URL}/{source_id}.json          (offline dev/tests)
"""

from __future__ import annotations

import json
import os
import urllib.request

# ER data_type (simplified SQL Server / postgres / bigquery) -> grounding vocab.
# Unknown types fall through to "string", same as every other grounding path.
_CATALOG_TYPE = {
    "tinyint": "short", "smallint": "short",
    "int": "integer", "integer": "integer",
    "bigint": "long",
    "decimal": "decimal", "numeric": "decimal", "money": "decimal", "smallmoney": "decimal",
    "float": "double", "real": "double", "double": "double", "double precision": "double",
    "bit": "boolean", "boolean": "boolean", "bool": "boolean",
    "date": "date",
    "datetime": "timestamp", "datetime2": "timestamp", "smalldatetime": "timestamp",
    "datetimeoffset": "timestamp", "timestamp": "timestamp",
    "timestamp without time zone": "timestamp", "timestamp with time zone": "timestamp",
    "time": "string",
    "char": "string", "varchar": "string", "nvarchar": "string", "nchar": "string",
    "text": "string", "ntext": "string", "character varying": "string", "character": "string",
    "uniqueidentifier": "string", "uuid": "string", "xml": "string",
    "json": "string", "jsonb": "string",
}


def _map(data_type: str) -> str:
    t = (data_type or "").strip().lower()
    t = t.split("(", 1)[0].strip()  # numeric(18,2) -> numeric (feed may not have simplified)
    return _CATALOG_TYPE.get(t, "string")


def fetch(source_id: str) -> "dict | None":
    """The ER catalog (DatabaseSchema JSON) for `source_id`, or None on any miss."""
    base = os.environ.get("ER_CATALOG_URL")
    if not base:
        return None
    try:
        if base.startswith("http"):
            url = f"{base.rstrip('/')}/catalog/{source_id}"
            with urllib.request.urlopen(url, timeout=5) as r:  # noqa: S310 (configured URL)
                return json.load(r)
        with open(os.path.join(base, f"{source_id}.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 — never block planning; fall back to live probe
        return None


# ER connection_config "type" -> az_agent SourceFormat value + the connection
# fields to seed onto a LogicalSource. Only NON-SECRET identity crosses the
# catalog (host/db/port/project) — credentials live in az_agent's own config.
def connection(schema: dict, fmt: str) -> "dict | None":
    """Connection identity for a source of az_agent format `fmt` (e.g. 'postgres'),
    pulled from the catalog's sanitized `connections`. Returns the LogicalSource
    fields to fill (server/database/port for postgres; gcp_project for bigquery),
    or None when the catalog carries no matching connection."""
    for c in schema.get("connections") or []:
        t = (c.get("type") or "").lower()
        if fmt == "postgres" and t == "postgres":
            out = {"server": c.get("host"), "database": c.get("database")}
            if c.get("port"):
                out["port"] = str(c["port"])
            return {k: v for k, v in out.items() if v}
        if fmt == "sql_table" and t == "sqlserver":
            out = {"server": c.get("host"), "database": c.get("database")}
            return {k: v for k, v in out.items() if v}
        if fmt == "bigquery" and t == "bigquery" and c.get("project_id"):
            return {"gcp_project": c["project_id"]}
    return None


def columns(schema: dict, table: str) -> "list[dict]":
    """[{name, type}] for `table` within a fetched catalog. `table` is
    'schema.table' or bare 'table' — matched on table_name (schema optional).
    [] when the table is not in the catalog."""
    want_schema, _, want_tbl = table.rpartition(".")
    want_schema, want_tbl = want_schema.lower(), want_tbl.lower()
    for t in schema.get("tables", []):
        if (t.get("table_name") or "").lower() != want_tbl:
            continue
        sn = (t.get("schema_name") or "").lower()
        if want_schema and sn and sn != want_schema:
            continue
        out = []
        for c in t.get("columns", []):
            name = c.get("name") or c.get("column_name")
            if name:
                out.append({"name": name, "type": _map(c.get("data_type") or c.get("type"))})
        return out
    return []
