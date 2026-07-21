"""List the tables (entities) this app can see in Dataverse, so a BRD can name
them and grounding can read their schema. Reuses probe_source's token/GET.

    python tools/list_dataverse.py            # custom + common business tables
    python tools/list_dataverse.py all        # every user-facing table
    python tools/list_dataverse.py <name>     # columns of one entity set (e.g. accounts)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_source import _get, _token  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import _load_dotenv  # type: ignore

    _load_dotenv()
except Exception:  # noqa: BLE001
    pass

URL = os.environ.get("DATAVERSE_URL", "").rstrip("/")
API = f"{URL}/api/data/v9.2"


def list_tables(show_all: bool) -> None:
    tok = _token(f"{URL}/.default")
    q = (f"{API}/EntityDefinitions?$select=LogicalName,EntitySetName,DisplayName,"
         f"IsCustomEntity&$filter=IsIntersect eq false and IsPrivate eq false")
    code, data = _get(q.replace(" ", "%20"), tok)
    if code != 200:
        print(f"HTTP {code}: {json.dumps(data)[:400]}")
        return
    ents = data.get("value", [])
    custom = [e for e in ents if e.get("IsCustomEntity")]
    common_names = {"account", "contact", "lead", "opportunity", "product",
                    "invoice", "salesorder", "quote", "incident", "campaign",
                    "systemuser", "team", "businessunit"}
    common = [e for e in ents if e.get("LogicalName") in common_names]

    def count(entity_set: str) -> str:
        c, d = _get(f"{API}/{entity_set}?$count=true&$top=1", tok)
        n = d.get("@odata.count") if c == 200 else None
        return str(n) if n is not None else "?"

    print("\nRow counts for common business tables (what a BRD would target):")
    for e in sorted(common, key=lambda r: r.get("LogicalName", "")):
        print(f"  {e['LogicalName']:<14} set={e.get('EntitySetName', ''):<18} rows={count(e.get('EntitySetName',''))}")

    def show(title, rows):
        print(f"\n{title} ({len(rows)}):")
        for e in sorted(rows, key=lambda r: r.get("LogicalName", "")):
            label = (e.get("DisplayName", {}) or {}).get("UserLocalizedLabel", {})
            label = (label or {}).get("Label", "")
            print(f"  {e['LogicalName']:<30} set={e.get('EntitySetName', ''):<32} {label}")

    print(f"Total user-facing tables visible: {len(ents)}")
    show("CUSTOM tables (org-specific — most likely BRD targets)", custom)
    if show_all:
        show("ALL user-facing tables", ents)
    else:
        show("Common business tables", common)
        print("\n(run `python tools/list_dataverse.py all` to see every table)")


def list_columns(entity_set: str) -> None:
    tok = _token(f"{URL}/.default")
    code, data = _get(f"{API}/{entity_set}?$top=1", tok)
    if code != 200:
        print(f"HTTP {code}: {json.dumps(data)[:400]}")
        return
    rows = data.get("value", [])
    if not rows:
        print(f"'{entity_set}' has no rows to sample.")
        return
    cols = [k for k in rows[0] if not k.startswith("@")]
    print(f"'{entity_set}' — {len(cols)} columns:")
    for c in sorted(cols):
        print(f"  {c}")


if __name__ == "__main__":
    if not URL:
        sys.exit("Set DATAVERSE_URL in .env first.")
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg and arg != "all":
        list_columns(arg)
    else:
        list_tables(show_all=(arg == "all"))
