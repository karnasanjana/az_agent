"""BigQuery schema extraction API with SSE streaming.

Provides endpoints for listing BigQuery datasets and extracting
schema with real-time progress updates via Server-Sent Events.

Follows the same two-step SSE flow as the SQL Server schema API:
POST /start returns stream_id, GET /stream/{id} streams SSE.
"""
import asyncio
import time
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.schemas.bigquery import BigQueryExtractionRequest, BigQueryRequest
from app.schemas.schema import ExtractionProgress
from app.security.encryption import get_encryptor
from app.security.logging import get_logger
from app.services.bigquery_extractor import BigQuerySchemaExtractor

logger = get_logger(__name__)

router = APIRouter(prefix="/api/bigquery", tags=["bigquery"])


def _get_gcloud_token() -> str | None:
    """Get access token from gcloud auth login."""
    import subprocess
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, timeout=10
        )
        token = result.stdout.strip()
        return token if token else None
    except Exception:
        return None


# =============================================================================
# Credential Storage for SSE Flow
# =============================================================================

@dataclass
class PendingBigQueryExtraction:
    """Temporary storage for BigQuery extraction credentials."""
    encrypted_project_id: str
    encrypted_access_token: str
    encrypted_datasets: str  # JSON-encoded list
    created_at: datetime
    table_count: int = 0
    requires_confirmation: bool = False


# In-memory storage with short TTL
_pending_extractions: dict[str, PendingBigQueryExtraction] = {}
_TTL_MINUTES = 5


def _cleanup_expired() -> None:
    """Remove extractions older than TTL."""
    cutoff = datetime.now() - timedelta(minutes=_TTL_MINUTES)
    expired = [k for k, v in _pending_extractions.items() if v.created_at < cutoff]
    for k in expired:
        del _pending_extractions[k]
        logger.info(f"Cleaned up expired BigQuery extraction: {k[:8]}...")


def _store_credentials(
    stream_id: str,
    project_id: str,
    access_token: str,
    datasets: list[str],
    table_count: int,
) -> None:
    """Store encrypted BigQuery credentials temporarily."""
    import json

    _cleanup_expired()

    encryptor = get_encryptor()
    _pending_extractions[stream_id] = PendingBigQueryExtraction(
        encrypted_project_id=encryptor.encrypt(project_id),
        encrypted_access_token=encryptor.encrypt(access_token),
        encrypted_datasets=encryptor.encrypt(json.dumps(datasets)),
        created_at=datetime.now(),
        table_count=table_count,
    )


def _retrieve_credentials(stream_id: str) -> tuple[str, str, list[str]] | None:
    """Retrieve and delete BigQuery credentials from storage.

    Returns:
        Tuple of (project_id, access_token, datasets) or None if not found/expired
    """
    import json

    _cleanup_expired()

    pending = _pending_extractions.get(stream_id)
    if not pending:
        return None

    # Delete after retrieval
    del _pending_extractions[stream_id]

    encryptor = get_encryptor()
    return (
        encryptor.decrypt(pending.encrypted_project_id),
        encryptor.decrypt(pending.encrypted_access_token),
        json.loads(encryptor.decrypt(pending.encrypted_datasets)),
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/datasets")
async def list_datasets(request: BigQueryRequest) -> list[dict]:
    """List BigQuery datasets in a project with table counts.

    Uses OAuth access token to authenticate with BigQuery API.

    Args:
        request: BigQuery project ID and OAuth access token

    Returns:
        List of {"name": str, "table_count": int} sorted by name
    """
    loop = asyncio.get_event_loop()

    def _list():
        from google.cloud import bigquery
        from google.oauth2.credentials import Credentials

        # Use user's OAuth access token
        token = request.access_token or _get_gcloud_token()
        credentials = Credentials(token=token)
        client = bigquery.Client(
            project=request.project_id, credentials=credentials
        )

        results = []
        datasets = list(client.list_datasets())

        for dataset_ref in datasets:
            dataset_name = dataset_ref.dataset_id
            try:
                # Use list_tables API (works with readonly scope, no query needed)
                tables = list(client.list_tables(dataset_ref.reference))
                table_count = len(tables)
                results.append({"name": dataset_name, "table_count": table_count})
            except Exception as e:
                logger.warning(
                    f"Could not count tables in dataset '{dataset_name}': {e}"
                )
                results.append({"name": dataset_name, "table_count": 0})

        # Sort by name
        results.sort(key=lambda x: x["name"])
        return results

    try:
        return await loop.run_in_executor(None, _list)
    except Exception as e:
        logger.error(f"Failed to list BigQuery datasets: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list datasets: {str(e)}"
        )


@router.post("/start")
async def start_bigquery_extraction(request: BigQueryExtractionRequest) -> dict:
    """Start BigQuery schema extraction and get stream ID.

    First step in two-step SSE flow. Counts tables across selected
    datasets and returns stream_id for use with GET /stream/{stream_id}.

    Args:
        request: BigQuery project ID, access token, and dataset list

    Returns:
        {"stream_id": "uuid", "table_count": int, "requires_confirmation": bool}
    """
    # Create extractor to count tables
    extractor = BigQuerySchemaExtractor(
        project_id=request.project_id,
        datasets=request.datasets,
        access_token=request.access_token,
    )

    try:
        table_count = await extractor.count_tables()
    except Exception as e:
        logger.error(f"Failed to count BigQuery tables: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to connect to BigQuery: {str(e)}"
        )

    # Generate stream ID
    stream_id = str(uuid.uuid4())

    # Store credentials temporarily
    _store_credentials(
        stream_id,
        request.project_id,
        request.access_token,
        request.datasets,
        table_count,
    )

    return {
        "stream_id": stream_id,
        "table_count": table_count,
        "requires_confirmation": False,
    }


@router.get("/stream/{stream_id}", response_class=EventSourceResponse)
async def stream_bigquery_extraction(
    stream_id: str,
) -> AsyncIterable[ServerSentEvent]:
    """Stream BigQuery schema extraction progress via SSE.

    Second step in two-step SSE flow. Extracts schema from BigQuery
    datasets, streaming progress updates.

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
                "message": "Stream not found or expired",
                "status": "error",
            },
            event="error",
        )
        return

    project_id, access_token, datasets = credentials

    # Create extractor
    extractor = BigQuerySchemaExtractor(
        project_id=project_id,
        datasets=datasets,
        access_token=access_token,
    )

    last_update_time = time.monotonic()
    extraction_start = time.monotonic()

    try:
        # Stream progress events
        async for progress in extractor.extract_with_progress():
            current_time = time.monotonic()

            # Add "Still working..." message for long extractions (>30s)
            elapsed = current_time - extraction_start
            if (
                elapsed > 30
                and progress.status == "progress"
                and "Still working" not in progress.message
            ):
                progress.message = f"{progress.message} Still working..."

            # Throttle updates to 500ms intervals
            # Always send non-progress events (complete, error, warning)
            if (
                current_time - last_update_time >= 0.5
            ) or progress.status != "progress":
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
        logger.error(f"BigQuery extraction stream error: {e}")
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
