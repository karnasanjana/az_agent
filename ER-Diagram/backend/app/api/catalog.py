"""Catalog seam — serve a diagram's reviewed schema to az_agent (the pipeline agent).

az_agent grounds Azure pipelines against the schema an engineer extracted and
reviewed HERE, instead of re-probing the source. The catalog is just a SHARED
diagram, so `source_id` is its share token — no extra auth, reusing
load_shared_diagram (which already strips credentials).

Response = az_agent's catalog contract:
    {"source_id", "schema_version", "database_name", "tables": [...],
     "foreign_keys": [...], "connections": [...]}  # connections = non-secret engine/host/db/port
"""
from fastapi import APIRouter, HTTPException

from app.services.diagram_storage import load_shared_diagram

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def catalog_payload(source_id: str, shared_data: dict) -> dict:
    """Reshape a load_shared_diagram() result into the az_agent catalog contract."""
    diagram = shared_data.get("diagram") or {}
    schema = diagram.get("schema") or {}
    history = shared_data.get("schema_history") or []
    return {
        "source_id": source_id,
        "schema_version": history[-1].get("version", 1) if history else 1,
        "database_name": schema.get("database_name") or diagram.get("database_name", ""),
        "tables": schema.get("tables", []),
        "foreign_keys": schema.get("foreign_keys", []),
        # Non-secret connection identity (engine + host/db/port) so az_agent can
        # build a pipeline without the engineer re-typing the connection.
        "connections": shared_data.get("connections", []),
    }


@router.get("/{source_id}")
async def get_catalog(source_id: str) -> dict:
    """The reviewed schema for a shared source (share token), for az_agent grounding."""
    data = load_shared_diagram(source_id)
    if not data:
        raise HTTPException(status_code=404, detail="Catalog not found — share the diagram first")
    return catalog_payload(source_id, data)
