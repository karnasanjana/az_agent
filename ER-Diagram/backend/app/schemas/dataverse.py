"""Dataverse request/response schemas.

Provides Pydantic models for Dataverse API endpoints including
entity listing and schema extraction.
"""
import re

from pydantic import BaseModel, field_validator


class DataverseRequest(BaseModel):
    """Request model for Dataverse entity listing.

    Uses OAuth access token for authentication with Dataverse Web API.
    """
    environment_url: str
    access_token: str

    @field_validator("environment_url")
    @classmethod
    def validate_environment_url(cls, v: str) -> str:
        """Validate and normalize environment URL.

        Strips protocol prefix and validates domain format.
        """
        stripped = v.strip().rstrip("/")
        # Strip protocol if present
        stripped = re.sub(r"^https?://", "", stripped)
        if not stripped:
            raise ValueError("Environment URL cannot be empty")
        # Basic domain validation
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$", stripped):
            raise ValueError(
                "Environment URL must be a valid domain "
                "(e.g., org.crm.dynamics.com)"
            )
        return stripped

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, v: str) -> str:
        """Validate access token is not empty."""
        if not v:
            raise ValueError("Access token cannot be empty")
        return v


class DataverseExtractionRequest(BaseModel):
    """Request model for Dataverse schema extraction.

    Specifies which entities to extract from a Dataverse environment.
    """
    environment_url: str
    access_token: str
    entities: list[str]

    @field_validator("environment_url")
    @classmethod
    def validate_environment_url(cls, v: str) -> str:
        """Validate and normalize environment URL."""
        stripped = v.strip().rstrip("/")
        stripped = re.sub(r"^https?://", "", stripped)
        if not stripped:
            raise ValueError("Environment URL cannot be empty")
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$", stripped):
            raise ValueError(
                "Environment URL must be a valid domain "
                "(e.g., org.crm.dynamics.com)"
            )
        return stripped

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, v: str) -> str:
        """Validate access token is not empty."""
        if not v:
            raise ValueError("Access token cannot be empty")
        return v

    @field_validator("entities")
    @classmethod
    def validate_entities(cls, v: list[str]) -> list[str]:
        """Validate entities list is not empty."""
        if not v:
            raise ValueError("At least one entity must be specified")
        return v
