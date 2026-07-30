"""Connection-carry: a catalog-backed postgres source needs only engine+tables
in the BRD; the ER diagram supplies server/database/port.

Covers the three new pieces: catalog.connection() mapping, the relaxed
LogicalSource validator, and grounding._seed_catalog_connection() filling the
source. Uses the local-dir catalog transport (ER_CATALOG_URL = a directory)."""
import json

import pytest

from agent import grounding
from models.logical import LogicalPlan, LogicalSource, SourceFormat, set_catalog_source_id


def _stub_catalog(tmp_path, monkeypatch):
    cat = {
        "source_id": "tok", "schema_version": 3,
        "tables": [{"schema_name": "public", "table_name": "orders",
                    "columns": [{"name": "id", "data_type": "bigint"}]}],
        "connections": [{"type": "postgres", "host": "pg-prod.example.com",
                         "port": 5432, "database": "shop"}],
    }
    (tmp_path / "tok.json").write_text(json.dumps(cat))
    monkeypatch.setenv("ER_CATALOG_URL", str(tmp_path))
    monkeypatch.delenv("CATALOG_SOURCE_ID", raising=False)


def test_connection_mapping():
    from tools import catalog
    cat = {"connections": [{"type": "postgres", "host": "h", "port": 5432, "database": "d"}]}
    assert catalog.connection(cat, "postgres") == {"server": "h", "database": "d", "port": "5432"}
    assert catalog.connection(cat, "bigquery") is None  # no matching engine


def test_validator_requires_connection_without_catalog(monkeypatch):
    set_catalog_source_id(None)
    monkeypatch.delenv("CATALOG_SOURCE_ID", raising=False)
    with pytest.raises(ValueError, match="postgres needs"):
        LogicalSource(entity="orders", format=SourceFormat.postgres, table_name="orders")


def test_catalog_source_constructs_and_seeds(tmp_path, monkeypatch):
    _stub_catalog(tmp_path, monkeypatch)
    set_catalog_source_id("tok")
    try:
        # validator now allows a postgres source with only table_name...
        src = LogicalSource(entity="orders", format=SourceFormat.postgres,
                            table_name="orders", schema_name="public")
        assert src.server is None and src.database is None
        # ...and grounding fills the connection from the catalog.
        plan = LogicalPlan(sources=[src], transforms=[], outputs=[])
        grounding._seed_catalog_connection(plan)
        assert src.server == "pg-prod.example.com"
        assert src.database == "shop"
        assert src.port == "5432"
        assert any("Connection for source 'orders' taken from the ER catalog" in a for a in plan.assumptions)
    finally:
        set_catalog_source_id(None)


def test_catalog_overrides_planner_guess(tmp_path, monkeypatch):
    # The catalog is authoritative: a placeholder the planner/refine invented must
    # be OVERWRITTEN (else it survives and makes the compile non-deterministic).
    _stub_catalog(tmp_path, monkeypatch)
    set_catalog_source_id("tok")
    try:
        src = LogicalSource(entity="orders", format=SourceFormat.postgres,
                            table_name="orders", server="your_postgres_server", database="guess")
        plan = LogicalPlan(sources=[src], transforms=[], outputs=[])
        plan.assumptions.append("Assumed PostgreSQL server name as your_postgres_server")
        grounding._seed_catalog_connection(plan)
        assert src.server == "pg-prod.example.com"  # catalog wins over the guess
        assert src.database == "shop"
        assert src.port == "5432"
        # the planner's false guess was stripped from the review
        assert not any("your_postgres_server" in a for a in plan.assumptions)
    finally:
        set_catalog_source_id(None)
