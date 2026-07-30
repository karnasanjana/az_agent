"""Schema advisor service using Gemini via Google Gen AI.

Sends the current database schema and user message to Gemini,
receives structural optimization suggestions OR data query plans.
"""
import json
import re

from google import genai
from google.genai import types

from app.schemas.chat import ChatMessage, ClarificationQuestion, QueryStep, Suggestion
from app.schemas.schema import DatabaseSchema
from app.security.logging import get_logger
from app.config import get_settings

logger = get_logger(__name__)

# Google Gen AI configuration is loaded from backend settings; no user secret
# is sent to the frontend.

SYSTEM_PROMPT = """You are an expert database schema advisor AND data analyst. You analyze database schemas, suggest structural optimizations, and help users query their data.

DATABASE SAFETY: Accepted schema suggestions update only the application's virtual ER diagram. They do not execute DDL or modify the connected source database. Never claim that PostgreSQL, SQL Server, BigQuery, Dataverse, or any other source was changed. Say "added to the diagram" unless a separate verified source-write result is explicitly provided.

You will receive the current schema and connection info. Your job is to:
1. Analyze the schema structure (tables, columns, relationships)
2. Suggest concrete structural changes when asked
3. When the user asks a DATA question (counts, aggregations, lookups, etc.), generate SQL queries to answer it
4. Be honest when the schema looks good and no changes are needed

IMPORTANT: Determine whether the user is asking a SCHEMA question or a DATA question:
- SCHEMA questions: "optimize this", "add relationship", "merge tables", "redundant tables?"
- DATA questions: "how many records", "show me orders", "what's the total revenue", "list all customers"

MULTI-DATABASE AWARENESS:
The schema may contain tables from MULTIPLE databases/datasets. Each table has a schema_name that identifies which database it belongs to (e.g., "UIP_DB_AcademicAdvisor_2", "UIP_StudentLMS_DB"). The schema is organized by database in the DATABASES section.

When analyzing relationships or suggesting optimizations:
1. FIRST analyze each database INDIVIDUALLY — suggest missing relationships, optimizations, and structural improvements WITHIN each database separately.
2. THEN analyze CROSS-DATABASE relationships — identify logical links between tables in different databases based on matching column names/patterns (e.g., student_id appearing in both databases).
3. Structure your explanation with clear headers per database, then a cross-database section.
4. For suggestions, group them: intra-database suggestions first (one suggestion group per database), then cross-database suggestions.

IMPORTANT: Always analyze the CURRENT schema as provided. If tables or relationships already exist in the schema (e.g., a "courses" table or a relationship you previously suggested), do NOT suggest adding them again. Only suggest what is genuinely missing from the current state.

CONVERSATIONAL CLARIFICATION:
When the user's request is ambiguous or broad, ASK CLARIFYING QUESTIONS before generating suggestions. This is critical for giving useful, targeted advice.

Ask clarifying questions when:
- Multiple databases are loaded and the user doesn't specify which one (e.g., "suggest missing relationships" — for which database? within databases, across databases, or both?)
- The request is vague (e.g., "optimize this" — optimize for read performance? normalize? denormalize?)
- Cross-database relationships involve column name mismatches where you need domain knowledge to confirm mappings (e.g., "Does `StudentId` in UIP_StudentLMS_DB refer to the same entity as `student_id` in UIP_DB_AcademicAdvisor_2?")
- The user asks to add/modify something but multiple valid approaches exist

Do NOT ask clarifying questions when:
- The request is clear and specific (e.g., "add a foreign key from enrollments.course_id to courses.course_id")
- Only one database is loaded — just analyze it directly
- The user has already answered a clarification and is following up

To ask clarifying questions, respond with type "clarification" and structured questions with clickable options:
{
  "type": "clarification",
  "explanation": "Brief context about why you're asking these questions.",
  "questions": [
    {
      "id": "q1",
      "text": "Which databases should I analyze for missing relationships?",
      "options": [
        {"id": "q1-a", "label": "Within DatabaseA only"},
        {"id": "q1-b", "label": "Within DatabaseB only"},
        {"id": "q1-c", "label": "Cross-database links"},
        {"id": "q1-d", "label": "All of the above"}
      ],
      "allow_custom_input": false
    },
    {
      "id": "q2",
      "text": "Do StudentId and student_id refer to the same students?",
      "options": [
        {"id": "q2-a", "label": "Yes, same students"},
        {"id": "q2-b", "label": "No, different"},
        {"id": "q2-c", "label": "Not sure"}
      ],
      "allow_custom_input": true
    }
  ]
}

RULES FOR CLARIFICATION QUESTIONS:
- Generate 2-5 options per question covering the most likely user intents
- Use short, clear labels (under 40 characters each)
- Set allow_custom_input to true when the answer might need domain-specific detail (e.g., column mapping confirmations)
- Set allow_custom_input to false for simple scope selections
- You can include 1-3 questions per clarification response
- Use real database/table names from the schema in your options

Once the user answers (by clicking an option or typing), THEN provide targeted suggestions based on their response.

For SCHEMA questions (when clear enough to proceed), respond with:
{
  "type": "schema",
  "explanation": "Your analysis with markdown formatting. Use headers like ### Database: {name} for per-database analysis, and ### Cross-Database Links for cross-database suggestions.",
  "suggestions": [
    {
      "id": "s1",
      "title": "Short title (include database name for clarity)",
      "changes": [
        {
          "action": "remove_table|add_table|merge_table|add_column|remove_column|move_column|add_relationship|remove_relationship",
          // Fields per action:
          // remove_table: table, schema_name
          // add_table: table, schema_name, columns (list of {name, data_type, is_nullable})
          // merge_table: source_table, target_table, schema_name
          // add_column: table, schema_name, column, data_type, is_nullable
          // remove_column: table, schema_name, column
          // move_column: column, from_table, to_table, schema_name
          // add_relationship: source_table, target_table, source_columns, target_columns, source_schema, target_schema, constraint_name
          // remove_relationship: constraint_name
        }
      ]
    }
  ]
}

For DATA questions, respond with:
{
  "type": "data",
  "explanation": "Brief explanation of what you're querying and why.",
  "query_plan": [
    {
      "source": "bigquery" or "sqlserver" or "postgres" or "dataverse",
      "query": "SELECT ... FROM ..." or "entity_set_name?$select=col1,col2&$filter=expr&$top=N&$orderby=expr",
      "alias": "descriptive_name"
    }
  ]
}

IMPORTANT RULES FOR DATA QUERIES:
- ONLY use type "data" with query_plan when the user explicitly asks for actual data from the database (row counts, records, aggregations, etc.) AND the answer cannot be determined from the schema metadata alone.
- If the answer is available from the schema metadata (e.g., table count, column names, relationship count), respond with type "schema" and answer in the explanation. Do NOT generate a query.
- Never mention internal details like "no query needed", "from schema metadata", or "this is available from the schema" in your explanation. Just answer the question directly.
- Generate ONLY SELECT queries. Never INSERT, UPDATE, DELETE, DROP, ALTER, or any DDL/DML.
- Use the exact table and column names from the schema (case-sensitive).
- For BigQuery tables, use fully qualified names: `project_id.dataset.table` or `dataset.table`.
- For SQL Server tables, use schema-qualified names: dbo.table (the schema is always "dbo" for SQL Server).
- For PostgreSQL tables, use schema-qualified lowercase names: public.table (or the actual schema_name). Use LIMIT (not TOP), and double-quote identifiers only if they are mixed-case.
- For Dataverse tables, use OData query format: "entity_set_name?$select=col1,col2&$filter=expr&$top=N&$orderby=expr"
  - entity_set_name is the PLURAL form of the entity logical name (e.g., "accounts" for entity "account", "contacts" for "contact"). Standard Dataverse convention: add "s" for most, "es" for entities ending in s/x/z, and special plurals like "companies" for "company".
  - Use $select to pick specific columns (attribute logical names from the schema)
  - Use $filter for OData filter expressions (e.g., "revenue gt 1000000", "contains(name,'Contoso')", "statecode eq 0")
  - Use $top to limit results (max 500)
  - Use $orderby for sorting (e.g., "revenue desc", "createdon asc")
  - If you just need all records from an entity, use: "entity_set_name?$top=500"
- Add LIMIT/TOP/$top to prevent returning too many rows (max 500).

CRITICAL — ROUTING QUERIES TO THE CORRECT DATABASE:
- Each database/dataset section has a [QUERY VIA: BIGQUERY], [QUERY VIA: SQLSERVER], [QUERY VIA: POSTGRES], or [QUERY VIA: DATAVERSE] tag. You MUST use this to set the correct "source" field in your query_plan. If NO tag is present and only one data source is connected, use that source.
- Tables tagged BIGQUERY can ONLY be queried with source: "bigquery". Tables tagged SQLSERVER can ONLY be queried with source: "sqlserver". Tables tagged POSTGRES can ONLY be queried with source: "postgres". Tables tagged DATAVERSE can ONLY be queried with source: "dataverse".
- You CANNOT join tables across different database types in a single SQL query. They live on completely different servers.
- NEVER query a table using the wrong source — it will fail.
- If you cannot determine which database to query, ask the user.

CROSS-DATABASE MERGE (APPLICATION-LEVEL JOIN):
When a question requires data from multiple database types (BigQuery, SQL Server, and/or Dataverse), you can instruct the system to merge results in Python by adding a "merge" field to your response.

IMPORTANT: Do NOT add LIMIT/TOP to queries used in a merge — the system needs ALL rows for accurate joins. The system automatically increases row limits for merge queries.

SINGLE-STEP MERGE (2 queries):
{
  "type": "data",
  "explanation": "...",
  "query_plan": [
    {"source": "sqlserver", "query": "SELECT customer_id, order_id FROM dbo.orders", "alias": "orders"},
    {"source": "bigquery", "query": "SELECT customer_id, customer_city FROM `project.dataset.customers`", "alias": "customers"}
  ],
  "merge": {
    "left_alias": "orders",
    "right_alias": "customers",
    "left_key": "customer_id",
    "right_key": "customer_id",
    "group_by": ["customer_city"],
    "aggregations": {"order_id": "count"}
  }
}

MULTI-STEP MERGE (3+ queries chained):
Use "steps" array. Each step joins two sources. After step 1, the result is available as "_merged" for step 2.
{
  "type": "data",
  "explanation": "...",
  "query_plan": [
    {"source": "bigquery", "query": "SELECT order_id, SUM(payment_value) AS order_total FROM `project.dataset.order_payments` GROUP BY order_id", "alias": "payments"},
    {"source": "sqlserver", "query": "SELECT order_id, customer_id FROM dbo.orders", "alias": "orders"},
    {"source": "bigquery", "query": "SELECT customer_id, customer_city FROM `project.dataset.customers`", "alias": "customers"}
  ],
  "merge": {
    "steps": [
      {"left": "payments", "right": "orders", "left_key": "order_id", "right_key": "order_id"},
      {"left": "_merged", "right": "customers", "left_key": "customer_id", "right_key": "customer_id"}
    ],
    "group_by": ["customer_city"],
    "aggregations": {"order_total": "avg"}
  }
}

Merge rules:
- Query aliases must match merge references.
- "left_key"/"right_key" are column names in the query results.
- "group_by" + "aggregations" are applied AFTER all join steps complete.
- Aggregation functions: avg, sum, count, min, max.
- "_merged" refers to the result of the previous step in a multi-step merge.
- Keep individual queries simple — return join keys + data columns. Let the merge handle joins and aggregation.
- DO NOT include LIMIT/TOP in queries used for merges.

RESPONSE SIZE MANAGEMENT:
- Keep the explanation concise — use bullet points, not paragraphs. Aim for under 2000 characters.
- Limit suggestions to a maximum of 5 per response. If more optimizations exist, mention them in the explanation and offer to provide more in a follow-up.
- Each suggestion should have a short title and minimal changes. Prefer grouping related changes (e.g., add table + its FKs) into one suggestion.

ALWAYS return valid JSON. No text before or after the JSON block.
NEVER output multiple JSON objects or "correct yourself" mid-response. Think through your answer fully, then output ONE single JSON response. If you realize you need to change your approach, just output the corrected version directly — do not show the wrong version first."""


