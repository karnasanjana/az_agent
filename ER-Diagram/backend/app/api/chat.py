"""Chat API for AI schema advisor and data queries.

Provides endpoints for sending messages to the schema advisor
and executing AI-generated queries against connected databases.
Supports SSE streaming for real-time agent workflow visibility.
"""
import asyncio
import json
import time
from collections.abc import AsyncIterable
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from pydantic import BaseModel, Field

from app.schemas.chat import ChatRequest, ChatResponse, DataSource
from app.schemas.schema import DatabaseSchema
from app.services.schema_advisor import (
    chat_with_advisor,
    fix_failed_query,
    generate_auto_documentation,
    infer_missing_relationships,
    summarize_results,
)
from app.services.query_executor import (
    execute_bigquery,
    execute_sqlserver,
    execute_postgres,
    execute_dataverse,
    consolidate_results,
    MERGE_SOFT_CAP,
)
from app.security.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

_executor = ThreadPoolExecutor(max_workers=4)


def _parse_dataverse_query(query: str, environment_url: str, access_token: str) -> dict:
    """Parse an AI-generated Dataverse OData query string into execute_dataverse kwargs.

    Expected format from AI: "entity_name?$select=col1,col2&$filter=expr&$top=N&$orderby=expr"
    or just "entity_name" for all records.
    """
    import urllib.parse

    query = query.strip()
    # Split entity name from query params
    if "?" in query:
        entity_part, params_str = query.split("?", 1)
        params = urllib.parse.parse_qs(params_str)
    else:
        entity_part = query
        params = {}

    kwargs: dict = {
        "entity_name": entity_part.strip().strip("/"),
        "environment_url": environment_url,
        "access_token": access_token,
    }

    if "$select" in params:
        kwargs["select"] = params["$select"][0]
    if "$filter" in params:
        kwargs["filter_expr"] = params["$filter"][0]
    if "$top" in params:
        try:
            kwargs["top"] = int(params["$top"][0])
        except ValueError:
            pass
    if "$orderby" in params:
        kwargs["orderby"] = params["$orderby"][0]

    return kwargs


def _build_data_sources_info(data_sources: list[DataSource]) -> str:
    """Build a text description of available data sources for Claude."""
    if not data_sources:
        return ""
    lines = []
    for ds in data_sources:
        if ds.type == "bigquery":
            lines.append(f"- BigQuery project: {ds.project_id}")
        elif ds.type == "sqlserver":
            lines.append(f"- SQL Server: {ds.host}:{ds.port}/{ds.database}")
        elif ds.type == "postgres":
            lines.append(f"- PostgreSQL: {ds.host}:{ds.port}/{ds.database}")
        elif ds.type == "dataverse":
            lines.append(f"- Dataverse: {ds.environment_url}")
    return "\n".join(lines)


# =============================================================================
# SSE Streaming Endpoint — real-time agent workflow
# =============================================================================

