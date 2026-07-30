"""Query execution service for BigQuery and SQL Server.

Executes read-only queries against connected databases and returns
results as structured data. Supports cross-database consolidation.
"""
import re
import time

from app.security.logging import get_logger

logger = get_logger(__name__)

# Maximum rows to return from a query (display only — keeps UI responsive)
MAX_ROWS = 500
# Soft cap for merge queries — beyond this, results are approximate (with warning)
MERGE_SOFT_CAP = 500_000
# Timeout for entire merge operation (seconds)
MERGE_TIMEOUT = 60
# Dangerous SQL patterns to block
DANGEROUS_PATTERNS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE|MERGE)\b',
    re.IGNORECASE
)


def validate_query(sql: str) -> str | None:
    """Validate that a SQL query is read-only.

    Returns None if valid, error message if invalid.
    """
    stripped = sql.strip().rstrip(';').strip()
    if not stripped:
        return "Query is empty"

    match = DANGEROUS_PATTERNS.search(stripped)
    if match:
        return f"Query contains forbidden keyword: {match.group(0).upper()}"

    return None


def execute_bigquery(
    query: str,
    project_id: str,
    access_token: str,
    max_rows: int | None = None,
) -> dict:
    """Execute a read-only query against BigQuery.

    Args:
        query: SQL query to execute
        project_id: GCP project ID
        access_token: OAuth access token

    Returns:
        {"columns": [...], "rows": [[...], ...], "row_count": int, "truncated": bool}
    """
    error = validate_query(query)
    if error:
        return {"error": error}

    try:
        from google.cloud import bigquery
        from google.oauth2.credentials import Credentials

        credentials = Credentials(token=access_token)
        client = bigquery.Client(project=project_id, credentials=credentials)

        job = client.query(query)
        result = job.result()

        columns = [field.name for field in result.schema]
        rows = []
        truncated = False

        row_limit = max_rows if max_rows is not None else MAX_ROWS
        for i, row in enumerate(result):
            if i >= row_limit:
                truncated = True
                break
            rows.append([_serialize_value(row[col]) for col in columns])

        resp = {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "total_rows": result.total_rows,
            "truncated": truncated,
            "bytes_processed": job.total_bytes_processed,
        }
        if truncated and row_limit == MERGE_SOFT_CAP:
            resp["warning"] = f"Query returned more than {MERGE_SOFT_CAP:,} rows — results may be approximate. Add filters or GROUP BY to narrow the data."
        return resp
    except Exception as e:
        logger.error(f"BigQuery query failed: {e}")
        return {"error": str(e)}


