"""Connection request/response schemas with error categorization.

Provides Pydantic models for connection testing API endpoint
and user-friendly error message formatting.
"""
from pydantic import BaseModel, field_validator


class ConnectionRequest(BaseModel):
    """Request model for database connection test.

    Validates SQL Server connection parameters.
    """
    host: str
    port: int = 1433
    database: str = ""
    username: str
    password: str

    @field_validator("host")
    @classmethod
    def strip_host_whitespace(cls, v: str) -> str:
        """Strip whitespace from hostname."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Host cannot be empty")
        if len(stripped) > 255:
            raise ValueError("Host must be 255 characters or less")
        return stripped

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port range."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("database")
    @classmethod
    def validate_database(cls, v: str) -> str:
        """Validate database name."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Database name cannot be empty")
        if len(stripped) > 128:
            raise ValueError("Database name must be 128 characters or less")
        return stripped

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Username cannot be empty")
        if len(stripped) > 128:
            raise ValueError("Username must be 128 characters or less")
        return stripped

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password is not empty."""
        if not v:
            raise ValueError("Password cannot be empty")
        return v


class ConnectionResponse(BaseModel):
    """Response model for database connection test."""
    success: bool
    message: str
    error_code: str | None = None


def categorize_error(error_message: str) -> str:
    """Map pyodbc error messages to user-friendly error codes.

    Args:
        error_message: Raw error message from pyodbc

    Returns:
        Error code string for categorization
    """
    upper_msg = error_message.upper()

    # Authentication failures
    if "18456" in error_message or "28000" in error_message:
        return "AUTH_FAILED"

    # Host/network errors
    if "08001" in error_message:
        if "SERVER IS NOT FOUND" in upper_msg or "NOT FOUND" in upper_msg:
            return "HOST_NOT_FOUND"
        return "NETWORK_ERROR"

    # Timeout errors
    if "HYT00" in error_message or "TIMEOUT" in upper_msg:
        return "TIMEOUT"

    # SSL/TLS errors
    if "SSL" in upper_msg or "CERTIFICATE" in upper_msg:
        return "SSL_ERROR"

    # Permission/syntax errors (42000 is SQL Server permission denied)
    if "42000" in error_message:
        return "PERMISSION_ERROR"

    # Driver errors
    if "IM002" in error_message or "DRIVER" in upper_msg:
        return "DRIVER_ERROR"

    # Database not found
    if "CANNOT OPEN DATABASE" in upper_msg or "4060" in error_message:
        return "DATABASE_NOT_FOUND"

    return "UNKNOWN_ERROR"


def format_user_message(success: bool, raw_message: str, error_code: str | None) -> str:
    """Format error message for end users.

    Args:
        success: Whether connection succeeded
        raw_message: Raw message from connection attempt
        error_code: Categorized error code

    Returns:
        User-friendly message string
    """
    if success:
        return "Connection successful! Your database credentials are valid."

    messages = {
        "AUTH_FAILED": "Authentication failed. Please check your username and password.",
        "HOST_NOT_FOUND": "Server not found. Please verify the hostname and ensure the server is accessible.",
        "NETWORK_ERROR": "Network error. Please check your connection and firewall settings.",
        "TIMEOUT": "Connection timed out. The server may be busy or unreachable.",
        "SSL_ERROR": "SSL/TLS error. Please contact your database administrator.",
        "PERMISSION_ERROR": "Permission denied. Your account may not have access to list databases.",
        "DRIVER_ERROR": "Database driver error. Please contact support.",
        "DATABASE_NOT_FOUND": "Database not found. Please verify the database name.",
    }

    if error_code and error_code in messages:
        return messages[error_code]

    # UNKNOWN_ERROR - include raw message for debugging
    return f"Connection failed: {raw_message}"
