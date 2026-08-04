"""GCS-based diagram storage service.

Provides CRUD operations for diagram persistence using Google Cloud Storage.
Diagrams are stored per-user under diagrams/{user_id}/{diagram_id}.json in a GCS bucket.
Shared diagrams are indexed at diagrams/_shared/{share_token}.json for public access.
"""
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timezone

from google.cloud import storage

# Bucket/project are env-configurable so a different deployment (or a local test)
# isn't pinned to one tenant's GCS. Defaults keep the original behaviour.
BUCKET_NAME = os.environ.get("GCS_BUCKET", "erdiagram")
GCS_PROJECT = os.environ.get("GCS_PROJECT", "gemini-for-zion")
GCS_PREFIX = "diagrams"
SHARED_PREFIX = "diagrams/_shared"
MAX_DIAGRAMS_PER_USER = 50


def _get_bucket():
    """Get the GCS bucket."""
    client = storage.Client(project=GCS_PROJECT)
    return client.bucket(BUCKET_NAME)


def _compute_schema_diff(old_schema: dict, new_schema: dict) -> dict | None:
    """Compare two schemas and return a change entry, or None if no changes."""
    old_tables = {t.get("table_name", ""): t for t in old_schema.get("tables", [])}
    new_tables = {t.get("table_name", ""): t for t in new_schema.get("tables", [])}

    old_names = set(old_tables.keys())
    new_names = set(new_tables.keys())

    added_tables = sorted(new_names - old_names)
    removed_tables = sorted(old_names - new_names)

    # Column-level changes for tables that exist in both
    modified_tables = []
    for name in sorted(old_names & new_names):
        old_cols = {c.get("name", ""): c for c in old_tables[name].get("columns", [])}
        new_cols = {c.get("name", ""): c for c in new_tables[name].get("columns", [])}

        old_col_names = set(old_cols.keys())
        new_col_names = set(new_cols.keys())

        added_cols = sorted(new_col_names - old_col_names)
        removed_cols = sorted(old_col_names - new_col_names)

        # Type changes for columns that exist in both
        type_changes = []
        for col_name in sorted(old_col_names & new_col_names):
            old_type = old_cols[col_name].get("data_type", "")
            new_type = new_cols[col_name].get("data_type", "")
            if old_type != new_type:
                type_changes.append({
                    "column": col_name,
                    "old_type": old_type,
                    "new_type": new_type,
                })

        if added_cols or removed_cols or type_changes:
            entry = {"table": name, "changes": []}
            for c in added_cols:
                col_type = new_cols[c].get("data_type", "unknown")
                entry["changes"].append(f"+ column {c} ({col_type})")
            for c in removed_cols:
                entry["changes"].append(f"- column {c}")
            for tc in type_changes:
                entry["changes"].append(
                    f"~ {tc['column']}: {tc['old_type']} → {tc['new_type']}"
                )
            modified_tables.append(entry)

    # FK changes
    old_fks = {fk.get("constraint_name", ""): fk for fk in old_schema.get("foreign_keys", [])}
    new_fks = {fk.get("constraint_name", ""): fk for fk in new_schema.get("foreign_keys", [])}
    added_fks = sorted(set(new_fks.keys()) - set(old_fks.keys()))
    removed_fks = sorted(set(old_fks.keys()) - set(new_fks.keys()))

    if not added_tables and not removed_tables and not modified_tables and not added_fks and not removed_fks:
        return None

    return {
        "added_tables": added_tables,
        "removed_tables": removed_tables,
        "modified_tables": modified_tables,
        "added_foreign_keys": added_fks,
        "removed_foreign_keys": removed_fks,
        "summary": _build_summary(added_tables, removed_tables, modified_tables, added_fks, removed_fks),
    }


def _build_summary(
    added_tables: list,
    removed_tables: list,
    modified_tables: list,
    added_fks: list,
    removed_fks: list,
) -> str:
    """Build a human-readable one-line summary of changes."""
    parts = []
    if added_tables:
        parts.append(f"{len(added_tables)} table(s) added")
    if removed_tables:
        parts.append(f"{len(removed_tables)} table(s) removed")
    if modified_tables:
        total_col_changes = sum(len(m["changes"]) for m in modified_tables)
        parts.append(f"{total_col_changes} column change(s) across {len(modified_tables)} table(s)")
    if added_fks:
        parts.append(f"{len(added_fks)} relationship(s) added")
    if removed_fks:
        parts.append(f"{len(removed_fks)} relationship(s) removed")
    return "; ".join(parts) if parts else "No changes"