def _schema_to_context(schema: DatabaseSchema, data_sources_info: str = "") -> str:
    """Convert schema to a concise text representation for the prompt.

    Groups tables by database/dataset (schema_name) so Claude can clearly
    distinguish which tables belong to which database.
    """
    lines = [f"Database: {schema.database_name}"]
    lines.append(f"Total Tables: {schema.table_count}, Total Relationships: {len(schema.foreign_keys)}")

    if data_sources_info:
        lines.append("")
        lines.append("DATA SOURCES:")
        lines.append(data_sources_info)

    # Group tables by schema_name (database/dataset)
    tables_by_db: dict[str, list] = {}
    for table in schema.tables:
        db_name = table.schema_name
        if db_name not in tables_by_db:
            tables_by_db[db_name] = []
        tables_by_db[db_name].append(table)

    # Sort databases by addition order if available
    order = schema.dataset_order or {}
    sorted_db_names = sorted(
        tables_by_db.keys(),
        key=lambda name: order.get(name, 999),
    )

    # Dataset-to-source mapping (bigquery or sqlserver)
    sources = schema.dataset_sources or {}

    lines.append("")
    lines.append(f"DATABASES ({len(tables_by_db)}):")
    for db_name in sorted_db_names:
        source_label = ""
        if db_name in sources:
            source_label = f" [SOURCE: {sources[db_name].upper()}]"
        added_label = ""
        if order.get(db_name):
            pos = order[db_name]
            if pos == max(order.values()):
                added_label = " [MOST RECENTLY ADDED]"
            else:
                added_label = f" [added #{pos}]"
        lines.append(f"  - {db_name} ({len(tables_by_db[db_name])} tables){source_label}{added_label}")

    # Output tables grouped by database (in addition order)
    for db_name in sorted_db_names:
        tables = tables_by_db[db_name]
        added_label = ""
        if order.get(db_name):
            pos = order[db_name]
            if pos == max(order.values()) and len(order) > 1:
                added_label = " — MOST RECENTLY ADDED"
            else:
                added_label = f" — added #{pos}"
        source_tag = ""
        if db_name in sources:
            source_tag = f" [QUERY VIA: {sources[db_name].upper()}]"
        lines.append("")
        lines.append(f"=== DATABASE: {db_name} ({len(tables)} tables){source_tag}{added_label} ===")
        lines.append("")

        for table in tables:
            prefix = "[VIEW]" if table.is_view else "[TABLE]"
            lines.append(f"{prefix} {table.schema_name}.{table.table_name}")
            for col in table.columns:
                pk = " [PK]" if col.is_primary_key else ""
                nullable = " NULL" if col.is_nullable else " NOT NULL"
                lines.append(f"  - {col.name}: {col.data_type}{pk}{nullable}")
            lines.append("")

    # Group relationships by intra-database vs cross-database
    if schema.foreign_keys:
        intra_fks: dict[str, list] = {}
        cross_fks = []

        for fk in schema.foreign_keys:
            src = f"{fk.source_schema}.{fk.source_table}({', '.join(fk.source_columns)})"
            tgt = f"{fk.target_schema}.{fk.target_table}({', '.join(fk.target_columns)})"
            fk_line = f"  {fk.constraint_name}: {src} -> {tgt}"

            if fk.source_schema == fk.target_schema:
                db = fk.source_schema
                if db not in intra_fks:
                    intra_fks[db] = []
                intra_fks[db].append(fk_line)
            else:
                cross_fks.append(fk_line)

        if intra_fks:
            lines.append("RELATIONSHIPS (within database):")
            for db_name, fk_lines in intra_fks.items():
                lines.append(f"  [{db_name}]")
                lines.extend(f"  {line}" for line in fk_lines)

        if cross_fks:
            lines.append("")
            lines.append("RELATIONSHIPS (cross-database):")
            lines.extend(cross_fks)

    return "\n".join(lines)


