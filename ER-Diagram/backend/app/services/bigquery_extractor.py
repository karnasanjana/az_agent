"""BigQuery schema extraction service.

Extracts database schema from Google BigQuery datasets including tables,
columns, and foreign key constraints. Uses async patterns with thread pool
executor for non-blocking BigQuery client calls.

Uses BigQuery REST API (list_tables, get_table) instead of INFORMATION_SCHEMA
queries to work with the bigquery.readonly OAuth scope.
"""
import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from google.oauth2.credentials import Credentials
from google.cloud import bigquery

from app.schemas.schema import (
    Column,
    DatabaseSchema,
    ExtractionProgress,
    ForeignKey,
    Table,
)
from app.security.logging import get_logger

logger = get_logger(__name__)

# Thread pool for running synchronous BigQuery client calls
_executor = ThreadPoolExecutor(max_workers=2)


def _generate_object_id(dataset: str, table_name: str) -> int:
    """Generate a stable integer object_id from dataset and table name."""
    key = f"{dataset}.{table_name}"
    hash_bytes = hashlib.md5(key.encode()).digest()[:8]
    return int.from_bytes(hash_bytes, byteorder="big") & 0x7FFFFFFF


class BigQuerySchemaExtractor:
    """Extracts complete schema from BigQuery datasets.

    Uses BigQuery API calls (not queries) to work with readonly OAuth scope.
    """

    def __init__(
        self,
        project_id: str,
        datasets: list[str],
        access_token: str,
    ):
        credentials = Credentials(token=access_token)
        self.client = bigquery.Client(project=project_id, credentials=credentials)
        self.project_id = project_id
        self.datasets = datasets
        self._tables: list[Table] = []
        self._foreign_keys: list[ForeignKey] = []
        self._start_time: float = 0

    async def count_tables(self) -> int:
        """Count total tables across all selected datasets using API."""
        loop = asyncio.get_event_loop()

        def _count():
            total = 0
            for dataset in self.datasets:
                try:
                    tables = list(self.client.list_tables(dataset))
                    total += len(tables)
                except Exception as e:
                    logger.warning(f"Could not count tables in dataset '{dataset}': {e}")
            return total

        return await loop.run_in_executor(_executor, _count)

    async def extract_with_progress(self) -> AsyncGenerator[ExtractionProgress, None]:
        """Extract schema with progress updates."""
        self._start_time = time.monotonic()

        yield ExtractionProgress(
            percentage=5,
            current_table=None,
            message="Starting BigQuery extraction...",
            status="progress",
        )

        await asyncio.sleep(0)

        try:
            total_datasets = len(self.datasets)
            tables_processed = 0
            total_tables = await self.count_tables()

            if total_tables == 0:
                yield ExtractionProgress(
                    percentage=100,
                    current_table=None,
                    message="No tables found in selected datasets.",
                    status="warning",
                )
                return

            for ds_idx, dataset in enumerate(self.datasets):
                # Extract tables for this dataset
                dataset_tables = await self._extract_tables(dataset)
                dataset_pct_start = 10 + int(80 * ds_idx / total_datasets)

                yield ExtractionProgress(
                    percentage=dataset_pct_start,
                    current_table=None,
                    message=f"Processing dataset '{dataset}': found {len(dataset_tables)} tables",
                    status="progress",
                )
                await asyncio.sleep(0)

                # Extract columns for each table
                for t_idx, table in enumerate(dataset_tables):
                    await self._extract_columns(dataset, table)
                    tables_processed += 1

                    if total_tables > 0:
                        pct = 10 + int(80 * tables_processed / total_tables)
                    else:
                        pct = dataset_pct_start

                    yield ExtractionProgress(
                        percentage=min(pct, 90),
                        current_table=f"{dataset}.{table.table_name}",
                        message=f"Extracted columns for {dataset}.{table.table_name}",
                        status="progress",
                    )
                    await asyncio.sleep(0)

                # Extract foreign keys for this dataset
                await self._extract_foreign_keys(dataset)

            yield ExtractionProgress(
                percentage=95,
                current_table=None,
                message="Finalizing extraction...",
                status="progress",
            )
            await asyncio.sleep(0)

            yield ExtractionProgress(
                percentage=100,
                current_table=None,
                message="Extraction complete",
                status="complete",
            )

        except Exception as e:
            logger.error(f"BigQuery schema extraction failed: {e}")
            yield ExtractionProgress(
                percentage=0,
                current_table=None,
                message=f"Extraction failed: {str(e)}",
                status="error",
            )
            raise

    async def _extract_tables(self, dataset: str) -> list[Table]:
        """Extract table names from a BigQuery dataset using list_tables API."""
        loop = asyncio.get_event_loop()

        def _list():
            return list(self.client.list_tables(dataset))

        table_refs = await loop.run_in_executor(_executor, _list)

        dataset_tables = []
        for table_ref in table_refs:
            table = Table(
                object_id=_generate_object_id(dataset, table_ref.table_id),
                schema_name=dataset,
                table_name=table_ref.table_id,
                columns=[],
                indexes=[],
                is_view=(table_ref.table_type == 'VIEW'),
            )
            self._tables.append(table)
            dataset_tables.append(table)

        return dataset_tables

    async def _extract_columns(self, dataset: str, table: Table) -> None:
        """Extract column metadata for a table using get_table API."""
        loop = asyncio.get_event_loop()

        def _get():
            table_ref = f"{self.project_id}.{dataset}.{table.table_name}"
            return self.client.get_table(table_ref)

        bq_table = await loop.run_in_executor(_executor, _get)

        for field in bq_table.schema:
            column = Column(
                name=field.name,
                data_type=field.field_type.lower(),
                is_nullable=(field.mode != "REQUIRED"),
                is_primary_key=False,
                is_identity=False,
            )
            table.columns.append(column)

    async def _extract_foreign_keys(self, dataset: str) -> None:
        """Extract foreign key constraints for a dataset.

        BigQuery table constraints are not accessible via the REST API
        with readonly scope, so we skip FK extraction gracefully.
        """
        # BigQuery FK constraints are rarely used and require
        # bigquery.jobs.create scope to query INFORMATION_SCHEMA.
        # With readonly scope, we cannot extract them.
        pass

    def get_result(self) -> DatabaseSchema:
        """Get final extraction result after extraction completes."""
        elapsed = time.monotonic() - self._start_time

        tables_with_fk: set[str] = set()
        for fk in self._foreign_keys:
            tables_with_fk.add(f"{fk.source_schema}.{fk.source_table}")
            tables_with_fk.add(f"{fk.target_schema}.{fk.target_table}")

        standalone_count = sum(
            1
            for t in self._tables
            if f"{t.schema_name}.{t.table_name}" not in tables_with_fk
        )

        return DatabaseSchema(
            database_name=self.project_id,
            tables=self._tables,
            foreign_keys=self._foreign_keys,
            extraction_time_seconds=round(elapsed, 2),
            table_count=len(self._tables),
            standalone_table_count=standalone_count,
        )
