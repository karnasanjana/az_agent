"""SharePoint schema extraction API with SSE streaming.

Same two-step SSE flow as Dataverse/BigQuery: POST /start returns a stream_id,
GET /stream/{id} streams progress and a final `result` event carrying the
DatabaseSchema. Auth is a delegated Microsoft Graph token (Sites.Read.All).
"""
import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.schemas.schema import ExtractionProgress
from app.schemas.sharepoint import SharePointExtractionRequest, SharePointRequest
from app.security.encryption import get_encryptor
from app.security.logging import get_logger
from app.services.sharepoint_extractor import SharePointSchemaExtractor

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sharepoint", tags=["sharepoint"])


@dataclass
class PendingSharePointExtraction:
    encrypted_site_url: str
    encrypted_access_token: str
    encrypted_lists: str  # JSON-encoded list
    created_at: datetime


_pending: dict[str, PendingSharePointExtraction] = {}
_TTL_MINUTES = 5


def _cleanup_expired() -> None:
    cutoff = datetime.now() - timedelta(minutes=_TTL_MINUTES)
    for k in [k for k, v in _pending.items() if v.created_at < cutoff]:
        del _pending[k]


def _store(stream_id: str, site_url: str, access_token: str, lists: list[str]) -> None:
    _cleanup_expired()
    enc = get_encryptor()
    _pending[stream_id] = PendingSharePointExtraction(
        encrypted_site_url=enc.encrypt(site_url),
        encrypted_access_token=enc.encrypt(access_token),
        encrypted_lists=enc.encrypt(json.dumps(lists)),
        created_at=datetime.now(),
    )


def _retrieve(stream_id: str) -> tuple[str, str, list[str]] | None:
    _cleanup_expired()
    p = _pending.pop(stream_id, None)
    if not p:
        return None
    enc = get_encryptor()
    return (
        enc.decrypt(p.encrypted_site_url),
        enc.decrypt(p.encrypted_access_token),
        json.loads(enc.decrypt(p.encrypted_lists)),
    )


@router.post("/lists")
async def list_lists(request: SharePointRequest) -> list[dict]:
    """List the lists in a SharePoint site."""
    loop = asyncio.get_event_loop()

    def _list():
        return SharePointSchemaExtractor(
            site_url=request.site_url, access_token=request.access_token
        ).list_lists()

    try:
        return await loop.run_in_executor(None, _list)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to list SharePoint lists: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list lists: {str(e)}")


@router.post("/start")
async def start_extraction(request: SharePointExtractionRequest) -> dict:
    """Store credentials and return a stream_id for GET /stream/{id}."""
    stream_id = str(uuid.uuid4())
    _store(stream_id, request.site_url, request.access_token, request.lists)
    return {
        "stream_id": stream_id,
        "table_count": len(request.lists),
        "requires_confirmation": False,
    }


@router.get("/stream/{stream_id}", response_class=EventSourceResponse)
async def stream_extraction(stream_id: str) -> AsyncIterable[ServerSentEvent]:
    """Stream extraction progress, ending with a `result` event."""
    creds = _retrieve(stream_id)
    if not creds:
        yield ServerSentEvent(
            data={"percentage": 0, "current_table": None,
                  "message": "Stream not found or expired", "status": "error"},
            event="error",
        )
        return

    site_url, access_token, lists = creds
    extractor = SharePointSchemaExtractor(
        site_url=site_url, access_token=access_token, lists=lists
    )
    last = time.monotonic()
    started = time.monotonic()

    try:
        async for progress in extractor.extract_with_progress():
            now = time.monotonic()
            if now - started > 30 and progress.status == "progress" \
                    and "Still working" not in progress.message:
                progress.message = f"{progress.message} Still working..."
            if (now - last >= 0.5) or progress.status != "progress":
                yield ServerSentEvent(data=progress.model_dump(), event=progress.status)
                last = now
            await asyncio.sleep(0)

        yield ServerSentEvent(data=extractor.get_result().model_dump(), event="result")
    except Exception as e:  # noqa: BLE001
        logger.error(f"SharePoint extraction stream error: {e}")
        yield ServerSentEvent(
            data=ExtractionProgress(
                percentage=0, current_table=None,
                message=f"Extraction failed: {str(e)}", status="error",
            ).model_dump(),
            event="error",
        )
