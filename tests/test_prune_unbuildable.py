"""prune_unbuildable: after repair rounds exhaust, unbuildable pieces are
dropped with notes and the REST builds — never a question wall that builds
nothing. Miniature of the BRD1 live run (CustomerAgeGroup needs birth_date,
which the real customers.csv does not have)."""

import shutil

from agent import builder, preflight
from agent.compiler import compile_plan
from agent.completeness import check, prune_unbuildable
from models.logical import (
    AggregationPlan, CaseBranch, CleaningOp, EntityTransform, JoinPlan,
    LogicalColumn, LogicalPlan, LogicalSource, OutputPlan,
)


def _plan():
    return LogicalPlan(
        project="bike_store",
        sources=[
            LogicalSource(entity="customers", format="csv", container="landing",
                          file_name="customers.csv",
                          columns=[LogicalColumn(name="customer_id", type="integer"),
                                   LogicalColumn(name="first_name"),
                                   LogicalColumn(name="city")]),
            LogicalSource(entity="orders", format="csv", container="landing",
                          file_name="orders.csv",
                          columns=[LogicalColumn(name="order_id", type="integer"),
                                   LogicalColumn(name="customer_id", type="integer"),
                                   LogicalColumn(name="amount", type="double")]),
        ],
        transforms=[EntityTransform(
            entity="customers",
            cleaning=[
                CleaningOp(op="trim", column="first_name"),  # buildable
                # BRD1 shape: age group derived from a column the data lacks
                CleaningOp(op="case", column="birth_date",
                           when=[CaseBranch(op="lt", value="1980", then="'Senior'")],
                           otherwise="'Adult'", new_column="customer_age_group"),
            ],
            dedup_keys=["customer_id"],
        )],
        outputs=[
            # healthy output — must survive and build
            OutputPlan(name="sales_by_city", from_entities=["customers", "orders"],
                       joins=[JoinPlan(left_entity="customers", right_entity="orders",
                                       left_keys=["customer_id"], right_keys=["customer_id"])],
                       group_by=["city"],
                       aggregations=[AggregationPlan(name="revenue", op="sum", column="amount")]),
            # poisoned output — groups by the column whose derivation is unbuildable
            OutputPlan(name="sales_by_age_group", from_entities=["customers", "orders"],
                       joins=[JoinPlan(left_entity="customers", right_entity="orders",
                                       left_keys=["customer_id"], right_keys=["customer_id"])],
                       group_by=["customer_age_group"],
                       aggregations=[AggregationPlan(name="revenue", op="sum", column="amount")]),
        ],
    )


def test_prune_builds_the_rest():
    plan = _plan()
    problems = check(plan)
    assert problems  # the poisoned pieces are real problems
    notes = prune_unbuildable(plan, problems)
    assert check(plan) == []  # what remains is consistent
    # the unbuildable transform op and output are gone, the healthy ones stay
    assert [o.name for o in plan.outputs] == ["sales_by_city"]
    ops = [op.new_column or op.column for op in plan.transforms[0].cleaning]
    assert ops == ["first_name"]
    # every drop is a visible note on the plan
    assert any("customer_age_group" in n for n in notes)
    assert any("sales_by_age_group" in n for n in notes)
    assert all(n in plan.assumptions for n in notes)
    # and the pruned plan compiles + passes preflight end to end
    spec = compile_plan(plan)
    run_id = "test_prune_builds"
    try:
        builder.write_artifacts(spec, run_id)
        assert preflight.validate(run_id)["passed"]
    finally:
        shutil.rmtree(builder.artifacts_dir(run_id), ignore_errors=True)