def _build_messages(
    user_message: str,
    schema: DatabaseSchema,
    history: list[ChatMessage],
    data_sources_info: str = "",
) -> list[dict]:
    """Build the message list for Claude API."""
    schema_context = _schema_to_context(schema, data_sources_info)

    messages = []

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    full_message = f"""Current schema:
```
{schema_context}
```

User question: {user_message}"""

    messages.append({"role": "user", "content": full_message})

    return messages


def _parse_response(text: str) -> dict:
    """Parse Claude's JSON response into structured data.

    Returns a dict with 'type', 'explanation', and either 'suggestions' or 'query_plan'.
    """
    # Try to extract JSON from markdown code blocks
    # Split on code block boundaries and try each block (last first, since AI may self-correct)
    code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    json_str = None
    for block in reversed(code_blocks):
        block = block.strip()
        if block.startswith('{'):
            try:
                json.loads(block)
                json_str = block
                break
            except json.JSONDecodeError:
                continue

    if json_str is None:
        # Try to find a top-level JSON object in the raw text
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace > first_brace:
            json_str = text[first_brace:last_brace + 1]
        else:
            json_str = text.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Claude response as JSON")
        return {"type": "schema", "explanation": text, "suggestions": []}

    response_type = data.get("type", "schema")
    explanation = data.get("explanation", "")

    if response_type == "data":
        query_plan = []
        for raw in data.get("query_plan", []):
            try:
                query_plan.append(QueryStep(**raw))
            except Exception as e:
                logger.warning(f"Failed to parse query step: {e}")
        result = {
            "type": "data",
            "explanation": explanation,
            "query_plan": query_plan,
        }
        # Include merge instruction if provided
        if data.get("merge"):
            result["merge"] = data["merge"]
        return result
    elif response_type == "clarification":
        questions = []
        for raw in data.get("questions", []):
            try:
                questions.append(ClarificationQuestion(**raw))
            except Exception as e:
                logger.warning(f"Failed to parse clarification question: {e}")
        return {
            "type": "clarification",
            "explanation": explanation,
            "questions": questions,
        }
    else:
        suggestions = []
        for raw in data.get("suggestions", []):
            try:
                suggestions.append(Suggestion(**raw))
            except Exception as e:
                logger.warning(f"Failed to parse suggestion: {e}")
        return {
            "type": "schema",
            "explanation": explanation,
            "suggestions": suggestions,
        }


