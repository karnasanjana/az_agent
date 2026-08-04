"""SharePoint schema extraction service.

Reads a SharePoint site's lists (tables), their columns, and lookup columns
(relationships) via Microsoft Graph v1.0 with a delegated Bearer token.
Mirrors DataverseSchemaExtractor so the SSE API layer is identical.
"""
import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

import requests

from app.schemas.schema import (
    Column,
    DatabaseSchema,
    ExtractionProgress,
    ForeignKey,
    Table,
)
from app.security.logging import get_logger

logger = get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
_GRAPH = "https://graph.microsoft.com/v1.0"

# SharePoint column facet -> simplified SQL-style type. Graph reports a column's
# type by which facet object is present (text, number, ...), not a type string.
_FACET_TYPE: dict[str, str] = {
    "text": "nvarchar",
    "number": "float",
    "currency": "decimal",
    "boolean": "bit",
    "dateTime": "datetime",
    "choice": "nvarchar",
    "lookup": "int",
    "personOrGroup": "nvarchar",
    "hyperlinkOrPicture": "nvarchar",
    "term": "nvarchar",
    "contentApprovalStatus": "nvarchar",
}


def _map_column_type(col: dict) -> str:
    """Pick the SQL-style type from whichever facet the Graph column carries."""
    for facet, sql in _FACET_TYPE.items():
        if col.get(facet) is not None:
            return sql
    return "nvarchar"


def _object_id(name: str) -> int:
    """Stable positive int id from a list name (matches Dataverse extractor)."""
    return int.from_bytes(hashlib.md5(name.encode()).digest()[:8], "big") & 0x7FFFFFFF


