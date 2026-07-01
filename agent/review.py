"""Review rendering: all three medallion layers for human approval.

Bronze is rendered as its Copy Activity JSON labelled "raw landing, no
transformation" — there is intentionally NO script section (its absence is
correct). Silver and Gold are rendered as their Mapping Data Flow JSON plus the
generated script. Everything is read back from artifacts/<run_id>/ so the review
shows exactly what will be deployed.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from agent.builder import DEPLOY_ORDER
from models.spec import MedallionLayer, PipelineSpec

BRONZE_LABEL = "raw landing, no transformation"


# --------------------------------------------------------------------------- #
# Loading helpers (shared by review / preflight / graph)
# --------------------------------------------------------------------------- #


def load_spec(run_dir: str) -> PipelineSpec:
    with open(os.path.join(run_dir, "spec.json"), "r", encoding="utf-8") as fh:
        return PipelineSpec.model_validate_json(fh.read())


def load_category(run_dir: str, category: str) -> Dict[str, Dict[str, Any]]:
    cat_dir = os.path.join(run_dir, category)
    objects: Dict[str, Dict[str, Any]] = {}
    if not os.path.isdir(cat_dir):
        return objects
    for fname in sorted(os.listdir(cat_dir)):
        if fname.endswith(".json"):
            with open(os.path.join(cat_dir, fname), "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            objects[doc["name"]] = doc["properties"]
    return objects


def load_script(run_dir: str, dataflow_name: str) -> str:
    path = os.path.join(run_dir, "dataflows", f"{dataflow_name}.script")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    return ""


def find_bronze_copy(spec: PipelineSpec):
    """Return (pipeline_name, copy_activity_obj) for the Bronze Copy activity."""
    # Prefer an explicit bronze-layer Copy; fall back to any Copy.
    for pl in spec.pipelines:
        for act in pl.activities:
            if act.type == "Copy" and act.layer == MedallionLayer.bronze:
                return pl.name, act
    for pl in spec.pipelines:
        for act in pl.activities:
            if act.type == "Copy":
                return pl.name, act
    return None, None


def _copy_activity_json(run_dir: str, pipeline_name: str, activity_name: str) -> Optional[Dict[str, Any]]:
    props = load_category(run_dir, "pipelines").get(pipeline_name)
    if not props:
        return None
    for act in props.get("activities", []):
        if act.get("name") == activity_name:
            return act
    return None


# --------------------------------------------------------------------------- #
# Structured review
# --------------------------------------------------------------------------- #


def render(run_id: str, root: str = "artifacts") -> Dict[str, Any]:
    run_dir = os.path.join(root, run_id)
    spec = load_spec(run_dir)

    pipelines_json = load_category(run_dir, "pipelines")
    dataflows_json = load_category(run_dir, "dataflows")

    # Bronze layer: Copy Activity only, no script.
    bronze_pl, bronze_act = find_bronze_copy(spec)
    bronze_block: Optional[Dict[str, Any]] = None
    if bronze_pl and bronze_act:
        bronze_block = {
            "label": BRONZE_LABEL,
            "pipeline": bronze_pl,
            "activity": bronze_act.name,
            "source_dataset": bronze_act.source_dataset,
            "sink_dataset": bronze_act.sink_dataset,
            "copy_activity": _copy_activity_json(run_dir, bronze_pl, bronze_act.name),
            "script": None,  # intentional: Bronze has no transformation
        }

    # Silver / Gold layers: data flow JSON + script.
    layer_blocks: Dict[str, Any] = {}
    for df in spec.dataflows:
        layer_blocks[df.layer.value] = {
            "dataflow": df.name,
            "json": dataflows_json.get(df.name),
            "script": load_script(run_dir, df.name),
            "source_dataset": df.source.dataset,
            "sink_dataset": df.sink.dataset,
        }

    def _flatten(category: str) -> List[Dict[str, Any]]:
        return [{"name": n, "json": p} for n, p in load_category(run_dir, category).items()]

    return {
        "run_id": run_id,
        "spec_name": spec.name,
        "layers": {
            "bronze": bronze_block,
            "silver": layer_blocks.get("silver"),
            "gold": layer_blocks.get("gold"),
        },
        "linked_services": _flatten("linkedServices"),
        "datasets": _flatten("datasets"),
        "dataflows": _flatten("dataflows"),
        "pipelines": [{"name": n, "json": p} for n, p in pipelines_json.items()],
        "triggers": _flatten("triggers"),
    }


# --------------------------------------------------------------------------- #
# Plain-text review (for terminals / logs)
# --------------------------------------------------------------------------- #


def render_text(run_id: str, root: str = "artifacts") -> str:
    data = render(run_id, root)
    out: List[str] = []

    def rule(title: str) -> None:
        out.append("\n" + "=" * 76)
        out.append(title)
        out.append("=" * 76)

    rule(f"REVIEW — {data['spec_name']}  (run {run_id})")

    bronze = data["layers"]["bronze"]
    rule("BRONZE — Copy Activity (raw landing, no transformation)")
    if bronze:
        out.append(f"pipeline: {bronze['pipeline']}   activity: {bronze['activity']}")
        out.append(f"source: {bronze['source_dataset']}  ->  sink: {bronze['sink_dataset']}")
        out.append("(no script section — Bronze performs no transformation)")
        out.append(json.dumps(bronze["copy_activity"], indent=2))
    else:
        out.append("MISSING — no Bronze Copy Activity found.")

    for layer in ("silver", "gold"):
        block = data["layers"].get(layer)
        rule(f"{layer.upper()} — Mapping Data Flow")
        if block:
            out.append(f"data flow: {block['dataflow']}")
            out.append(f"source: {block['source_dataset']}  ->  sink: {block['sink_dataset']}")
            out.append("\n-- script --")
            out.append(block["script"])
        else:
            out.append(f"MISSING — no {layer} data flow found.")

    rule("PIPELINES")
    for pl in data["pipelines"]:
        out.append(f"\n# {pl['name']}")
        out.append(json.dumps(pl["json"], indent=2))

    return "\n".join(out)
