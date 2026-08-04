"""Join-key carry: when the ER catalog has a foreign key between a gold join's
two tables, the FK columns are the authoritative join keys — grounding overrides
whatever the planner name-guessed. No FK (e.g. BigQuery, or an unrelated pair)
leaves the planner's keys as the fallback. Local-dir catalog transport."""
import json

from agent import grounding
from models.logical import (
    JoinPlan, LogicalPlan, LogicalSource, OutputPlan, SourceFormat,
    set_catalog_source_id,
)


def _stub_catalog(tmp_path, monkeypatch, fks):
    cat = {
        "source_id": "tok", "schema_version": 1,
        "tables": [
            {"schema_name": "public", "table_name": "customer",
             "columns": [{"name": "customer_id", "data_type": "int"}]},
            {"schema_name": "public", "table_name": "rental",
             "columns": [{"name": "customer_id", "data_type": "int"}]},
        ],
        "foreign_keys": fks,
    }
    (tmp_path / "tok.json").write_text(json.dumps(cat))
    monkeypatch.setenv("ER_CATALOG_URL", str(tmp_path))
    monkeypatch.delenv("CATALOG_SOURCE_ID", raising=False)


def test_relationships_reader():
    from tools import catalog
    cat = {"foreign_keys": [
        {"source_table": "Rental", "source_columns": ["customer_id"],
         "target_table": "Customer", "target_columns": ["customer_id"]},
        {"source_table": "x", "source_columns": ["a"], "target_table": "y",
         "target_columns": ["a", "b"]},  # mismatched arity -> dropped
    ]}
    rels = catalog.relationships(cat)
    assert rels == [{"source_table": "rental", "source_columns": ["customer_id"],
                     "target_table": "customer", "target_columns": ["customer_id"]}]
    assert catalog.relationships({}) == []  # BigQuery / no FKs


def _plan_with_join(left_keys, right_keys):
    customer = LogicalSource(entity="customer", format=SourceFormat.postgres,
                             table_name="customer", schema_name="public")
    rental = LogicalSource(entity="rental", format=SourceFormat.postgres,
                           table_name="rental", schema_name="public")
    out = OutputPlan(
        name="rentals_by_customer", from_entities=["customer", "rental"],
        joins=[JoinPlan(left_entity="customer", right_entity="rental",
                        left_keys=left_keys, right_keys=right_keys)],
    )
    return LogicalPlan(sources=[customer, rental], transforms=[], outputs=[out])


def test_join_keys_corrected_from_fk(tmp_path, monkeypatch):
    _stub_catalog(tmp_path, monkeypatch, [
        {"source_table": "rental", "source_columns": ["customer_id"],
         "target_table": "customer", "target_columns": ["customer_id"]},
    ])
    set_catalog_source_id("tok")
    try:
        plan = _plan_with_join(left_keys=["id"], right_keys=["cust_id"])  # wrong guess
        grounding._seed_catalog_joins(plan)
        j = plan.outputs[0].joins[0]
        assert j.left_keys == ["customer_id"]   # customer side (FK target)
        assert j.right_keys == ["customer_id"]  # rental side (FK source)
        assert any("catalog foreign key" in a for a in plan.assumptions)
    finally:
        set_catalog_source_id(None)


def test_no_fk_leaves_planner_keys(tmp_path, monkeypatch):
    _stub_catalog(tmp_path, monkeypatch, [])  # no FKs (the BigQuery case)
    set_catalog_source_id("tok")
    try:
        plan = _plan_with_join(left_keys=["a"], right_keys=["b"])
        notes = grounding._seed_catalog_joins(plan)
        assert notes == []
        j = plan.outputs[0].joins[0]
        assert j.left_keys == ["a"] and j.right_keys == ["b"]  # untouched fallback
    finally:
        set_catalog_source_id(None)
