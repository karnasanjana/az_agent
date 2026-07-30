"""Diagram persistence API endpoints.

Provides CRUD endpoints for saving, loading, listing, updating,
and deleting diagrams. All endpoints require X-User-ID header
for user isolation. Connection configs are encrypted at rest.
Shared diagrams can be loaded without auth via share token.
"""
from fastapi import APIRouter, Header, HTTPException
from typing import Optional

from app.schemas.diagrams import (
    DiagramFull,
    DiagramMetadata,
    SaveDiagramRequest,
    UpdateDiagramRequest,
    SaveAnnotationsRequest,
    UpdateShareSettingsRequest,
)
from app.services.diagram_storage import DiagramStorage, load_shared_diagram
from app.security.encryption import get_encryptor
from app.security.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/diagrams", tags=["diagrams"])

# Fields to encrypt in connection_configs
_SENSITIVE_FIELDS = {"password", "access_token"}


def _get_storage(x_user_id: str) -> DiagramStorage:
    """Create DiagramStorage instance, validating user ID."""
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(status_code=401, detail="X-User-ID header is required")
    return DiagramStorage(x_user_id.strip())


def _encrypt_configs(diagram_data: dict) -> dict:
    """Encrypt sensitive fields in connection_configs before saving to GCS."""
    configs = diagram_data.get("connection_configs")
    if not configs or not isinstance(configs, list):
        return diagram_data

    encryptor = get_encryptor()
    encrypted_configs = []
    for config in configs:
        encrypted = dict(config)
        for field in _SENSITIVE_FIELDS:
            if field in encrypted and encrypted[field]:
                try:
                    encrypted[field] = encryptor.encrypt(str(encrypted[field]))
                    encrypted[f"_{field}_encrypted"] = True
                except Exception as e:
                    logger.warning(f"Failed to encrypt {field}: {e}")
        encrypted_configs.append(encrypted)

    return {**diagram_data, "connection_configs": encrypted_configs}


def _decrypt_configs(diagram_data: dict) -> dict:
    """Decrypt sensitive fields in connection_configs when loading from GCS."""
    if not diagram_data or "diagram" not in diagram_data:
        return diagram_data

    configs = diagram_data["diagram"].get("connection_configs")
    if not configs or not isinstance(configs, list):
        return diagram_data

    encryptor = get_encryptor()
    decrypted_configs = []
    for config in configs:
        decrypted = dict(config)
        for field in _SENSITIVE_FIELDS:
            if decrypted.get(f"_{field}_encrypted") and field in decrypted:
                try:
                    decrypted[field] = encryptor.decrypt(decrypted[field])
                except Exception as e:
                    logger.warning(f"Failed to decrypt {field}: {e}")
                    decrypted[field] = None
                del decrypted[f"_{field}_encrypted"]
        decrypted_configs.append(decrypted)

    diagram_data["diagram"]["connection_configs"] = decrypted_configs
    return diagram_data


