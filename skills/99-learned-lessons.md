---
name: learned-lessons
description: Rules distilled automatically from self-heal incidents. Appended by the agent, not hand-written.
---
# Learned lessons (auto-appended from self-heal)
Rules below were learned from real runtime failures. Follow them when planning
transformations and writing data-flow expressions.

- Every argument of coalesce (and any default/fill value) must match the column's type, or the flow fails with DF-DT-001 "Types for Function coalesce not compatible". Quote defaults for string columns (coalesce(name, '0')) and use bare numerics only for numeric columns (coalesce(qty, 0)).
- Never leave an implementable transformation as a suggestion. If it can be expressed with the closed op vocabulary (e.g. {op: coalesce, column: category_id, args: ['0']}), put it in the plan's transforms/cleaning; suggestions are only for things the vocabulary cannot express.
- When using string manipulation functions like 'replace', ensure all arguments are of StringType. If an argument is a different type, explicitly cast it to StringType using `toString()` to avoid DF-FN-002 errors.
- When defining join conditions, ensure that the data types of the columns used in the condition are identical. If they differ, explicitly cast one column to match the other's type (e.g., `toInteger()`, `toString()`) to prevent inefficient joins and runtime failures.
- Pick each column's type from the DATA and the operations that consume it (arithmetic/aggregations need numerics, date parts need timestamps) — never from whatever an older Delta table in the target folder happens to contain. Delta sinks overwrite the target table (table action Overwrite), so this run's schema always wins; casting a column to string just to appease a stale table is wrong and breaks downstream sums.
- "Manual trigger" / "run on demand" / "triggered manually" is NOT a schedule and is NOT unsupported — it is the DEFAULT (a pipeline with no schedule already runs on demand from the ADF UI/API). Never call set_schedule for it and never note it as unsupported/suggestion; leave schedule unset and move on.
- Do not use leading double underscores in column or alias names within Data Flow expressions, as they cause DSL parsing and token recognition errors (DF-DSL-001). Use standard alphanumeric names starting with a letter or a single underscore instead.
- When writing comparison or filter expressions, ensure both operands have compatible data types to avoid ADF error code DF-FN-0015. For boolean columns, compare them against boolean literals (true/false) instead of string literals ('true'/'false').
- To prevent DF-EXPR-010 errors, qualify ambiguous column names with their source stream prefix (e.g., StreamName@ColumnName) in joins and aggregations. Ensure all referenced columns exist in the incoming schema, or inline their computed expressions if they have not been projected yet.
- When naming Azure Data Factory resources, such as Integration Runtimes, ensure names consist only of letters, numbers, and hyphens. Avoid special characters like underscores to prevent 'InvalidName' errors during resource provisioning.
