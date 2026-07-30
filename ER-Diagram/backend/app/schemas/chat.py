"""Chat API Pydantic models."""
from typing import Literal
from pydantic import BaseModel, Field

from app.schemas.schema import DatabaseSchema


class ChatMessage(BaseModel):
    """A single chat message."""
    role: Literal["user", "assistant"]
    content: str


class SchemaChange(BaseModel):
    """A single structural change to the schema."""
    action: Literal[
        "add_table", "remove_table", "merge_table",
        "add_column", "remove_column", "move_column",
        "add_relationship", "remove_relationship",
    ]
    table: str | None = None
    schema_name: str | None = None
    source_table: str | None = None
    target_table: str | None = None
    column: str | None = None
    data_type: str | None = None
    is_nullable: bool | None = None
    from_table: str | None = None
    to_table: str | None = None
    source_schema: str | None = None
    target_schema: str | None = None
    source_columns: list[str] | None = None
    target_columns: list[str] | None = None
    constraint_name: str | None = None
    columns: list[dict] | None = None


class Suggestion(BaseModel):
    """A single optimization suggestion from the AI."""
    id: str
    title: str
    changes: list[SchemaChange]


class ClarificationOption(BaseModel):
    """A clickable option for a clarification question."""
    id: str
    label: str


class ClarificationQuestion(BaseModel):
    """A structured clarification question with clickable options."""
    id: str
    text: str
    options: list[ClarificationOption]
    allow_custom_input: bool = True


class QueryStep(BaseModel):
    """A single query to execute against a database."""
    source: Literal["bigquery", "sqlserver", "postgres", "dataverse"]
    query: str
    alias: str
    dataset: str | None = None  # BigQuery dataset name


class MergeInstruction(BaseModel):
    """Instructions for merging results from multiple queries in Python."""
    left_alias: str  # alias of left query result
    right_alias: str  # alias of right query result
    left_key: str  # column name to join on in left result
    right_key: str  # column name to join on in right result
    select_columns: list[str] | None = None  # columns to include in output (all if None)
    group_by: list[str] | None = None  # columns to group by after merge
    aggregations: dict[str, str] | None = None  # column -> agg function (avg, sum, count, min, max)


class DataSource(BaseModel):
    """Connection details for a data source."""
    type: Literal["bigquery", "sqlserver", "postgres", "dataverse"]
    # BigQuery
    project_id: str | None = None
    access_token: str | None = None
    # SQL Server / PostgreSQL (same host/port/database/username/password shape)
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    # Dataverse
    environment_url: str | None = None


class ChatRequest(BaseModel):
    """Request to the chat endpoint."""
    message: str
    db_schema: DatabaseSchema = Field(alias="schema")
    history: list[ChatMessage] = []
    data_sources: list[DataSource] = []

    model_config = {"populate_by_name": True}


class ChatResponse(BaseModel):
    """Full (non-streaming) response from the chat endpoint."""
    explanation: str
    suggestions: list[Suggestion] = []
    query_plan: list[QueryStep] | None = None
    query_results: dict | None = None
