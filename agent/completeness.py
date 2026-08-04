"""Completeness check: the deterministic critic for a LogicalPlan.

NOT an LLM. This is the "Agent 2" from the multi-agent sketch, done in code so
it never adds nondeterminism or cost. It answers the questions a reviewer would
ask of the plan before any ADF is built: is every output traceable to sources?
does every multi-entity output have joins that connect its entities? does every
referenced column exist (when the schema is known)?

Its output — one plain-English line per problem — is fed straight back to the
extractor LLM in the /plan repair loop. The model fixes its own plan; a human
never edits code for a new failure class.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set

from models.logical import LogicalPlan, LogicalSource, OutputPlan, SourceFormat
from models.spec import _OP_ARITH, _norm_op

_NUMERIC = re.compile(r"-?\d+(\.\d+)?")


def _entity_columns(src: LogicalSource) -> Set[str]:
    return {c.name for c in src.columns}


def _connected(entities: List[str], edges: List[tuple]) -> bool:
    """True when `edges` (undirected) connect every entity into one component."""
    if len(entities) <= 1:
        return True
    parent = {e: e for e in entities}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    roots = {find(e) for e in entities}
    return len(roots) == 1


_PRUNE_OUT_RE = re.compile(r"output '([^']+)'")

# Column names that imply a division (percentage / rate / ratio / average / per).
_RATIO_RE = re.compile(r"(?:^|_)(pct|percent|rate|ratio|share|avg|average|mean|per)(?:$|_|\d)", re.I)


def _ratio_without_division(ops: List) -> List[str]:
    """Names of ratio/percentage-looking derived columns whose derivation chain
    contains NO division. The arithmetic vocabulary carries one operator per op,
    so a mixed `a * 100 / b` gets folded into a single multiply
    (`a * 100 * b`) — the `/` silently becomes `*`, corrupting gold and passing
    every gate (BRD 04 `cfr_pct`, live). A real ratio must contain a `divide`
    somewhere in its chain."""
    by_col = {(o.new_column or o.column): o for o in ops if (o.new_column or o.column)}

    def has_divide(col: str, seen: Set[str]) -> bool:
        op = by_col.get(col)
        if op is None or col in seen:
            return False
        seen.add(col)
        if _norm_op(op.op or "") == "divide":
            return True
        operands = [op.column] + list(getattr(op, "args", None) or [])
        return any(has_divide(str(o), seen) for o in operands if o)

    bad: List[str] = []
    for o in ops:
        name = o.new_column or o.column or ""
        if _RATIO_RE.search(name) and not has_divide(name, set()):
            bad.append(name)
    return bad


def _prune_transform_ops(plan: LogicalPlan) -> List[str]:
    """Drop transform pieces that reference columns the (grounded) source data
    does not have — casts, cleaning ops, filters, dedup keys. One note each.
    Entities without a known schema are left untouched."""
    notes: List[str] = []
    src_by_entity = {s.entity: s for s in plan.sources}
    for t in plan.transforms:
        src = src_by_entity.get(t.entity)
        if src is None or not _entity_columns(src):
            continue
        available = set(_entity_columns(src))
        kept_casts = []
        for c in t.casts:
            if c.name in available:
                kept_casts.append(c)
            else:
                notes.append(
                    f"'{t.entity}': cast of '{c.name}' not built — the source "
                    "data has no such column"
                )
        t.casts = kept_casts
        kept_ops = []
        for op in t.cleaning:
            operands = [op.column] + (
                list(op.args) if _norm_op(op.op) in _OP_ARITH else []
            )
            missing = [
                o for o in operands
                if not _NUMERIC.fullmatch(str(o).strip()) and o not in available
            ]
            if missing:
                notes.append(
                    f"'{t.entity}': {op.op} -> "
                    f"'{op.new_column or op.column}' not built — column(s) "
                    f"{missing} are not in the source data"
                )
                continue
            available.add(op.new_column or op.column)
            kept_ops.append(op)
        t.cleaning = kept_ops
        kept_filters = []
        for f in t.filters:
            if f.column in available:
                kept_filters.append(f)
            else:
                notes.append(
                    f"'{t.entity}': filter on '{f.column}' not built — the "
                    "source data has no such column"
                )
        t.filters = kept_filters
        kept_keys = [k for k in t.dedup_keys if k in available]
        for k in t.dedup_keys:
            if k not in available:
                notes.append(
                    f"'{t.entity}': dedup key '{k}' not built — the source "
                    "data has no such column"
                )
        t.dedup_keys = kept_keys
    return notes


def _salvage_group_by(plan: LogicalPlan) -> List[str]:
    """Drop only the group_by columns an output can't build, keeping the output
    when OTHER group_by columns remain — instead of discarding a whole mart for
    one fabricated key (customer_value lost revenue/order_count over a bogus
    `loyalty_tier`). Outputs whose ENTIRE grouping is unbuildable fall through
    to the whole-output drop, unchanged."""
    notes: List[str] = []
    src_by_entity = {s.entity: s for s in plan.sources}
    xf_by_entity = {t.entity: t for t in plan.transforms}
    for out in plan.outputs:
        known = [src_by_entity[e] for e in out.from_entities if e in src_by_entity]
        if not known or not all(_entity_columns(s) for s in known):
            continue  # ungrounded — cannot prove anything, leave alone
        available: Set[str] = set()
        for s in known:
            available |= _entity_columns(s)
            xf = xf_by_entity.get(s.entity)
            if xf is not None:
                available |= {c.new_column or c.column for c in xf.cleaning}
        available |= {d.new_column or d.column for d in out.derived}
        available |= {a.name for a in out.aggregations}
        available |= {d.new_column or d.column for d in out.post_agg_derived}
        missing = [g for g in out.group_by if g not in available]
        if missing and len(missing) < len(out.group_by):
            out.group_by = [g for g in out.group_by if g in available]
            for g in missing:
                notes.append(
                    f"gold output '{out.name}': group_by column '{g}' not built — "
                    "it isn't in the source data; grouped by the remaining columns"
                )
    return notes


def prune_unbuildable(plan: LogicalPlan, problems: List[str]) -> List[str]:
    """LAST RESORT after repair rounds exhaust: drop the pieces the checker
    can't resolve so the REST of the plan still builds, and record each as a
    'not built' assumption the user can act on in chat.

    Build-don't-ask, reliability over a wrong guess: a transform op or gold
    output that references a column not in the data is REMOVED — not shipped
    with a guessed column and not turned into a question wall that builds
    nothing (BRD1 live run: 8 outputs, 0 built). Returns one note per drop."""
    notes = _prune_transform_ops(plan)
    notes += _salvage_group_by(plan)
    # Transform pruning may remove derived columns outputs depended on — take a
    # fresh problem list, then drop every output that still has a problem.
    bad = {
        m.group(1)
        for p in check(plan)
        for m in [_PRUNE_OUT_RE.search(p)]
        if m
    }
    for o in plan.outputs:
        if o.name in bad:
            notes.append(
                f"gold output '{o.name}' not built: it references a column that "
                "isn't in the source data — add or correct that column in chat "
                "and I'll build it"
            )
    plan.outputs = [o for o in plan.outputs if o.name not in bad]
    # A pipeline that still lists a removed output would re-trigger 'gold
    # output unknown' — drop those references too.
    for pl in plan.pipelines:
        pl.gold = [g for g in pl.gold if g not in bad]
    for n in notes:
        if n not in plan.assumptions:
            plan.assumptions.append(n)
    return notes


# Tokens an LLM reaches for when the BRD named NO real data source and it
# fabricated one anyway (the Pydantic validator forces location fields to be
# present, so "no location" never reaches here — only placeholder values do).
# Conservative on purpose: real sources don't call themselves 'dummy'/'lorem'.
_PLACEHOLDER_RE = re.compile(
    r"(?:^|[\s_./-])(dummy|placeholder|changeme|lorem|ipsum|tbd|xxx+|foobar|"
    r"your[-_](?:table|source|db|database|bucket|file|url))(?:$|[\s_./-])",
    re.I,
)

# Whole-entity names a model coins when the BRD named nothing — matched EXACTLY
# (not as substrings), so a real 'data'/'orders'/'input_records' source is never
# touched, only the bare generic fallbacks no real BRD uses as a source name.
_FABRICATED_ENTITY_NAMES = {
    "input_data", "dummy_data", "sample_data", "your_data", "my_data",
    "test_data", "data_source", "datasource", "source_data", "unknown_source",
    "generic_data", "placeholder_data", "example_data",
}


def _looks_invented(s: LogicalSource) -> bool:
    """True when a source's identifying fields are obvious placeholders — the
    model built a plan from a BRD that pointed at no real data (B1: gibberish
    in must not yield a confident green plan out)."""
    if (s.entity or "").strip().lower() in _FABRICATED_ENTITY_NAMES:
        return True
    idents = [
        s.entity, s.container, s.folder, s.file_name, s.http_url, s.server,
        s.database, s.table_name, s.dataverse_url, s.entity_set,
        s.sharepoint_site, s.sharepoint_list, s.bq_dataset, s.gcp_project,
    ]
    return bool(_PLACEHOLDER_RE.search(" ".join(x for x in idents if x)))


def check(plan: LogicalPlan) -> List[str]:
    """Problems that make the plan inconsistent; empty list = pass."""
    problems: List[str] = []
    src_by_entity: Dict[str, LogicalSource] = {}

    # 1. at least one source.
    if not plan.sources:
        problems.append("no sources: the plan must ingest at least one entity")

    # 1b. a source the model fabricated from a BRD that named no real data —
    #     ask for the real source instead of shipping a confident fiction.
    for s in plan.sources:
        if _looks_invented(s):
            problems.append(
                f"source '{s.entity}' looks invented (placeholder identifiers) — "
                "the BRD names no real data source; provide the actual source "
                "(URL / table / container + file) and its columns"
            )

    # 2. no duplicate entities.
    seen: Set[str] = set()
    for s in plan.sources:
        if s.entity in seen:
            problems.append(f"duplicate source entity '{s.entity}'")
        seen.add(s.entity)
        src_by_entity[s.entity] = s

    # 2b. a source USED by transforms/outputs whose schema could not be verified
    #     against its live catalog (grounding cleared the guessed columns after a
    #     table/list-not-found) — building on invented columns deploys a pipeline
    #     that fails at runtime. Ask for the real coordinates instead of shipping
    #     a fabricated schema. Only for catalog-verifiable formats; a not-yet-
    #     uploaded CSV legitimately has no schema at plan time.
    _VERIFIABLE = {SourceFormat.postgres, SourceFormat.dataverse,
                   SourceFormat.bigquery, SourceFormat.sharepoint}
    used_entities = {t.entity for t in plan.transforms} | {
        e for o in plan.outputs for e in o.from_entities
    }
    for s in plan.sources:
        if s.entity in used_entities and s.format in _VERIFIABLE and not _entity_columns(s):
            problems.append(
                f"source '{s.entity}': its schema could not be verified against the "
                f"real {s.format.value} source — the named table/list was not found; "
                "confirm the exact source name and columns"
            )

    # 3. every transform entity exists.
    for t in plan.transforms:
        if t.entity not in src_by_entity:
            problems.append(f"transform references unknown entity '{t.entity}'")
        elif src_by_entity[t.entity].format == SourceFormat.binary:
            problems.append(
                f"transform references binary entity '{t.entity}' — binary sources "
                "support byte-for-byte Bronze copy only"
            )

    for out in plan.outputs:
        # 4. every from_entities entity exists.
        for e in out.from_entities:
            if e not in src_by_entity:
                problems.append(f"output '{out.name}': unknown entity '{e}'")
            elif src_by_entity[e].format == SourceFormat.binary:
                problems.append(
                    f"output '{out.name}': binary entity '{e}' cannot feed a data flow output"
                )

        # 6. join endpoints are within from_entities. (Key presence/pairing is
        #    enforced by JoinPlan's own validator at parse time.)
        edges = []
        for j in out.joins:
            for side in (j.left_entity, j.right_entity):
                if side not in out.from_entities:
                    problems.append(
                        f"output '{out.name}': join uses '{side}' not in from_entities"
                    )
            edges.append((j.left_entity, j.right_entity))

        # 5. multi-entity outputs must be connected by joins.
        known = [e for e in out.from_entities if e in src_by_entity]
        if len(known) >= 2 and not _connected(known, edges):
            problems.append(
                f"output '{out.name}': entities {known} are not connected by joins"
            )

        # 7. group_by without aggregations.
        if out.group_by and not out.aggregations:
            problems.append(f"output '{out.name}': group_by without aggregations")

        # 8. aggregation name colliding with a group_by column.
        gb = set(out.group_by)
        for a in out.aggregations:
            if a.name in gb:
                problems.append(
                    f"output '{out.name}': aggregation '{a.name}' duplicates a group_by column"
                )

        # 8b. two aggregations with the same op+column are IDENTICAL for every
        # row. The model creates the second to fake a "total across all groups"
        # for a percent-of-total; dividing by it yields a constant (always
        # 100%) that passes every gate. A real cross-group total needs a
        # window/global aggregate this system can't express.
        agg_seen: Dict[tuple, str] = {}
        for a in out.aggregations:
            key = (_norm_op(a.op), a.column)
            if key in agg_seen:
                problems.append(
                    f"output '{out.name}': aggregations '{agg_seen[key]}' and "
                    f"'{a.name}' are identical ({a.op} of '{a.column}') — a "
                    "per-group count cannot stand in for a total across all "
                    "groups (that needs a window/global aggregate, which is "
                    "unsupported); drop one and mark the percent-of-total unsupported"
                )
            else:
                agg_seen[key] = a.name

        # 8c. a ratio/percentage-named derived column with no division in its
        # chain — a '/' folded into a multiply (silent gold corruption).
        for name in _ratio_without_division(list(out.derived) + list(out.post_agg_derived)):
            problems.append(
                f"output '{out.name}': '{name}' looks like a ratio/percentage but "
                "its derivation contains no division — a '/' was likely folded into "
                "a multiply (e.g. `a * 100 * b` instead of `a * 100 / b`); use the "
                "`divide` op (chained through new_column) for the division"
            )

        # 10. top_n without sort.
        if out.top_n is not None and not out.sort:
            problems.append(f"output '{out.name}': top_n without sort — say what 'top' means")

        # 9. column existence for outputs (only when every source entity has a schema).
        known_srcs = [src_by_entity[e] for e in known]
        if known_srcs and all(_entity_columns(s) for s in known_srcs):
            available: Set[str] = set()
            for s in known_srcs:
                available |= _entity_columns(s)
                # Gold reads the SILVER output — every column the entity's
                # transform derives (TenureBand, NetSales, ...) is available.
                # Omitting these flagged correct plans and sent the repair
                # loop chasing a problem that didn't exist.
                xf = next((t for t in plan.transforms if t.entity == s.entity), None)
                if xf is not None:
                    available |= {c.new_column or c.column for c in xf.cleaning}
            available |= {d.new_column or d.column for d in out.derived}
            available |= {a.name for a in out.aggregations}
            available |= {d.new_column or d.column for d in out.post_agg_derived}
            refs: List[tuple] = []
            for j in out.joins:
                refs += [(k, None) for k in j.left_keys + j.right_keys]
            refs += [(g, None) for g in out.group_by]
            refs += [(a.column, None) for a in out.aggregations]
            refs += [(s.column, None) for s in out.sort]
            refs += [(f.column, None) for f in out.filters]
            for col, _ in refs:
                if col not in available:
                    problems.append(
                        f"output '{out.name}': '{col}' is not a column of "
                        f"{known} (has: {sorted(available)})"
                    )

    # 11. Pipeline structure (only when the BRD specified one). Every membership
    #     reference must resolve, invokes must point at declared pipelines, and
    #     every entity + output must be covered so nothing goes unbuilt.
    if plan.pipelines:
        pl_names = {p.name for p in plan.pipelines}
        out_names = {o.name for o in plan.outputs}
        covered_ingest: Set[str] = set()
        covered_silver: Set[str] = set()
        covered_gold: Set[str] = set()
        for p in plan.pipelines:
            for e in p.ingest:
                (covered_ingest.add(e) if e in src_by_entity
                 else problems.append(f"pipeline '{p.name}': ingest entity '{e}' unknown"))
            for e in p.silver:
                (covered_silver.add(e) if e in src_by_entity
                 else problems.append(f"pipeline '{p.name}': silver entity '{e}' unknown"))
            for o in p.gold:
                (covered_gold.add(o) if o in out_names
                 else problems.append(f"pipeline '{p.name}': gold output '{o}' unknown"))
            for child in p.invokes:
                if child not in pl_names:
                    problems.append(f"pipeline '{p.name}': invokes unknown pipeline '{child}'")
        for e in src_by_entity:
            if e not in covered_ingest:
                problems.append(f"entity '{e}' is not ingested by any pipeline")
        for t in plan.transforms:
            if t.entity in src_by_entity and t.entity not in covered_silver:
                problems.append(f"entity '{t.entity}' has a transform but no silver pipeline")
        for o in out_names:
            if o not in covered_gold:
                problems.append(f"output '{o}' is not built by any pipeline")

    # 9b. column existence for transforms (only when the source has a schema).
    for t in plan.transforms:
        src = src_by_entity.get(t.entity)
        if src is None:
            continue
        cols = _entity_columns(src)
        if not cols:
            continue
        available = set(cols)
        # Missing columns are reported ONCE via this set — never added to
        # `available`, which polluted later error messages with hallucinated
        # columns in the "has:" list (BRD1 live run showed birth_date as
        # existing right after flagging it missing).
        reported: Set[str] = set()

        def _flag(name: str) -> None:
            if name not in reported:
                problems.append(
                    f"'{name}' is not a column of '{t.entity}' (has: {sorted(available)})"
                )
                reported.add(name)

        for col in (c.name for c in t.casts):
            if col not in available:
                _flag(col)
            available.add(col)  # the cast's TARGET is available downstream
        # Cleaning ops in order: arithmetic args are operands (columns or
        # numbers), other ops' args are literals; a new_column becomes available
        # to LATER ops (the compiler splits chained ops into sequential
        # transforms).
        for c in t.cleaning:
            operands = [c.column] + (list(c.args) if _norm_op(c.op) in _OP_ARITH else [])
            for operand in operands:
                if _NUMERIC.fullmatch(str(operand).strip()):
                    continue  # numeric literal, not a column
                if operand not in available:
                    _flag(operand)
            # Only a real derivation introduces a NEW name; an in-place op's
            # column is either already available or stays (truthfully) missing.
            if c.new_column:
                available.add(c.new_column)
        for col in [f.column for f in t.filters] + list(t.dedup_keys):
            if col not in available:
                _flag(col)
        for c in t.cleaning:
            problems.extend(_unreachable_case_branches(f"transform '{t.entity}'", c))

    for out in plan.outputs:
        for c in list(out.derived) + list(out.post_agg_derived):
            problems.extend(_unreachable_case_branches(f"output '{out.name}'", c))

    return problems


def _canon(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def align_plan(plan: LogicalPlan) -> List[str]:
    """Deterministically repair UNAMBIGUOUS column-name mismatches in outputs:
    the model derives 'TenureBand' then references 'tenure_band' — same column,
    different casing — and repair rounds churn on it. When exactly one
    available column matches after canonicalization (lowercase, separators
    stripped), rewrite the reference IN PLACE and return one note per fix.
    Ambiguous or no-match names are left for check() to flag."""
    notes: List[str] = []
    src_by_entity = {s.entity: s for s in plan.sources}
    xf_by_entity = {t.entity: t for t in plan.transforms}

    for out in plan.outputs:
        available: Set[str] = set()
        for e in out.from_entities:
            s = src_by_entity.get(e)
            if s is None or not _entity_columns(s):
                available = set()  # ungrounded entity — cannot align safely
                break
            available |= _entity_columns(s)
            xf = xf_by_entity.get(e)
            if xf is not None:
                available |= {c.new_column or c.column for c in xf.cleaning}
        if not available:
            continue
        available |= {d.new_column or d.column for d in out.derived}
        available |= {a.name for a in out.aggregations}
        available |= {d.new_column or d.column for d in out.post_agg_derived}
        by_canon: Dict[str, Set[str]] = {}
        for n in available:
            by_canon.setdefault(_canon(n), set()).add(n)

        def fix(name: str, where: str) -> str:
            if not name or name in available:
                return name
            match = by_canon.get(_canon(name)) or set()
            if len(match) == 1:
                actual = next(iter(match))
                notes.append(
                    f"output '{out.name}': aligned column reference "
                    f"'{name}' -> '{actual}' ({where})"
                )
                return actual
            return name

        for j in out.joins:
            j.left_keys = [fix(k, "join key") for k in j.left_keys]
            j.right_keys = [fix(k, "join key") for k in j.right_keys]
        out.group_by = [fix(g, "group_by") for g in out.group_by]
        for a in out.aggregations:
            a.column = fix(a.column, "aggregation")
        for srt in out.sort:
            srt.column = fix(srt.column, "sort")
        for f in out.filters:
            f.column = fix(f.column, "filter")
        for d in out.post_agg_derived:
            d.column = fix(d.column, "post-aggregation derived")
    return notes


def _branch_matches(op: str, threshold: float, x: float) -> bool:
    key = _norm_op(op)
    return {
        "lt": x < threshold, "le": x <= threshold,
        "gt": x > threshold, "ge": x >= threshold,
        "eq": x == threshold, "ne": x != threshold,
    }.get(key, False)


def _unreachable_case_branches(where: str, c) -> List[str]:
    """Detect case branches that can NEVER match because earlier branches
    already cover every value — e.g. StockStatus [gt 10, le 10, gt 0]: the
    third branch is dead and quantity 0 lands in the wrong bucket. Numeric
    thresholds only (sample-point evaluation, first-match-wins semantics);
    non-numeric branches are skipped."""
    when = list(getattr(c, "when", None) or [])
    if len(when) < 2 or _norm_op(c.op or "") != "case":
        return []
    try:
        thresholds = [float(b.value) for b in when]
    except (TypeError, ValueError):
        return []
    points: Set[float] = set()
    for v in thresholds:
        points.update({v, v - 0.5, v + 0.5})
    points.add(min(thresholds) - 1e9)
    points.add(max(thresholds) + 1e9)
    out: List[str] = []
    for i, b in enumerate(when[1:], start=1):
        reachable = any(
            _branch_matches(b.op, thresholds[i], p)
            and not any(_branch_matches(w.op, thresholds[j], p) for j, w in enumerate(when[:i]))
            for p in points
        )
        if not reachable:
            out.append(
                f"{where}: case on '{c.column}' branch {i + 1} "
                f"({b.op} {b.value} -> {b.then}) can never match — earlier "
                "branches already cover those values; reorder the branches or "
                "adjust the thresholds"
            )
    return out
