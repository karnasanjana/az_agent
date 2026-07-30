"""Database connection utilities with ephemeral connection pattern.

SEC-03: Connection closed immediately after schema extraction.
No connection pooling - each connection is created and destroyed per use.
"""
from contextlib import contextmanager
from typing import Generator, Optional
import pyodbc
import logging

from app.security.logging import get_logger

logger = get_logger(__name__)


class ConnectionError(Exception):
    """Custom exception for connection failures."""
    pass


def build_connection_string(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    *,
    driver: str = "ODBC Driver 18 for SQL Server",
    timeout: int = 30,
    trust_server_certificate: bool = True,  # Dev only, should be False in prod
) -> str:
    """Build SQL Server ODBC connection string.

    SEC-01: Connection uses TLS encryption (ODBC Driver 18 default).

    Args:
        host: SQL Server hostname or IP
        port: SQL Server port (typically 1433)
        database: Database name
        username: SQL Server username
        password: SQL Server password
        driver: ODBC driver name
        timeout: Connection timeout in seconds
        trust_server_certificate: Trust self-signed certs (dev only!)

    Returns:
        ODBC connection string

    Note:
        Password is included in string but never logged (see logging filter).
    """
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={host},{port}",
        f"DATABASE={database}",
        f"UID={username}",
        f"PWD={password}",
        "Encrypt=yes",
        f"Connection Timeout={timeout}",
    ]

    if trust_server_certificate:
        parts.append("TrustServerCertificate=yes")

    return ";".join(parts)


@contextmanager
def get_db_connection(
    connection_string: str,
    timeout: int = 30,
) -> Generator[pyodbc.Connection, None, None]:
    """Context manager for ephemeral database connections.

    SEC-03: Connection is ALWAYS closed after the context exits,
    even if an exception occurs. No connection pooling.

    Usage:
        with get_db_connection(conn_str) as conn:
            cursor = conn.cursor()
            # Use connection...
        # Connection is now closed

    Args:
        connection_string: ODBC connection string
        timeout: Connection timeout in seconds

    Yields:
        Active pyodbc.Connection

    Raises:
        ConnectionError: If connection fails
    """
    conn: Optional[pyodbc.Connection] = None
    try:
        logger.info("Opening database connection")
        conn = pyodbc.connect(connection_string, timeout=timeout)
        yield conn
    except pyodbc.Error as e:
        # Log error without connection string (may contain password)
        logger.error(f"Database connection failed: {e.args[0] if e.args else 'Unknown error'}")
        raise ConnectionError(f"Failed to connect to database: {e}") from e
    finally:
        if conn is not None:
            try:
                conn.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")


def test_connection(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
) -> tuple[bool, str]:
    """Test database connectivity.

    SEC-03: Connection is immediately closed after test.

    Args:
        host: SQL Server hostname or IP
        port: SQL Server port
        database: Database name
        username: SQL Server username
        password: SQL Server password

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        conn_str = build_connection_string(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
        )

        with get_db_connection(conn_str, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return True, "Connection successful"

    except ConnectionError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Unexpected error: {e}"
