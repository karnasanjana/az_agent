"""Drift-summary logic for catalog-grounded sources (agent.grounding._schema_drift)."""
from agent.grounding import _schema_drift
from models.logical import LogicalColumn as C


def test_no_drift_when_identical():
    cols = [C(name="id", type="long"), C(name="name", type="string")]
    assert _schema_drift(cols, list(cols)) == ""


def test_unreadable_live_source_is_not_drift():
    # Live probe returned nothing (source down) — must NOT be reported as drift.
    assert _schema_drift([C(name="id", type="long")], []) == ""


def test_added_removed_and_type_change():
    catalog = [C(name="id", type="long"), C(name="total", type="decimal"),
               C(name="old", type="string")]
    live = [C(name="id", type="long"), C(name="total", type="double"),
            C(name="new", type="string")]
    d = _schema_drift(catalog, live)
    assert "added new" in d
    assert "removed old" in d
    assert "total decimal→double" in d