class DiagramStorage:
    """GCS-based diagram CRUD operations.

    Each user gets a prefix under GCS_PREFIX/. Diagrams are stored
    as individual JSON blobs named by UUID.
    """

    def __init__(self, user_id: str) -> None:
        self.user_id = self._sanitize(user_id)
        self.prefix = f"{GCS_PREFIX}/{self.user_id}"
        self.bucket = _get_bucket()

    @staticmethod
    def _sanitize(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9\-]", "_", value)

    def _blob_path(self, diagram_id: str) -> str:
        safe_id = self._sanitize(diagram_id)
        return f"{self.prefix}/{safe_id}.json"

    def _sql_blob_path(self, diagram_id: str) -> str:
        safe_id = self._sanitize(diagram_id)
        return f"{self.prefix}/{safe_id}.sql"

    def save_sql(self, diagram_id: str, sql_content: str) -> None:
        """Save SQL DDL alongside a diagram."""
        blob = self.bucket.blob(self._sql_blob_path(diagram_id))
        blob.upload_from_string(sql_content, content_type="text/sql")

    def get_sql(self, diagram_id: str) -> str | None:
        """Get saved SQL DDL for a diagram."""
        blob = self.bucket.blob(self._sql_blob_path(diagram_id))
        if not blob.exists():
            return None
        return blob.download_as_text()

    def save(self, name: str, diagram_data: dict) -> dict:
        if self.count() >= MAX_DIAGRAMS_PER_USER:
            raise ValueError(
                f"Maximum of {MAX_DIAGRAMS_PER_USER} diagrams per user reached. "
                "Please delete some diagrams before saving new ones."
            )

        diagram_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        tables = diagram_data.get("tables", [])
        if not tables:
            schema = diagram_data.get("schema", {})
            tables = schema.get("tables", []) if isinstance(schema, dict) else []

        metadata = {
            "id": diagram_id,
            "name": name,
            "created_at": now,
            "updated_at": now,
            "table_count": len(tables),
            "database_name": diagram_data.get("database_name", ""),
            "share_token": None,
        }

        file_data = {"metadata": metadata, "diagram": diagram_data}
        blob = self.bucket.blob(self._blob_path(diagram_id))
        blob.upload_from_string(
            json.dumps(file_data, indent=2),
            content_type="application/json",
        )

        return metadata

    def update(self, diagram_id: str, name: str, diagram_data: dict) -> dict | None:
        blob = self.bucket.blob(self._blob_path(diagram_id))

        if not blob.exists():
            return None

        existing = json.loads(blob.download_as_text())
        metadata = existing["metadata"]

        # --- Schema change tracking ---
        old_schema = existing.get("diagram", {}).get("schema", {})
        new_schema = diagram_data.get("schema", {})
        change_entry = _compute_schema_diff(old_schema, new_schema)
        history = existing.get("schema_history", [])
        if change_entry:
            change_entry["timestamp"] = datetime.now(timezone.utc).isoformat()
            change_entry["version"] = len(history) + 1
            history.append(change_entry)
            # Keep last 50 change entries to avoid unbounded growth
            if len(history) > 50:
                history = history[-50:]

        tables = diagram_data.get("tables", [])
        if not tables:
            schema = diagram_data.get("schema", {})
            tables = schema.get("tables", []) if isinstance(schema, dict) else []

        metadata["name"] = name
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        metadata["table_count"] = len(tables)
        metadata["database_name"] = diagram_data.get("database_name", "")

        file_data = {
            "metadata": metadata,
            "diagram": diagram_data,
            "schema_history": history,
        }
        blob.upload_from_string(
            json.dumps(file_data, indent=2),
            content_type="application/json",
        )

        return metadata

    def get_history(self, diagram_id: str) -> list[dict]:
        """Get schema change history for a diagram."""
        blob = self.bucket.blob(self._blob_path(diagram_id))
        if not blob.exists():
            return []
        data = json.loads(blob.download_as_text())
        return data.get("schema_history", [])

    def list_all(self) -> list[dict]:
        results = []
        blobs = self.bucket.list_blobs(prefix=f"{self.prefix}/")
        for blob in blobs:
            if not blob.name.endswith(".json"):
                continue
            try:
                data = json.loads(blob.download_as_text())
                results.append(data["metadata"])
            except (json.JSONDecodeError, KeyError):
                continue

        results.sort(key=lambda m: m.get("updated_at", ""), reverse=True)
        return results

    def load(self, diagram_id: str) -> dict | None:
        blob = self.bucket.blob(self._blob_path(diagram_id))

        if not blob.exists():
            return None

        return json.loads(blob.download_as_text())

    def delete(self, diagram_id: str) -> bool:
        blob = self.bucket.blob(self._blob_path(diagram_id))

        if not blob.exists():
            return False

        blob.delete()

        # Also delete the SQL file if it exists
        sql_blob = self.bucket.blob(self._sql_blob_path(diagram_id))
        if sql_blob.exists():
            sql_blob.delete()

        return True

    def count(self) -> int:
        blobs = list(self.bucket.list_blobs(prefix=f"{self.prefix}/"))
        return len([b for b in blobs if b.name.endswith(".json")])

    def create_share_token(self, diagram_id: str) -> str | None:
        """Generate a share token for a diagram and create a shared index file."""
        blob = self.bucket.blob(self._blob_path(diagram_id))
        if not blob.exists():
            return None

        data = json.loads(blob.download_as_text())
        metadata = data["metadata"]

        # If already shared, return existing token
        if metadata.get("share_token"):
            return metadata["share_token"]

        # Generate a URL-safe token
        token = secrets.token_urlsafe(16)
        metadata["share_token"] = token
        data["metadata"] = metadata

        # Update the diagram file
        blob.upload_from_string(
            json.dumps(data, indent=2), content_type="application/json"
        )

        # Create shared index pointer
        pointer = {"user_id": self.user_id, "diagram_id": diagram_id}
        shared_blob = self.bucket.blob(f"{SHARED_PREFIX}/{token}.json")
        shared_blob.upload_from_string(
            json.dumps(pointer), content_type="application/json"
        )

        return token

    def update_share_settings(self, diagram_id: str, show_relationships: bool, share_note: str) -> bool:
        """Update display settings for a shared diagram."""
        blob = self.bucket.blob(self._blob_path(diagram_id))
        if not blob.exists():
            return False

        data = json.loads(blob.download_as_text())
        metadata = data["metadata"]
        if not metadata.get("share_token"):
            return False  # Not shared

        metadata["share_settings"] = {
            "show_relationships": show_relationships,
            "share_note": share_note,
        }
        data["metadata"] = metadata
        blob.upload_from_string(
            json.dumps(data, indent=2), content_type="application/json"
        )
        return True

    def revoke_share_token(self, diagram_id: str) -> bool:
        """Remove share token from a diagram and delete the shared index."""
        blob = self.bucket.blob(self._blob_path(diagram_id))
        if not blob.exists():
            return False

        data = json.loads(blob.download_as_text())
        metadata = data["metadata"]
        token = metadata.get("share_token")
        if not token:
            return True  # Already unshared

        metadata["share_token"] = None
        data["metadata"] = metadata
        blob.upload_from_string(
            json.dumps(data, indent=2), content_type="application/json"
        )

        # Delete shared index pointer
        shared_blob = self.bucket.blob(f"{SHARED_PREFIX}/{token}.json")
        if shared_blob.exists():
            shared_blob.delete()

        return True


