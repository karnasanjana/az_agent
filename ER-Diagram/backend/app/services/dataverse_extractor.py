"""Dataverse schema extraction service.

Extracts database schema from Microsoft Dataverse environments including
entities (tables), attributes (columns), and relationships (foreign keys).
Uses the Dataverse Web API (OData v4) with Bearer token authentication.
"""
import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

import requests

from app.schemas.schema import (
    Column,
    DatabaseSchema,
    ExtractionProgress,
    ForeignKey,
    Table,
)
from app.security.logging import get_logger

logger = get_logger(__name__)

# Thread pool for running synchronous HTTP calls
_executor = ThreadPoolExecutor(max_workers=2)

# Dataverse attribute type to SQL-style type mapping
_TYPE_MAP: dict[str, str] = {
    "String": "nvarchar",
    "Memo": "nvarchar",
    "Integer": "int",
    "BigInt": "bigint",
    "Double": "float",
    "Decimal": "decimal",
    "Money": "decimal",
    "Boolean": "bit",
    "DateTime": "datetime",
    "Lookup": "uniqueidentifier",
    "Uniqueidentifier": "uniqueidentifier",
    "Picklist": "int",
    "State": "int",
    "Status": "int",
}


def _map_attribute_type(attr_type: str) -> str:
    """Map a Dataverse attribute type to a simplified SQL-style type."""
    return _TYPE_MAP.get(attr_type, "nvarchar")


def _generate_object_id(entity_name: str) -> int:
    """Generate a stable integer object_id from entity name."""
    hash_bytes = hashlib.md5(entity_name.encode()).digest()[:8]
    return int.from_bytes(hash_bytes, byteorder="big") & 0x7FFFFFFF


