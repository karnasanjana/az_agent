"""B3: load-audit columns are a first-class op, not 'unsupported'.

A load timestamp renders currentTimestamp(); a constant tag renders a quoted
literal. Both pass CleaningOp validation and type-check cleanly."""
from agent.typecheck import _op_result_type
from models.logical import CleaningOp
from models.spec import _render_op


def test_currenttimestamp_renders_noarg():
    assert _render_op("currenttimestamp", None, []) == "currentTimestamp()"
    assert _render_op("now", None, []) == "currentTimestamp()"
    assert _render_op("currentutc", None, []) == "currentUTC()"


def test_literal_renders_quoted():
    assert _render_op("literal", "covid", []) == "'covid'"
    assert _render_op("literal", None, ["covid"]) == "'covid'"
    assert _render_op("literal", "42", []) == "42"  # numeric bare


def test_ops_pass_cleaningop_validation():
    CleaningOp(op="currenttimestamp", column="", new_column="load_timestamp")
    CleaningOp(op="literal", column="covid", new_column="source_name")


def test_result_types():
    assert _op_result_type("currenttimestamp", None, {}) == "timestamp"
    assert _op_result_type("literal", None, {}) == "string"
