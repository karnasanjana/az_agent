"""SQLite connector — the reference implementation of the connector contract.

Cheapest possible source (a local .db file, no server, no creds), so it proves
the contract + guards before the expensive enterprise engines inherit them.
Read-only is belt-and-braces: the base contract rejects non-SELECT SQL, AND the
DB is opened in the driver's read-only/immutable mode so a slip can't write.
"""
from __future__ import annotations

import os
import sqlite3
import time

from app.schemas.schema import Column, DatabaseSchema, ForeignKey, Index, Table
from app.services.connectors.base import ReadOnlyConnector


class SQLiteConnector(ReadOnlyConnector):
    def __init__(self, source_id: str, path: str):
        self.source_id = source_id
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        # mode=ro + immutable: the driver refuses writes even if a query slips past.
        uri = f"file:{os.path.abspath(self.path)}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True, timeout=self.timeout_s)
        conn.execute(f"PRAGMA busy_timeout={self.timeout_s * 1000}")
        return conn

    def extract_schema(self) -> DatabaseSchema:
        started = time.monotonic()
        tables: list[Table] = []
        fks: list[ForeignKey] = []
        conn = self._connect()
        try:
            objs = conn.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            for oid, (name, kind) in enumerate(objs, start=1):
                cols = [
                    Column(name=cname, data_type=(ctype or "").lower() or "text",
                           is_nullable=not notnull, is_primary_key=bool(pk))
                    for _cid, cname, ctype, notnull, _dflt, pk
                    in conn.execute(f'PRAGMA table_info("{name}")')
                ]
                table = Table(object_id=oid, schema_name="main", table_name=name,
                              is_view=(kind == "view"), columns=cols)
                for _seqno, idxname, unique, *_ in conn.execute(f'PRAGMA index_list("{name}")'):
                    idxcols = [r[2] for r in conn.execute(f'PRAGMA index_info("{idxname}")')]
                    table.indexes.append(Index(name=idxname, index_type="BTREE",
                                               is_unique=bool(unique), columns=idxcols))
                tables.append(table)
                for row in conn.execute(f'PRAGMA foreign_key_list("{name}")'):
                    fk_id, seq, ttable, ffrom, tto = row[0], row[1], row[2], row[3], row[4]
                    fks.append(ForeignKey(
                        constraint_name=f"{name}_fk_{fk_id}_{seq}",
                        source_schema="main", source_table=name, source_columns=[ffrom],
                        target_schema="main", target_table=ttable, target_columns=[tto or ffrom]))
        finally:
            conn.close()

        connected = ({f"main.{fk.source_table}" for fk in fks}
                     | {f"main.{fk.target_table}" for fk in fks})
        return DatabaseSchema(
            database_name=os.path.basename(self.path),
            tables=tables, foreign_keys=fks,
            extraction_time_seconds=round(time.monotonic() - started, 2),
            table_count=len(tables),
            standalone_table_count=sum(f"main.{t.table_name}" not in connected for t in tables),
        )

    def _sample_sql(self, schema: str, table: str, limit: int) -> str:
        safe = table.replace('"', '""')
        return f'SELECT * FROM "{safe}" LIMIT {int(limit)}'

    def _execute(self, sql: str, limit: int) -> dict:
        # ponytail: row cap via fetchmany bounds the result; a runaway scan isn't
        # interrupted mid-flight — add sqlite3 set_progress_handler if that bites.
        conn = self._connect()
        try:
            cur = conn.execute(sql)
            names = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(limit)
        finally:
            conn.close()
        return {"columns": names, "rows": [list(r) for r in rows], "row_count": len(rows)}
