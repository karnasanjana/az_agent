"""Connection test API endpoint.

Provides endpoint for testing SQL Server database connectivity
with user-friendly error responses.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException

from app.database.connection import (
    build_connection_string,
    get_db_connection,
    test_connection,
)
from app.schemas.connection import (
    ConnectionRequest,
    ConnectionResponse,
    categorize_error,
    format_user_message,
)
from app.security.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/connection", tags=["connection"])

# Thread pool for synchronous pyodbc calls
_executor = ThreadPoolExecutor(max_workers=2)


@router.post("/test", response_model=ConnectionResponse)
async def test_database_connection(request: ConnectionRequest) -> ConnectionResponse:
    """Test database connection with provided credentials.

    Tests connectivity to a SQL Server database using the provided
    credentials. Returns success status and user-friendly messages.

    SEC-03: Connection is ephemeral - closed immediately after test.

    Args:
        request: Connection parameters (host, port, database, username, password)

    Returns:
        ConnectionResponse with success status, message, and error_code if failed
    """
    success, raw_message = test_connection(
        host=request.host,
        port=request.port,
        database=request.database,
        username=request.username,
        password=request.password,
    )

    error_code = None
    if not success:
        error_code = categorize_error(raw_message)

    message = format_user_message(success, raw_message, error_code)

    return ConnectionResponse(
        success=success,
        message=message,
        error_code=error_code,
    )


@router.post("/databases")
async def list_databases(request: ConnectionRequest) -> list[dict]:
    """List user databases on SQL Server with table counts.

    Connects to the `master` database to enumerate all user databases
    (excluding system databases), then counts user tables in each.
    Databases the user cannot access are silently skipped.

    Args:
        request: Connection parameters (database field is ignored; connects to master)

    Returns:
        List of {"name": str, "table_count": int} sorted by name
    """
    loop = asyncio.get_event_loop()

    def _list_databases():
        results = []

        # Try connecting to master to list all databases (works on SQL Server instances)
        try:
            conn_str = build_connection_string(
                host=request.host,
                port=request.port,
                database="master",
                username=request.username,
                password=request.password,
            )
            with get_db_connection(conn_str) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name"
                )
                db_names = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            # Azure SQL Database may not allow master access — fall back to
            # the database from the connection request (or try to detect it)
            logger.info(f"Cannot access master database, using single-database mode: {e}")
            db_names = []
            # Use the database from the request if provided
            if request.database:
                db_names = [request.database]
            else:
                # Try to get the current database name from the connection
                try:
                    conn_str = build_connection_string(
                        host=request.host,
                        port=request.port,
                        database="",
                        username=request.username,
                        password=request.password,
                    )
                    with get_db_connection(conn_str) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT DB_NAME()")
                        db_name = cursor.fetchone()[0]
                        if db_name and db_name.lower() != "master":
                            db_names = [db_name]
                except Exception:
                    pass

        # For each database, count user tables
        for db_name in db_names:
            try:
                db_conn_str = build_connection_string(
                    host=request.host,
                    port=request.port,
                    database=db_name,
                    username=request.username,
                    password=request.password,
                )
                with get_db_connection(db_conn_str) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT COUNT(*) FROM sys.objects "
                        "WHERE type IN ('U','V') AND is_ms_shipped = 0"
                    )
                    table_count = cursor.fetchone()[0]
                    results.append({"name": db_name, "table_count": table_count})
            except Exception as e:
                logger.warning(
                    f"Skipping database '{db_name}': {e}"
                )
                # Still include the database but with unknown table count
                results.append({"name": db_name, "table_count": 0})

        return results

    try:
        return await loop.run_in_executor(_executor, _list_databases)
    except Exception as e:
        logger.error(f"Failed to list databases: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list databases: {str(e)}")