def get_client() -> genai.Client:
    """Create a Gemini Developer API client from backend-only settings."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError(
            "Schema Advisor is not configured. Set GEMINI_API_KEY in backend/.env."
        )
    return genai.Client(api_key=settings.gemini_api_key)


def chat_with_advisor(
    user_message: str,
    schema: DatabaseSchema,
    history: list[ChatMessage],
    data_sources_info: str = "",
) -> dict:
    """Send a message to Claude and get response.

    Returns:
        Dict with 'type', 'explanation', and 'suggestions' or 'query_plan'
    """
    client = get_client()
    messages = _build_messages(user_message, schema, history, data_sources_info)

    # Convert Anthropic-style messages to Gemini format
    gemini_contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        gemini_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

    response = client.models.generate_content(
        model=get_settings().gemini_model,
        contents=gemini_contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=8192,
        ),
    )

    response_text = response.text
    return _parse_response(response_text)


FIX_QUERY_PROMPT = """You are a SQL query fixer. A query failed with an error. Fix the query and return ONLY the corrected SQL.

Database type: {source}
Original query:
{query}

Error:
{error}

Rules:
- Return ONLY the corrected SQL query, no explanation, no markdown, no code blocks.
- Keep the same intent and columns as the original query.
- Fix only the syntax/structural issue that caused the error.
- For BigQuery: use backtick-quoted fully qualified table names like `project.dataset.table`.
- For SQL Server: use dbo.table format, use TOP instead of LIMIT.
- For PostgreSQL: use schema-qualified lowercase names like public.table, use LIMIT.
- Do NOT add LIMIT/TOP if the original query didn't have one (merge queries need all rows)."""


