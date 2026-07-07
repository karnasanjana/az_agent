"""Acceptance tests for agent/compiler.py (Step 2)."""

import os
import shutil

import pytest

from agent import builder, preflight
from agent.compiler import compile_plan
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


def _plan():
    return LogicalPlan(
        project="retail",
        sources=[
            LogicalSource(
                entity="orders",
                format="csv",
                file_name="orders.csv",
                columns=[
                    LogicalColumn(name="order_id"),
                    LogicalColumn(name="customer_id"),
                    LogicalColumn(name="amount", type="decimal(18,2)"),
                    LogicalColumn(name="month"),
                    LogicalColumn(name="status"),
                ],
            ),
            LogicalSource(
                entity="customers",
                format="csv",
                file_name="customers.csv",
                columns=[LogicalColumn(name="customer_id"), LogicalColumn(name="region")],
            ),
        ],
        transforms=[
            EntityTransform(
                entity="orders",
                casts=[LogicalColumn(name="amount", type="decimal(18,2)")],
                cleaning=[CleaningOp(op="trim", column="status")],
                filters=[FilterRule(op="not_null", column="order_id")],
                dedup_keys=["order_id"],
            ),
        ],
        outputs=[
            OutputPlan(
                name="monthly_sales",
                from_entities=["orders", "customers"],
                joins=[
                    JoinPlan(
                        left_entity="orders",
                        right_entity="customers",
                        left_keys=["customer_id"],
                        right_keys=["customer_id"],
                    )
                ],
                group_by=["month"],
                aggregations=[
                    AggregationPlan(name="total_amount", op="sum", column="amount"),
                    AggregationPlan(name="order_count", op="count", column="order_id"),
                ],
                sort=[SortPlan(column="total_amount", order="desc")],
                top_n=10,
            )
        ],
    )


def test_compile_clean_spec():
    spec = compile_plan(_plan())
    assert spec.naming_violations() == []
    assert spec.cross_reference_errors() == []
    storage_ls = [ls for ls in spec.linked_services if ls.name == "ls_storage"]
    assert len(storage_ls) == 1
    # 2 landing + 2 bronze + 2 silver (orders + customers pass-through) + 1 gold
    assert len(spec.datasets) == 7
    master = next(p for p in spec.pipelines if p.name == "pl_master_retail")
    # ingest x2 + silver orders + silver customers (pass-through) + gold = 5
    assert len([a for a in master.activities if a.type == "ExecutePipeline"]) == 5
    gold = next(a for a in master.activities if a.name == "run_gold_monthly_sales")
    assert gold.depends_on == ["run_silver_orders", "run_silver_customers"]


def test_compile_deterministic():
    a = compile_plan(_plan()).model_dump()
    b = compile_plan(_plan()).model_dump()
    assert a == b


def test_aggregation_dup_group_by_raises():
    plan = _plan()
    plan.outputs[0].aggregations[0].name = "month"  # collides with group_by
    with pytest.raises(ValueError):
        compile_plan(plan)


def test_gold_date_part_grouping(monkeypatch):
    """Year/Month grouping from a timestamp must build a real gold flow — not be
    dropped as unsupported (the monthly_sales gap the user hit)."""
    monkeypatch.setenv("MOCK", "true")
    plan = LogicalPlan(
        project="retail_sales",
        sources=[
            LogicalSource(entity="orders", format="csv", file_name="o.csv",
                          columns=[LogicalColumn(name="order_id"),
                                   LogicalColumn(name="order_purchase_timestamp")]),
            LogicalSource(entity="payments", format="csv", file_name="p.csv",
                          columns=[LogicalColumn(name="order_id"),
                                   LogicalColumn(name="payment_value", type="decimal(18,2)")]),
        ],
        transforms=[EntityTransform(entity="orders",
                                    casts=[LogicalColumn(name="order_purchase_timestamp", type="timestamp")])],
        outputs=[OutputPlan(
            name="monthly_sales",
            from_entities=["orders", "payments"],
            joins=[JoinPlan(left_entity="orders", right_entity="payments",
                            left_keys=["order_id"], right_keys=["order_id"])],
            derived=[CleaningOp(op="year", column="order_purchase_timestamp", new_column="order_year"),
                     CleaningOp(op="month", column="order_purchase_timestamp", new_column="order_month")],
            group_by=["order_year", "order_month"],
            aggregations=[AggregationPlan(name="total_sales", op="sum", column="payment_value")],
        )],
    )
    spec = compile_plan(plan)
    gold = next(df for df in spec.dataflows if df.name == "df_gold_monthly_sales")
    exprs = [c.expression for t in gold.transforms for c in t.columns]
    assert "year(order_purchase_timestamp)" in exprs
    assert "month(order_purchase_timestamp)" in exprs
    run_id = "test_gold_dateparts"
    run_dir = builder.artifacts_dir(run_id)
    try:
        builder.write_artifacts(spec, run_id)
        assert preflight.validate(run_id)["passed"]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_build_and_preflight(monkeypatch):
    monkeypatch.setenv("MOCK", "true")
    run_id = "test_compile_run"
    run_dir = builder.artifacts_dir(run_id)
    try:
        spec = compile_plan(_plan())
        builder.write_artifacts(spec, run_id)
        pf = preflight.validate(run_id)
        assert pf["passed"], [c for c in pf["checks"] if not c["passed"]]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