class DataverseSchemaExtractor:
    """Extracts complete schema from a Dataverse environment.

    Uses the Dataverse Web API (OData v4) with Bearer token auth.
    """

    def __init__(
        self,
        environment_url: str,
        access_token: str,
        entities: list[str] | None = None,
    ):
        self.base_url = f"https://{environment_url}"
        self.access_token = access_token
        self.entities = entities or []
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
        }
        self._tables: list[Table] = []
        self._foreign_keys: list[ForeignKey] = []
        self._start_time: float = 0

    def _api_get(self, path: str) -> dict:
        """Make a GET request to the Dataverse Web API."""
        url = f"{self.base_url}{path}"
        response = requests.get(url, headers=self._headers, timeout=60)
        response.raise_for_status()
        return response.json()

    def list_entities(self) -> list[dict]:
        """List entities available in the Dataverse environment.

        Returns:
            List of {"name": str, "display_name": str, "is_custom": bool}
            sorted by name.
        """
        path = (
            "/api/data/v9.2/EntityDefinitions"
            "?$select=LogicalName,SchemaName,DisplayName,EntitySetName,"
            "PrimaryIdAttribute,PrimaryNameAttribute,IsCustomEntity"
            "&$filter=IsIntersect eq false and IsValidForAdvancedFind eq true"
        )
        data = self._api_get(path)

        results = []
        for entity in data.get("value", []):
            logical_name = entity.get("LogicalName", "")
            display_label = entity.get("DisplayName", {})
            localized = display_label.get("UserLocalizedLabel")
            display_name = (
                localized.get("Label", logical_name)
                if localized
                else logical_name
            )
            results.append({
                "name": logical_name,
                "display_name": display_name,
                "is_custom": entity.get("IsCustomEntity", False),
                "table_count": 1,  # Each entity is one table
            })

        results.sort(key=lambda x: x["name"])
        return results

    async def count_entities(self) -> int:
        """Count selected entities."""
        return len(self.entities)

    async def extract_with_progress(self) -> AsyncGenerator[ExtractionProgress, None]:
        """Extract schema with progress updates."""
        self._start_time = time.monotonic()
        loop = asyncio.get_event_loop()

        yield ExtractionProgress(
            percentage=5,
            current_table=None,
            message="Starting Dataverse extraction...",
            status="progress",
        )
        await asyncio.sleep(0)

        try:
            total = len(self.entities)
            if total == 0:
                yield ExtractionProgress(
                    percentage=100,
                    current_table=None,
                    message="No entities selected.",
                    status="warning",
                )
                return

            entity_set = set(self.entities)

            for idx, entity_name in enumerate(self.entities):
                # Extract attributes (columns)
                yield ExtractionProgress(
                    percentage=10 + int(80 * idx / total),
                    current_table=entity_name,
                    message=f"Extracting attributes for {entity_name}",
                    status="progress",
                )
                await asyncio.sleep(0)

                table = await loop.run_in_executor(
                    _executor, self._extract_entity, entity_name
                )
                self._tables.append(table)

                # Extract ManyToOne relationships (foreign keys)
                fks = await loop.run_in_executor(
                    _executor, self._extract_relationships, entity_name, entity_set
                )
                self._foreign_keys.extend(fks)

                yield ExtractionProgress(
                    percentage=10 + int(80 * (idx + 1) / total),
                    current_table=entity_name,
                    message=f"Extracted {entity_name} ({len(table.columns)} columns)",
                    status="progress",
                )
                await asyncio.sleep(0)

            yield ExtractionProgress(
                percentage=95,
                current_table=None,
                message="Finalizing extraction...",
                status="progress",
            )
            await asyncio.sleep(0)

            yield ExtractionProgress(
                percentage=100,
                current_table=None,
                message="Extraction complete",
                status="complete",
            )

        except Exception as e:
            logger.error(f"Dataverse schema extraction failed: {e}")
            yield ExtractionProgress(
                percentage=0,
                current_table=None,
                message=f"Extraction failed: {str(e)}",
                status="error",
            )
            raise

    def _extract_entity(self, entity_name: str) -> Table:
        """Extract attributes for a single entity."""
        path = (
            f"/api/data/v9.2/EntityDefinitions(LogicalName='{entity_name}')"
            "/Attributes"
            "?$select=LogicalName,SchemaName,DisplayName,AttributeType,"
            "AttributeTypeName,IsPrimaryId,IsPrimaryName,RequiredLevel"
        )
        data = self._api_get(path)

        columns: list[Column] = []
        for attr in data.get("value", []):
            attr_type = attr.get("AttributeType", "String")
            required_level = attr.get("RequiredLevel", {})
            required_value = required_level.get("Value", "None")

            columns.append(Column(
                name=attr.get("LogicalName", ""),
                data_type=_map_attribute_type(attr_type),
                is_nullable=(required_value != "ApplicationRequired"),
                is_primary_key=attr.get("IsPrimaryId", False),
                is_identity=False,
            ))

        return Table(
            object_id=_generate_object_id(entity_name),
            schema_name="dataverse",
            table_name=entity_name,
            columns=columns,
            indexes=[],
            is_view=False,
        )

    def _extract_relationships(
        self, entity_name: str, entity_set: set[str]
    ) -> list[ForeignKey]:
        """Extract ManyToOne relationships for an entity.

        Only includes relationships where both source and target entities
        are in the selected entities set.
        """
        path = (
            f"/api/data/v9.2/EntityDefinitions(LogicalName='{entity_name}')"
            "/ManyToOneRelationships"
            "?$select=SchemaName,ReferencedEntity,ReferencedAttribute,"
            "ReferencingEntity,ReferencingAttribute"
        )
        data = self._api_get(path)

        fks: list[ForeignKey] = []
        for rel in data.get("value", []):
            referenced_entity = rel.get("ReferencedEntity", "")
            referencing_entity = rel.get("ReferencingEntity", "")

            # Only include if both entities are in the selected set
            if referenced_entity not in entity_set:
                continue
            if referencing_entity not in entity_set:
                continue

            fks.append(ForeignKey(
                constraint_name=rel.get("SchemaName", ""),
                source_table=referencing_entity,
                source_schema="dataverse",
                source_columns=[rel.get("ReferencingAttribute", "")],
                target_table=referenced_entity,
                target_schema="dataverse",
                target_columns=[rel.get("ReferencedAttribute", "")],
            ))

        return fks

    def get_result(self) -> DatabaseSchema:
        """Get final extraction result after extraction completes."""
        elapsed = time.monotonic() - self._start_time

        tables_with_fk: set[str] = set()
        for fk in self._foreign_keys:
            tables_with_fk.add(f"{fk.source_schema}.{fk.source_table}")
            tables_with_fk.add(f"{fk.target_schema}.{fk.target_table}")

        standalone_count = sum(
            1
            for t in self._tables
            if f"{t.schema_name}.{t.table_name}" not in tables_with_fk
        )

        return DatabaseSchema(
            database_name="Dataverse",
            tables=self._tables,
            foreign_keys=self._foreign_keys,
            extraction_time_seconds=round(elapsed, 2),
            table_count=len(self._tables),
            standalone_table_count=standalone_count,
        )
