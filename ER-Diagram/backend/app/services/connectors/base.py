"""The enterprise connector contract + cross-cutting guards.

Every source connector (native or MCP-backed) subclasses ReadOnlyConnector and
emits the common DatabaseSchema. The guards below are enforced HERE — once — so
every engine behaves the same:

  * read-only        : only a single SELECT/WITH query is ever sent to a source
  * row cap          : results are bounded, so a fat table can't OOM the server
  * audit            : one structured line per source access (who/what/rows)

A connector implements _execute (run a validated SELECT), extract_schema, and
_sample_sql; it never re-implements the guards. That's how "read-only, enforced
not hoped" holds across dozens of engines without trusting each one.
"""
from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod

from app.schemas.schema import DatabaseSchema
from app.security.logging import get_logger

logger = get_logger(__name__)

DEFAULT_ROW_CAP = 1000
DEFAULT_TIMEOUT_S = 30

# Keywords that mutate data or schema. Scanned AFTER string/identifier literals
# are stripped, so a value like WHERE note = 'please update' is not a false hit.
# Catches data-modifying CTEs too (Postgres: WITH t AS (DELETE ...)).
_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|merge|"
    r"replace|call|exec|execute|copy|vacuum|attach|detach|reindex|set)\b",
    re.IGNORECASE,
)
_STRING_LITERAL = re.compile(r"'[^']*'|\"[^\"]*\"")
_STARTS_READ = re.compile(r"^\s*(select|with)\b", re.IGNORECASE | re.DOTALL)


class WriteAttemptError(PermissionError):
    """A statement that isn't a single read-only SELECT/WITH was submitted."""


def assert_read_only(sql: str) -> None:
    """Reject anything that could mutate the source. Enforced before the query
    ever reaches the engine — this app queries enterprise sources, never writes."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise WriteAttemptError("empty query")
    if ";" in stripped:
        raise WriteAttemptError("multiple statements are not allowed")
    if not _STARTS_READ.match(stripped):
        raise WriteAttemptError("read-only: only SELECT/WITH queries are allowed")
    scan = _STRING_LITERAL.sub("", stripped)  # ignore literal values/identifiers
    hit = _WRITE.search(scan)
    if hit:
        raise WriteAttemptError(f"read-only: refused a query containing '{hit.group(1)}'")


def audit(source_id: str, action: str, sql: str | None = None, rows: int | None = None) -> None:
    """One structured audit line per source access — the enterprise trail."""
    logger.info(
        "connector-audit source=%s action=%s rows=%s sql=%s",
        source_id, action, rows, (sql or "").replace("\n", " ")[:500],
    )


class ReadOnlyConnector(ABC):
    """Base for every read-only source connector. source_id is the stable id used
    across the app and as the catalog id for az_agent grounding."""

    source_id: str
    row_cap: int = DEFAULT_ROW_CAP
    timeout_s: int = DEFAULT_TIMEOUT_S

    # --- engine-specific: subclasses implement these three ---
    @abstractmethod
    def extract_schema(self) -> DatabaseSchema:
        """Introspect the source into the common DatabaseSchema model."""

    @abstractmethod
    def _execute(self, sql: str, limit: int) -> dict:
        """Run an ALREADY-VALIDATED read-only SELECT, capped at `limit` rows.
        Returns {"columns": [...], "rows": [[...], ...], "row_count": int}."""

    @abstractmethod
    def _sample_sql(self, schema: str, table: str, limit: int) -> str:
        """Engine-specific SELECT for a table sample (safe identifier quoting)."""

    # --- guarded, uniform: subclasses do NOT override these ---
    def run_readonly_sql(self, sql: str, limit: int | None = None) -> dict:
        assert_read_only(sql)  # enforce first, always
        cap = min(limit or self.row_cap, self.row_cap)
        t = time.monotonic()
        try:
            result = self._execute(sql, cap)
        except WriteAttemptError:
            raise
        except Exception:
            audit(self.source_id, "query-error", sql, 0)
            raise
        result["elapsed_s"] = round(time.monotonic() - t, 3)
        audit(self.source_id, "query", sql, result.get("row_count"))
        return result

    def sample(self, schema: str, table: str, limit: int = 50) -> dict:
        return self.run_readonly_sql(self._sample_sql(schema, table, limit), limit)
