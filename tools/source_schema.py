"""Read the SCHEMA of an external source before planning — the "read schema
first" discovery step. Thin equivalents of the read-only tools in the reference
MCP servers (Dataverse-MCP, github-mcp-server, sharepoint-mcp), calling the same
underlying APIs directly. No bulk data — just column names + types for grounding.

Discovery tools (what a source-discovery agent would expose, read-only):
    dataverse_tables(env_url)                 -> [ {logical, set, label, rows?} ]
    dataverse_schema(env_url, logical_name)   -> [ {name, type} ]     (from metadata)
    github_schema(raw_url)                     -> [ {name, type:string} ] (CSV header)
    sharepoint_list_schema(host, path, list)   -> [ {name, type} ]     (Graph columns)
    postgres_schema(table)                     -> [ {name, type} ]     (information_schema)
    bigquery_schema(dataset.table)             -> [ {name, type} ]     (BQ metadata)
    gcs_schema(bucket/path.csv)                -> [ {name, type:string} ] (CSV header)

CLI:
    python tools/source_schema.py dataverse account
    python tools/source_schema.py github https://raw.githubusercontent.com/.../file.csv
    python tools/source_schema.py sharepoint <host> <site_path> <list>
    python tools/source_schema.py postgres [schema.]table          # env: PG_* / PG_DSN
    python tools/source_schema.py bigquery [project.]dataset.table  # env: GCP_PROJECT + ADC
    python tools/source_schema.py gcs bucket/path/to/file.csv       # ADC
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_source import _get, _token  # noqa: E402  (proven token/GET helpers)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import _load_dotenv  # type: ignore

    _load_dotenv()
except Exception:  # noqa: BLE001
    pass


# --- Dataverse ------------------------------------------------------------- #

# Dataverse AttributeType -> our grounding type vocabulary.
_DV_TYPE = {
    "String": "string", "Memo": "string", "Boolean": "boolean",
    "Integer": "integer", "BigInt": "long",
    "Decimal": "decimal", "Double": "double", "Money": "decimal",
    "DateTime": "timestamp",
    "Lookup": "string", "Customer": "string", "Owner": "string",
    "Uniqueidentifier": "string", "Picklist": "integer",
    "State": "integer", "Status": "integer",
}


def _dv_api(env_url: str) -> str:
    return f"{env_url.rstrip('/')}/api/data/v9.2"


def dataverse_schema(env_url: str, logical_name: str) -> list[dict]:
    """Real column list + types from Dataverse metadata — works with 0 rows."""
    tok = _token(f"{env_url.rstrip('/')}/.default")
    url = (f"{_dv_api(env_url)}/EntityDefinitions(LogicalName='{logical_name}')"
           f"/Attributes?$select=LogicalName,AttributeType")
    code, data = _get(url, tok)
    if code != 200:
        raise RuntimeError(f"dataverse_schema {logical_name}: HTTP {code} {json.dumps(data)[:300]}")
    cols = [{"name": a["LogicalName"], "type": _DV_TYPE.get(a.get("AttributeType"), "string")}
            for a in data.get("value", []) if a.get("LogicalName")]
    return sorted(cols, key=lambda c: c["name"])


def dataverse_tables(env_url: str) -> list[dict]:
    tok = _token(f"{env_url.rstrip('/')}/.default")
    url = (f"{_dv_api(env_url)}/EntityDefinitions?$select=LogicalName,EntitySetName,"
           f"DisplayName&$filter=IsIntersect eq false and IsPrivate eq false").replace(" ", "%20")
    code, data = _get(url, tok)
    if code != 200:
        raise RuntimeError(f"dataverse_tables: HTTP {code}")
    out = []
    for e in data.get("value", []):
        label = ((e.get("DisplayName") or {}).get("UserLocalizedLabel") or {}).get("Label", "")
        out.append({"logical": e.get("LogicalName"), "set": e.get("EntitySetName"), "label": label})
    return out


# --- GitHub (raw CSV over HTTP) -------------------------------------------- #

def _csv_header_cols(data: bytes) -> list[dict]:
    """Columns from a CSV header row. Types are string — grounding refines from
    sampled rows later, same as any http_csv source."""
    text = data.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text else ""
    names = [c.strip() for c in next(csv.reader(io.StringIO(first)))] if first else []
    return [{"name": n, "type": "string"} for n in names if n]


def github_schema(raw_url: str) -> list[dict]:
    """CSV header from a raw GitHub URL."""
    with urllib.request.urlopen(raw_url, timeout=30) as resp:
        return _csv_header_cols(resp.read(64 * 1024))


# --- Postgres (local or hosted; incl. GCP Cloud SQL) ----------------------- #

# information_schema.columns.data_type -> our grounding type vocabulary.
_PG_TYPE = {
    "smallint": "short", "integer": "integer", "bigint": "long",
    "numeric": "decimal", "decimal": "decimal",
    "real": "double", "double precision": "double",
    "boolean": "boolean",
    "date": "date",
    "timestamp without time zone": "timestamp",
    "timestamp with time zone": "timestamp",
    "character varying": "string", "character": "string", "text": "string",
    "uuid": "string", "json": "string", "jsonb": "string",
}


def _pg_connect():
    """Connect to Postgres from env. PG_DSN wins; else PG_HOST/PORT/DATABASE/
    USER/PASSWORD (defaults target a local server). Shared by inject_to_bronze."""
    import psycopg  # lazy: pip install "psycopg[binary]" only when Postgres is used

    dsn = os.environ.get("PG_DSN")
    if dsn:
        return psycopg.connect(dsn)
    return psycopg.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=os.environ.get("PG_PORT", "5432"),
        dbname=os.environ.get("PG_DATABASE", "postgres"),
        user=os.environ.get("PG_USER", "postgres"),
        password=os.environ.get("PG_PASSWORD", ""),
    )


def postgres_schema(table: str) -> list[dict]:
    """Real column list + types from information_schema — works with 0 rows.
    `table` is 'schema.table' or bare 'table' (defaults to schema 'public')."""
    schema, _, tbl = table.rpartition(".")
    schema = schema or "public"
    with _pg_connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
            (schema, tbl),
        )
        rows = cur.fetchall()
    if not rows:
        raise RuntimeError(f"postgres_schema {table}: no columns (schema '{schema}', wrong name?)")
    return [{"name": n, "type": _PG_TYPE.get(t, "string")} for n, t in rows]


# --- Google BigQuery ------------------------------------------------------- #

# BigQuery field_type -> our grounding type vocabulary.
_BQ_TYPE = {
    "STRING": "string", "BYTES": "string",
    "INTEGER": "long", "INT64": "long",
    "FLOAT": "double", "FLOAT64": "double",
    "NUMERIC": "decimal", "BIGNUMERIC": "decimal",
    "BOOLEAN": "boolean", "BOOL": "boolean",
    "TIMESTAMP": "timestamp", "DATETIME": "timestamp",
    "DATE": "date", "TIME": "string",
}


def _gcp_credentials():
    """Keyless GCP auth from the user's gcloud login — mirrors ER-Diagram's
    approach (`gcloud auth print-access-token`). Works with a plain `gcloud auth
    login` (no ADC login, no downloaded service-account key). Returns None to let
    the client fall back to Application Default Credentials (a key file or
    `gcloud auth application-default login`) when gcloud isn't on PATH."""
    import shutil
    import subprocess

    exe = shutil.which("gcloud")  # resolves gcloud.CMD on Windows
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "auth", "print-access-token"],
            capture_output=True, text=True, timeout=20,
        )
        token = out.stdout.strip()
        if token:
            from google.oauth2.credentials import Credentials

            return Credentials(token=token)
    except Exception:  # noqa: BLE001 — fall back to ADC / key
        pass
    return None