@router.post("/stream", response_class=EventSourceResponse)
async def stream_message(request: ChatRequest) -> AsyncIterable[ServerSentEvent]:
    """Generate SSE events for the agent workflow."""
    loop = asyncio.get_event_loop()
    data_sources_info = _build_data_sources_info(request.data_sources)

    # --- Step 1: Planning ---
    yield ServerSentEvent(
        data=({"type": "planning", "status": "running", "description": "Analyzing question..."}),
        event="step",
    )
    await asyncio.sleep(0)

    plan_start = time.monotonic()
    try:
        response = await loop.run_in_executor(
            _executor,
            lambda: chat_with_advisor(
                user_message=request.message,
                schema=request.db_schema,
                history=request.history,
                data_sources_info=data_sources_info,
            ),
        )
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        yield ServerSentEvent(
            data=({"type": "planning", "status": "error", "error": str(e)}),
            event="step",
        )
        yield ServerSentEvent(
            data=({"error": f"Planning failed: {str(e)}"}),
            event="error",
        )
        return

    plan_time = round(time.monotonic() - plan_start, 2)

    # Use Claude's explanation as the planning description
    plan_description = response.get("explanation", "Analyzed question and generated query plan")

    yield ServerSentEvent(
        data=({
            "type": "planning",
            "status": "success",
            "time": plan_time,
            "description": plan_description,
        }),
        event="step",
    )
    await asyncio.sleep(0)

    # --- Non-data responses: emit result immediately ---
    if response["type"] != "data" or not response.get("query_plan"):
        if response["type"] == "clarification":
            result = {
                "type": "clarification",
                "explanation": response["explanation"],
                "suggestions": [],
                "query_plan": None,
                "query_results": None,
                "questions": [q.model_dump() for q in response.get("questions", [])],
            }
        else:
            result = {
                "type": "schema",
                "explanation": response["explanation"],
                "suggestions": [s.model_dump() for s in response.get("suggestions", [])],
                "query_plan": None,
                "query_results": None,
            }
        yield ServerSentEvent(data=(result), event="result")
        return

    # --- Step 2: Execute queries one by one (with retry on failure) ---
    MAX_RETRIES = 2
    query_plan = response["query_plan"]
    merge_instruction = response.get("merge")

    bq_source = next((ds for ds in request.data_sources if ds.type == "bigquery"), None)
    sql_source = next((ds for ds in request.data_sources if ds.type == "sqlserver"), None)
    pg_source = next((ds for ds in request.data_sources if ds.type == "postgres"), None)
    dv_source = next((ds for ds in request.data_sources if ds.type == "dataverse"), None)
    row_limit = MERGE_SOFT_CAP if merge_instruction else None

    results = []
    aliases = []
    workflow_steps = [{
        "type": "planning",
        "status": "success",
        "time": plan_time,
        "description": "Analyzed question and generated query plan",
    }]

    for step in query_plan:
        aliases.append(step.alias)
        current_query = step.query
        attempt = 0
        result = None

        while attempt <= MAX_RETRIES:
            # Emit "running" event
            desc = step.alias if attempt == 0 else f"{step.alias} (retry {attempt})"
            yield ServerSentEvent(
                data=({
                    "type": "query",
                    "status": "running" if attempt == 0 else "retrying",
                    "source": step.source,
                    "alias": step.alias,
                    "description": f"Retrying with corrected query (attempt {attempt})..." if attempt > 0 else None,
                }),
                event="step",
            )
            await asyncio.sleep(0)

            step_start = time.monotonic()

            if step.source == "bigquery":
                if not bq_source or not bq_source.project_id or not bq_source.access_token:
                    result = {"error": "BigQuery credentials not available"}
                    break
                kwargs = {"query": current_query, "project_id": bq_source.project_id, "access_token": bq_source.access_token}
                if row_limit:
                    kwargs["max_rows"] = row_limit
                result = await loop.run_in_executor(_executor, lambda kw=kwargs: execute_bigquery(**kw))

            elif step.source == "sqlserver":
                if not sql_source or not sql_source.host:
                    result = {"error": "SQL Server credentials not available"}
                    break
                kwargs = {
                    "query": current_query, "host": sql_source.host,
                    "port": sql_source.port or 1433, "database": sql_source.database or "",
                    "username": sql_source.username or "", "password": sql_source.password or "",
                }
                if row_limit:
                    kwargs["max_rows"] = row_limit
                result = await loop.run_in_executor(_executor, lambda kw=kwargs: execute_sqlserver(**kw))

            elif step.source == "postgres":
                if not pg_source or not pg_source.host:
                    result = {"error": "PostgreSQL credentials not available"}
                    break
                kwargs = {
                    "query": current_query, "host": pg_source.host,
                    "port": pg_source.port or 5432, "database": pg_source.database or "",
                    "username": pg_source.username or "", "password": pg_source.password or "",
                }
                if row_limit:
                    kwargs["max_rows"] = row_limit
                result = await loop.run_in_executor(_executor, lambda kw=kwargs: execute_postgres(**kw))

            elif step.source == "dataverse":
                if not dv_source or not dv_source.environment_url or not dv_source.access_token:
                    result = {"error": "Dataverse credentials not available"}
                    break
                # Parse OData query from the AI-generated query string
                dv_kwargs = _parse_dataverse_query(current_query, dv_source.environment_url, dv_source.access_token)
                if row_limit:
                    dv_kwargs["max_rows"] = row_limit
                result = await loop.run_in_executor(_executor, lambda kw=dv_kwargs: execute_dataverse(**kw))
            else:
                result = {"error": f"Unknown source type: {step.source}"}
                break

            step_elapsed = round(time.monotonic() - step_start, 2)

            # Success — break out of retry loop
            if "error" not in result:
                break

            # Failed — try to fix the query
            if attempt < MAX_RETRIES:
                logger.info(f"Query failed for {step.alias}, attempting fix (attempt {attempt + 1})")
                yield ServerSentEvent(
                    data=({
                        "type": "query",
                        "status": "fixing",
                        "source": step.source,
                        "alias": step.alias,
                        "description": f"Query failed — asking AI to fix it...",
                        "error": result["error"],
                    }),
                    event="step",
                )
                await asyncio.sleep(0)

                fixed_query = await loop.run_in_executor(
                    _executor,
                    lambda src=step.source, q=current_query, err=result["error"]: fix_failed_query(src, q, err),
                )

                if fixed_query:
                    current_query = fixed_query
                    attempt += 1
                    continue
                else:
                    # Couldn't fix — give up
                    logger.warning(f"Could not fix query for {step.alias}")
                    break
            else:
                break

        # Record final result for this step
        results.append(result)
        step_elapsed = round(time.monotonic() - step_start, 2) if result else 0
        step_info = {
            "type": "query",
            "source": step.source,
            "alias": step.alias,
            "query": current_query,
        }
        if result and "error" in result:
            step_info.update({"status": "error", "error": result["error"], "time": step_elapsed})
            if attempt > 0:
                step_info["description"] = f"Failed after {attempt} retry attempt{'s' if attempt > 1 else ''}"
        else:
            step_info.update({
                "status": "success",
                "rows": result.get("row_count", 0) if result else 0,
                "time": step_elapsed,
                "bytes_processed": result.get("bytes_processed") if result else None,
            })
            if attempt > 0:
                step_info["description"] = f"Succeeded after {attempt} retry attempt{'s' if attempt > 1 else ''}"
        workflow_steps.append(step_info)

        # Emit completed step
        yield ServerSentEvent(data=(step_info), event="step")
        await asyncio.sleep(0)

    # --- Step 3: Merge ---
    if merge_instruction:
        yield ServerSentEvent(
            data=({"type": "merge", "status": "running", "description": "Merging cross-database results..."}),
            event="step",
        )
        await asyncio.sleep(0)

    consolidated = await loop.run_in_executor(
        _executor,
        lambda: consolidate_results(results, aliases, merge_instruction),
    )

    if merge_instruction and consolidated.get("merged"):
        merged = consolidated["merged"]
        merge_step = {
            "type": "merge",
            "status": "error" if "error" in merged else "success",
            "time": 0,
        }
        if "error" not in merged:
            desc = ""
            if merge_instruction.get("steps"):
                keys = [f"{s.get('left_key', '?')}" for s in merge_instruction["steps"]]
                desc = f"Chained merge on {', '.join(keys)}"
            else:
                lk = merge_instruction.get("left_key") or merge_instruction.get("left_alias", "?")
                desc = f"Merged on {lk}"
            if merge_instruction.get("group_by"):
                desc += f" → grouped by {', '.join(merge_instruction['group_by'])}"
            if merge_instruction.get("aggregations"):
                aggs = [f"{fn}({col})" for col, fn in merge_instruction["aggregations"].items()]
                desc += f" → {', '.join(aggs)}"
            merge_step["description"] = desc
            merge_step["rows"] = merged.get("row_count", 0)
        else:
            merge_step["error"] = merged["error"]
        workflow_steps.append(merge_step)
        yield ServerSentEvent(data=(merge_step), event="step")
        await asyncio.sleep(0)

    # --- Step 4: Summarize results using Haiku ---
    # Merged (cross-database) result if there was one; otherwise the single
    # query's own rows — so a one-database query gets a plain-English summary too.
    merged_data = consolidated.get("merged")
    if not merged_data:
        ok_sources = [s for s in consolidated.get("sources", []) if "error" not in s and s.get("rows")]
        if len(ok_sources) == 1:
            merged_data = ok_sources[0]
    summary = None
    if merged_data and "error" not in merged_data and merged_data.get("rows"):
        yield ServerSentEvent(
            data=({"type": "summarizing", "status": "running", "description": "Generating insights from results..."}),
            event="step",
        )
        await asyncio.sleep(0)

        summary_start = time.monotonic()
        summary = await loop.run_in_executor(
            _executor,
            lambda: summarize_results(
                question=request.message,
                columns=merged_data.get("columns", []),
                rows=merged_data.get("rows", []),
            ),
        )
        summary_time = round(time.monotonic() - summary_start, 2)

        summary_step = {
            "type": "summarizing",
            "status": "success",
            "time": summary_time,
            "description": "Generated result insights",
        }
        workflow_steps.append(summary_step)
        yield ServerSentEvent(data=(summary_step), event="step")
        await asyncio.sleep(0)

    # Add workflow to consolidated results
    total_time = round(sum(s.get("time", 0) for s in workflow_steps), 2)
    consolidated["workflow"] = {"steps": workflow_steps, "total_time": total_time}

    # --- Final result ---
    # Truncate source rows for the SSE payload (merge already used all rows)
    MAX_DISPLAY_ROWS = 500
    display_sources = []
    for src in consolidated.get("sources", []):
        if "rows" in src and len(src["rows"]) > MAX_DISPLAY_ROWS:
            display_sources.append({
                **src,
                "rows": src["rows"][:MAX_DISPLAY_ROWS],
                "row_count": src.get("row_count", len(src["rows"])),
                "truncated": True,
            })
        else:
            display_sources.append(src)
    display_results = {**consolidated, "sources": display_sources}

    final = {
        "type": "data",
        "plan_description": response["explanation"],  # Planning context (shown in workflow)
        "explanation": summary or "",                  # Result summary from Haiku (shown below result)
        "suggestions": [],
        "query_plan": [step.model_dump() for step in query_plan],
        "query_results": display_results,
    }
    yield ServerSentEvent(data=(final), event="result")


