"""LLM reasoning point: BRD text -> validated LogicalPlan.

The ONLY creative step in the plan path. The model decides WHAT the business
wants — entities, cleanings, joins, outputs — and nothing about ADF. The
deterministic compiler (agent/compiler.py) builds every name, dataset, and
expression. This is the search-space collapse: a ~40-line prompt asking for
business intent replaces the old ~200-line ADF-authoring prompt in
agent/parser.py.

There is NO free-text expression field in a LogicalPlan, so the model cannot
emit invalid ADF DSL — invalid syntax is unrepresentable. Anything it cannot
express goes in `unsupported` (loud), never silently dropped.

Mirrors agent/parser.py's shape (async run + message history) so the follow-up
chat continues the same conversation and edits the existing plan.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from config import default_model_settings, get_model, structured_output
from models.logical import LogicalPlan

_SYSTEM_PROMPT = """\
You are a senior data engineer. Read the user's requirements (a BRD document or
plain sentences) and produce a LogicalPlan: WHAT data exists, HOW it must be
cleaned, and WHAT business outputs are needed. You do NOT design Azure Data
Factory objects — no pipeline names, no datasets, no JSON, no ADF expressions.
A deterministic compiler builds all of that from your plan.

Rules:
- sources: one entry per business entity (file or table) named in the
  requirements. entity = short snake_case business name (orders, customers).
  Use the EXACT file names / URLs / table names the requirements give.
- transforms: one entry per entity that needs cleaning. Express EVERYTHING as
  structured ops from the closed vocabulary — casts (target types), cleaning
  ops (trim/upper/lower/replace/...), filters (not_null/eq/gt/...), dedup_keys.
  There is NO free-text expression field. If logic cannot be expressed with the
  vocabulary, put one plain-English line in `unsupported` instead.
- outputs: one entry per business output the requirements ask for. Joins list
  the key columns on both sides. Aggregations use sum/avg/min/max/count/
  count_distinct/first. "top N" = sort + top_n. Do NOT invent outputs the
  requirements never asked for.
- schedule: only when the requirements state or clearly imply one.
- unsupported: every requirement you recognized but cannot express (validation
  gates, alerting, archive/delete steps, SCD2, incremental merge, ForEach
  patterns). One short line each. NEVER silently drop a requirement.
- assumptions: every decision you made that the requirements left open
  (dedup keys chosen, date formats, join types). Short lines.
- clarifications: AT MOST 2, ONLY when a core fact is missing (e.g. no source
  location at all). Otherwise assume and record in assumptions.
- This is a conversation: on follow-up messages, return the FULL updated plan
  with the requested change applied, everything else unchanged.
"""


def build_extractor_agent():
    from pydantic_ai import Agent

    return Agent(
        get_model(),
        output_type=structured_output(LogicalPlan),
        system_prompt=_SYSTEM_PROMPT,
        retries=4,
        model_settings=default_model_settings(),
    )


async def extract_plan(
    brd_text: str, message_history: "Optional[List[Any]]" = None
) -> "Tuple[LogicalPlan, List[Any]]":
    """Run the extractor and return ``(plan, message_history)``. The history feeds
    :func:`refine_plan` so the follow-up chat continues the same conversation."""
    agent = build_extractor_agent()
    result = await agent.run(brd_text, message_history=message_history)
    return result.output, result.all_messages()


async def refine_plan(
    instruction: str, message_history: "List[Any]"
) -> "Tuple[LogicalPlan, List[Any]]":
    """Continue the conversation: apply a change / answer a clarification / fix a
    validation problem, returning the updated ``(plan, message_history)``."""
    agent = build_extractor_agent()
    result = await agent.run(instruction, message_history=message_history)
    return result.output, result.all_messages()


def extract_plan_sync(brd_text: str) -> LogicalPlan:
    """Blocking variant for scripts / threads with no running event loop."""
    agent = build_extractor_agent()
    return agent.run_sync(brd_text).output
