"""Visual pipeline graph: one node per execution step, edges from dependsOn.

For a medallion spec the nodes are the familiar Bronze -> Silver -> Gold layers
(ids "bronze"/"silver"/"gold" so the UI can color them). For any other shape the
nodes are the pipeline's actual steps (Copy activities, data flows, invoked
pipelines) in dependency order. Each node embeds its deployable JSON (and, for
data flows, the script) so the UI can show detail on click without another
round-trip.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from agent.review import (
    BRONZE_LABEL,
    load_category,
    load_script,
    load_spec,
)
from models.spec import PipelineSpec


def _master_pipeline(spec: PipelineSpec):
    """The master is the pipeline whose activities are all ExecutePipeline."""
    for pl in spec.pipelines:
        if pl.activities and all(a.type == "ExecutePipeline" for a in pl.activities):
            return pl
    return None


def _activity_json(pipelines_json: Dict[str, Any], pipeline: str, activity: str):
    for act in pipelines_json.get(pipeline, {}).get("activities", []):
        if act.get("name") == activity:
            return act
    return None


def _copy_node(pipelines_json, pl, act, node_id: str, label: str, layer: Optional[str]):
    return {
        "id": node_id,
        "layer": layer,
        "label": label,
        "kind": "Copy Activity",
        "note": BRONZE_LABEL if layer == "bronze" else "copy, no transformation",
        "object": pl.name,
        "source_dataset": act.source_dataset,
        "sink_dataset": act.sink_dataset,
        "json": _activity_json(pipelines_json, pl.name, act.name),
        "script": None,
    }


def _flow_node(run_dir: str, dataflows_json, df, node_id: str, label: str):
    return {
        "id": node_id,
        "layer": df.layer.value if df.layer else None,
        "label": label,
        "kind": "Mapping Data Flow",
        "note": f"{len(df.transforms)} transformations",
        "object": df.name,
        "source_dataset": df.source.dataset,
        "sink_dataset": df.sink.dataset,
        "json": dataflows_json.get(df.name),
        "script": load_script(run_dir, df.name),
    }


def _child_step(spec: PipelineSpec, run_dir: str, pipelines_json, dataflows_json, pipeline_name: str):
    """Resolve an invoked child pipeline to its representative node payload
    (its Copy activity or its data flow). Returns None when unresolvable."""
    pl = next((p for p in spec.pipelines if p.name == pipeline_name), None)
    if pl is None:
        return None
    for act in pl.activities:
        if act.type == "Copy":
            layer = act.layer.value if act.layer else None
            node_id = layer or pl.name
            label = layer.upper() if layer else pl.name
            return _copy_node(pipelines_json, pl, act, node_id, label, layer)
        if act.type == "ExecuteDataFlow":
            df = next((d for d in spec.dataflows if d.name == act.data_flow), None)
            if df is not None:
                layer = df.layer.value if df.layer else None
                node_id = layer or df.name
                label = layer.upper() if layer else df.name
                return _flow_node(run_dir, dataflows_json, df, node_id, label)
    return None


def graph(run_id: str, root: str = "artifacts") -> Dict[str, Any]:
    run_dir = os.path.join(root, run_id)
    spec = load_spec(run_dir)

    pipelines_json = load_category(run_dir, "pipelines")
    dataflows_json = load_category(run_dir, "dataflows")

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen: set = set()

    master = _master_pipeline(spec)
    if master is not None:
        # One node per LAYER (many ingest/silver/gold activities collapse to
        # bronze/silver/gold). act_to_node maps EVERY activity to its layer node —
        # including the deduped ones — so a dependsOn pointing at, say,
        # run_silver_orders (deduped) still resolves and the silver->gold edge is
        # not lost. Mapping only the first-seen activity per layer dropped exactly
        # that edge, leaving gold with no incoming edge (rendered out of order).
        act_to_node: Dict[str, str] = {}
        for act in master.activities:
            node = _child_step(spec, run_dir, pipelines_json, dataflows_json, act.invoked_pipeline)
            if node is None:
                continue
            act_to_node[act.name] = node["id"]
            if node["id"] in seen:
                continue
            seen.add(node["id"])
            nodes.append(node)
        seen_edges: set = set()
        for act in master.activities:
            to_id = act_to_node.get(act.name)
            for dep in act.depends_on:
                from_id = act_to_node.get(dep)
                # Skip self-loops (two activities of the same layer) and duplicates
                # that the layer collapse would otherwise produce.
                if from_id and to_id and from_id != to_id and (from_id, to_id) not in seen_edges:
                    seen_edges.add((from_id, to_id))
                    edges.append({"from": from_id, "to": to_id, "condition": "Succeeded"})
    else:
        # No master: one node per activity across the (usually single) pipeline(s).
        act_to_node = {}
        for pl in spec.pipelines:
            for act in pl.activities:
                node = None
                if act.type == "Copy":
                    layer = act.layer.value if act.layer else None
                    node_id = layer or act.name
                    label = layer.upper() if layer else act.name
                    node = _copy_node(pipelines_json, pl, act, node_id, label, layer)
                elif act.type == "ExecuteDataFlow":
                    df = next((d for d in spec.dataflows if d.name == act.data_flow), None)
                    if df is not None:
                        layer = df.layer.value if df.layer else None
                        node_id = layer or df.name
                        label = layer.upper() if layer else df.name
                        node = _flow_node(run_dir, dataflows_json, df, node_id, label)
                if node is None or node["id"] in seen:
                    continue
                seen.add(node["id"])
                act_to_node[act.name] = node["id"]
                nodes.append(node)
            for act in pl.activities:
                to_id = act_to_node.get(act.name)
                for dep in act.depends_on:
                    from_id = act_to_node.get(dep)
                    if from_id and to_id:
                        edges.append({"from": from_id, "to": to_id, "condition": "Succeeded"})

    # Medallion fallback: layered nodes but no explicit dependencies -> canonical order.
    if not edges:
        by_id = {n["id"]: n for n in nodes}
        order = [l for l in ("bronze", "silver", "gold") if l in by_id]
        for a, b in zip(order, order[1:]):
            edges.append({"from": a, "to": b, "condition": "Succeeded"})

    return {
        "run_id": run_id,
        "master_pipeline": master.name if master else None,
        "nodes": nodes,
        "edges": edges,
    }
