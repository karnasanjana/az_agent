"""Schema extraction Pydantic models and SQL queries.

Provides data models for database schema metadata including tables,
columns, foreign keys, indexes, and extraction progress tracking.

Used by SchemaExtractor service to structure extracted metadata.
"""
from typing import Literal
from pydantic import BaseModel


class Column(BaseModel):
    """Database column metadata."""
    name: str
    data_type: str  # Simplified type (varchar, not varchar(255))
    is_nullable: bool
    is_primary_key: bool = False
    is_identity: bool = False
    description: str | None = None  # AI-generated plain-English description


class ForeignKey(BaseModel):
    """Foreign key relationship.

    Supports composite foreign keys via source_columns/target_columns arrays.
    """
    constraint_name: str
    source_table: str
    source_schema: str
    source_columns: list[str]  # Supports composite FKs
    target_table: str
    target_schema: str
    target_columns: list[str]  # Matching columns in target


class Index(BaseModel):
    """Index metadata."""
    name: str
    index_type: str  # CLUSTERED, NONCLUSTERED, etc.
    is_unique: bool
    columns: list[str]  # Column names in key order
    included_columns: list[str] = []  # Non-key included columns


class Table(BaseModel):
    """Database table or view with all metadata."""
    object_id: int  # SQL Server object_id for internal use
    schema_name: str
    table_name: str
    columns: list[Column]
    indexes: list[Index] = []
    is_view: bool = False  # True for views, False for base tables
    description: str | None = None  # AI-generated plain-English description


class DatabaseSchema(BaseModel):
    """Complete database schema extraction result."""
    database_name: str
    tables: list[Table]
    foreign_keys: list[ForeignKey]
    extraction_time_seconds: float
    table_count: int
    standalone_table_count: int  # Tables with no FK relationships
    dataset_order: dict[str, int] | None = None  # schema_name → addition order (1 = first)
    dataset_sources: dict[str, str] | None = None  # schema_name → "bigquery" or "sqlserver"


class ExtractionProgress(BaseModel):
    """Progress update for SSE streaming."""
    percentage: int  # 0-100
    current_table: str | None = None
    message: str
    status: Literal["progress", "complete", "error", "warning"]


def simplify_data_type(sql_type: str) -> str:
    """Simplify SQL Server data type to user-friendly name.

    Strips precision/length from types for non-technical users.

    Examples:
        varchar(255) -> varchar
        decimal(18,2) -> decimal
        nvarchar(max) -> nvarchar
        datetime2(7) -> datetime2
        int -> int (unchanged)

    Args:
        sql_type: Raw SQL Server data type name

    Returns:
        Simplified type name without precision/length
    """
    # Types that don't need simplification
    simple_types = {
        'int', 'bigint', 'smallint', 'tinyint',
        'bit', 'money', 'smallmoney',
        'float', 'real',
        'date', 'time', 'datetime', 'datetime2', 'datetimeoffset', 'smalldatetime',
        'text', 'ntext', 'image',
        'uniqueidentifier', 'xml', 'sql_variant',
    }

    # Return as-is if already simple
    type_lower = sql_type.lower().strip()
    if type_lower in simple_types:
        return type_lower

    # Strip precision/length from types like varchar(255), decimal(18,2)
    if '(' in type_lower:
        return type_lower.split('(')[0]

    return type_lower


# =============================================================================
# SQL Query Constants
# =============================================================================
# Queries include both user tables (type='U') and views (type='V')

TABLE_COUNT_QUERY = """
SELECT COUNT(*) AS table_count
FROM sys.objects
WHERE type IN ('U', 'V') AND is_ms_shipped = 0
"""

TABLES_QUERY = """
SELECT
    o.object_id,
    s.name AS schema_name,
    o.name AS table_name,
    o.type AS object_type
FROM sys.objects o
INNER JOIN sys.schemas s ON o.schema_id = s.schema_id
WHERE o.type IN ('U', 'V')  -- User tables and views
  AND o.is_ms_shipped = 0   -- Exclude system objects
ORDER BY s.name, o.name
"""

COLUMNS_QUERY = """
SELECT
    c.object_id,
    c.name AS column_name,
    t.name AS data_type,
    c.is_nullable,
    c.is_identity,
    c.column_id
FROM sys.columns c
INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
WHERE c.object_id IN (
    SELECT object_id FROM sys.objects WHERE type IN ('U', 'V') AND is_ms_shipped = 0
)
ORDER BY c.object_id, c.column_id
"""

PRIMARY_KEYS_QUERY = """
SELECT
    i.object_id,
    c.name AS column_name
FROM sys.indexes i
INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
WHERE i.is_primary_key = 1
ORDER BY i.object_id, ic.key_ordinal
"""

FOREIGN_KEYS_QUERY = """
SELECT
    fk.name AS constraint_name,
    fk.object_id AS constraint_object_id,
    fk.parent_object_id AS source_table_id,
    OBJECT_NAME(fk.parent_object_id) AS source_table,
    SCHEMA_NAME(t1.schema_id) AS source_schema,
    fk.referenced_object_id AS target_table_id,
    OBJECT_NAME(fk.referenced_object_id) AS target_table,
    SCHEMA_NAME(t2.schema_id) AS target_schema,
    COL_NAME(fkc.parent_object_id, fkc.parent_column_id) AS source_column,
    COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) AS target_column,
    fkc.constraint_column_id AS column_ordinal
FROM sys.foreign_keys fk
INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
INNER JOIN sys.tables t1 ON fk.parent_object_id = t1.object_id
INNER JOIN sys.tables t2 ON fk.referenced_object_id = t2.object_id
ORDER BY fk.name, fkc.constraint_column_id
"""

INDEXES_QUERY = """
SELECT
    i.object_id,
    i.name AS index_name,
    i.type_desc AS index_type,
    i.is_unique,
    c.name AS column_name,
    ic.key_ordinal,
    ic.is_included_column
FROM sys.indexes i
INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
WHERE i.is_primary_key = 0
  AND i.type > 0  -- Exclude heaps (type = 0)
  AND i.object_id IN (
      SELECT object_id FROM sys.objects WHERE type IN ('U', 'V') AND is_ms_shipped = 0
  )
ORDER BY i.object_id, i.name, ic.key_ordinal
"""
