"""Diagram persistence request/response schemas.

Provides Pydantic models for diagram CRUD API endpoints.
"""
from pydantic import BaseModel, field_validator


class SaveDiagramRequest(BaseModel):
    """Request model for saving a new diagram."""

    name: str
    diagram: dict

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Strip whitespace, reject empty, enforce max length."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Diagram name cannot be empty")
        if len(stripped) > 100:
            raise ValueError("Diagram name must be 100 characters or less")
        return stripped


class UpdateDiagramRequest(BaseModel):
    """Request model for updating an existing diagram."""

    name: str
    diagram: dict

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Strip whitespace, reject empty, enforce max length."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Diagram name cannot be empty")
        if len(stripped) > 100:
            raise ValueError("Diagram name must be 100 characters or less")
        return stripped


class DiagramMetadata(BaseModel):
    """Diagram metadata returned in list and save responses."""

    id: str
    name: str
    created_at: str
    updated_at: str
    table_count: int
    database_name: str
    share_token: str | None = None


class DiagramFull(BaseModel):
    """Full diagram response including metadata and diagram data."""

    metadata: DiagramMetadata
    diagram: dict


class Annotation(BaseModel):
    """A user annotation on a table or column."""

    id: str
    target_type: str  # 'table' or 'column'
    target_table: str  # schema_name.table_name
    target_column: str | None = None  # column name (if column annotation)
    text: str
    created_at: str
    created_by: str
    updated_at: str


class SaveAnnotationsRequest(BaseModel):
    """Request model for saving annotations."""

    annotations: list[dict]


class UpdateShareSettingsRequest(BaseModel):
    """Request model for updating share display settings."""

    show_relationships: bool = False
    share_note: str = ""
