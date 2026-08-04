"""SharePoint request/response schemas.

Pydantic models for the SharePoint connector: listing lists in a site and
extracting their schema. Auth is a delegated Microsoft Graph access token
(scope Sites.Read.All), acquired in the browser via MSAL — same pattern as
Dataverse, different resource.
"""
import re

from pydantic import BaseModel, field_validator


def _normalize_site_url(v: str) -> str:
    """Strip protocol/trailing slash and validate a SharePoint site URL like
    `contoso.sharepoint.com/sites/Sales`."""
    stripped = re.sub(r"^https?://", "", v.strip()).rstrip("/")
    if not stripped:
        raise ValueError("Site URL cannot be empty")
    # hostname[/server-relative/path] — hostname must look like a domain
    host = stripped.split("/", 1)[0]
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$", host):
        raise ValueError(
            "Site URL must start with a valid host "
            "(e.g. contoso.sharepoint.com/sites/Sales)"
        )
    return stripped


class SharePointRequest(BaseModel):
    """Request to list the lists in a SharePoint site."""
    site_url: str
    access_token: str

    @field_validator("site_url")
    @classmethod
    def _site(cls, v: str) -> str:
        return _normalize_site_url(v)

    @field_validator("access_token")
    @classmethod
    def _token(cls, v: str) -> str:
        if not v:
            raise ValueError("Access token cannot be empty")
        return v


class SharePointExtractionRequest(BaseModel):
    """Request to extract schema for the chosen SharePoint lists."""
    site_url: str
    access_token: str
    lists: list[str]

    @field_validator("site_url")
    @classmethod
    def _site(cls, v: str) -> str:
        return _normalize_site_url(v)

    @field_validator("access_token")
    @classmethod
    def _token(cls, v: str) -> str:
        if not v:
            raise ValueError("Access token cannot be empty")
        return v

    @field_validator("lists")
    @classmethod
    def _lists(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one list must be specified")
        return v
