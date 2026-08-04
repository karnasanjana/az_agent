"""ER-flow contract: when a diagram (catalog) is attached, a source that is not a
table in that diagram is flagged for clarification — the agent verifies against
the connected data instead of inventing a source. No catalog -> no-op."""
import json

from agent.grounding import catalog_membership_problems, resolve_sources_to_catalog
from models.logical import (
    LogicalPlan, LogicalSource, SourceFormat, set_catalog_source_id,
)


def _catalog(tmp_path, monkeypatch):
    cat = {"source_id": "tok", "schema_version": 1,
           "connections": [{"type": "postgres", "host": "pg", "database": "db"}],
           "tables": [
               {"schema_name": "public", "table_name": "customer",
                "columns": [{"name": "customer_id", "data_type": "int"}]},
               {"schema_name": "public", "table_name": "payment",
                "columns": [{"name": "payment_id", "data_type": "int"}]},
           ]}
    (tmp_path / "tok.json").write_text(json.dumps(cat))
    monkeypatch.setenv("ER_CATALOG_URL", str(tmp_path))
    monkeypatch.delenv("CATALOG_SOURCE_ID", raising=False)


def test_off_diagram_source_flagged(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch)
    set_catalog_source_id("tok")
    try:
        plan = LogicalPlan(sources=[LogicalSource(entity="banana", format=SourceFormat.csv, container="landing", file_name="banana.csv")],
                           transforms=[], outputs=[])
        problems = catalog_membership_problems(plan)
        assert problems and "banana" in problems[0]
    finally:
        set_catalog_source_id(None)


def test_diagram_table_source_ok(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch)
    set_catalog_source_id("tok")
    try:
        plan = LogicalPlan(sources=[LogicalSource(
            entity="customer", format=SourceFormat.postgres, table_name="customer",
            schema_name="public", server="pg", database="db")], transforms=[], outputs=[])
        assert catalog_membership_problems(plan) == []
    finally:
        set_catalog_source_id(None)


def test_no_catalog_is_noop(monkeypatch):
    monkeypatch.delenv("CATALOG_SOURCE_ID", raising=False)
    set_catalog_source_id(None)
    plan = LogicalPlan(sources=[LogicalSource(entity="banana", format=SourceFormat.csv, container="landing", file_name="banana.csv")],
                       transforms=[], outputs=[])
    assert catalog_membership_problems(plan) == []


def test_resolve_snaps_plural_and_csv_to_diagram(tmp_path, monkeypatch):
    # the BUG A repro: model made 'payments' a CSV; must snap to postgres 'payment'
    _catalog(tmp_path, monkeypatch)
    set_catalog_source_id("tok")
    try:
        s = LogicalSource(entity="payments", format=SourceFormat.csv,
                          container="landing", file_name="payments.csv")
        plan = LogicalPlan(sources=[s], transforms=[], outputs=[])
        resolve_sources_to_catalog(plan)
        assert s.table_name == "payment"          # plural snapped to real table
        assert s.format == SourceFormat.postgres  # csv -> engine format
        assert catalog_membership_problems(plan) == []  # now recognised, not flagged
    finally:
        set_catalog_source_id(None)


def test_resolve_leaves_unknown_table_for_clarification(tmp_path, monkeypatch):
    _catalog(tmp_path, monkeypatch)
    set_catalog_source_id("tok")
    try:
        s = LogicalSource(entity="loyalty_points", format=SourceFormat.csv,
                          container="landing", file_name="lp.csv")
        plan = LogicalPlan(sources=[s], transforms=[], outputs=[])
        resolve_sources_to_catalog(plan)
        assert s.format == SourceFormat.csv  # untouched — not a diagram table
        assert catalog_membership_problems(plan)  # still flagged
    finally:
        set_catalog_source_id(None)