def bigquery_schema(ref: str) -> list[dict]:
    """Column list + types from BigQuery table metadata. `ref` is
    'dataset.table' or 'project.dataset.table'. Keyless auth via the user's
    gcloud login (_gcp_credentials), falling back to ADC / a service-account key."""
    from google.cloud import bigquery  # lazy import

    client = bigquery.Client(
        project=os.environ.get("GCP_PROJECT") or None, credentials=_gcp_credentials()
    )
    table = client.get_table(ref)
    return [{"name": f.name, "type": _BQ_TYPE.get(f.field_type, "string")} for f in table.schema]


# --- Google Cloud Storage (CSV object) ------------------------------------- #

def _gcs_blob(path: str):
    """A GCS blob handle for 'bucket/path/to/file' (a leading gs:// is fine)."""
    from google.cloud import storage  # lazy import

    p = path[5:] if path.startswith("gs://") else path
    bucket, _, name = p.partition("/")
    if not name:
        raise ValueError(f"gcs path must be 'bucket/path/to/file', got: {path}")
    client = storage.Client(
        project=os.environ.get("GCP_PROJECT") or None, credentials=_gcp_credentials()
    )
    return client.bucket(bucket).blob(name)


def gcs_schema(path: str) -> list[dict]:
    """CSV header from a GCS object 'bucket/path/to/file.csv'. Auth via ADC."""
    head = _gcs_blob(path).download_as_bytes(start=0, end=64 * 1024 - 1)
    return _csv_header_cols(head)