def fix_failed_query(
    source: str,
    query: str,
    error: str,
) -> str | None:
    """Ask Claude to fix a failed SQL query.

    Returns the corrected query string, or None if fix failed.
    """
    try:
        client = get_client()
        prompt = FIX_QUERY_PROMPT.format(source=source, query=query, error=error)

        response = client.models.generate_content(
            model=get_settings().gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=2048),
        )

        fixed = response.text.strip()
        # Strip markdown code blocks if present
        if fixed.startswith("```"):
            lines = fixed.split("\n")
            fixed = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        fixed = fixed.strip().rstrip(";")

        if not fixed or fixed == query:
            return None

        logger.info(f"Query fix generated: {fixed[:100]}...")
        return fixed
    except Exception as e:
        logger.error(f"Failed to fix query: {e}")
        return None


INFER_RELATIONSHIPS_PROMPT = """You are an expert database architect. Analyze the schema below and identify likely foreign-key relationships that DO NOT already exist.

For each potential relationship, score your confidence as a number between 0 and 1:
- > 0.8 = high confidence (e.g., `customer_id` column referencing `customers.id`, exact name + compatible type)
- 0.5 - 0.8 = medium confidence (plausible link but naming or type ambiguity)
- < 0.5 = low confidence (heuristic guess)

Consider:
- Column name matching (customer_id -> customers.id, user_fk -> users.user_id)
- Data type compatibility (don't link a varchar to an int)
- Cross-database links (tables in different schema_names that reference each other)
- Singular/plural conventions (order_id -> orders.id)
- Do NOT propose relationships that already appear in the EXISTING RELATIONSHIPS list.
- Do NOT propose self-referential duplicates already present.

Return ONLY valid JSON in this exact shape (no prose, no markdown fences):
{{
  "relationships": [
    {{
      "source_table": "orders",
      "source_schema": "dbo",
      "source_column": "customer_id",
      "target_table": "customers",
      "target_schema": "dbo",
      "target_column": "id",
      "confidence": 0.92,
      "reason": "Exact name match + int type, customers.id is the primary key"
    }}
  ]
}}

If you find no missing relationships, return {{"relationships": []}}.

SCHEMA:
{schema_context}

EXISTING RELATIONSHIPS:
{existing_fks}
"""


