"""Acceptance for the /plan logical-plan wiring (Step 5+6).

Monkeypatches the extractor so no live model is needed: verifies the new path
compiles a valid plan into an approvable run, and that the completeness repair
loop feeds a bad plan back and converges.
"""

import os
import shutil

import pytest
from fastapi.testclient import TestClient

import app as app_module
from models.logical import (
    AggregationPlan,
    EntityTransform,
    LogicalColumn,
    LogicalPlan,
    LogicalSource,
    OutputPlan,
)


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MOCK", "true")
    monkeypatch.delenv("LEGACY_PARSER", raising=False)
    # This file exercises the ONE-SHOT extractor loop; the tool-agent path is
    # covered by tests/test_plantools.py, the auto default by test_plancache.py.
    monkeypatch.setenv("PLAN_MODE", "oneshot")
    # These tests stub the extractor and share one BRD text, so a cached plan
    # from an earlier test would short-circuit the stub under test.
    monkeypatch.setenv("PLAN_CACHE", "false")
    yield
    for rid in list(app_module._RUNS):
        rd = app_module._RUNS[rid].get("run_dir")
        if rd:
            shutil.rmtree(rd, ignore_errors=True)
        app_module._RUNS.pop(rid, None)


def _good_plan():
    return LogicalPlan(
        project="retail",
        sources=[
            LogicalSource(
                entity="orders",
                format="csv",
                file_name="orders.csv",
                columns=[LogicalColumn(name="order_id"), LogicalColumn(name="month"),
                         LogicalColumn(name="amount", type="decimal(18,2)")],
            ),
        ],
        transforms=[EntityTransform(entity="orders", dedup_keys=["order_id"])],
        outputs=[
            OutputPlan(
                name="monthly_sales",
                from_entities=["orders"],
                group_by=["month"],
                aggregations=[AggregationPlan(name="total", op="sum", column="amount")],
            )
        ],
    )


def test_plan_happy_path(monkeypatch):
    async def fake_extract(text, message_history=None):
        return _good_plan(), []

    monkeypatch.setattr(app_module, "_store_and_respond", app_module._store_and_respond)
    from agent import extractor
    monkeypatch.setattr(extractor, "extract_plan", fake_extract)

    client = TestClient(app_module.app)
    r = client.post("/plan", data={"brd": "irrelevant, extractor is stubbed"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "AWAITING_APPROVAL"
    assert body["preflight"]["passed"]
    # logical plan persisted for audit
    run_dir = app_module._RUNS[body["run_id"]]["run_dir"]
    assert os.path.isfile(os.path.join(run_dir, "logical_plan.json"))


def test_completeness_repair_loop(monkeypatch):
    """First extraction returns a broken plan (group_by w/o aggregations); the
    refine call returns the fixed plan. Loop must converge, not 422."""
    calls = {"n": 0}

    async def fake_extract(text, message_history=None):
        bad = _good_plan()
        bad.outputs[0].aggregations = []  # group_by without aggregations -> fails check
        return bad, []

    async def fake_refine(instruction, message_history):
        calls["n"] += 1
        return _good_plan(), message_history

    from agent import extractor
    monkeypatch.setattr(extractor, "extract_plan", fake_extract)
    monkeypatch.setattr(extractor, "refine_plan", fake_refine)

    client = TestClient(app_module.app)
    r = client.post("/plan", data={"brd": "x"})
    assert r.status_code == 200, r.text
    assert calls["n"] >= 1  # repair loop ran
    assert r.json()["preflight"]["passed"]


def test_repaired_plan_is_regrounded(tmp_path, monkeypatch):
    """A refine returns a FULL plan whose source columns are model-authored
    again. Grounding must be re-applied to it, or every repair round after the
    first checks (and compiles) against hallucinated columns."""
    landing = tmp_path / "tenant" / "storage" / "landing"
    landing.mkdir(parents=True)
    (landing / "orders.csv").write_text(
        "order_id,month,amount\n1,2026-07,10.5\n", encoding="utf-8"
    )
    import agent.grounding as grounding

    monkeypatch.setattr(grounding, "MOCK_TENANT_DIR", str(tmp_path / "tenant"))

    async def fake_extract(text, message_history=None):
        bad = _good_plan()
        bad.outputs[0].aggregations = []  # force one repair round
        return bad, []

    async def fake_refine(instruction, message_history):
        p = _good_plan()
        # the model re-invents the schema on the way back
        p.sources[0].columns = [LogicalColumn(name="totally_made_up")]
        return p, message_history

    from agent import extractor
    monkeypatch.setattr(extractor, "extract_plan", fake_extract)
    monkeypatch.setattr(extractor, "refine_plan", fake_refine)

    client = TestClient(app_module.app)
    r = client.post("/plan", data={"brd": "x"})
    assert r.status_code == 200, r.text
    plan = app_module._RUNS[r.json()["run_id"]]["logical_plan"]
    cols = [c.name for c in plan.sources[0].columns]
    assert cols == ["order_id", "month", "amount"]  # real header, not the model's


def test_unsupported_triage_loop(monkeypatch):
    """A plan with unsupported items triggers ONE triage round carrying the
    capability card; the model re-expresses what fits. Items still unsupported
    after triage ride into the response (and gate /approve)."""
    calls = {"prompts": []}

    async def fake_extract(text, message_history=None):
        p = _good_plan()
        p.unsupported = [
            "Convert first_name to Proper Case",  # expressible — model over-marked
            "Send a Teams alert on failure",      # genuine gap
        ]
        return p, []

    async def fake_refine(instruction, message_history):
        calls["prompts"].append(instruction)
        p = _good_plan()  # proper case re-expressed; alerting stays
        p.unsupported = ["Send a Teams alert on failure"]
        p.suggestions = ["Alerting not supported -> monitor the run from the UI instead?"]
        return p, message_history

    from agent import extractor
    monkeypatch.setattr(extractor, "extract_plan", fake_extract)
    monkeypatch.setattr(extractor, "refine_plan", fake_refine)

    client = TestClient(app_module.app)
    r = client.post("/plan", data={"brd": "x"})
    assert r.status_code == 200, r.text
    assert len(calls["prompts"]) == 1  # exactly one triage round
    # the triage prompt carries the live capability card
    assert "proper" in calls["prompts"][0]
    assert "validate_first" in calls["prompts"][0]
    body = r.json()
    assert body["unsupported"] == ["Send a Teams alert on failure"]
    assert body["suggestions"] == [
        "Alerting not supported -> monitor the run from the UI instead?"
    ]
    # the genuine gap gates approval until acknowledged
    a = client.post("/approve", json={"run_id": body["run_id"]})
    assert a.status_code == 409
    assert a.json()["detail"]["unsupported"] == ["Send a Teams alert on failure"]
    a = client.post("/approve", json={"run_id": body["run_id"],
                                      "acknowledge_unsupported": True})
    assert a.status_code == 200


def test_no_convergence_returns_422(monkeypatch):
    async def fake_extract(text, message_history=None):
        bad = _good_plan()
        bad.outputs[0].aggregations = []
        return bad, []

    async def fake_refine(instruction, message_history):
        bad = _good_plan()
        bad.outputs[0].aggregations = []  # never fixes
        return bad, message_history

    from agent import extractor
    monkeypatch.setattr(extractor, "extract_plan", fake_extract)
    monkeypatch.setattr(extractor, "refine_plan", fake_refine)

    client = TestClient(app_module.app)
    r = client.post("/plan", data={"brd": "x"})
    assert r.status_code == 422
    assert "problems" in r.json()["detail"]
