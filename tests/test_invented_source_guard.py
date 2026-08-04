"""B1: a BRD that names no real data source must not yield a confident green
plan — the model's fabricated placeholder source is flagged for clarification."""
from agent.completeness import _looks_invented, check
from models.logical import LogicalPlan, LogicalSource, SourceFormat


def test_placeholder_source_flagged():
    s = LogicalSource(entity="dummy_data", format=SourceFormat.http_csv,
                      http_url="http://host/dummy.csv")
    assert _looks_invented(s)
    problems = check(LogicalPlan(sources=[s], transforms=[], outputs=[]))
    assert any("looks invented" in p for p in problems)


def test_real_source_not_flagged():
    s = LogicalSource(entity="customer", format=SourceFormat.postgres,
                      table_name="customer", schema_name="public",
                      server="pg", database="retaildb")
    assert not _looks_invented(s)
    problems = check(LogicalPlan(sources=[s], transforms=[], outputs=[]))
    assert not any("looks invented" in p for p in problems)


def test_real_http_source_not_flagged():
    s = LogicalSource(entity="covid_cases", format=SourceFormat.http_csv,
                      http_url="https://raw.githubusercontent.com/data/covid.csv")
    assert not _looks_invented(s)


def test_generic_fabricated_entity_name_flagged():
    # the exact 'input_data' fallback a model coins from a content-free BRD
    s = LogicalSource(entity="input_data", format=SourceFormat.csv,
                      container="landing", file_name="input.csv")
    assert _looks_invented(s)


def test_data_named_source_not_flagged():
    # 'data' / 'orders' are real names — exact-match list must not touch them
    for name, tbl in [("data", "data"), ("orders", "orders")]:
        s = LogicalSource(entity=name, format=SourceFormat.postgres,
                          table_name=tbl, schema_name="public",
                          server="pg", database="db")
        assert not _looks_invented(s)
