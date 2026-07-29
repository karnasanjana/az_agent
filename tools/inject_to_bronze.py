"""Data-injecting link: copy an external source's rows into the BRONZE layer as
CSV, so grounding + the silver/gold flows have real data to work on.

This is the BOOTSTRAP mover (quick, agent-side). The PRODUCTION mover is an ADF
Copy activity emitted by the compiler — same source, same bronze target, but it
runs in Azure on a schedule without an agent present. Use this to prove the flow
and seed bronze; use the pipeline for real scheduled loads.

    python tools/inject_to_bronze.py dataverse account         # -> mock bronze (safe)
    python tools/inject_to_bronze.py github <raw_csv_url> [entity]
    python tools/inject_to_bronze.py sharepoint <host> <path> <list>
    python tools/inject_to_bronze.py postgres [schema.]table [entity]   # env: PG_* / PG_DSN
    python tools/inject_to_bronze.py bigquery [project.]dataset.table [entity]  # GCP_PROJECT + ADC
    python tools/inject_to_bronze.py gcs bucket/path/to/file.csv [entity]       # ADC
    ... add  --real  to write to the real ADLS/Blob bronze container instead.

Default target is mock_tenant/storage/bronze/<entity>/<entity>.csv (local, no
Azure side effects). --real uploads to the configured storage account's bronze
container.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_source import _get, _token  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import _load_dotenv  # type: ignore

    _load_dotenv()
except Exception:  # noqa: BLE001
    pass

_MAX_ROWS = int(os.environ.get("INJECT_MAX_ROWS", "50000"))  # ponytail: cap, page if you need more


# --- pull rows from each source -> (columns, rows) ------------------------- #

def _pull_dataverse(env_url: str, entity_set: str) -> tuple[list[str], list[dict]]:
    tok = _token(f"{env_url.rstrip('/')}/.default")
    url = f"{env_url.rstrip('/')}/api/data/v9.2/{entity_set}?$top=5000"
    rows: list[dict] = []
    while url and len(rows) < _MAX_ROWS:
        code, data = _get(url, tok)
        if code != 200:
            raise RuntimeError(f"dataverse read {entity_set}: HTTP {code}")
        for r in data.get("value", []):
            rows.append({k: v for k, v in r.items() if "@" not in k})
        url = data.get("@odata.nextLink")
    cols: list[str] = []
    for r in rows:  # union of keys, first-seen order
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols, rows


def _pull_github(raw_url: str) -> bytes:
    with urllib.request.urlopen(raw_url, timeout=60) as resp:
        return resp.read()


def _pull_postgres(table: str) -> tuple[list[str], list[dict]]:
    from source_schema import _pg_connect  # shared connection helper

    schema, _, tbl = table.rpartition(".")
    ref = f'"{schema}"."{tbl}"' if schema else f'"{tbl}"'  # quote identifiers
    with _pg_connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {ref} LIMIT {_MAX_ROWS}")  # ref is operator input, not web-facing
        cols = [d.name for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return cols, rows


def _pull_bigquery(ref: str) -> tuple[list[str], list[dict]]:
    from google.cloud import bigquery  # lazy import

    from source_schema import _gcp_credentials  # keyless gcloud-login auth

    client = bigquery.Client(
        project=os.environ.get("GCP_PROJECT") or None, credentials=_gcp_credentials()
    )
    table = client.get_table(ref)
    cols = [f.name for f in table.schema]
    rows = [dict(r.items()) for r in client.list_rows(table, max_results=_MAX_ROWS)]
    return cols, rows


def _pull_gcs(path: str) -> bytes:
    from source_schema import _gcs_blob  # byte-for-byte, like _pull_github

    return _gcs_blob(path).download_as_bytes()  # ponytail: whole object; assumes CSV bronze target


def _pull_sharepoint(host: str, path: str, lst: str) -> tuple[list[str], list[dict]]:
    tok = _token("https://graph.microsoft.com/.default")
    g = "https://graph.microsoft.com/v1.0"
    code, site = _get(f"{g}/sites/{host}:{path}", tok)
    if code != 200:
        raise RuntimeError(f"sharepoint site: HTTP {code}")
    import urllib.parse
    url = (f"{g}/sites/{site['id']}/lists/{urllib.parse.quote(lst)}"
           f"/items?$expand=fields&$top=5000")
    rows: list[dict] = []
    while url and len(rows) < _MAX_ROWS:
        code, data = _get(url, tok)
        if code != 200:
            raise RuntimeError(f"sharepoint items: HTTP {code}")
        for it in data.get("value", []):
            # Skip OData annotations (@) and SharePoint compliance/version
            # internals (_UIVersionString, …): leading-underscore names break
            # the Data Flow DSL, and the schema reader excludes them too.
            rows.append({k: v for k, v in (it.get("fields") or {}).items()
                         if not (k.startswith("@") or k.startswith("_"))})
        url = data.get("@odata.nextLink")
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols, rows


def _to_csv(cols: list[str], rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    return buf.getvalue().encode("utf-8")


# --- write to bronze (mock local, or real storage) ------------------------- #

def _write_mock(entity: str, data: bytes, container: str) -> str:
    from config import MOCK_TENANT_DIR
    path = os.path.join(MOCK_TENANT_DIR, "storage", container, entity, f"{entity}.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _write_real(entity: str, data: bytes, container: str) -> str:
    from config import (AzureConfig, get_blob_service_client, get_datalake_client,
                        storage_kind)
    cfg = AzureConfig.from_env()
    path = f"{entity}/{entity}.csv"
    if storage_kind() == "blob":
        svc = get_blob_service_client(cfg)
        cc = svc.get_container_client(container)
        if not cc.exists():
            cc.create_container()
        cc.get_blob_client(path).upload_blob(data, overwrite=True)
    else:
        svc = get_datalake_client(cfg)
        fs = svc.get_file_system_client(container)
        if not fs.exists():
            fs.create_file_system()
        fs.get_file_client(path).upload_data(data, overwrite=True)
    return f"{container}/{path} on {cfg.adls_account_name}"


def inject(kind: str, args: list[str], real: bool, container: str) -> None:
    if kind == "dataverse":
        entity_set = args[0]
        entity = entity_set  # e.g. 'accounts'
        cols, rows = _pull_dataverse(os.environ["DATAVERSE_URL"], entity_set)
        data = _to_csv(cols, rows)
        print(f"dataverse {entity_set}: {len(rows)} rows, {len(cols)} columns")
    elif kind == "github":
        raw_url = args[0]
        entity = args[1] if len(args) > 1 else raw_url.rstrip("/").split("/")[-1].rsplit(".", 1)[0]
        data = _pull_github(raw_url)
        print(f"github {raw_url}: {len(data)} bytes")
    elif kind == "sharepoint":
        host, path, lst = args[0], args[1], args[2]
        entity = lst.lower().replace(" ", "_")
        cols, rows = _pull_sharepoint(host, path, lst)
        data = _to_csv(cols, rows)
        print(f"sharepoint {lst}: {len(rows)} rows, {len(cols)} columns")
    elif kind == "postgres":
        table = args[0]
        entity = args[1] if len(args) > 1 else table.rpartition(".")[2]
        cols, rows = _pull_postgres(table)
        data = _to_csv(cols, rows)
        print(f"postgres {table}: {len(rows)} rows, {len(cols)} columns")
    elif kind == "bigquery":
        ref = args[0]
        entity = args[1] if len(args) > 1 else ref.rpartition(".")[2]
        cols, rows = _pull_bigquery(ref)
        data = _to_csv(cols, rows)
        print(f"bigquery {ref}: {len(rows)} rows, {len(cols)} columns")
    elif kind == "gcs":
        path = args[0]
        entity = args[1] if len(args) > 1 else path.rstrip("/").split("/")[-1].rsplit(".", 1)[0]
        data = _pull_gcs(path)
        print(f"gcs {path}: {len(data)} bytes")
    else:
        sys.exit(f"unknown source '{kind}'")

    where = _write_real(entity, data, container) if real else _write_mock(entity, data, container)
    print(f"-> wrote {container}: {where}")


if __name__ == "__main__":
    real = "--real" in sys.argv
    container = "bronze"
    rest = []
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--real":
            continue
        if a == "--container":
            container = next(it, "bronze")
            continue
        rest.append(a)
    if len(rest) < 2:
        sys.exit(__doc__)
    inject(rest[0], rest[1:], real, container)
