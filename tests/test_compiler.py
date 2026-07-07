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
