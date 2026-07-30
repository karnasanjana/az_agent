"""Schema extraction API with SSE streaming.

Provides endpoints for extracting database schema with real-time
progress updates via Server-Sent Events.

Per Pitfall 1 from RESEARCH.md: EventSource only supports GET.
Uses two-step flow: POST /start returns stream_id, GET /stream/{id} streams SSE.
"""
import asyncio
import time
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from pydantic import BaseModel

from app.schemas.chat import DataSource
from app.schemas.connection import ConnectionRequest
from app.schemas.schema import ExtractionProgress, DatabaseSchema
from app.services.query_executor import execute_bigquery, execute_sqlserver
from app.services.schema_extractor import SchemaExtractor
from app.security.encryption import get_encryptor
from app.security.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/schema", tags=["schema"])


# =============================================================================
# Credential Storage for SSE Flow
# =============================================================================
# Pitfall 1: EventSource only supports GET, so we POST credentials first,
# get a stream_id, then GET the SSE stream with that id.

@dataclass
class PendingExtraction:
    """Temporary storage for extraction credentials."""
    encrypted_host: str
    encrypted_port: str
    encrypted_database: str
    encrypted_username: str
    encrypted_password: str
    created_at: datetime
    table_count: int = 0
    confirmed: bool = False  # For 500+ table confirmation
    requires_confirmation: bool = False


# In-memory storage with short TTL
_pending_extractions: dict[str, PendingExtraction] = {}
_TTL_MINUTES = 5


def _cleanup_expired() -> None:
    """Remove extractions older than TTL."""
    cutoff = datetime.now() - timedelta(minutes=_TTL_MINUTES)
    expired = [k for k, v in _pending_extractions.items() if v.created_at < cutoff]
    for k in expired:
        del _pending_extractions[k]
        logger.info(f"Cleaned up expired extraction: {k[:8]}...")


def _store_credentials(
    stream_id: str,
    request: ConnectionRequest,
    table_count: int,
    requires_confirmation: bool,
) -> None:
    """Store encrypted credentials temporarily."""
    _cleanup_expired()

    encryptor = get_encryptor()
    _pending_extractions[stream_id] = PendingExtraction(
        encrypted_host=encryptor.encrypt(request.host),
        encrypted_port=encryptor.encrypt(str(request.port)),
        encrypted_database=encryptor.encrypt(request.database),
        encrypted_username=encryptor.encrypt(request.username),
        encrypted_password=encryptor.encrypt(request.password),
        created_at=datetime.now(),
        table_count=table_count,
        confirmed=not requires_confirmation,  # Auto-confirm if no confirmation needed
        requires_confirmation=requires_confirmation,
    )


def _retrieve_credentials(stream_id: str) -> Optional[tuple[str, int, str, str, str]]:
    """Retrieve and delete credentials from storage.

    Returns:
        Tuple of (host, port, database, username, password) or None if not found/expired
    """
    _cleanup_expired()

    pending = _pending_extractions.get(stream_id)
    if not pending:
        return None

    # Check if confirmed (for 500+ table databases)
    if pending.requires_confirmation and not pending.confirmed:
        return None

    # Delete after retrieval
    del _pending_extractions[stream_id]

    encryptor = get_encryptor()
    return (
        encryptor.decrypt(pending.encrypted_host),
        int(encryptor.decrypt(pending.encrypted_port)),
        encryptor.decrypt(pending.encrypted_database),
        encryptor.decrypt(pending.encrypted_username),
        encryptor.decrypt(pending.encrypted_password),
    )


# =============================================================================
# API Endpoints
# =============================================================================

class StartResponse:
    """Response model for /start endpoint."""
    pass


@router.post("/start")
async def start_extraction(request: ConnectionRequest) -> dict:
    """Start schema extraction and get stream ID.

    First step in two-step SSE flow. Returns stream_id for use with
    GET /stream/{stream_id} endpoint.

    Args:
        request: Database connection credentials

    Returns:
        {
            "stream_id": "uuid",
            "table_count": int,
            "requires_confirmation": bool,
            "message": str (if empty or 500+ tables)
        }
    """
    # Create extractor to count tables
    extractor = SchemaExtractor(
        host=request.host,
        port=request.port,
        database=request.database,
        username=request.username,
        password=request.password,
    )

    try:
        table_count = await extractor.count_tables()
    except Exception as e:
        logger.error(f"Failed to count tables: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to connect: {str(e)}")

    # Generate stream ID
    stream_id = str(uuid.uuid4())

    # Handle edge cases
    if table_count == 0:
        return {
            "stream_id": stream_id,
            "table_count": 0,
            "requires_confirmation": False,
            "message": "No tables found. This database appears empty.",
        }

    requires_confirmation = table_count >= 500

    # Store credentials temporarily
    _store_credentials(stream_id, request, table_count, requires_confirmation)

    response = {
        "stream_id": stream_id,
        "table_count": table_count,
        "requires_confirmation": requires_confirmation,
    }

    if requires_confirmation:
        response["message"] = f"Large database detected: {table_count} tables. Please confirm to proceed."

    return response


