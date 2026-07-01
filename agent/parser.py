"""LLM reasoning point #1: BRD text -> validated PipelineSpec.

Pydantic AI is the only framework used, and only for this: it makes Claude
return a VALIDATED ``PipelineSpec`` instance. There is no manual ``json.loads``,
no fence-stripping, no schema prompt-engineering by hand — the agent's
``output_type`` is the Pydantic model and the SDK enforces it.

If the BRD is ambiguous, the model is instructed to populate ``clarifications``
rather than invent components.

The same agent powers the post-generation CHAT: ``refine_spec`` continues the
conversation (Pydantic AI message history) so the user can ask for small changes
or answer the agent's clarifying questions, and the model edits the existing
spec instead of starting over.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from config import get_claude_model
from models.spec import PipelineSpec

_SYSTEM_PROMPT = """\
You are a senior Azure Data Engineer. Convert a Business Requirements Document
(BRD) into a single, fully-specified ADF medallion pipeline (Bronze -> Silver ->
Gold) as a PipelineSpec.

Hard rules:
- ADF only. No Databricks, Synapse, or Fabric.
- Managed Identity for storage; anonymous auth for the public HTTP source. Never
  emit keys, SAS tokens, or connection strings.
- Emit exactly ONE Azure storage linked service for the whole pipeline (one account =
  one ls_), and make every Bronze/Silver/Gold dataset reference that SAME name. Do not
  create per-layer or per-file storage linked services — multiple/inconsistent names
  cause "invalid reference" deploy failures.
- Naming prefixes are mandatory and lowercase: linked services ls_, datasets ds_,
  data flows df_, pipelines pl_ (e.g. a BRD that says "PL_Retail_Master" becomes
  "pl_retail_master").
- Use the smallest General Purpose Data Flow compute (8 cores).
- The master pipeline must chain Bronze -> Silver -> Gold using dependsOn with the
  Succeeded condition, so a failed Bronze halts downstream work.
- Provide both a manual trigger and a daily schedule trigger.

DATASETS must resolve to real files. When the BRD names specific source files (e.g.
olist_customers_dataset.csv), put the CONCRETE file name in that dataset's location
(location.file_name) and create a SEPARATE source dataset per file — do NOT leave the
file name to a runtime parameter, and do NOT collapse multiple files onto one shared
wildcard dataset. A source dataset with only a container and no file name fails in ADF.
Avoid parameterizing container/folder/file unless the BRD truly requires per-run paths;
concrete locations are preferred and run reliably.

SCOPE DISCIPLINE — build ONLY what the BRD asks for. Do NOT invent datasets, data
flows, gold aggregates, archive/backup steps, logging/audit tables, or "nice to have"
outputs the BRD never mentions. If the BRD names ONE gold output (e.g. monthly_sales),
produce EXACTLY ONE gold dataset and ONE gold data flow — not a suite of extra
aggregates. Inventing unrequested outputs is a defect, not thoroughness.

DATASET REUSE — one dataset per (file, layer), reused across the layer boundary. A
bronze Copy's sink dataset is the SAME dataset the silver data flow reads as its
source; a silver sink dataset is the SAME one the gold data flow reads. Never emit a
separate "_source" and "_sink" dataset for the same file at the same location. For N
named source files expect about: N landing + N bronze + N silver + (only the BRD's
gold outputs). For 5 files and one gold output that is ~16 datasets total — if you are
producing many more, you are inventing scope or duplicating datasets; stop and trim.

ONLY three activity types are supported: Copy, ExecuteDataFlow, ExecutePipeline. Do
NOT emit GetMetadata, IfCondition, Validation, Delete, Lookup, ForEach, or any other
activity type — they cannot be built and will be dropped. Model "validate the file
exists / handle missing files" as a plain Copy (ADF surfaces those errors at run
time); do not add validation activities.

REQUIRED STRUCTURE — every medallion spec MUST include all of these, or it will be
rejected. Never return empty `dataflows` or `pipelines`:
- At least one Copy activity with layer="bronze" (raw landing -> bronze, NO transform).
- At least one DataFlow with layer="silver" and at least one with layer="gold",
  each with a real source -> transforms -> sink.
- A master pipeline (pl_...) whose activities are ExecutePipeline steps chaining
  bronze -> silver -> gold with dependsOn Succeeded.

BUILD FIRST. Your default is to return a COMPLETE, approvable spec — not to ask
questions. If the BRD is large (many source files, many outputs), still deliver the
full Bronze->Silver->Gold structure; simplify if you must (a representative bronze
Copy, consolidated data flows). Apply sensible defaults instead of asking:
standard timestamp formats, silver/{dataset}/ paths, snappy Parquet, etc.

Silently OMIT anything this ADF model cannot represent — custom logging tables,
archive/delete steps, generic "error handling", manual Studio tweaks. Do NOT turn
these into questions. They are out of scope; just leave them out.

`clarifications` is a LAST RESORT, only for info that genuinely BLOCKS you from
building a core layer (e.g. no source location at all, a transform that references an
unknown column). Keep it to AT MOST 2 short, specific questions. If you can make a
reasonable assumption, make it and proceed with empty `clarifications`. Never use
`clarifications` to explain caveats, ADF Studio steps, or things you omitted.

This is a CONVERSATION. After the first pass the user may answer your
clarifications or ask for small changes ("rename the gold sink", "add a filter on
Confirmed > 0", "use Parquet for silver"). When they do, return the FULL updated
spec with that change applied — keep everything else exactly as it was, preserve
names and references, and only re-raise a clarification if the new request itself
is ambiguous.
"""


def _system_prompt() -> str:
    """Base instructions plus any Azure/ADF skills loaded from skills/*.md."""
    from agent.skills import load_skills

    skills = load_skills()
    return f"{_SYSTEM_PROMPT}\n\n{skills}" if skills else _SYSTEM_PROMPT


def build_parser_agent():
    from pydantic_ai import Agent

    return Agent(
        get_claude_model(),
        output_type=PipelineSpec,
        system_prompt=_system_prompt(),
        # Give the model room to self-correct structured-output hiccups; Pydantic
        # AI feeds the validation error back on each retry.
        retries=4,
        # A full medallion spec (multiple datasets + silver/gold data flows +
        # pipelines) is large — without headroom the structured output truncates
        # and comes back with empty dataflows/pipelines.
        model_settings={"max_tokens": 16384, "temperature": 0.0},
    )


async def parse_brd(
    brd_text: str, message_history: "Optional[List[Any]]" = None
) -> "Tuple[PipelineSpec, List[Any]]":
    """Run the parser agent and return ``(spec, message_history)``.

    The returned message history is fed back into :func:`refine_spec` so the
    follow-up chat continues the same conversation (the model remembers the BRD
    and the spec it just produced).

    Async so it can be awaited from inside FastAPI's running event loop — calling
    the sync ``run_sync`` there raises "This event loop is already running".
    """
    agent = build_parser_agent()
    result = await agent.run(brd_text, message_history=message_history)
    return result.output, result.all_messages()


async def refine_spec(
    instruction: str, message_history: "List[Any]"
) -> "Tuple[PipelineSpec, List[Any]]":
    """Continue the conversation: apply a change request or answer to clarifying
    questions, returning the updated ``(spec, message_history)``."""
    agent = build_parser_agent()
    result = await agent.run(instruction, message_history=message_history)
    return result.output, result.all_messages()


def parse_brd_sync(brd_text: str) -> PipelineSpec:
    """Blocking variant for scripts / threads with no running event loop."""
    agent = build_parser_agent()
    return agent.run_sync(brd_text).output
