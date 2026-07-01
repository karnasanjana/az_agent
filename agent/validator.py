"""Validator: trigger the master pipeline, poll live ADF state, surface results.

v1 policy is FAIL-LOUD: on a failed run we stop and surface the error clearly in
the UI. The Claude self-heal loop (patch failing artifact -> redeploy -> retry,
cap 3) is OPT-IN behind SELF_HEAL=true, so it can be enabled once the real
failure modes in a given tenant are understood.

Per-layer status (Bronze -> Silver -> Gold) and run IDs are streamed back to the
caller via an ``on_update`` callback so the UI can show progress live. MOCK mode
simulates a run without touching Azure.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from agent.builder import DEPLOY_ORDER
from agent.deployer import deploy_object
from config import RETRY_CAP, AzureConfig, mock_mode

_TERMINAL = {"Succeeded", "Failed", "Cancelled"}
_MASTER = "pl_master_pipeline"
_LAYER_ORDER = ["bronze", "silver", "gold"]

UpdateFn = Callable[[Dict[str, Any]], None]


def self_heal_enabled() -> bool:
    return os.environ.get("SELF_HEAL", "").strip().lower() in {"1", "true", "yes", "on"}


def _noop(_: Dict[str, Any]) -> None:
    pass


def _default_params() -> Dict[str, Any]:
    # Every generated pipeline parameter carries a defaultValue, so the master run
    # needs no explicit parameters — passing unknown ones (e.g. report_date) would
    # be rejected by ADF. Rely on the defaults baked into the pipeline.
    return {}


def _empty_layers() -> Dict[str, Dict[str, Any]]:
    return {layer: {"status": "Pending", "run_id": None, "error": None} for layer in _LAYER_ORDER}


# --------------------------------------------------------------------------- #
# Master pipeline name discovery
# --------------------------------------------------------------------------- #


def _master_name(run_dir: str) -> str:
    pl_dir = os.path.join(run_dir, "pipelines")
    if os.path.isdir(pl_dir):
        for fname in sorted(os.listdir(pl_dir)):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(pl_dir, fname), "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            acts = doc["properties"].get("activities", [])
            if acts and all(a.get("type") == "ExecutePipeline" for a in acts):
                return doc["name"]
    return _MASTER


# --------------------------------------------------------------------------- #
# Live status mapping
# --------------------------------------------------------------------------- #


def _layer_status_real(adf, cfg: AzureConfig, run_id: str) -> Dict[str, Dict[str, Any]]:
    now = _dt.datetime.utcnow()
    flt = {
        "lastUpdatedAfter": (now - _dt.timedelta(days=1)).isoformat() + "Z",
        "lastUpdatedBefore": (now + _dt.timedelta(minutes=5)).isoformat() + "Z",
    }
    resp = adf.activity_runs.query_by_pipeline_run(
        cfg.resource_group, cfg.factory_name, run_id, filter_parameters=flt
    )
    layers = _empty_layers()
    for act in resp.value or []:
        name = (act.activity_name or "").lower()
        layer = next((l for l in _LAYER_ORDER if l in name), None)
        if layer is None:
            continue
        child_run_id = None
        if isinstance(act.output, dict):
            child_run_id = act.output.get("pipelineRunId")
        err = None
        if isinstance(act.error, dict) and act.error.get("message"):
            err = act.error.get("message")
        layers[layer] = {"status": act.status, "run_id": child_run_id, "error": err}
    return layers


def _failed_activities(adf, cfg: AzureConfig, run_id: str) -> List[Tuple[str, str]]:
    now = _dt.datetime.utcnow()
    flt = {
        "lastUpdatedAfter": (now - _dt.timedelta(days=1)).isoformat() + "Z",
        "lastUpdatedBefore": (now + _dt.timedelta(minutes=5)).isoformat() + "Z",
    }
    resp = adf.activity_runs.query_by_pipeline_run(
        cfg.resource_group, cfg.factory_name, run_id, filter_parameters=flt
    )
    failures: List[Tuple[str, str]] = []
    for act in resp.value or []:
        if act.status == "Failed":
            msg = act.error.get("message", "") if isinstance(act.error, dict) else ""
            failures.append((act.activity_name, msg))
    return failures


# --------------------------------------------------------------------------- #
# Running the pipeline
# --------------------------------------------------------------------------- #


def _run_real(
    run_dir: str,
    cfg: AzureConfig,
    parameters: Dict[str, Any],
    on_update: UpdateFn,
    poll_seconds: int = 15,
    timeout_seconds: int = 1800,
) -> Dict[str, Any]:
    from config import get_datafactory_client

    adf = get_datafactory_client(cfg)
    master = _master_name(run_dir)
    run = adf.pipelines.create_run(cfg.resource_group, cfg.factory_name, master, parameters=parameters)
    run_id = run.run_id
    on_update({"run_id": run_id, "status": "InProgress", "layers": _empty_layers()})

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        info = adf.pipeline_runs.get(cfg.resource_group, cfg.factory_name, run_id)
        layers = _layer_status_real(adf, cfg, run_id)
        on_update({"run_id": run_id, "status": info.status, "layers": layers})
        if info.status in _TERMINAL:
            result: Dict[str, Any] = {"run_id": run_id, "status": info.status, "layers": layers}
            if info.status != "Succeeded":
                result["failures"] = _failed_activities(adf, cfg, run_id)
                result["error"] = info.message or "; ".join(m for _, m in result["failures"])
            return result
        time.sleep(poll_seconds)

    return {"run_id": run_id, "status": "TimedOut", "layers": _layer_status_real(adf, cfg, run_id)}


def _run_mock(on_update: UpdateFn) -> Dict[str, Any]:
    """Simulate a Bronze->Silver->Gold run (no Azure)."""
    run_id = "mock-" + _dt.datetime.utcnow().strftime("%H%M%S")
    layers = _empty_layers()
    on_update({"run_id": run_id, "status": "InProgress", "layers": dict(layers)})
    for layer in _LAYER_ORDER:
        layers[layer] = {"status": "InProgress", "run_id": f"{run_id}-{layer}", "error": None}
        on_update({"run_id": run_id, "status": "InProgress", "layers": dict(layers)})
        time.sleep(0.4)
        layers[layer] = {"status": "Succeeded", "run_id": f"{run_id}-{layer}", "error": None}
        on_update({"run_id": run_id, "status": "InProgress", "layers": dict(layers)})
    return {"run_id": run_id, "status": "Succeeded", "layers": layers, "mock": True}


# --------------------------------------------------------------------------- #
# Optional self-heal (OFF by default)
# --------------------------------------------------------------------------- #


class HealedArtifact(BaseModel):
    explanation: str = Field(..., description="One-line summary of the fix.")
    properties: Dict[str, Any] = Field(..., description="Corrected ADF 'properties' body.")


_HEAL_PROMPT = """\
You are an Azure Data Factory expert. A single ADF artifact failed at runtime.
Given its current ARM 'properties' JSON and the runtime error, return the
corrected 'properties' body. Preserve names, references, and Managed Identity
auth. Change only what is necessary. Never add keys, SAS tokens, or connection
strings.
"""


def _artifact_inventory(run_dir: str) -> Dict[str, str]:
    inventory: Dict[str, str] = {}
    for category in DEPLOY_ORDER:
        cat_dir = os.path.join(run_dir, category)
        if os.path.isdir(cat_dir):
            for fname in os.listdir(cat_dir):
                if fname.endswith(".json"):
                    inventory[fname[:-5]] = category
    return inventory


def _pick_target(error_message: str, inventory: Dict[str, str]) -> Optional[Tuple[str, str]]:
    for name, category in inventory.items():
        if name and name in error_message:
            return name, category
    for name, category in inventory.items():
        if category == "dataflows":
            return name, category
    return next(iter(inventory.items()), None)


def heal_artifact(run_dir: str, category: str, name: str, error_message: str) -> str:
    from pydantic_ai import Agent

    from config import get_claude_model

    path = os.path.join(run_dir, category, f"{name}.json")
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    agent = Agent(get_claude_model(), output_type=HealedArtifact, system_prompt=_HEAL_PROMPT)
    user_msg = (
        f"Artifact category: {category}\nArtifact name: {name}\n"
        f"Runtime error:\n{error_message}\n\n"
        f"Current properties JSON:\n{json.dumps(doc['properties'], indent=2)}"
    )
    healed = agent.run_sync(user_msg).output
    doc["properties"] = healed.properties
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    return healed.explanation


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def execute(
    run_dir: str,
    cfg: "AzureConfig | None" = None,
    parameters: "Dict[str, Any] | None" = None,
    on_update: "UpdateFn | None" = None,
) -> Dict[str, Any]:
    """Run the master pipeline and report the outcome.

    Default (v1): fail-loud — one run, surface the error. With SELF_HEAL=true and
    a real backend, patch the failing artifact and retry up to RETRY_CAP.
    """
    on_update = on_update or _noop
    parameters = parameters or _default_params()

    if mock_mode():
        report = _run_mock(on_update)
        return {"status": report["status"], "attempts": [report]}

    cfg = cfg or AzureConfig.from_env()

    # Fail-loud single attempt (v1 default).
    if not self_heal_enabled():
        report = _run_real(run_dir, cfg, parameters, on_update)
        return {"status": report["status"], "attempts": [report]}

    # Opt-in self-heal loop.
    inventory = _artifact_inventory(run_dir)
    attempts: List[Dict[str, Any]] = []
    for attempt in range(1, RETRY_CAP + 1):
        report = _run_real(run_dir, cfg, parameters, on_update)
        report["attempt"] = attempt
        if report["status"] == "Succeeded":
            attempts.append(report)
            return {"status": "Succeeded", "attempts": attempts}

        error_blob = report.get("error") or "; ".join(m for _, m in report.get("failures", []))
        target = _pick_target(error_blob or "", inventory)
        if target is None or attempt == RETRY_CAP:
            report["healed"] = None
            attempts.append(report)
            break
        name, category = target
        explanation = heal_artifact(run_dir, category, name, error_blob or report["status"])
        deploy_object(run_dir, category, name, cfg)
        report["healed"] = {"category": category, "name": name, "fix": explanation}
        attempts.append(report)

    return {"status": "Failed", "attempts": attempts}
