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

from models.logical import LogicalPlan, LogicalSource, OutputPlan
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


def check(plan: LogicalPlan) -> List[str]:
    """Problems that make the plan inconsistent; empty list = pass."""
    problems: List[str] = []
    src_by_entity: Dict[str, LogicalSource] = {}

    # 1. at least one source.
    if not plan.sources:
        problems.append("no sources: the plan must ingest at least one entity")

    # 2. no duplicate entities.
    seen: Set[str] = set()
    for s in plan.sources:
        if s.entity in seen:
            problems.append(f"duplicate source entity '{s.entity}'")
        seen.add(s.entity)
        src_by_entity[s.entity] = s

    # 3. every transform entity exists.
    for t in plan.transforms:
        if t.entity not in src_by_entity:
            problems.append(f"transform references unknown entity '{t.entity}'")

    for out in plan.outputs:
        # 4. every from_entities entity exists.
        for e in out.from_entities:
            if e not in src_by_entity:
                problems.append(f"output '{out.name}': unknown entity '{e}'")

        # 6. join endpoints are within from_entities.
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

        # 10. top_n without sort.
        if out.top_n is not None and not out.sort:
            problems.append(f"output '{out.name}': top_n without sort — say what 'top' means")

        # 9. column existence for outputs (only when every source entity has a schema).
        known_srcs = [src_by_entity[e] for e in known]
        if known_srcs and all(_entity_columns(s) for s in known_srcs):
            available: Set[str] = set()
            for s in known_srcs:
                available |= _entity_columns(s)
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
        for col in (c.name for c in t.casts):
            if col not in available:
                problems.append(
                    f"'{col}' is not a column of '{t.entity}' (has: {sorted(available)})"
                )
            available.add(col)
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
                    problems.append(
                        f"'{operand}' is not a column of '{t.entity}' "
                        f"(has: {sorted(available)})"
                    )
                    available.add(operand)  # report once
            available.add(c.new_column or c.column)
        for col in [f.column for f in t.filters] + list(t.dedup_keys):
            if col not in available:
                problems.append(
                    f"'{col}' is not a column of '{t.entity}' (has: {sorted(available)})"
                )
                available.add(col)

    return problems
