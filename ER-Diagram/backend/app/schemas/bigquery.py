"""BigQuery request/response schemas.

Provides Pydantic models for BigQuery API endpoints including
dataset listing and schema extraction.
"""
from pydantic import BaseModel, field_validator


class BigQueryRequest(BaseModel):
    """Request model for BigQuery dataset listing.

    Uses OAuth access token for authentication.
    """
    project_id: str
    access_token: str

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        """Validate project ID is not empty."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Project ID cannot be empty")
        return stripped

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, v: str) -> str:
        """Validate access token is not empty."""
        if not v:
            raise ValueError("Access token cannot be empty")
        return v


class BigQueryExtractionRequest(BaseModel):
    """Request model for BigQuery schema extraction.

    Specifies which datasets to extract from a project.
    """
    project_id: str
    access_token: str
    datasets: list[str]

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        """Validate project ID is not empty."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Project ID cannot be empty")
        return stripped

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, v: str) -> str:
        """Validate access token is not empty."""
        if not v:
            raise ValueError("Access token cannot be empty")
        return v

    @field_validator("datasets")
    @classmethod
    def validate_datasets(cls, v: list[str]) -> list[str]:
        """Validate datasets list is not empty."""
        if not v:
            raise ValueError("At least one dataset must be specified")
        return v
