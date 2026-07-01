"""Visual pipeline graph: Bronze -> Silver -> Gold nodes with dependsOn edges.

Nodes are the medallion layers (Bronze = Copy Activity, Silver/Gold = Mapping
Data Flow). Edges come from the master pipeline's dependsOn chain, plus each
node's source/sink datasets. Each node embeds its JSON (and, for Silver/Gold, its
script) so the UI can show detail on click without another round-trip.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from agent.review import (
    BRONZE_LABEL,
    find_bronze_copy,
    load_category,
    load_script,
    load_spec,
)
from models.spec import MedallionLayer, PipelineSpec


def _layer_of_pipeline(spec: PipelineSpec, pipeline_name: str) -> Optional[Tuple[str, str]]:
    """Resolve an invoked pipeline to (layer, underlying_object_name)."""
    pl = next((p for p in spec.pipelines if p.name == pipeline_name), None)
    if pl is None:
        return None
    for act in pl.activities:
        if act.type == "Copy":
            return "bronze", pl.name
        if act.type == "ExecuteDataFlow":
            df = next((d for d in spec.dataflows if d.name == act.data_flow), None)
            if df is not None:
                return df.layer.value, df.name
    return None


def _master_pipeline(spec: PipelineSpec):
    """The master is the pipeline whose activities are all ExecutePipeline."""
    for pl in spec.pipelines:
        if pl.activities and all(a.type == "ExecutePipeline" for a in pl.activities):
            return pl
    return None


def graph(run_id: str, root: str = "artifacts") -> Dict[str, Any]:
    run_dir = os.path.join(root, run_id)
    spec = load_spec(run_dir)

    pipelines_json = load_category(run_dir, "pipelines")
    dataflows_json = load_category(run_dir, "dataflows")

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    layer_to_node: Dict[str, str] = {}

    # --- Bronze node (Copy Activity, no script) ----------------------------- #
    bronze_pl, bronze_act = find_bronze_copy(spec)
    if bronze_act is not None:
        copy_json = None
        for act in pipelines_json.get(bronze_pl, {}).get("activities", []):
            if act.get("name") == bronze_act.name:
                copy_json = act
        node_id = "bronze"
        layer_to_node["bronze"] = node_id
        nodes.append(
            {
                "id": node_id,
                "layer": "bronze",
                "label": "BRONZE",
                "kind": "Copy Activity",
                "note": BRONZE_LABEL,
                "object": bronze_pl,
                "source_dataset": bronze_act.source_dataset,
                "sink_dataset": bronze_act.sink_dataset,
                "json": copy_json,
                "script": None,  # Bronze has no transformation
            }
        )

    # --- Silver / Gold nodes (Mapping Data Flow + script) ------------------- #
    for df in spec.dataflows:
        node_id = df.layer.value
        layer_to_node[df.layer.value] = node_id
        nodes.append(
            {
                "id": node_id,
                "layer": df.layer.value,
                "label": df.layer.value.upper(),
                "kind": "Mapping Data Flow",
                "note": f"{len(df.transforms)} transformations",
                "object": df.name,
                "source_dataset": df.source.dataset,
                "sink_dataset": df.sink.dataset,
                "json": dataflows_json.get(df.name),
                "script": load_script(run_dir, df.name),
            }
        )

    # --- Edges from the master pipeline dependsOn chain --------------------- #
    master = _master_pipeline(spec)
    if master is not None:
        act_layer: Dict[str, str] = {}
        for act in master.activities:
            resolved = _layer_of_pipeline(spec, act.invoked_pipeline)
            if resolved:
                act_layer[act.name] = resolved[0]
        for act in master.activities:
            to_layer = act_layer.get(act.name)
            for dep in act.depends_on:
                from_layer = act_layer.get(dep)
                if from_layer and to_layer and from_layer in layer_to_node and to_layer in layer_to_node:
                    edges.append(
                        {
                            "from": layer_to_node[from_layer],
                            "to": layer_to_node[to_layer],
                            "condition": "Succeeded",
                        }
                    )
    else:
        # No master: fall back to the canonical medallion order among present layers.
        order = [l for l in ("bronze", "silver", "gold") if l in layer_to_node]
        for a, b in zip(order, order[1:]):
            edges.append({"from": layer_to_node[a], "to": layer_to_node[b], "condition": "Succeeded"})

    return {
        "run_id": run_id,
        "master_pipeline": master.name if master else None,
        "nodes": nodes,
        "edges": edges,
    }
