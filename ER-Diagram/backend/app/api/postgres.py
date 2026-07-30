"""PostgreSQL connection and schema extraction endpoints."""
import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncIterable

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.schemas.connection import ConnectionRequest, ConnectionResponse
from app.security.encryption import CredentialEncryptor
from app.security.logging import get_logger
from app.services.postgres_extractor import extract_postgres_schema

router = APIRouter(prefix="/api/postgres", tags=["postgres"])
logger = get_logger(__name__)
_pending: dict[str, str] = {}


def _encryptor() -> CredentialEncryptor:
    return CredentialEncryptor(os.environ["FERNET_KEY"])


def _connect(request: ConnectionRequest):
    return psycopg.connect(
        host=request.host, port=request.port, dbname=request.database,
        user=request.username, password=request.password, connect_timeout=8,
    )


@router.post("/test", response_model=ConnectionResponse)
async def test_postgres(request: ConnectionRequest) -> ConnectionResponse:
    try:
        await asyncio.to_thread(lambda: _test(request))
        return ConnectionResponse(success=True, message="Connection successful! Your PostgreSQL credentials are valid.")
    except psycopg.OperationalError as exc:
        message = str(exc).lower()
        if "password authentication failed" in message:
            friendly, code = "Authentication failed. Please check your username and password.", "AUTH_FAILED"
        elif "does not exist" in message:
            friendly, code = "Database not found. Please verify the database name.", "DATABASE_NOT_FOUND"
        else:
            friendly, code = f"PostgreSQL connection failed: {str(exc).splitlines()[0]}", "CONNECTION_ERROR"
        return ConnectionResponse(success=False, message=friendly, error_code=code)


def _test(request: ConnectionRequest) -> None:
    with _connect(request) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()


@router.post("/databases")
async def list_postgres_databases(request: ConnectionRequest) -> list[dict]:
    def query():
        with _connect(request) as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) FROM information_schema.tables
                WHERE table_catalog = current_database()
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND table_type IN ('BASE TABLE', 'VIEW')
            """)
            return [{"name": request.database, "table_count": cur.fetchone()[0]}]
    try:
        return await asyncio.to_thread(query)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start")
async def start_postgres(request: ConnectionRequest) -> dict:
    databases = await list_postgres_databases(request)
    stream_id = str(uuid.uuid4())
    payload = request.model_dump_json()
    _pending[stream_id] = _encryptor().encrypt(payload)
    count = databases[0]["table_count"]
    return {"stream_id": stream_id, "table_count": count, "requires_confirmation": count >= 500}


@router.get("/stream/{stream_id}", response_class=EventSourceResponse)
async def stream_postgres(stream_id: str) -> AsyncIterable[ServerSentEvent]:
    encrypted = _pending.pop(stream_id, None)
    if not encrypted:
        yield ServerSentEvent(data={"message": "Stream not found or expired", "status": "error"}, event="error")
        return
    request = ConnectionRequest.model_validate_json(_encryptor().decrypt(encrypted))
    started = time.monotonic()
    try:
        yield ServerSentEvent(data={"percentage": 10, "message": "Reading PostgreSQL catalogs", "status": "progress"}, event="progress")
        result = await asyncio.to_thread(extract_postgres_schema, request, started)
        yield ServerSentEvent(data={"percentage": 100, "message": "Extraction complete", "status": "complete"}, event="complete")
        yield ServerSentEvent(data=result.model_dump(), event="result")
    except Exception as exc:
        logger.error(f"PostgreSQL extraction failed: {exc}")
        yield ServerSentEvent(data={"percentage": 0, "message": str(exc), "status": "error"}, event="error")
