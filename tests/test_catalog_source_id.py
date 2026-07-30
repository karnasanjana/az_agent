"""Per-request catalog source id (contextvar) overrides the env fallback."""
import json
from types import SimpleNamespace

from agent import grounding


def _stub_catalog(tmp_path, monkeypatch):
    cat = {"source_id": "tok", "schema_version": 7, "tables": [
        {"schema_name": "public", "table_name": "orders",
         "columns": [{"name": "id", "data_type": "bigint"}]}]}
    (tmp_path / "tok.json").write_text(json.dumps(cat))
    monkeypatch.setenv("ER_CATALOG_URL", str(tmp_path))
    monkeypatch.delenv("CATALOG_SOURCE_ID", raising=False)


def test_no_source_id_no_catalog(tmp_path, monkeypatch):
    _stub_catalog(tmp_path, monkeypatch)
    grounding.set_catalog_source_id(None)
    assert grounding._catalog_columns_for(SimpleNamespace(table_name="orders", schema_name="public")) == ([], None)


def test_per_request_id_grounds_from_catalog(tmp_path, monkeypatch):
    _stub_catalog(tmp_path, monkeypatch)
    grounding.set_catalog_source_id("tok")
    try:
        cols, ver = grounding._catalog_columns_for(SimpleNamespace(table_name="orders", schema_name="public"))
        assert ver == 7
        assert [(c.name, c.type) for c in cols] == [("id", "long")]
    finally:
        grounding.set_catalog_source_id(None)  # don't leak into other tests
