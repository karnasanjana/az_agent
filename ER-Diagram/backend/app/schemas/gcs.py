"""Google Cloud Storage request schemas.

Lists data files (CSV/JSON/JSONL/Parquet) in a bucket and infers a table per
file. Auth reuses the Google OAuth access token from sign-in (needs the
devstorage.read_only scope).
"""
from pydantic import BaseModel, field_validator


def _clean_bucket(v: str) -> str:
    b = v.strip().removeprefix("gs://").strip("/")
    if not b:
        raise ValueError("Bucket name cannot be empty")
    return b


class GcsRequest(BaseModel):
    """List data files in a bucket (optionally under a prefix)."""
    bucket: str
    prefix: str = ""
    access_token: str

    @field_validator("bucket")
    @classmethod
    def _bucket(cls, v: str) -> str:
        return _clean_bucket(v)

    @field_validator("access_token")
    @classmethod
    def _token(cls, v: str) -> str:
        if not v:
            raise ValueError("Access token cannot be empty")
        return v


class GcsExtractionRequest(BaseModel):
    """Extract a schema (one table per file) for the chosen files."""
    bucket: str
    prefix: str = ""
    access_token: str
    files: list[str]

    @field_validator("bucket")
    @classmethod
    def _bucket(cls, v: str) -> str:
        return _clean_bucket(v)

    @field_validator("access_token")
    @classmethod
    def _token(cls, v: str) -> str:
        if not v:
            raise ValueError("Access token cannot be empty")
        return v

    @field_validator("files")
    @classmethod
    def _files(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one file must be specified")
        return v
