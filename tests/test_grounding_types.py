"""Grounded type propagation through flow transforms (agent/grounding.py).

Regression for the bike-store join failure (run 5ee8ff8cc21a): landing infers
category_id as string, silver casts it to integer, then the BRD's 'replace
null with 0' adds coalesce(category_id, 0) — whose result type came out STRING
and re-broke the gold join against categories (integer). LLM repairs kept
adding the correct cast; grounding kept erasing it: a pure compiler-side bug.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.grounding import _expr_type, _flow_output_columns, _split_args
from models.spec import (
    Column,
    DataFlow,
    DataFlowEndpoint,
    DerivedColumn,
    MedallionLayer,
    Transform,
    TransformKind,
)


def test_coalesce_keeps_column_type():
    cols = {"category_id": "integer"}
    assert _expr_type("coalesce(category_id, 0)", cols) == "integer"
    assert _expr_type("coalesce(name, 'Unknown')", {"name": "string"}) == "string"


def test_iif_clamp_keeps_column_type():
    cols = {"quantity": "integer"}
    assert _expr_type("iif(quantity < 0, 0, quantity)", cols) == "integer"


def test_coalesce_numeric_literals_fall_back_to_double():
    assert _expr_type("coalesce(unknown_col, 0)", {}) == "double"


def test_split_args_respects_nesting_and_quotes():
    assert _split_args("a, iif(b, 'x,y', c), 0") == ["a", "iif(b, 'x,y', c)", "0"]


def test_cast_then_coalesce_survives_flow_simulation():
    """The exact silver-products chain: string source -> castTypes(toInteger)
    -> cleanColumns(coalesce). Sink schema must say integer."""
    df = DataFlow(
        name="df_silver_products",
        layer=MedallionLayer.silver,
        source=DataFlowEndpoint(stream_name="srcProducts", dataset="ds_bronze_products"),
        sink=DataFlowEndpoint(stream_name="sinkProducts", dataset="ds_silver_products"),
        transforms=[
            Transform(kind=TransformKind.cast, name="castTypes", columns=[
                DerivedColumn(name="category_id", expression="toInteger(category_id)"),
            ]),
            Transform(kind=TransformKind.derived, name="cleanColumns", columns=[
                DerivedColumn(name="category_id", expression="coalesce(category_id, 0)"),
            ]),
        ],
    )
    out = _flow_output_columns(df, [Column(name="category_id", type="string"),
                                    Column(name="product_name", type="string")])
    types = {c.name: c.type for c in out}
    assert types["category_id"] == "integer"
    assert types["product_name"] == "string"


def test_note_fabricated_discloses_dropped_columns():
    # bug 6: a requested column absent from the real schema must not vanish
    # silently. _note_fabricated flags exactly the model columns not in the
    # real schema and records each as a plan assumption.
    from agent.grounding import _note_fabricated
    from models.logical import LogicalPlan, LogicalSource, LogicalColumn

    src = LogicalSource(entity="cases", format="dataverse",
                        dataverse_url="https://x", entity_set="incidents",
                        columns=[LogicalColumn(name="incidentid"),
                                 LogicalColumn(name="sla_hours_target")])
    plan = LogicalPlan(project="p", sources=[src])
    notes = _note_fabricated(src, ["incidentid", "title"], plan)
    assert any("sla_hours_target" in n for n in notes)
    assert not any("incidentid" in n for n in notes)  # real column, no note
    assert all(n in plan.assumptions for n in notes)
