"""Acceptance tests for agent/completeness.py (Step 3). One per check."""

from agent.completeness import check
from models.logical import (
    AggregationPlan,
    CleaningOp,
    EntityTransform,
    FilterRule,
    JoinPlan,
    LogicalColumn,
    LogicalPlan,
    LogicalSource,
    OutputPlan,
    SortPlan,
)


def _src(entity="orders", cols=None):
    return LogicalSource(
        entity=entity,
        format="csv",
        file_name=f"{entity}.csv",
        columns=[LogicalColumn(name=c) for c in (cols or [])],
    )


def _has(problems, phrase):
    return any(phrase in p for p in problems)


def test_ok_plan_passes():
    plan = LogicalPlan(sources=[_src("orders", ["id"])])
    assert check(plan) == []


def test_no_sources():
    plan = LogicalPlan.model_construct(sources=[], transforms=[], outputs=[])
    assert _has(check(plan), "no sources")


def test_duplicate_entity():
    plan = LogicalPlan(sources=[_src("orders"), _src("orders")])
    assert _has(check(plan), "duplicate source entity 'orders'")


def test_transform_unknown_entity():
    plan = LogicalPlan(sources=[_src("orders")], transforms=[EntityTransform(entity="ghosts")])
    assert _has(check(plan), "transform references unknown entity 'ghosts'")


def test_output_unknown_entity():
    plan = LogicalPlan(
        sources=[_src("orders")],
        outputs=[OutputPlan(name="o", from_entities=["ghost"])],
    )
    assert _has(check(plan), "unknown entity 'ghost'")


def test_disconnected_entities():
    plan = LogicalPlan(
        sources=[_src("a"), _src("b")],
        outputs=[OutputPlan(name="o", from_entities=["a", "b"])],  # no join
    )
    assert _has(check(plan), "are not connected by joins")


def test_join_endpoint_outside_from_entities():
    plan = LogicalPlan(
        sources=[_src("a"), _src("b"), _src("c")],
        outputs=[
            OutputPlan(
                name="o",
                from_entities=["a", "b"],
                joins=[JoinPlan(left_entity="a", right_entity="c", left_keys=["k"], right_keys=["k"])],
            )
        ],
    )
    assert _has(check(plan), "not in from_entities")


def test_group_by_without_aggregations():
    plan = LogicalPlan(
        sources=[_src("orders")],
        outputs=[OutputPlan(name="o", from_entities=["orders"], group_by=["month"])],
    )
    assert _has(check(plan), "group_by without aggregations")


def test_aggregation_dup_group_by():
    plan = LogicalPlan(
        sources=[_src("orders")],
        outputs=[
            OutputPlan(
                name="o",
                from_entities=["orders"],
                group_by=["month"],
                aggregations=[AggregationPlan(name="month", op="sum", column="amount")],
            )
        ],
    )
    assert _has(check(plan), "duplicates a group_by column")


def test_top_n_without_sort():
    plan = LogicalPlan(
        sources=[_src("orders")],
        outputs=[OutputPlan(name="o", from_entities=["orders"], top_n=5)],
    )
    assert _has(check(plan), "top_n without sort")


def test_unknown_column_in_transform():
    plan = LogicalPlan(
        sources=[_src("orders", ["order_id", "status"])],
        transforms=[EntityTransform(entity="orders", cleaning=[CleaningOp(op="trim", column="ghost")])],
    )
    assert _has(check(plan), "'ghost' is not a column of 'orders'")


def test_unknown_column_in_output():
    plan = LogicalPlan(
        sources=[_src("orders", ["order_id", "month"])],
        outputs=[
            OutputPlan(
                name="o",
                from_entities=["orders"],
                group_by=["month"],
                aggregations=[AggregationPlan(name="total", op="sum", column="ghost")],
            )
        ],
    )
    assert _has(check(plan), "'ghost' is not a column of")
