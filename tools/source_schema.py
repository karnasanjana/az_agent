"""Read the SCHEMA of an external source before planning — the "read schema
first" discovery step. Thin equivalents of the read-only tools in the reference
MCP servers (Dataverse-MCP, github-mcp-server, sharepoint-mcp), calling the same
underlying APIs directly. No bulk data — just column names + types for grounding.

Discovery tools (what a source-discovery agent would expose, read-only):
    dataverse_tables(env_url)                 -> [ {logical, set, label, rows?} ]
    dataverse_schema(env_url, logical_name)   -> [ {name, type} ]     (from metadata)
    github_schema(raw_url)                     -> [ {name, type:string} ] (CSV header)
    sharepoint_list_schema(host, path, list)   -> [ {name, type} ]     (Graph columns)

CLI:
    python tools/source_schema.py dataverse account
    python tools/source_schema.py github https://raw.githubusercontent.com/.../file.csv
    python tools/source_schema.py sharepoint <host> <site_path> <list>
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

def github_schema(raw_url: str) -> list[dict]:
    """CSV header from a raw GitHub URL. Types are string (grounding refines from
    sampled rows later, same as any http_csv source)."""
    with urllib.request.urlopen(raw_url, timeout=30) as resp:
        head = resp.read(64 * 1024)
    text = head.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text else ""
    names = [c.strip() for c in next(csv.reader(io.StringIO(first)))] if first else []
    return [{"name": n, "type": "string"} for n in names if n]


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
    sid = site["id"]
    code, cols = _get(f"{g}/sites/{sid}/lists/{urllib.parse.quote(list_name)}/columns", tok)
    if code != 200:
        raise RuntimeError(f"sharepoint columns: HTTP {code} {json.dumps(cols)[:200]}")
    out = []
    for c in cols.get("value", []):
        if c.get("hidden") or c.get("readOnly"):
            continue
        kind = next((k for k in _SP_TYPE if k in c), "text")
        out.append({"name": c.get("name"), "type": _SP_TYPE.get(kind, "string")})
    return out


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
    else:
        sys.exit(f"unknown source '{kind}'")