class SharePointSchemaExtractor:
    """Extract schema for the selected lists in one SharePoint site via Graph."""

    def __init__(
        self,
        site_url: str,
        access_token: str,
        lists: list[str] | None = None,
    ):
        self.site_url = site_url.strip().rstrip("/")
        self.access_token = access_token
        self.lists = lists or []
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        self._site_id: str | None = None
        self._tables: list[Table] = []
        self._foreign_keys: list[ForeignKey] = []
        # list display-name -> Graph list id, filled in list_lists()/_resolve.
        self._name_to_id: dict[str, str] = {}
        self._id_to_name: dict[str, str] = {}
        self._start_time: float = 0

    def _get(self, url: str) -> dict:
        r = requests.get(url, headers=self._headers, timeout=60)
        r.raise_for_status()
        return r.json()

    def _resolve_site_id(self) -> str:
        """Resolve the Graph site id from the site URL (host + server path)."""
        if self._site_id:
            return self._site_id
        host, _, path = self.site_url.partition("/")
        # /sites/{host}:/sites/Sales  (path omitted -> the root site of the host)
        suffix = f"{host}:/{path}" if path else host
        data = self._get(f"{_GRAPH}/sites/{suffix}?$select=id")
        self._site_id = data["id"]
        return self._site_id

    def list_lists(self) -> list[dict]:
        """List the (non-hidden, generic) lists in the site, sorted by name."""
        site_id = self._resolve_site_id()
        data = self._get(
            f"{_GRAPH}/sites/{site_id}/lists"
            "?$select=id,name,displayName,list&$top=200"
        )
        results = []
        for lst in data.get("value", []):
            meta = lst.get("list") or {}
            if meta.get("hidden"):
                continue
            # Keep user lists (genericList); skip system template libraries.
            if meta.get("template") not in (None, "genericList", "documentLibrary"):
                continue
            name = lst.get("name") or lst.get("displayName") or lst["id"]
            self._name_to_id[name] = lst["id"]
            self._id_to_name[lst["id"]] = name
            results.append({
                "name": name,
                "display_name": lst.get("displayName", name),
                "is_custom": True,
                "table_count": 1,
            })
        results.sort(key=lambda x: x["name"])
        return results

    async def extract_with_progress(self) -> AsyncGenerator[ExtractionProgress, None]:
        self._start_time = time.monotonic()
        loop = asyncio.get_event_loop()

        yield ExtractionProgress(
            percentage=5, current_table=None,
            message="Connecting to SharePoint...", status="progress",
        )
        await asyncio.sleep(0)

        try:
            # Need the name<->id map to resolve lookups; list_lists fills it.
            await loop.run_in_executor(_executor, self.list_lists)
            selected_ids = {self._name_to_id.get(n) for n in self.lists}
            selected_ids.discard(None)

            total = len(self.lists)
            if total == 0:
                yield ExtractionProgress(
                    percentage=100, current_table=None,
                    message="No lists selected.", status="warning",
                )
                return

            for idx, name in enumerate(self.lists):
                yield ExtractionProgress(
                    percentage=10 + int(80 * idx / total),
                    current_table=name,
                    message=f"Reading columns for {name}",
                    status="progress",
                )
                await asyncio.sleep(0)

                table, fks = await loop.run_in_executor(
                    _executor, self._extract_list, name, selected_ids
                )
                self._tables.append(table)
                self._foreign_keys.extend(fks)

                yield ExtractionProgress(
                    percentage=10 + int(80 * (idx + 1) / total),
                    current_table=name,
                    message=f"Extracted {name} ({len(table.columns)} columns)",
                    status="progress",
                )
                await asyncio.sleep(0)

            yield ExtractionProgress(
                percentage=100, current_table=None,
                message="Extraction complete", status="complete",
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"SharePoint schema extraction failed: {e}")
            yield ExtractionProgress(
                percentage=0, current_table=None,
                message=f"Extraction failed: {str(e)}", status="error",
            )
            raise

    def _extract_list(
        self, name: str, selected_ids: set[str]
    ) -> tuple[Table, list[ForeignKey]]:
        """Read a list's columns; lookup columns to selected lists become FKs."""
        list_id = self._name_to_id.get(name)
        if not list_id:
            return Table(object_id=_object_id(name), schema_name="sharepoint",
                         table_name=name, columns=[], indexes=[], is_view=False), []
        site_id = self._resolve_site_id()
        data = self._get(f"{_GRAPH}/sites/{site_id}/lists/{list_id}/columns")

        columns: list[Column] = []
        fks: list[ForeignKey] = []
        for col in data.get("value", []):
            if col.get("hidden"):
                continue
            col_name = col.get("name", "")
            is_id = col_name.lower() == "id"
            columns.append(Column(
                name=col_name,
                data_type="int" if is_id else _map_column_type(col),
                is_nullable=not (col.get("required") or is_id),
                is_primary_key=is_id,
                is_identity=is_id,
            ))
            lookup = col.get("lookup")
            if lookup and lookup.get("listId") in selected_ids:
                target = self._id_to_name.get(lookup["listId"])
                if target:
                    fks.append(ForeignKey(
                        constraint_name=f"{name}_{col_name}_fk",
                        source_table=name, source_schema="sharepoint",
                        source_columns=[col_name],
                        target_table=target, target_schema="sharepoint",
                        target_columns=[lookup.get("columnName") or "id"],
                    ))

        return Table(object_id=_object_id(name), schema_name="sharepoint",
                     table_name=name, columns=columns, indexes=[], is_view=False), fks

    def get_result(self) -> DatabaseSchema:
        elapsed = time.monotonic() - self._start_time
        with_fk: set[str] = set()
        for fk in self._foreign_keys:
            with_fk.add(f"{fk.source_schema}.{fk.source_table}")
            with_fk.add(f"{fk.target_schema}.{fk.target_table}")
        standalone = sum(
            1 for t in self._tables
            if f"{t.schema_name}.{t.table_name}" not in with_fk
        )
        return DatabaseSchema(
            database_name="SharePoint",
            tables=self._tables,
            foreign_keys=self._foreign_keys,
            extraction_time_seconds=round(elapsed, 2),
            table_count=len(self._tables),
            standalone_table_count=standalone,
        )
