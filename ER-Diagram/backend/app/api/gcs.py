"""Google Cloud Storage schema extraction API with SSE streaming.

Two-step SSE flow (POST /start -> GET /stream/{id}) like the other sources.
Auth is the signed-in user's Google token (devstorage.read_only).
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

from app.schemas.gcs import GcsExtractionRequest, GcsRequest
from app.schemas.schema import ExtractionProgress
from app.security.encryption import get_encryptor
from app.security.logging import get_logger
from app.services.gcs_extractor import GcsSchemaExtractor

logger = get_logger(__name__)

router = APIRouter(prefix="/api/gcs", tags=["gcs"])


@dataclass
class PendingGcsExtraction:
    encrypted_bucket: str
    encrypted_prefix: str
    encrypted_access_token: str
    encrypted_files: str
    created_at: datetime


_pending: dict[str, PendingGcsExtraction] = {}
_TTL_MINUTES = 5


def _cleanup_expired() -> None:
    cutoff = datetime.now() - timedelta(minutes=_TTL_MINUTES)
    for k in [k for k, v in _pending.items() if v.created_at < cutoff]:
        del _pending[k]


def _store(stream_id: str, bucket: str, prefix: str, token: str, files: list[str]) -> None:
    _cleanup_expired()
    enc = get_encryptor()
    _pending[stream_id] = PendingGcsExtraction(
        encrypted_bucket=enc.encrypt(bucket),
        encrypted_prefix=enc.encrypt(prefix or ""),
        encrypted_access_token=enc.encrypt(token),
        encrypted_files=enc.encrypt(json.dumps(files)),
        created_at=datetime.now(),
    )


def _retrieve(stream_id: str) -> tuple[str, str, str, list[str]] | None:
    _cleanup_expired()
    p = _pending.pop(stream_id, None)
    if not p:
        return None
    enc = get_encryptor()
    return (
        enc.decrypt(p.encrypted_bucket),
        enc.decrypt(p.encrypted_prefix),
        enc.decrypt(p.encrypted_access_token),
        json.loads(enc.decrypt(p.encrypted_files)),
    )


@router.post("/files")
async def list_files(request: GcsRequest) -> list[dict]:
    """List data files (CSV/JSON/Parquet) in the bucket under an optional prefix."""
    loop = asyncio.get_event_loop()

    def _list():
        return GcsSchemaExtractor(
            bucket=request.bucket, access_token=request.access_token,
            prefix=request.prefix,
        ).list_files()

    try:
        return await loop.run_in_executor(None, _list)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to list GCS files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.post("/start")
async def start_extraction(request: GcsExtractionRequest) -> dict:
    stream_id = str(uuid.uuid4())
    _store(stream_id, request.bucket, request.prefix, request.access_token, request.files)
    return {
        "stream_id": stream_id,
        "table_count": len(request.files),
        "requires_confirmation": False,
    }


@router.get("/stream/{stream_id}", response_class=EventSourceResponse)
async def stream_extraction(stream_id: str) -> AsyncIterable[ServerSentEvent]:
    creds = _retrieve(stream_id)
    if not creds:
        yield ServerSentEvent(
            data={"percentage": 0, "current_table": None,
                  "message": "Stream not found or expired", "status": "error"},
            event="error",
        )
        return

    bucket, prefix, token, files = creds
    extractor = GcsSchemaExtractor(bucket=bucket, access_token=token, prefix=prefix, files=files)
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
        logger.error(f"GCS extraction stream error: {e}")
        yield ServerSentEvent(
            data=ExtractionProgress(
                percentage=0, current_table=None,
                message=f"Extraction failed: {str(e)}", status="error",
            ).model_dump(),
            event="error",
        )