def test_salvage_drops_only_the_bad_group_by_key():
    # customer_value shape: a fabricated `loyalty_tier` group_by must not take
    # down the whole mart — the other keys + aggregations still build.
    plan = LogicalPlan(
        project="retail",
        sources=[LogicalSource(entity="orders", format="csv", container="landing",
                               file_name="orders.csv",
                               columns=[LogicalColumn(name="order_id", type="integer"),
                                        LogicalColumn(name="email"),
                                        LogicalColumn(name="amount", type="double")])],
        outputs=[OutputPlan(
            name="customer_value", from_entities=["orders"],
            group_by=["email", "loyalty_tier"],  # loyalty_tier does not exist
            aggregations=[AggregationPlan(name="revenue", op="sum", column="amount")])],
    )
    assert check(plan)  # loyalty_tier is flagged
    notes = prune_unbuildable(plan, check(plan))
    assert check(plan) == []
    assert [o.name for o in plan.outputs] == ["customer_value"]  # survived
    assert plan.outputs[0].group_by == ["email"]  # only the bad key dropped
    assert any("loyalty_tier" in n for n in notes)


def test_identical_aggregations_flagged():
    # pct_of_total = a/a*100 faked via a duplicate count -> always 100. check()
    # must catch it so it can never silently ship as a real metric.
    plan = LogicalPlan(
        project="sla",
        sources=[LogicalSource(entity="cases", format="csv", container="landing",
                               file_name="cases.csv",
                               columns=[LogicalColumn(name="case_id", type="integer"),
                                        LogicalColumn(name="priority")])],
        outputs=[OutputPlan(
            name="priority_share", from_entities=["cases"], group_by=["priority"],
            aggregations=[AggregationPlan(name="n", op="count", column="case_id"),
                          AggregationPlan(name="total", op="count", column="case_id")])],
    )
    probs = check(plan)
    assert any("identical" in p and "priority_share" in p for p in probs)


def test_prune_leaves_ungrounded_entities_alone():
    plan = _plan()
    plan.sources[0].columns = []  # customers schema unknown -> nothing provable
    before = len(plan.transforms[0].cleaning)
    prune_unbuildable(plan, [])
    assert len(plan.transforms[0].cleaning) == before


def test_prune_clears_pipeline_gold_refs():
    from models.logical import LogicalPipeline
    plan = _plan()
    plan.pipelines = [
        LogicalPipeline(name="PL_Bronze", ingest=["customers", "orders"]),
        LogicalPipeline(name="PL_Silver", silver=["customers"]),
        LogicalPipeline(name="PL_Gold", gold=["sales_by_city", "sales_by_age_group"]),
        LogicalPipeline(name="PL_Master", invokes=["PL_Bronze", "PL_Silver", "PL_Gold"]),
    ]
    prune_unbuildable(plan, check(plan))
    assert check(plan) == []
    gold_pl = next(p for p in plan.pipelines if p.name == "PL_Gold")
    assert gold_pl.gold == ["sales_by_city"]


def test_ratio_named_column_without_division_flagged():
    # BRD 04: cfr_pct = deaths * 100 / confirmed folded into a single multiply
    # (deaths * 100 * confirmed) -> silent corruption. check() must flag it.
    from models.logical import CleaningOp
    plan = LogicalPlan(
        project="covid",
        sources=[LogicalSource(entity="c", format="csv", container="landing",
                               file_name="c.csv",
                               columns=[LogicalColumn(name="country"),
                                        LogicalColumn(name="deaths", type="long"),
                                        LogicalColumn(name="confirmed", type="long")])],
        outputs=[OutputPlan(
            name="focus", from_entities=["c"], group_by=["country"],
            aggregations=[AggregationPlan(name="peak", op="max", column="confirmed"),
                          AggregationPlan(name="pk_d", op="max", column="deaths")],
            post_agg_derived=[CleaningOp(op="multiply", column="pk_d", args=["100", "peak"],
                                         new_column="cfr_pct")])],
    )
    assert any("ratio/percentage" in p and "cfr_pct" in p for p in check(plan))
    # a correct percentage that DOES divide is not flagged
    plan.outputs[0].post_agg_derived = [
        CleaningOp(op="divide", column="pk_d", args=["peak"], new_column="cfr_ratio")]
    assert not any("ratio/percentage" in p for p in check(plan))
