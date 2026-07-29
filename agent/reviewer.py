"""PLAN_REVIEW: one LLM pass comparing the BRD against the finished plan.

Deterministic preflight proves the plan BUILDS; it cannot prove the plan says
what the BRD says. This reviewer reads both and reports semantic gaps —
requirements missing from the plan or contradicted by it. Findings are
ADVISORY: they render in the review panel next to the approval gate and never
block it (a second LLM opinion can itself be wrong; the deterministic checks
stay the hard floor).

Enabled by default; PLAN_REVIEW=false turns it off. Skipped in MOCK mode and
on cache hits (a cached plan was already reviewed when it was first built).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

_PROMPT = """\
You are a strict, terse reviewer for a system that turns a BRD (business
requirements document) into an Azure Data Factory pipeline plan. You are given
the original requirements, the final logical plan (JSON), and the RENDERED Data
Flow expressions that will actually run.

Deterministic checks already proved the plan BUILDS. Your job is the thing they
cannot check: does each rendered expression COMPUTE WHAT THE BRD ASKED? These
errors are syntactically valid, so they pass every other gate — read the
expressions literally and compare to the requirement.

Hunt especially for these recurring corruptions:
- ARITHMETIC: a division folded into a multiply. A ratio / percentage / rate /
  average / "per" metric whose expression has NO `/` is wrong (e.g. the BRD says
  `deaths * 100 / confirmed` but the expression is `deaths * 100 * confirmed`).
- STRING OPS: a replacement or argument that is a DESCRIPTION or placeholder,
  not a real value — e.g. `regexReplace(x, '...', 'alphanumeric_space')` where
  the 3rd arg should be `''`.
- COMPARISONS: a filter/iif/case comparing a column to a QUOTED value that is
  really another COLUMN name (`resolveby < 'createdon'`) — a type mismatch, not
  a literal.
- FAKE TOTALS: two identical aggregations used as numerator and denominator so a
  "percent of total" is always 100; or a placeholder/sentinel literal (e.g.
  `'1900-01-01'`) standing in for a comparison the system can't express.
- CLAIMED-NOT-BUILT: a column or output the BRD asked for that is absent from
  the expressions, or an output whose name promises something it doesn't do
  (e.g. `top_product_per_category` that is a plain group-by of all products).

Report ONLY genuine gaps:
- a requirement the plan does not implement at all (severity "missing"),
- a requirement implemented incorrectly / a corrupt expression (severity "wrong").

Do NOT report: style; items already in the plan's `unsupported`, `assumptions`,
`suggestions`, or `clarifications`; implementation details the compiler owns
(naming, datasets, linked services, dependency wiring, manual triggers). If the
plan covers the BRD, return an empty findings list.
"""


class ReviewFinding(BaseModel):
    requirement: str = Field(description="The BRD requirement, quoted or tightly paraphrased.")
    issue: str = Field(description="What the plan is missing or getting wrong, one sentence.")
    severity: str = Field(description="'missing' or 'wrong'.")


class PlanReview(BaseModel):
    findings: List[ReviewFinding] = Field(default_factory=list)


def enabled() -> bool:
    return os.environ.get("PLAN_REVIEW", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


_EXPR_KEYS = ("derive(", "aggregate(", "filter(", "window(")


def rendered_expressions(spec: Any) -> str:
    """The business-logic lines of every compiled data flow — the derive /
    aggregate / filter expressions that actually run — so the reviewer sees what
    the DSL COMPUTES, not just the plan's op names. Boilerplate (source/sink/
    column-list) is dropped. Best-effort: returns '' if anything goes wrong."""
    try:
        from agent import builder

        ds_map = {d.name: d for d in spec.datasets}
        out: List[str] = []
        for df in spec.dataflows:
            script = builder.build_dataflow_script(df, ds_map)
            for ln in script.splitlines():
                s = ln.strip()
                if any(k in s for k in _EXPR_KEYS) and not s.startswith(("source(", "sink(")):
                    out.append(f"{df.name}: {s}")
        return "\n".join(out)
    except Exception:  # noqa: BLE001
        return ""


async def review_plan(brd_text: str, plan: Any, spec: Any = None) -> List[Dict[str, str]]:
    """(BRD, LogicalPlan, compiled spec) -> advisory findings. Best-effort: any
    failure returns [] — the reviewer must never break a good plan."""
    if not brd_text:
        return []
    try:
        from pydantic_ai import Agent

        from agent.retry import retry_async
        from config import default_model_settings, get_model, structured_output

        agent = Agent(
            get_model(),
            output_type=structured_output(PlanReview),
            system_prompt=_PROMPT,
            model_settings=default_model_settings(),
        )
        exprs = rendered_expressions(spec) if spec is not None else ""
        prompt = (
            f"Requirements:\n{brd_text}\n\n"
            f"Final plan (JSON):\n{plan.model_dump_json(indent=1)}"
            + (f"\n\nRendered Data Flow expressions (what actually runs):\n{exprs}"
               if exprs else "")
        )
        result = await retry_async(lambda: agent.run(prompt))
        return [f.model_dump() for f in result.output.findings]
    except Exception:  # noqa: BLE001
        return []