def infer_missing_relationships(schema: DatabaseSchema) -> list[dict]:
    """Use Claude Sonnet to infer FK relationships missing from the schema.

    Returns a list of dicts with keys:
        source_table, source_schema, source_column,
        target_table, target_schema, target_column,
        confidence (float 0-1), reason (str)
    """
    schema_context = _schema_to_context(schema)

    # Build a clear list of existing FKs so the model excludes them
    existing_lines: list[str] = []
    existing_keys: set[tuple] = set()
    for fk in schema.foreign_keys:
        for sc, tc in zip(fk.source_columns, fk.target_columns):
            existing_keys.add((
                fk.source_schema, fk.source_table, sc,
                fk.target_schema, fk.target_table, tc,
            ))
            existing_lines.append(
                f"- {fk.source_schema}.{fk.source_table}.{sc} -> "
                f"{fk.target_schema}.{fk.target_table}.{tc}"
            )
    existing_fks = "\n".join(existing_lines) if existing_lines else "(none)"

    prompt = INFER_RELATIONSHIPS_PROMPT.format(
        schema_context=schema_context,
        existing_fks=existing_fks,
    )

    try:
        client = get_client()
        response = client.models.generate_content(
            model=get_settings().gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=8192),
        )
        text = response.text

        # Extract JSON
        code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        json_str = None
        for block in reversed(code_blocks):
            block = block.strip()
            if block.startswith('{'):
                try:
                    json.loads(block)
                    json_str = block
                    break
                except json.JSONDecodeError:
                    continue
        if json_str is None:
            first = text.find('{')
            last = text.rfind('}')
            json_str = text[first:last + 1] if first != -1 and last > first else text.strip()

        data = json.loads(json_str)
        raw_rels = data.get("relationships", [])

        results: list[dict] = []
        for r in raw_rels:
            try:
                key = (
                    r.get("source_schema"), r.get("source_table"), r.get("source_column"),
                    r.get("target_schema"), r.get("target_table"), r.get("target_column"),
                )
                if None in key:
                    continue
                if key in existing_keys:
                    continue
                conf = float(r.get("confidence", 0))
                if conf < 0:
                    conf = 0.0
                if conf > 1:
                    conf = 1.0
                results.append({
                    "source_table": r["source_table"],
                    "source_schema": r["source_schema"],
                    "source_column": r["source_column"],
                    "target_table": r["target_table"],
                    "target_schema": r["target_schema"],
                    "target_column": r["target_column"],
                    "confidence": conf,
                    "reason": str(r.get("reason", "")),
                })
            except Exception as e:
                logger.warning(f"Skipping malformed inferred relationship: {e}")
                continue

        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results
    except Exception as e:
        logger.error(f"infer_missing_relationships failed: {e}")
        return []