# --- SharePoint list (Graph) ----------------------------------------------- #

_SP_TYPE = {"text": "string", "note": "string", "number": "double",
            "currency": "decimal", "dateTime": "timestamp", "boolean": "boolean",
            "choice": "string", "lookup": "string", "personOrGroup": "string"}


def sharepoint_list_schema(host: str, site_path: str, list_name: str) -> list[dict]:
    tok = _token("https://graph.microsoft.com/.default")
    g = "https://graph.microsoft.com/v1.0"
    code, site = _get(f"{g}/sites/{host}:{site_path}", tok)
    if code != 200:
        raise RuntimeError(f"sharepoint site: HTTP {code} {json.dumps(site)[:200]}")
    lst = f"{g}/sites/{site['id']}/lists/{urllib.parse.quote(list_name)}"
    code, cols = _get(f"{lst}/columns", tok)
    if code != 200:
        raise RuntimeError(f"sharepoint columns: HTTP {code} {json.dumps(cols)[:200]}")
    type_of = {}
    for c in cols.get("value", []):
        kind = next((k for k in _SP_TYPE if k in c), "text")
        type_of[c.get("name")] = _SP_TYPE.get(kind, "string")
    code, items = _get(f"{lst}/items?$expand=fields&$top=1", tok)
    if code != 200:
        raise RuntimeError(f"sharepoint items: HTTP {code} {json.dumps(items)[:200]}")
    fields = ((items.get("value") or [{}])[0].get("fields") or {})
    # Membership = /columns (the STABLE full set — includes columns null in the
    # sampled row) UNIONed with the item's `fields` (adds the readOnly `id` KEY
    # the mover writes). Exclude OData annotations (@) and SharePoint's
    # compliance/version internals (_UIVersionString, _ComplianceFlags, …):
    # they appear in item fields but are leading-underscore identifiers the
    # Data Flow DSL rejects (DF-DSL-001), and the mover skips them too.
    def _ok(n: str) -> bool:
        return bool(n) and not n.startswith("@") and not n.startswith("_")

    names: list[str] = []
    for c in cols.get("value", []):
        n = c.get("name")
        if _ok(n) and not c.get("hidden") and n not in names:
            names.append(n)
    for k in fields:
        if _ok(k) and k not in names:
            names.append(k)
    return [{"name": n, "type": type_of.get(n, "string")} for n in names]


if __name__ == "__main__":
    import urllib.parse  # noqa: F811  (used by sharepoint)

    if len(sys.argv) < 3:
        sys.exit(__doc__)
    kind, arg = sys.argv[1], sys.argv[2]
    if kind == "dataverse":
        env = os.environ["DATAVERSE_URL"]
        print(f"# {arg} schema ({env})")
        for c in dataverse_schema(env, arg):
            print(f"  {c['name']:<40} {c['type']}")
    elif kind == "github":
        for c in github_schema(arg):
            print(f"  {c['name']:<40} {c['type']}")
    elif kind == "sharepoint":
        host, path, lst = sys.argv[2], sys.argv[3], sys.argv[4]
        for c in sharepoint_list_schema(host, path, lst):
            print(f"  {c['name']:<40} {c['type']}")
    elif kind == "postgres":
        for c in postgres_schema(arg):
            print(f"  {c['name']:<40} {c['type']}")
    elif kind == "bigquery":
        for c in bigquery_schema(arg):
            print(f"  {c['name']:<40} {c['type']}")
    elif kind == "gcs":
        for c in gcs_schema(arg):
            print(f"  {c['name']:<40} {c['type']}")
    else:
        sys.exit(f"unknown source '{kind}'")