@router.post("", response_model=DiagramMetadata, status_code=201)
async def save_diagram(
    request: SaveDiagramRequest,
    x_user_id: str = Header(...),
) -> DiagramMetadata:
    """Save a new diagram. Encrypts connection configs before storing."""
    storage = _get_storage(x_user_id)
    try:
        diagram_data = _encrypt_configs(request.diagram)
        metadata = storage.save(name=request.name, diagram_data=diagram_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return DiagramMetadata(**metadata)


@router.get("", response_model=list[DiagramMetadata])
async def list_diagrams(
    x_user_id: str = Header(...),
) -> list[DiagramMetadata]:
    """List all diagrams for the current user."""
    storage = _get_storage(x_user_id)
    return [DiagramMetadata(**m) for m in storage.list_all()]


@router.get("/shared/{share_token}", response_model=DiagramFull)
async def load_shared_diagram_endpoint(
    share_token: str,
) -> DiagramFull:
    """Load a shared diagram by its token. No auth required."""
    result = load_shared_diagram(share_token)
    if result is None:
        raise HTTPException(status_code=404, detail="Shared diagram not found or link expired")
    return DiagramFull(**result)


@router.get("/{diagram_id}", response_model=DiagramFull)
async def load_diagram(
    diagram_id: str,
    x_user_id: str = Header(...),
) -> DiagramFull:
    """Load a full diagram. Decrypts connection configs."""
    storage = _get_storage(x_user_id)
    result = storage.load(diagram_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Diagram not found")
    result = _decrypt_configs(result)
    return DiagramFull(**result)


@router.put("/{diagram_id}", response_model=DiagramMetadata)
async def update_diagram(
    diagram_id: str,
    request: UpdateDiagramRequest,
    x_user_id: str = Header(...),
) -> DiagramMetadata:
    """Update an existing diagram. Encrypts connection configs before storing."""
    storage = _get_storage(x_user_id)
    diagram_data = _encrypt_configs(request.diagram)
    metadata = storage.update(
        diagram_id=diagram_id, name=request.name, diagram_data=diagram_data
    )
    if metadata is None:
        raise HTTPException(status_code=404, detail="Diagram not found")
    return DiagramMetadata(**metadata)


@router.delete("/{diagram_id}")
async def delete_diagram(
    diagram_id: str,
    x_user_id: str = Header(...),
) -> dict:
    """Delete a diagram."""
    storage = _get_storage(x_user_id)
    deleted = storage.delete(diagram_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Diagram not found")
    return {"success": True}


@router.post("/{diagram_id}/share")
async def share_diagram(
    diagram_id: str,
    x_user_id: str = Header(...),
) -> dict:
    """Generate a share token for a diagram (creates read-only public link)."""
    storage = _get_storage(x_user_id)
    token = storage.create_share_token(diagram_id)
    if token is None:
        raise HTTPException(status_code=404, detail="Diagram not found")
    return {"share_token": token}


@router.put("/{diagram_id}/share")
async def update_share_settings(
    diagram_id: str,
    request: UpdateShareSettingsRequest,
    x_user_id: str = Header(...),
) -> dict:
    """Update display settings for a shared diagram."""
    storage = _get_storage(x_user_id)
    updated = storage.update_share_settings(
        diagram_id, request.show_relationships, request.share_note
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Diagram not found or not shared")
    return {"success": True}


@router.delete("/{diagram_id}/share")
async def unshare_diagram(
    diagram_id: str,
    x_user_id: str = Header(...),
) -> dict:
    """Revoke the share token for a diagram."""
    storage = _get_storage(x_user_id)
    revoked = storage.revoke_share_token(diagram_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Diagram not found")
    return {"success": True}


@router.get("/{diagram_id}/history")
async def get_history(
    diagram_id: str,
    x_user_id: str = Header(...),
) -> dict:
    """Get schema change history for a diagram."""
    storage = _get_storage(x_user_id)
    history = storage.get_history(diagram_id)
    return {"history": history}


@router.post("/{diagram_id}/sql")
async def save_sql(
    diagram_id: str,
    x_user_id: str = Header(...),
    body: dict = ...,
) -> dict:
    """Save SQL DDL alongside a diagram."""
    storage = _get_storage(x_user_id)
    sql_content = body.get("sql", "")
    if not sql_content:
        raise HTTPException(status_code=400, detail="SQL content is required")
    storage.save_sql(diagram_id, sql_content)
    return {"success": True}


@router.get("/{diagram_id}/sql")
async def get_sql(
    diagram_id: str,
    x_user_id: str = Header(...),
) -> dict:
    """Get saved SQL DDL for a diagram."""
    storage = _get_storage(x_user_id)
    sql = storage.get_sql(diagram_id)
    if sql is None:
        raise HTTPException(status_code=404, detail="SQL not found for this diagram")
    return {"sql": sql}