# =============================================================================
# Legacy non-streaming endpoint (kept for backward compatibility)
# =============================================================================

@router.post("/message")
async def send_message(request: ChatRequest) -> dict:
    """Send a message to the schema advisor (non-streaming)."""
    try:
        loop = asyncio.get_event_loop()
        data_sources_info = _build_data_sources_info(request.data_sources)

        plan_start = time.monotonic()
        response = await loop.run_in_executor(
            _executor,
            lambda: chat_with_advisor(
                user_message=request.message,
                schema=request.db_schema,
                history=request.history,
                data_sources_info=data_sources_info,
            ),
        )
        plan_time = round(time.monotonic() - plan_start, 2)

        if response["type"] == "data" and response.get("query_plan"):
            query_plan = response["query_plan"]
            merge_instruction = response.get("merge")

            bq_source = next((ds for ds in request.data_sources if ds.type == "bigquery"), None)
            sql_source = next((ds for ds in request.data_sources if ds.type == "sqlserver"), None)
            dv_source = next((ds for ds in request.data_sources if ds.type == "dataverse"), None)
            row_limit = MERGE_SOFT_CAP if merge_instruction else None

            results = []
            aliases = []
            workflow_steps = [{"type": "planning", "status": "success", "time": plan_time, "description": "Analyzed question and generated query plan"}]
            total_start = time.monotonic()

            for step in query_plan:
                aliases.append(step.alias)
                step_start = time.monotonic()
                step_info = {"type": "query", "source": step.source, "alias": step.alias, "query": step.query}

                if step.source == "bigquery" and bq_source and bq_source.project_id and bq_source.access_token:
                    kwargs = {"query": step.query, "project_id": bq_source.project_id, "access_token": bq_source.access_token}
                    if row_limit: kwargs["max_rows"] = row_limit
                    result = execute_bigquery(**kwargs)
                elif step.source == "sqlserver" and sql_source and sql_source.host:
                    kwargs = {"query": step.query, "host": sql_source.host, "port": sql_source.port or 1433,
                              "database": sql_source.database or "", "username": sql_source.username or "", "password": sql_source.password or ""}
                    if row_limit: kwargs["max_rows"] = row_limit
                    result = execute_sqlserver(**kwargs)
                elif step.source == "postgres" and pg_source and pg_source.host:
                    kwargs = {"query": step.query, "host": pg_source.host, "port": pg_source.port or 5432,
                              "database": pg_source.database or "", "username": pg_source.username or "", "password": pg_source.password or ""}
                    if row_limit: kwargs["max_rows"] = row_limit
                    result = execute_postgres(**kwargs)
                elif step.source == "dataverse" and dv_source and dv_source.environment_url and dv_source.access_token:
                    dv_kwargs = _parse_dataverse_query(step.query, dv_source.environment_url, dv_source.access_token)
                    if row_limit: dv_kwargs["max_rows"] = row_limit
                    result = execute_dataverse(**dv_kwargs)
                else:
                    result = {"error": f"Credentials not available for {step.source}"}

                results.append(result)
                step_elapsed = round(time.monotonic() - step_start, 2)
                if "error" in result:
                    step_info.update({"status": "error", "error": result["error"], "time": step_elapsed})
                else:
                    step_info.update({"status": "success", "rows": result.get("row_count", 0), "time": step_elapsed, "bytes_processed": result.get("bytes_processed")})
                workflow_steps.append(step_info)

            consolidated = consolidate_results(results, aliases, merge_instruction)

            if merge_instruction and consolidated.get("merged"):
                merged = consolidated["merged"]
                merge_step = {"type": "merge", "status": "error" if "error" in merged else "success", "time": 0}
                if "error" not in merged:
                    desc = "Merged results"
                    if merge_instruction.get("group_by"):
                        desc += f" → grouped by {', '.join(merge_instruction['group_by'])}"
                    merge_step["description"] = desc
                    merge_step["rows"] = merged.get("row_count", 0)
                workflow_steps.append(merge_step)

            total_elapsed = round(time.monotonic() - total_start + plan_time, 2)
            consolidated["workflow"] = {"steps": workflow_steps, "total_time": total_elapsed}

            return {
                "type": "data",
                "explanation": response["explanation"],
                "suggestions": [],
                "query_plan": [step.model_dump() for step in query_plan],
                "query_results": consolidated,
            }

        elif response["type"] == "clarification":
            return {
                "type": "clarification",
                "explanation": response["explanation"],
                "suggestions": [],
                "query_plan": None,
                "query_results": None,
                "questions": [q.model_dump() for q in response.get("questions", [])],
            }
        else:
            return {
                "type": "schema",
                "explanation": response["explanation"],
                "suggestions": [s.model_dump() for s in response.get("suggestions", [])],
                "query_plan": None,
                "query_results": None,
            }

    except Exception as e:
        logger.error(f"Chat message failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


# =============================================================================
# Auto-Documentation Endpoint
# =============================================================================

class AutoDocumentRequest(BaseModel):
    """Request body for the auto-document endpoint.

    The incoming JSON field name is "schema"; we alias it to db_schema
    internally to avoid shadowing BaseModel.schema.
    """
    model_config = {"populate_by_name": True}
    db_schema: DatabaseSchema = Field(alias="schema")


@router.post("/auto-document")
async def auto_document(request: AutoDocumentRequest) -> dict:
    """Generate AI descriptions for every table and column in a schema.

    Uses Claude Haiku to produce descriptions in a single fast call,
    then merges them into the provided schema and returns the enriched schema.
    """
    try:
        loop = asyncio.get_event_loop()
        descriptions = await loop.run_in_executor(
            _executor,
            lambda: generate_auto_documentation(request.db_schema),
        )

        # Merge descriptions into a copy of the schema
        schema_dict = request.db_schema.model_dump()
        table_descriptions = descriptions.get("tables", {}) or {}

        for table in schema_dict.get("tables", []):
            # Try multiple key formats: "table_name", "schema.table_name", "schema_name.table_name"
            t_name = table["table_name"]
            s_name = table.get("schema_name", "")
            t_desc = (
                table_descriptions.get(t_name)
                or table_descriptions.get(f"{s_name}.{t_name}")
                or {}
            )
            if isinstance(t_desc, dict):
                if t_desc.get("description"):
                    table["description"] = t_desc["description"]
                col_desc_map = t_desc.get("columns", {}) or {}
                for col in table.get("columns", []):
                    desc = col_desc_map.get(col["name"])
                    if desc:
                        col["description"] = desc

        return {"schema": schema_dict, "table_count": len(table_descriptions)}
    except Exception as e:
        logger.error(f"Auto-document failed: {e}")
        raise HTTPException(status_code=500, detail=f"Auto-document failed: {str(e)}")


# =============================================================================
# Infer Relationships Endpoint
# =============================================================================

class InferRelationshipsRequest(BaseModel):
    """Request body for the infer-relationships endpoint."""
    model_config = {"populate_by_name": True}
    db_schema: DatabaseSchema = Field(alias="schema")


@router.post("/infer-relationships")
async def infer_relationships(request: InferRelationshipsRequest) -> dict:
    """Use Claude Sonnet to infer likely missing FK relationships.

    Returns:
        {"relationships": [{source_table, source_schema, source_column,
                            target_table, target_schema, target_column,
                            confidence (0-1 float), reason}]}
    """
    try:
        loop = asyncio.get_event_loop()
        relationships = await loop.run_in_executor(
            _executor,
            lambda: infer_missing_relationships(request.db_schema),
        )
        return {"relationships": relationships}
    except Exception as e:
        logger.error(f"Infer relationships failed: {e}")
        raise HTTPException(status_code=500, detail=f"Infer relationships failed: {str(e)}")


# =============================================================================
# Impact Analysis Endpoint
# =============================================================================

class ImpactAnalysisRequest(BaseModel):
    """Request body for the impact-analysis endpoint."""
    model_config = {"populate_by_name": True}
    db_schema: DatabaseSchema = Field(alias="schema")
    target_table: str
    target_column: str | None = None


@router.post("/impact-analysis")
async def impact_analysis(request: ImpactAnalysisRequest) -> dict:
    """Analyze the impact of changing a table or column.

    Returns all tables/columns that reference or depend on the target,
    plus AI-generated risk assessment.
    """
    schema = request.db_schema
    target_table = request.target_table
    target_column = request.target_column

    # Find direct FK dependencies (tables that reference target)
    direct_refs = []
    for fk in schema.foreign_keys:
        # Tables that reference this table via FK
        if fk.target_table == target_table:
            if target_column is None or target_column in fk.target_columns:
                direct_refs.append({
                    "type": "referenced_by",
                    "table": f"{fk.source_schema}.{fk.source_table}",
                    "columns": fk.source_columns,
                    "constraint": fk.constraint_name,
                    "relationship": f"{fk.source_table}.{','.join(fk.source_columns)} → {fk.target_table}.{','.join(fk.target_columns)}",
                })
        # Tables this table references
        if fk.source_table == target_table:
            if target_column is None or target_column in fk.source_columns:
                direct_refs.append({
                    "type": "references",
                    "table": f"{fk.target_schema}.{fk.target_table}",
                    "columns": fk.target_columns,
                    "constraint": fk.constraint_name,
                    "relationship": f"{fk.source_table}.{','.join(fk.source_columns)} → {fk.target_table}.{','.join(fk.target_columns)}",
                })

    # Cascade analysis: find indirect dependencies (2nd-level refs)
    indirect_refs = []
    direct_tables = {ref["table"].split(".")[-1] for ref in direct_refs if ref["type"] == "referenced_by"}
    for fk in schema.foreign_keys:
        if fk.target_table in direct_tables and fk.source_table != target_table:
            indirect_refs.append({
                "type": "indirect_dependency",
                "table": f"{fk.source_schema}.{fk.source_table}",
                "via": fk.target_table,
                "constraint": fk.constraint_name,
            })

    # AI risk assessment
    risk_summary = None
    try:
        target_desc = f"{target_table}" + (f".{target_column}" if target_column else "")
        dep_count = len(direct_refs) + len(indirect_refs)
        tables_affected = list({r["table"] for r in direct_refs + indirect_refs})

        if dep_count == 0:
            risk_summary = {
                "level": "low",
                "message": f"No foreign key dependencies found for {target_desc}. Changes are safe from a referential integrity perspective.",
            }
        elif dep_count <= 3:
            risk_summary = {
                "level": "medium",
                "message": f"Changing {target_desc} affects {dep_count} relationship(s) across {len(tables_affected)} table(s). Review each dependency before making changes.",
            }
        else:
            risk_summary = {
                "level": "high",
                "message": f"Changing {target_desc} has wide impact: {dep_count} relationship(s) across {len(tables_affected)} table(s). This is a high-risk change that requires careful migration planning.",
            }
    except Exception:
        pass

    return {
        "target": {
            "table": target_table,
            "column": target_column,
        },
        "direct_dependencies": direct_refs,
        "indirect_dependencies": indirect_refs,
        "total_impact_count": len(direct_refs) + len(indirect_refs),
        "risk": risk_summary,
    }
