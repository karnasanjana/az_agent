"""Dataverse schema extraction API with SSE streaming.

Provides endpoints for listing Dataverse entities and extracting
schema with real-time progress updates via Server-Sent Events.

Follows the same two-step SSE flow as the BigQuery schema API:
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

from app.schemas.dataverse import DataverseExtractionRequest, DataverseRequest
from app.schemas.schema import ExtractionProgress
from app.security.encryption import get_encryptor
from app.security.logging import get_logger
from app.services.dataverse_extractor import DataverseSchemaExtractor

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dataverse", tags=["dataverse"])


# =============================================================================
# Credential Storage for SSE Flow
# =============================================================================

@dataclass
class PendingDataverseExtraction:
    """Temporary storage for Dataverse extraction credentials."""
    encrypted_environment_url: str
    encrypted_access_token: str
    encrypted_entities: str  # JSON-encoded list
    created_at: datetime
    entity_count: int = 0
    requires_confirmation: bool = False


# In-memory storage with short TTL
_pending_extractions: dict[str, PendingDataverseExtraction] = {}
_TTL_MINUTES = 5


def _cleanup_expired() -> None:
    """Remove extractions older than TTL."""
    cutoff = datetime.now() - timedelta(minutes=_TTL_MINUTES)
    expired = [k for k, v in _pending_extractions.items() if v.created_at < cutoff]
    for k in expired:
        del _pending_extractions[k]
        logger.info(f"Cleaned up expired Dataverse extraction: {k[:8]}...")


def _store_credentials(
    stream_id: str,
    environment_url: str,
    access_token: str,
    entities: list[str],
    entity_count: int,
) -> None:
    """Store encrypted Dataverse credentials temporarily."""
    import json

    _cleanup_expired()

    encryptor = get_encryptor()
    _pending_extractions[stream_id] = PendingDataverseExtraction(
        encrypted_environment_url=encryptor.encrypt(environment_url),
        encrypted_access_token=encryptor.encrypt(access_token),
        encrypted_entities=encryptor.encrypt(json.dumps(entities)),
        created_at=datetime.now(),
        entity_count=entity_count,
    )


def _retrieve_credentials(stream_id: str) -> tuple[str, str, list[str]] | None:
    """Retrieve and delete Dataverse credentials from storage.

    Returns:
        Tuple of (environment_url, access_token, entities) or None if not found/expired
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
        encryptor.decrypt(pending.encrypted_environment_url),
        encryptor.decrypt(pending.encrypted_access_token),
        json.loads(encryptor.decrypt(pending.encrypted_entities)),
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/entities")
async def list_entities(request: DataverseRequest) -> list[dict]:
    """List Dataverse entities in an environment.

    Uses OAuth access token to authenticate with Dataverse Web API.

    Args:
        request: Dataverse environment URL and OAuth access token

    Returns:
        List of {"name": str, "display_name": str, "is_custom": bool} sorted by name
    """
    loop = asyncio.get_event_loop()

    def _list():
        extractor = DataverseSchemaExtractor(
            environment_url=request.environment_url,
            access_token=request.access_token,
        )
        return extractor.list_entities()

    try:
        return await loop.run_in_executor(None, _list)
    except Exception as e:
        logger.error(f"Failed to list Dataverse entities: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to list entities: {str(e)}"
        )


@router.post("/start")
async def start_dataverse_extraction(request: DataverseExtractionRequest) -> dict:
    """Start Dataverse schema extraction and get stream ID.

    First step in two-step SSE flow. Returns stream_id for use
    with GET /stream/{stream_id}.

    Args:
        request: Dataverse environment URL, access token, and entity list

    Returns:
        {"stream_id": "uuid", "table_count": int, "requires_confirmation": bool}
    """
    entity_count = len(request.entities)

    # Generate stream ID
    stream_id = str(uuid.uuid4())

    # Store credentials temporarily
    _store_credentials(
        stream_id,
        request.environment_url,
        request.access_token,
        request.entities,
        entity_count,
    )

    return {
        "stream_id": stream_id,
        "table_count": entity_count,
        "requires_confirmation": False,
    }


@router.get("/stream/{stream_id}", response_class=EventSourceResponse)
async def stream_dataverse_extraction(
    stream_id: str,
) -> AsyncIterable[ServerSentEvent]:
    """Stream Dataverse schema extraction progress via SSE.

    Second step in two-step SSE flow. Extracts schema from Dataverse
    entities, streaming progress updates.

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

    environment_url, access_token, entities = credentials

    # Create extractor
    extractor = DataverseSchemaExtractor(
        environment_url=environment_url,
        access_token=access_token,
        entities=entities,
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
        logger.error(f"Dataverse extraction stream error: {e}")
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