def execute_sqlserver(
    query: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    max_rows: int | None = None,
) -> dict:
    """Execute a read-only query against SQL Server.

    Args:
        query: SQL query to execute
        host/port/database/username/password: Connection details

    Returns:
        {"columns": [...], "rows": [[...], ...], "row_count": int, "truncated": bool}
    """
    error = validate_query(query)
    if error:
        return {"error": error}

    try:
        import pyodbc

        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={host},{port};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"TrustServerCertificate=yes;"
        )
        conn = pyodbc.connect(conn_str, timeout=30)
        cursor = conn.cursor()
        cursor.execute(query)

        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = []
        truncated = False

        row_limit = max_rows if max_rows is not None else MAX_ROWS
        for i, row in enumerate(cursor.fetchall()):
            if i >= row_limit:
                truncated = True
                break
            rows.append([_serialize_value(v) for v in row])

        cursor.close()
        conn.close()

        resp = {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
        if truncated and row_limit == MERGE_SOFT_CAP:
            resp["warning"] = f"Query returned more than {MERGE_SOFT_CAP:,} rows — results may be approximate. Add filters or GROUP BY to narrow the data."
        return resp
    except Exception as e:
        logger.error(f"SQL Server query failed: {e}")
        return {"error": str(e)}


def execute_postgres(
    query: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    max_rows: int | None = None,
) -> dict:
    """Execute a read-only query against PostgreSQL (psycopg, same driver the
    extractor uses). Mirrors execute_sqlserver — validate, run, row-cap, serialize.

    Returns {"columns", "rows", "row_count", "truncated"} or {"error"}.
    """
    error = validate_query(query)
    if error:
        return {"error": error}

    try:
        import psycopg

        conn = psycopg.connect(
            host=host, port=port or 5432, dbname=database,
            user=username, password=password, connect_timeout=30,
        )
        try:
            cur = conn.execute(query)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = []
            truncated = False
            row_limit = max_rows if max_rows is not None else MAX_ROWS
            for i, row in enumerate(cur):
                if i >= row_limit:
                    truncated = True
                    break
                rows.append([_serialize_value(v) for v in row])
        finally:
            conn.close()

        resp = {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}
        if truncated and row_limit == MERGE_SOFT_CAP:
            resp["warning"] = f"Query returned more than {MERGE_SOFT_CAP:,} rows — results may be approximate. Add filters or GROUP BY to narrow the data."
        return resp
    except Exception as e:
        logger.error(f"PostgreSQL query failed: {e}")
        return {"error": str(e)}


def execute_dataverse(
    entity_name: str,
    environment_url: str,
    access_token: str,
    select: str | None = None,
    filter_expr: str | None = None,
    top: int | None = None,
    orderby: str | None = None,
    max_rows: int | None = None,
) -> dict:
    """Execute a read-only OData query against Dataverse Web API.

    Args:
        entity_name: The entity set name (plural, e.g. 'accounts', 'contacts')
        environment_url: Dataverse environment domain (e.g. 'org.crm.dynamics.com')
        access_token: OAuth Bearer token
        select: $select columns (comma-separated)
        filter_expr: $filter OData expression
        top: $top limit
        orderby: $orderby expression
        max_rows: Override default row limit

    Returns:
        {"columns": [...], "rows": [[...], ...], "row_count": int, "truncated": bool}
    """
    try:
        import requests

        base_url = environment_url
        if not base_url.startswith("https://"):
            base_url = f"https://{base_url}"

        # Build OData query parameters
        params = {}
        if select:
            params["$select"] = select
        if filter_expr:
            params["$filter"] = filter_expr
        if orderby:
            params["$orderby"] = orderby

        row_limit = max_rows if max_rows is not None else MAX_ROWS
        # Request one extra row to detect truncation
        params["$top"] = str(min(top or row_limit, row_limit) + 1)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
            "Prefer": "odata.include-annotations=OData.Community.Display.V1.FormattedValue",
        }

        url = f"{base_url}/api/data/v9.2/{entity_name}"
        response = requests.get(url, headers=headers, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()

        records = data.get("value", [])

        # Extract columns from first record (skip OData metadata fields)
        if not records:
            return {"columns": [], "rows": [], "row_count": 0, "truncated": False}

        columns = [
            k for k in records[0].keys()
            if not k.startswith("@") and not k.startswith("_") and not k.endswith("@OData.Community.Display.V1.FormattedValue")
        ]

        truncated = len(records) > row_limit
        rows = []
        for record in records[:row_limit]:
            rows.append([_serialize_value(record.get(col)) for col in columns])

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    except Exception as e:
        logger.error(f"Dataverse query failed: {e}")
        return {"error": str(e)}


def consolidate_results(
    results: list[dict],
    aliases: list[str],
    merge_instruction: dict | None = None,
) -> dict:
    """Merge multiple query results into a combined view.

    If merge_instruction is provided, joins result sets in Python
    and produces an aggregated merged result. Supports multi-step chained merges.

    Returns:
        {"sources": [{"alias": str, "columns": [...], "rows": [...], ...}, ...],
         "merged": {...} if merge was performed}
    """
    sources = []
    for result, alias in zip(results, aliases):
        sources.append({"alias": alias, **result})

    output: dict = {"sources": sources}

    # Perform application-level merge if instructed
    if merge_instruction:
        merge_start = time.monotonic()
        try:
            merged = _execute_merge(sources, merge_instruction)
            elapsed = time.monotonic() - merge_start
            if merged:
                logger.info(f"Merge completed in {elapsed:.1f}s")
                # Check for source warnings and propagate
                warnings = []
                for s in sources:
                    if s.get("warning"):
                        warnings.append(s["warning"])
                if warnings:
                    merged["warning"] = " | ".join(warnings)
                output["merged"] = merged
        except TimeoutError:
            output["merged"] = {"error": f"Merge timed out after {MERGE_TIMEOUT}s. Try narrowing your query with filters."}
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            output["merged"] = {"error": f"Merge failed: {str(e)}"}

    return output


def _execute_merge(sources: list[dict], instruction: dict) -> dict | None:
    """Execute merge instruction — supports both single-step and multi-step merges."""
    steps = instruction.get("steps")
    if steps:
        # Multi-step chained merge
        return _chained_merge(sources, steps, instruction)
    else:
        # Single-step merge (backward compatible)
        return _single_merge(sources, instruction)


def _single_merge(
    sources: list[dict],
    instruction: dict,
    extra_sources: list[dict] | None = None,
) -> dict | None:
    """Join two result sets and optionally aggregate."""
    all_sources = list(sources)
    if extra_sources:
        all_sources.extend(extra_sources)

    left_alias = instruction.get("left_alias") or instruction.get("left")
    right_alias = instruction.get("right_alias") or instruction.get("right")
    left_key = instruction.get("left_key")
    right_key = instruction.get("right_key")
    group_by = instruction.get("group_by")
    aggregations = instruction.get("aggregations", {})

    # Find the source results by alias
    left = next((s for s in all_sources if s.get("alias") == left_alias), None)
    right = next((s for s in all_sources if s.get("alias") == right_alias), None)

    if not left or not right:
        return {"error": f"Could not find sources: {left_alias}, {right_alias}"}
    if "error" in left or "error" in right:
        return {"error": "Cannot merge — one or more source queries failed"}

    left_cols = left.get("columns", [])
    right_cols = right.get("columns", [])
    left_rows = left.get("rows", [])
    right_rows = right.get("rows", [])

    if left_key not in left_cols or right_key not in right_cols:
        return {"error": f"Join keys not found: {left_key} in {left_cols}, {right_key} in {right_cols}"}

    left_key_idx = left_cols.index(left_key)
    right_key_idx = right_cols.index(right_key)

    # Build index on right side for fast lookup
    right_index: dict[str, list[list]] = {}
    for row in right_rows:
        key = str(row[right_key_idx])
        if key not in right_index:
            right_index[key] = []
        right_index[key].append(row)

    # Join: all left cols + right cols (excluding join key to avoid duplication)
    right_non_key_indices = [i for i, c in enumerate(right_cols) if c != right_key]
    merged_cols = left_cols + [right_cols[i] for i in right_non_key_indices]
    merged_rows = []
    join_start = time.monotonic()

    for left_row in left_rows:
        # Timeout check every 10K rows
        if len(merged_rows) % 10_000 == 0 and time.monotonic() - join_start > MERGE_TIMEOUT:
            raise TimeoutError(f"Join exceeded {MERGE_TIMEOUT}s timeout")
        key = str(left_row[left_key_idx])
        matching_rights = right_index.get(key, [])
        for right_row in matching_rights:
            merged_row = list(left_row) + [right_row[i] for i in right_non_key_indices]
            merged_rows.append(merged_row)

    logger.info(f"Merge {left_alias} x {right_alias}: {len(left_rows)} x {len(right_rows)} -> {len(merged_rows)} joined rows")

    # Apply group_by + aggregation if specified
    if group_by and aggregations:
        merged_cols, merged_rows = _aggregate(merged_cols, merged_rows, group_by, aggregations)

    return {
        "alias": "merged_result",
        "columns": merged_cols,
        "rows": merged_rows[:MAX_ROWS],
        "row_count": min(len(merged_rows), MAX_ROWS),
        "truncated": len(merged_rows) > MAX_ROWS,
    }


def _chained_merge(sources: list[dict], steps: list[dict], instruction: dict) -> dict | None:
    """Execute a chain of merge steps, where each step can reference '_merged' (previous result)."""
    current_merged = None

    for i, step in enumerate(steps):
        # Make _merged available as a source
        merge_sources = list(sources)
        if current_merged:
            merge_sources.append(current_merged)

        # Build single-step instruction
        step_instruction = dict(step)

        # If this is the last step, apply final group_by and aggregations
        if i == len(steps) - 1:
            if instruction.get("group_by"):
                step_instruction["group_by"] = instruction["group_by"]
            if instruction.get("aggregations"):
                step_instruction["aggregations"] = instruction["aggregations"]

        result = _single_merge(sources, step_instruction, [current_merged] if current_merged else None)
        if not result or "error" in result:
            return result

        # Tag result as _merged for next step
        current_merged = {**result, "alias": "_merged"}

    return current_merged


def _aggregate(
    columns: list[str],
    rows: list[list],
    group_by: list[str],
    aggregations: dict[str, str],
) -> tuple[list[str], list[list]]:
    """Group rows and apply aggregation functions."""
    group_indices = [columns.index(c) for c in group_by if c in columns]
    agg_specs = []
    for col, func in aggregations.items():
        if col in columns:
            agg_specs.append((columns.index(col), func.lower(), col))

    # Group rows
    groups: dict[tuple, list[list]] = {}
    for row in rows:
        key = tuple(row[i] for i in group_indices)
        if key not in groups:
            groups[key] = []
        groups[key].append(row)

    # Output columns: group_by cols + aggregated cols
    out_cols = list(group_by) + [f"{func}_{col}" for _, func, col in agg_specs]
    out_rows = []

    for key, group_rows in groups.items():
        out_row: list = list(key)
        for col_idx, func, _ in agg_specs:
            values = []
            for r in group_rows:
                v = r[col_idx]
                if v is not None:
                    try:
                        values.append(float(v))
                    except (ValueError, TypeError):
                        pass
            if not values:
                out_row.append(None)
            elif func == "avg":
                out_row.append(round(sum(values) / len(values), 2))
            elif func == "sum":
                out_row.append(round(sum(values), 2))
            elif func == "count":
                out_row.append(len(values))
            elif func == "min":
                out_row.append(min(values))
            elif func == "max":
                out_row.append(max(values))
            else:
                out_row.append(None)
        out_rows.append(out_row)

    # Sort by first aggregation column descending
    if agg_specs and out_rows:
        agg_col_idx = len(group_by)  # First aggregated column
        out_rows.sort(key=lambda r: r[agg_col_idx] if r[agg_col_idx] is not None else 0, reverse=True)

    return out_cols, out_rows


def _serialize_value(value) -> str | int | float | bool | None:
    """Convert a database value to JSON-serializable type."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return str(value)
