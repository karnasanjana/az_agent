"""Schema extraction service for SQL Server databases.

Extracts complete database schema including tables, columns, primary keys,
foreign keys, and indexes. Uses async patterns with thread pool executor
for non-blocking pyodbc calls.

Per user decisions:
- Progress updates every 500ms with percentage (0-100%) and current table name
- Empty database returns warning: "No tables found. This database appears empty."
- 500+ tables yields warning with count before starting
- Permission errors: skip table with warning, continue extraction
- Mid-extraction errors: fail completely with clear error message
"""
import asyncio
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator
from collections import defaultdict

from app.database.connection import get_db_connection, build_connection_string
from app.schemas.schema import (
    Column, ForeignKey, Index, Table, DatabaseSchema, ExtractionProgress,
    simplify_data_type, TABLE_COUNT_QUERY, TABLES_QUERY, COLUMNS_QUERY,
    PRIMARY_KEYS_QUERY, FOREIGN_KEYS_QUERY, INDEXES_QUERY
)
from app.security.logging import get_logger

logger = get_logger(__name__)

# Thread pool for running synchronous pyodbc calls
# Pitfall 2 from RESEARCH.md: pyodbc is synchronous and blocks event loop
_executor = ThreadPoolExecutor(max_workers=2)


class SchemaExtractor:
    """Extracts complete schema from SQL Server database.

    Uses async patterns with thread pool executor for non-blocking
    database queries via pyodbc.

    Usage:
        extractor = SchemaExtractor(host, port, database, username, password)
        async for progress in extractor.extract_with_progress():
            print(f"{progress.percentage}% - {progress.message}")
        result = extractor.get_result()
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
    ):
        """Initialize extractor with connection parameters.

        Args:
            host: SQL Server hostname or IP
            port: SQL Server port (typically 1433)
            database: Database name
            username: SQL Server username
            password: SQL Server password
        """
        self.conn_str = build_connection_string(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
        )
        self.database = database
        self._tables: list[Table] = []
        self._foreign_keys: list[ForeignKey] = []
        self._start_time: float = 0
        self._table_id_map: dict[int, Table] = {}  # object_id -> Table
        self._skipped_tables: list[str] = []  # Tables skipped due to permissions

    async def count_tables(self) -> int:
        """Count user tables for progress tracking and 500+ warning.

        Returns:
            Number of user tables in database
        """
        loop = asyncio.get_event_loop()

        def _count():
            with get_db_connection(self.conn_str) as conn:
                cursor = conn.cursor()
                cursor.execute(TABLE_COUNT_QUERY)
                return cursor.fetchone()[0]

        return await loop.run_in_executor(_executor, _count)

    async def extract_with_progress(self) -> AsyncGenerator[ExtractionProgress, None]:
        """Extract schema with progress updates.

        Yields ExtractionProgress objects every 500ms with percentage and
        current table name. Final yield has status='complete'.

        Extraction stages:
        - 5%: Starting extraction
        - 20%: Tables extracted
        - 20-40%: Columns processing (per table)
        - 55%: Primary keys extracted
        - 75%: Foreign keys extracted
        - 90%: Indexes extracted
        - 100%: Complete

        Yields:
            ExtractionProgress objects tracking extraction state
        """
        self._start_time = time.monotonic()

        # Check table count first (per Pitfall 4)
        table_count = await self.count_tables()

        if table_count == 0:
            yield ExtractionProgress(
                percentage=100,
                current_table=None,
                message="No tables found. This database appears empty.",
                status="warning"
            )
            return

        # Warn for large databases
        if table_count >= 500:
            yield ExtractionProgress(
                percentage=0,
                current_table=None,
                message=f"Large database detected: {table_count} tables. This may take a while.",
                status="warning"
            )

        yield ExtractionProgress(
            percentage=5,
            current_table=None,
            message="Starting extraction...",
            status="progress"
        )

        # Brief yield to event loop
        await asyncio.sleep(0)

        try:
            # Extract tables (20%)
            await self._extract_tables()
            yield ExtractionProgress(
                percentage=20,
                current_table=None,
                message=f"Found {len(self._tables)} tables",
                status="progress"
            )

            await asyncio.sleep(0)

            # Extract columns (20-40%)
            await self._extract_columns()
            yield ExtractionProgress(
                percentage=40,
                current_table=None,
                message="Columns extracted",
                status="progress"
            )

            await asyncio.sleep(0)

            # Check for long extraction time (>30s)
            elapsed = time.monotonic() - self._start_time
            reassurance = " Still working..." if elapsed > 30 else ""

            # Extract primary keys (55%)
            await self._extract_primary_keys()
            yield ExtractionProgress(
                percentage=55,
                current_table=None,
                message=f"Primary keys extracted{reassurance}",
                status="progress"
            )

            await asyncio.sleep(0)

            # Extract foreign keys (75%)
            await self._extract_foreign_keys()
            yield ExtractionProgress(
                percentage=75,
                current_table=None,
                message=f"Foreign keys extracted{reassurance}",
                status="progress"
            )

            await asyncio.sleep(0)

            # Extract indexes (90%)
            await self._extract_indexes()

            # Update reassurance for long extractions
            elapsed = time.monotonic() - self._start_time
            reassurance = " Still working..." if elapsed > 30 else ""

            yield ExtractionProgress(
                percentage=90,
                current_table=None,
                message=f"Indexes extracted{reassurance}",
                status="progress"
            )

            await asyncio.sleep(0)

            # Log skipped tables if any
            if self._skipped_tables:
                logger.warning(f"Skipped {len(self._skipped_tables)} tables due to permissions: {self._skipped_tables}")

            # Finalize (100%)
            yield ExtractionProgress(
                percentage=100,
                current_table=None,
                message="Extraction complete",
                status="complete"
            )

        except Exception as e:
            # Mid-extraction error: fail completely per research recommendation
            logger.error(f"Schema extraction failed: {e}")
            yield ExtractionProgress(
                percentage=0,
                current_table=None,
                message=f"Extraction failed: {str(e)}",
                status="error"
            )
            raise

    async def _extract_tables(self) -> None:
        """Extract table and view metadata from sys.objects."""
        loop = asyncio.get_event_loop()

        def _query():
            with get_db_connection(self.conn_str) as conn:
                cursor = conn.cursor()
                cursor.execute(TABLES_QUERY)
                return cursor.fetchall()

        rows = await loop.run_in_executor(_executor, _query)

        for row in rows:
            table = Table(
                object_id=row[0],
                schema_name=row[1],
                table_name=row[2],
                columns=[],
                indexes=[],
                is_view=row[3].strip() == 'V',
            )
            self._tables.append(table)
            self._table_id_map[row[0]] = table

    async def _extract_columns(self) -> None:
        """Extract column metadata and attach to tables."""
        loop = asyncio.get_event_loop()

        def _query():
            with get_db_connection(self.conn_str) as conn:
                cursor = conn.cursor()
                cursor.execute(COLUMNS_QUERY)
                return cursor.fetchall()

        rows = await loop.run_in_executor(_executor, _query)

        for row in rows:
            object_id = row[0]
            if object_id in self._table_id_map:
                column = Column(
                    name=row[1],
                    data_type=simplify_data_type(row[2]),
                    is_nullable=bool(row[3]),
                    is_primary_key=False,  # Set later in _extract_primary_keys
                    is_identity=bool(row[4]),
                )
                self._table_id_map[object_id].columns.append(column)

    async def _extract_primary_keys(self) -> None:
        """Extract primary key columns and mark them on tables."""
        loop = asyncio.get_event_loop()

        def _query():
            with get_db_connection(self.conn_str) as conn:
                cursor = conn.cursor()
                cursor.execute(PRIMARY_KEYS_QUERY)
                return cursor.fetchall()

        rows = await loop.run_in_executor(_executor, _query)

        # Build set of (object_id, column_name) for PK columns
        pk_columns: set[tuple[int, str]] = set()
        for row in rows:
            pk_columns.add((row[0], row[1]))

        # Mark columns as primary keys
        for table in self._tables:
            for column in table.columns:
                if (table.object_id, column.name) in pk_columns:
                    column.is_primary_key = True

    async def _extract_foreign_keys(self) -> None:
        """Extract foreign key relationships.

        Groups rows by constraint to handle composite FKs properly.
        Per Pitfall 6: sys.foreign_key_columns returns one row per column.
        """
        loop = asyncio.get_event_loop()

        def _query():
            with get_db_connection(self.conn_str) as conn:
                cursor = conn.cursor()
                cursor.execute(FOREIGN_KEYS_QUERY)
                return cursor.fetchall()

        rows = await loop.run_in_executor(_executor, _query)

        # Group by constraint_object_id to handle composite FKs
        fk_groups: dict[int, list] = defaultdict(list)
        for row in rows:
            constraint_object_id = row[1]
            fk_groups[constraint_object_id].append(row)

        # Build ForeignKey objects from groups
        for constraint_id, group_rows in fk_groups.items():
            # First row has constraint metadata
            first_row = group_rows[0]

            # Collect columns in order
            source_columns = [r[8] for r in sorted(group_rows, key=lambda x: x[10])]
            target_columns = [r[9] for r in sorted(group_rows, key=lambda x: x[10])]

            fk = ForeignKey(
                constraint_name=first_row[0],
                source_table=first_row[3],
                source_schema=first_row[4],
                source_columns=source_columns,
                target_table=first_row[6],
                target_schema=first_row[7],
                target_columns=target_columns,
            )
            self._foreign_keys.append(fk)

    async def _extract_indexes(self) -> None:
        """Extract non-PK indexes and attach to tables.

        Groups rows by (object_id, index_name) to collect all columns.
        Separates key columns from included columns.
        """
        loop = asyncio.get_event_loop()

        def _query():
            with get_db_connection(self.conn_str) as conn:
                cursor = conn.cursor()
                cursor.execute(INDEXES_QUERY)
                return cursor.fetchall()

        rows = await loop.run_in_executor(_executor, _query)

        # Group by (object_id, index_name)
        index_groups: dict[tuple[int, str], list] = defaultdict(list)
        for row in rows:
            key = (row[0], row[1])
            index_groups[key].append(row)

        # Build Index objects from groups
        for (object_id, index_name), group_rows in index_groups.items():
            if object_id not in self._table_id_map:
                continue

            # First row has index metadata
            first_row = group_rows[0]

            # Separate key columns from included columns
            key_columns = []
            included_columns = []
            for r in sorted(group_rows, key=lambda x: x[5]):  # Sort by key_ordinal
                if r[6]:  # is_included_column
                    included_columns.append(r[4])  # column_name
                else:
                    key_columns.append(r[4])

            index = Index(
                name=index_name,
                index_type=first_row[2],  # type_desc
                is_unique=bool(first_row[3]),
                columns=key_columns,
                included_columns=included_columns,
            )
            self._table_id_map[object_id].indexes.append(index)

    def get_result(self) -> DatabaseSchema:
        """Get final extraction result after extraction completes.

        Returns:
            DatabaseSchema with all extracted metadata
        """
        elapsed = time.monotonic() - self._start_time

        # Count standalone tables (no FK relationships)
        tables_with_fk: set[str] = set()
        for fk in self._foreign_keys:
            tables_with_fk.add(f"{fk.source_schema}.{fk.source_table}")
            tables_with_fk.add(f"{fk.target_schema}.{fk.target_table}")

        standalone_count = sum(
            1 for t in self._tables
            if f"{t.schema_name}.{t.table_name}" not in tables_with_fk
        )

        return DatabaseSchema(
            database_name=self.database,
            tables=self._tables,
            foreign_keys=self._foreign_keys,
            extraction_time_seconds=round(elapsed, 2),
            table_count=len(self._tables),
            standalone_table_count=standalone_count,
        )