@router.post("/confirm/{stream_id}")
async def confirm_extraction(stream_id: str) -> dict:
    """Confirm extraction for large databases (500+ tables).

    Args:
        stream_id: Stream ID from /start endpoint

    Returns:
        {"confirmed": true}

    Raises:
        HTTPException 404 if stream_id not found or expired
    """
    pending = _pending_extractions.get(stream_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Stream not found or expired")

    pending.confirmed = True
    return {"confirmed": True}


@router.get("/stream/{stream_id}", response_class=EventSourceResponse)
async def stream_extraction(stream_id: str) -> AsyncIterable[ServerSentEvent]:
    """Stream schema extraction progress via SSE.

    Second step in two-step SSE flow. Connects to database and extracts
    schema, streaming progress updates every 500ms.

    Args:
        stream_id: Stream ID from /start endpoint

    Yields:
        ServerSentEvent with progress or complete/error events
    """
    # Retrieve credentials
    credentials = _retrieve_credentials(stream_id)
    if not credentials:
        yield ServerSentEvent(
            data={
                "percentage": 0,
                "current_table": None,
                "message": "Stream not found, expired, or requires confirmation",
                "status": "error",
            },
            event="error",
        )
        return

    host, port, database, username, password = credentials

    # Create extractor
    extractor = SchemaExtractor(
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
    )

    last_update_time = time.monotonic()
    extraction_start = time.monotonic()

    try:
        # Stream progress events
        async for progress in extractor.extract_with_progress():
            current_time = time.monotonic()

            # Add "Still working..." message for long extractions (>30s)
            elapsed = current_time - extraction_start
            if elapsed > 30 and progress.status == "progress" and "Still working" not in progress.message:
                progress.message = f"{progress.message} Still working..."

            # Throttle updates to 500ms intervals
            # Always send non-progress events (complete, error, warning)
            if (current_time - last_update_time >= 0.5) or progress.status != "progress":
                yield ServerSentEvent(
                    data=progress.model_dump(),
                    event=progress.status,
                )
                last_update_time = current_time

            # Brief yield to event loop
            await asyncio.sleep(0)

        # Send final result
        result = extractor.get_result()
        yield ServerSentEvent(
            data=result.model_dump(),
            event="result",
        )

    except Exception as e:
        logger.error(f"Extraction stream error: {e}")
        error_progress = ExtractionProgress(
            percentage=0,
            current_table=None,
            message=f"Extraction failed: {str(e)}",
            status="error",
        )
        yield ServerSentEvent(
            data=error_progress.model_dump(),
            event="error",
        )


# =============================================================================
# Sample Data Preview Endpoint
# =============================================================================

class SampleDataRequest(BaseModel):
    """Request body for the sample data endpoint."""
    table_name: str
    schema_name: str
    limit: int = 5
    data_sources: list[DataSource] = []


@router.post("/sample")
async def get_sample_data(request: SampleDataRequest) -> dict:
    """Fetch a small sample of rows for a table.

    Routes the query to the correct data source (SQL Server or BigQuery)
    based on the table's schema_name and the provided data sources.

    Returns:
        {"columns": [...], "rows": [[...], ...], "row_count": int}
    """
    limit = max(1, min(int(request.limit or 5), 100))

    # Try SQL Server first if available
    sql_source = next((ds for ds in request.data_sources if ds.type == "sqlserver"), None)
    bq_source = next((ds for ds in request.data_sources if ds.type == "bigquery"), None)

    table_name = request.table_name
    schema_name = request.schema_name

    loop = asyncio.get_event_loop()

    # Heuristic: if a SQL Server source is available, try it; if it errors and
    # BigQuery is available, fall back to BigQuery.
    last_error: str | None = None

    if sql_source and sql_source.host:
        # Quote identifiers with brackets for SQL Server
        safe_schema = schema_name.replace("]", "]]")
        safe_table = table_name.replace("]", "]]")
        query = f"SELECT TOP {limit} * FROM [{safe_schema}].[{safe_table}]"

        result = await loop.run_in_executor(
            None,
            lambda: execute_sqlserver(
                query=query,
                host=sql_source.host or "",
                port=sql_source.port or 1433,
                database=sql_source.database or "",
                username=sql_source.username or "",
                password=sql_source.password or "",
                max_rows=limit,
            ),
        )
        if "error" not in result:
            return {
                "columns": result.get("columns", []),
                "rows": result.get("rows", []),
                "row_count": result.get("row_count", 0),
            }
        last_error = result.get("error")
        logger.info(f"SQL Server sample failed for {schema_name}.{table_name}: {last_error}")

    if bq_source and bq_source.project_id and bq_source.access_token:
        # BigQuery: use schema_name as dataset, project_id as project
        query = f"SELECT * FROM `{bq_source.project_id}.{schema_name}.{table_name}` LIMIT {limit}"
        result = await loop.run_in_executor(
            None,
            lambda: execute_bigquery(
                query=query,
                project_id=bq_source.project_id or "",
                access_token=bq_source.access_token or "",
                max_rows=limit,
            ),
        )
        if "error" not in result:
            return {
                "columns": result.get("columns", []),
                "rows": result.get("rows", []),
                "row_count": result.get("row_count", 0),
            }
        last_error = result.get("error")
        logger.info(f"BigQuery sample failed for {schema_name}.{table_name}: {last_error}")

    raise HTTPException(
        status_code=400,
        detail=last_error or "No data source available to sample this table",
    )
