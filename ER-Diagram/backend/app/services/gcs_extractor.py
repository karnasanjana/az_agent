"""Google Cloud Storage schema extraction service.

Lists data files in a bucket and infers one table per file by sampling the first
chunk of each: CSV/TSV header + rows, JSON/JSONL first object, or a Parquet
footer (best-effort). Uses the Storage JSON API with the signed-in user's Google
token (devstorage.read_only). Mirrors the other SSE extractors.
"""
import asyncio
import csv
import hashlib
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

import requests

from app.schemas.schema import Column, DatabaseSchema, ExtractionProgress, Table
from app.security.logging import get_logger

logger = get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
_API = "https://storage.googleapis.com/storage/v1"
_DATA_EXT = (".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".parquet")
_SAMPLE_BYTES = 131072  # 128 KB is plenty for a header + a few rows


def _arrow_type(t: str) -> str:
    """Map a pyarrow type string to a SQL-style type."""
    t = t.lower()
    if "bool" in t:
        return "bit"
    if any(k in t for k in ("int", "uint")):
        return "int"
    if any(k in t for k in ("float", "double", "decimal")):
        return "float"
    if "timestamp" in t:
        return "datetime"
    if "date" in t:
        return "date"
    return "nvarchar"


def _object_id(name: str) -> int:
    return int.from_bytes(hashlib.md5(name.encode()).digest()[:8], "big") & 0x7FFFFFFF


def _table_name(object_name: str, prefix: str) -> str:
    """File path -> a table name: drop the prefix + extension, keep it readable."""
    name = object_name[len(prefix):] if prefix and object_name.startswith(prefix) else object_name
    name = name.strip("/")
    name = re.sub(r"\.[^.]+$", "", name)          # drop extension
    return re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "table"


def _infer_scalar(value) -> str:
    """SQL-style type from one sample value (or string cell)."""
    if isinstance(value, bool):
        return "bit"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if not isinstance(value, str):
        return "nvarchar"
    s = value.strip()
    if s == "":
        return "nvarchar"
    if re.fullmatch(r"[-+]?\d+", s):
        return "int"
    if re.fullmatch(r"[-+]?\d*\.\d+", s):
        return "float"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?", s):
        return "datetime" if ("T" in s or ":" in s) else "date"
    return "nvarchar"


class GcsSchemaExtractor:
    """One table per selected file; columns inferred from a sampled chunk."""

    def __init__(self, bucket: str, access_token: str, prefix: str = "",
                 files: list[str] | None = None):
        self.bucket = bucket
        self.prefix = prefix or ""
        self.access_token = access_token
        self.files = files or []
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._tables: list[Table] = []
        self._start_time: float = 0

    def list_files(self) -> list[dict]:
        """List data files (paged) under the bucket/prefix, sorted by name."""
        results, page_token = [], None
        while True:
            params = {"prefix": self.prefix, "maxResults": 1000}
            if page_token:
                params["pageToken"] = page_token
            r = requests.get(f"{_API}/b/{self.bucket}/o", headers=self._headers,
                             params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            for obj in data.get("items", []):
                name = obj.get("name", "")
                if name.endswith("/"):  # folder placeholder
                    continue
                if name.lower().endswith(_DATA_EXT):
                    results.append({"name": name, "display_name": name,
                                    "is_custom": True, "table_count": 1})
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        results.sort(key=lambda x: x["name"])
        return results

    def _sample(self, object_name: str) -> bytes:
        """Download the first chunk of an object (Range request)."""
        from urllib.parse import quote
        url = f"{_API}/b/{self.bucket}/o/{quote(object_name, safe='')}?alt=media"
        headers = {**self._headers, "Range": f"bytes=0-{_SAMPLE_BYTES - 1}"}
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        return r.content

    def _columns_for(self, object_name: str) -> list[Column]:
        low = object_name.lower()
        try:
            if low.endswith(".parquet"):
                return self._parquet_columns(object_name)
            sample = self._sample(object_name)
            if low.endswith((".json", ".jsonl", ".ndjson")):
                return self._json_columns(sample)
            delim = "\t" if low.endswith(".tsv") else ","
            return self._csv_columns(sample, delim)
        except Exception as e:  # noqa: BLE001 — a bad file must not kill the run
            logger.warning(f"GCS: could not infer columns for {object_name}: {e}")
            return []

    def _csv_columns(self, sample: bytes, delim: str) -> list[Column]:
        text = sample.decode("utf-8", errors="replace")
        # Drop a possibly-truncated last line from the range request.
        lines = text.splitlines()
        if len(lines) > 1:
            lines = lines[:-1]
        reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
        rows = list(reader)
        if not rows:
            return []
        header = rows[0]
        body = rows[1:11]  # up to 10 sample rows
        cols: list[Column] = []
        for i, name in enumerate(header):
            types = {_infer_scalar(r[i]) for r in body if i < len(r) and r[i] != ""}
            dtype = next(iter(types)) if len(types) == 1 else "nvarchar"
            cols.append(Column(name=(name or f"col_{i}").strip(), data_type=dtype,
                               is_nullable=True, is_primary_key=False, is_identity=False))
        return cols

    def _json_columns(self, sample: bytes) -> list[Column]:
        text = sample.decode("utf-8", errors="replace").lstrip()
        obj = None
        if text.startswith("["):
            # JSON array — grab the first complete object.
            m = re.search(r"\{.*?\}", text, re.S)
            if m:
                obj = json.loads(m.group(0))
        else:
            obj = json.loads(text.splitlines()[0])  # JSONL: first line
        if not isinstance(obj, dict):
            return []
        return [Column(name=str(k), data_type=_infer_scalar(v), is_nullable=True,
                       is_primary_key=False, is_identity=False) for k, v in obj.items()]

    def _parquet_columns(self, object_name: str) -> list[Column]:
        try:
            import pyarrow.parquet as pq  # optional dep
        except Exception:  # noqa: BLE001
            return []
        # Parquet metadata lives in the footer, so read the whole object.
        from urllib.parse import quote
        url = f"{_API}/b/{self.bucket}/o/{quote(object_name, safe='')}?alt=media"
        r = requests.get(url, headers=self._headers, timeout=120)
        r.raise_for_status()
        schema = pq.read_schema(io.BytesIO(r.content))
        return [Column(name=f.name, data_type=_arrow_type(str(f.type)),
                       is_nullable=True, is_primary_key=False, is_identity=False)
                for f in schema]

    async def extract_with_progress(self) -> AsyncGenerator[ExtractionProgress, None]:
        self._start_time = time.monotonic()
        loop = asyncio.get_event_loop()
        yield ExtractionProgress(percentage=5, current_table=None,
                                 message="Connecting to Cloud Storage...", status="progress")
        await asyncio.sleep(0)
        try:
            total = len(self.files)
            if total == 0:
                yield ExtractionProgress(percentage=100, current_table=None,
                                         message="No files selected.", status="warning")
                return
            for idx, obj in enumerate(self.files):
                tname = _table_name(obj, self.prefix)
                yield ExtractionProgress(percentage=10 + int(80 * idx / total),
                                         current_table=tname,
                                         message=f"Sampling {obj}", status="progress")
                await asyncio.sleep(0)
                cols = await loop.run_in_executor(_executor, self._columns_for, obj)
                self._tables.append(Table(object_id=_object_id(obj), schema_name="gcs",
                                          table_name=tname, columns=cols, indexes=[],
                                          is_view=False))
                yield ExtractionProgress(percentage=10 + int(80 * (idx + 1) / total),
                                         current_table=tname,
                                         message=f"Extracted {tname} ({len(cols)} columns)",
                                         status="progress")
                await asyncio.sleep(0)
            yield ExtractionProgress(percentage=100, current_table=None,
                                     message="Extraction complete", status="complete")
        except Exception as e:  # noqa: BLE001
            logger.error(f"GCS schema extraction failed: {e}")
            yield ExtractionProgress(percentage=0, current_table=None,
                                     message=f"Extraction failed: {str(e)}", status="error")
            raise

    def get_result(self) -> DatabaseSchema:
        elapsed = time.monotonic() - self._start_time
        return DatabaseSchema(
            database_name=f"gs://{self.bucket}",
            tables=self._tables,
            foreign_keys=[],
            extraction_time_seconds=round(elapsed, 2),
            table_count=len(self._tables),
            standalone_table_count=len(self._tables),
        )