SUMMARIZE_PROMPT = """You are a data analyst. Summarize the query results below in 2-3 concise sentences. Focus on the key findings — highlight top/bottom values, notable patterns, or interesting outliers.

User's question: {question}

Result columns: {columns}
Result data (first {row_count} rows):
{data}

Rules:
- Be concise and specific — mention actual numbers and names from the data.
- Use natural language, not technical jargon.
- Do NOT mention databases, SQL, queries, or technical details.
- Do NOT use markdown formatting.
- If the data is grouped/ranked, call out the top 3-5 and bottom 1-2 entries."""


AUTO_DOC_PROMPT = """You are a database documentation expert. Given a database schema, generate concise plain-English descriptions for every table and every column.

Schema:
{schema_text}

Foreign key relationships (use these to enrich column descriptions when relevant):
{fk_text}

Rules:
- Generate ONE 1-line description per table explaining what it stores (max ~15 words).
- Generate ONE brief description per column explaining what it represents (~3-7 words). Be very concise.
- For foreign key columns, mention what they link to (e.g., "Foreign key linking to customers table").
- Use natural, non-technical language. Avoid restating the column name verbatim.
- Cover EVERY table and EVERY column in the schema. Do not skip any.
- Use the EXACT table_name (without schema prefix) and column name strings from the schema as keys. For example, use "users" not "dbo.users".

Return ONLY valid JSON in this exact shape, no markdown, no code blocks, no commentary:
{{
  "tables": {{
    "<table_name>": {{
      "description": "<table description>",
      "columns": {{
        "<column_name>": "<column description>",
        ...
      }}
    }},
    ...
  }}
}}"""


def _schema_to_doc_context(schema: DatabaseSchema) -> tuple[str, str]:
    """Build a compact text representation of the schema for documentation prompts.

    For large schemas (many columns), uses a condensed format to stay within token limits.
    """
    total_columns = sum(len(t.columns) for t in schema.tables)
    compact = total_columns > 200  # Switch to compact format for large schemas

    lines = []
    for table in schema.tables:
        prefix = "VIEW" if table.is_view else "TABLE"
        lines.append(f"{prefix} {table.table_name}")
        if compact:
            # Compact: just column names on one line
            col_names = [f"{c.name}{'[PK]' if c.is_primary_key else ''}" for c in table.columns]
            lines.append(f"  columns: {', '.join(col_names)}")
        else:
            for col in table.columns:
                pk = " [PK]" if col.is_primary_key else ""
                lines.append(f"  - {col.name}: {col.data_type}{pk}")
        lines.append("")

    fk_lines = []
    for fk in schema.foreign_keys:
        fk_lines.append(f"  {fk.source_table}.{', '.join(fk.source_columns)} -> {fk.target_table}.{', '.join(fk.target_columns)}")

    return "\n".join(lines), "\n".join(fk_lines) if fk_lines else "  (none)"