def load_shared_diagram(token: str) -> dict | None:
    """Load a diagram by its share token (no auth required)."""
    bucket = _get_bucket()

    # Look up the pointer
    pointer_blob = bucket.blob(f"{SHARED_PREFIX}/{token}.json")
    if not pointer_blob.exists():
        return None

    pointer = json.loads(pointer_blob.download_as_text())
    user_id = pointer["user_id"]
    diagram_id = pointer["diagram_id"]

    # Load the actual diagram
    storage = DiagramStorage(user_id)
    data = storage.load(diagram_id)
    if data is None:
        return None

    # Strip credentials from the diagram, but keep a NON-SECRET connection
    # descriptor (engine + host/db/port) so az_agent can build a pipeline from
    # this source without the engineer re-typing the connection. Secrets
    # (password/access_token/username) never cross the share token.
    diagram = data.get("diagram", {})
    connections = _public_connections(diagram.pop("connection_configs", None))

    return {
        "metadata": data["metadata"],
        "diagram": diagram,
        "schema_history": data.get("schema_history", []),
        "connections": connections,
    }


# Only these connection fields are safe to expose over a (no-auth) share token —
# everything else (password, access_token, username, encryption flags) is dropped.
_PUBLIC_CONN_FIELDS = {"type", "host", "port", "database", "project_id",
                       "environment_url", "bq_dataset", "schema"}


def _public_connections(configs: object) -> list[dict]:
    if not isinstance(configs, list):
        return []
    return [
        {k: v for k, v in c.items() if k in _PUBLIC_CONN_FIELDS and v not in (None, "")}
        for c in configs if isinstance(c, dict)
    ]
