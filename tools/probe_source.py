"""Probe whether THIS app registration can actually read Dataverse / SharePoint.

Run it, read the verdict. It uses the same AZURE_* service-principal creds the
deployer uses, gets a token for each source's scope, and makes one real read.
Whatever fails tells us exactly which permission/consent is missing — no guessing.

    python tools/probe_source.py

Set these in .env (or the shell). App reg (you already have these):
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET

Dataverse (fill to test it):
    DATAVERSE_URL      e.g. https://orgXXXX.crm.dynamics.com
    DATAVERSE_TABLE    optional entity-set, e.g. accounts  (else just WhoAmI)

SharePoint via Graph (fill to test it):
    SHAREPOINT_HOSTNAME   e.g. contoso.sharepoint.com
    SHAREPOINT_SITE_PATH  e.g. /sites/Finance
    SHAREPOINT_LIST       optional list display name (else just lists the lists)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Load .env the same way config.py does, then reuse its loader if present.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import _load_dotenv  # type: ignore

    _load_dotenv()
except Exception:  # noqa: BLE001 — probe must run even standalone
    pass


def _cred_env(name: str) -> str | None:
    """Source app reg first (SOURCE_*), else fall back to the deploy SP (AZURE_*)."""
    return os.environ.get(f"SOURCE_{name}") or os.environ.get(f"AZURE_{name}")


def _token(scope: str) -> str:
    from azure.identity import ClientSecretCredential

    cred = ClientSecretCredential(
        tenant_id=_cred_env("TENANT_ID"),
        client_id=_cred_env("CLIENT_ID"),
        client_secret=_cred_env("CLIENT_SECRET"),
    )
    return cred.get_token(scope).token


def _get(url: str, token: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(body)
        except Exception:  # noqa: BLE001
            pass
        return e.code, {"error_body": body}


def _cols(row: dict) -> list[str]:
    return [k for k in row if not k.startswith("@") and not k.startswith("_")][:12]


def discover_dataverse() -> list[str]:
    """Ask the Global Discovery Service which environments this app can reach.
    Works app-only once the app is an Application User in at least one env."""
    try:
        tok = _token("https://globaldisco.crm.dynamics.com/.default")
    except Exception as e:  # noqa: BLE001
        print(f"  discovery token FAILED: {e}")
        return []
    code, data = _get(
        "https://globaldisco.crm.dynamics.com/api/discovery/v2.0/Instances", tok)
    if code != 200:
        print(f"  discovery -> HTTP {code}: {json.dumps(data)[:300]}")
        return []
    urls = [i["ApiUrl"].rstrip("/") for i in data.get("value", []) if i.get("ApiUrl")]
    envs = [f"{i.get('FriendlyName')} ({i.get('ApiUrl')})" for i in data.get("value", [])]
    print(f"  discovered {len(urls)} environment(s): {envs}")
    return urls


def probe_dataverse() -> None:
    url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not url:
        print("Dataverse: no DATAVERSE_URL — trying Global Discovery...")
        found = discover_dataverse()
        if not found:
            print("  (set DATAVERSE_URL manually if discovery is blocked)\n")
            return
        url = found[0]
        print(f"  testing first environment: {url}")
    print(f"Dataverse: {url}")
    try:
        tok = _token(f"{url}/.default")
    except Exception as e:  # noqa: BLE001
        print(f"  token FAILED: {e}\n")
        return
    api = f"{url}/api/data/v9.2"
    code, who = _get(f"{api}/WhoAmI", tok)
    if code != 200:
        print(f"  WhoAmI -> HTTP {code}. {_hint_dataverse(code)}")
        print(f"  detail: {json.dumps(who)[:400]}\n")
        return
    print(f"  WhoAmI OK  (UserId={who.get('UserId', '?')})  -> app IS a valid Application User")
    table = os.environ.get("DATAVERSE_TABLE", "").strip()
    if not table:
        print("  (set DATAVERSE_TABLE to also read rows + see the schema)\n")
        return
    code, data = _get(f"{api}/{table}?$top=3", tok)
    if code != 200:
        print(f"  read '{table}' -> HTTP {code}. Role lacks Read on this table? {json.dumps(data)[:300]}\n")
        return
    rows = data.get("value", [])
    print(f"  read '{table}' OK  ({len(rows)} rows). Columns: {_cols(rows[0]) if rows else '(no rows)'}\n")


def _hint_dataverse(code: int) -> str:
    if code in (401, 403):
        return ("App reg is NOT an Application User in this environment (or lacks a "
                "security role). Add it in Power Platform admin center > Environment > "
                "Settings > Users+permissions > Application users.")
    return "Check DATAVERSE_URL is the environment (org) URL."


def probe_sharepoint() -> None:
    host = os.environ.get("SHAREPOINT_HOSTNAME", "").strip()
    site_path = os.environ.get("SHAREPOINT_SITE_PATH", "").strip()
    print("SharePoint:")
    try:
        tok = _token("https://graph.microsoft.com/.default")
    except Exception as e:  # noqa: BLE001
        print(f"  token FAILED: {e}\n")
        return
    g = "https://graph.microsoft.com/v1.0"
    # No site given? Try to discover the tenant's SharePoint root hostname.
    if not host or not site_path:
        code, root = _get(f"{g}/sites/root", tok)
        if code == 200:
            wu = root.get("webUrl", "")
            print(f"  root site OK: {wu}  (hostname = {root.get('siteCollection', {}).get('hostname')})")
            print("  -> set SHAREPOINT_HOSTNAME to that hostname and SHAREPOINT_SITE_PATH to a /sites/... path\n")
        else:
            print(f"  /sites/root -> HTTP {code}. {_hint_sharepoint(code)}")
            print("  (Sites.Selected can't enumerate — you must supply the exact site URL)\n")
        return
    print(f"  {host}{site_path}")
    code, site = _get(f"{g}/sites/{host}:{site_path}", tok)
    if code != 200:
        print(f"  resolve site -> HTTP {code}. {_hint_sharepoint(code)}")
        print(f"  detail: {json.dumps(site)[:400]}\n")
        return
    site_id = site.get("id", "")
    print(f"  site OK  (id={site_id.split(',')[1] if ',' in site_id else site_id})")
    list_name = os.environ.get("SHAREPOINT_LIST", "").strip()
    if not list_name:
        code, lists = _get(f"{g}/sites/{site_id}/lists?$select=displayName&$top=25", tok)
        names = [l.get("displayName") for l in lists.get("value", [])]
        print(f"  lists ({len(names)}): {names}\n")
        return
    q = f"{g}/sites/{site_id}/lists/{urllib.parse.quote(list_name)}/items?$expand=fields&$top=3"
    code, data = _get(q, tok)
    if code != 200:
        print(f"  read list '{list_name}' -> HTTP {code}. {json.dumps(data)[:300]}\n")
        return
    items = data.get("value", [])
    fields = list(items[0].get("fields", {}).keys())[:12] if items else "(no items)"
    print(f"  read '{list_name}' OK  ({len(items)} items). Fields: {fields}\n")


def _hint_sharepoint(code: int) -> str:
    if code in (401, 403):
        return ("App reg lacks admin-consented Graph app permission (Sites.Read.All or "
                "Sites.Selected). If Sites.Selected, the site must also be granted to "
                "this app. Grant admin consent in Entra > App registrations > API permissions.")
    if code == 404:
        return "Site path not found — check SHAREPOINT_HOSTNAME and SHAREPOINT_SITE_PATH."
    return ""


if __name__ == "__main__":
    import urllib.parse  # used by probe_sharepoint

    missing = [n for n in ("TENANT_ID", "CLIENT_ID", "CLIENT_SECRET") if not _cred_env(n)]
    if missing:
        sys.exit("Missing app-registration creds: set SOURCE_" + ", SOURCE_".join(missing)
                 + " (or AZURE_*) in .env.")
    print("=" * 70)
    probe_dataverse()
    probe_sharepoint()
    print("=" * 70)
    print("401/403 = permission/consent gap (see hint). 200 = we can land it to bronze.")