def _repair_truncated_json(text: str) -> str:
    """Attempt to repair truncated JSON by removing the last incomplete entry and closing braces.

    Works for the auto-doc shape: {"tables": {"t1": {...}, "t2": {...}, ...}}
    If the output was cut off mid-entry, we strip back to the last complete entry
    and close all open braces/brackets.
    """
    # Find the last complete key-value pair boundary ("},")
    last_complete = text.rfind('},')
    if last_complete == -1:
        last_complete = text.rfind('}')
    if last_complete == -1:
        raise json.JSONDecodeError("Cannot repair: no complete entry found", text, 0)

    truncated = text[:last_complete + 1]

    # Count open braces/brackets and close them
    open_braces = truncated.count('{') - truncated.count('}')
    open_brackets = truncated.count('[') - truncated.count(']')

    truncated += '}' * max(0, open_braces)
    truncated += ']' * max(0, open_brackets)

    return truncated


def generate_auto_documentation(schema: DatabaseSchema) -> dict:
    """Generate AI descriptions for every table and column in the schema.

    Uses Claude Haiku for fast, single-call documentation generation.

    Returns:
        Dict shaped as {"tables": {"<table_name>": {"description": "...", "columns": {"<col>": "...", ...}}, ...}}
        Returns {"tables": {}} on failure.
    """
    try:
        client = get_client()
        schema_text, fk_text = _schema_to_doc_context(schema)
        prompt = AUTO_DOC_PROMPT.format(schema_text=schema_text, fk_text=fk_text)
        logger.info(f"Auto-doc: calling Gemini with prompt length={len(prompt)}")

        response = client.models.generate_content(
            model=get_settings().gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=8192),
        )

        logger.info(f"Auto-doc: Gemini response received, length={len(response.text) if response.text else 0}")
        text = response.text.strip()

        # Strip markdown code fences if present
        code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        json_str = None
        for block in reversed(code_blocks):
            block = block.strip()
            if block.startswith('{'):
                try:
                    json.loads(block)
                    json_str = block
                    break
                except json.JSONDecodeError:
                    continue
        if json_str is None:
            first = text.find('{')
            last = text.rfind('}')
            if first != -1 and last > first:
                json_str = text[first:last + 1]
            else:
                json_str = text

        # Try parsing, and if truncated, attempt to repair by closing open braces
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Auto-doc: JSON parse failed, attempting repair of truncated output")
            repaired = _repair_truncated_json(json_str)
            data = json.loads(repaired)
        if "tables" not in data or not isinstance(data["tables"], dict):
            logger.warning("Auto-doc response missing 'tables' key")
            return {"tables": {}}

        logger.info(f"Auto-documentation generated for {len(data['tables'])} tables")
        return data
    except Exception as e:
        import traceback
        logger.error(f"Failed to generate auto-documentation: {e}\n{traceback.format_exc()}")
        return {"tables": {}}


def summarize_results(
    question: str,
    columns: list[str],
    rows: list[list],
) -> str | None:
    """Generate a natural language summary of query results using Haiku.

    Returns a short summary string, or None if summarization failed.
    """
    if not rows:
        return None

    try:
        client = get_client()

        # Send at most 30 rows to keep the prompt small
        preview_rows = rows[:30]
        data_str = "\n".join(
            " | ".join(str(cell) for cell in row)
            for row in preview_rows
        )

        prompt = SUMMARIZE_PROMPT.format(
            question=question,
            columns=" | ".join(columns),
            row_count=len(preview_rows),
            data=data_str,
        )

        response = client.models.generate_content(
            model=get_settings().gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=512),
        )

        summary = response.text.strip()
        logger.info(f"Result summary generated: {summary[:80]}...")
        return summary
    except Exception as e:
        logger.error(f"Failed to summarize results: {e}")
        return None
