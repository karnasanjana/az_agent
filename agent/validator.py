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


def _pending_steps(run_dir: str) -> List[Dict[str, Any]]:
    """One Pending entry per activity of the pipeline that will run, in declared
    order — the generic (non-medallion) progress view the UI renders."""
    docs = _load_pipelines(run_dir)
    props = docs.get(_master_name(run_dir), {})
    return [
        {"name": a.get("name"), "status": "Pending", "run_id": None, "error": None}
        for a in props.get("activities", [])
    ]


def _steps_to_layers(steps: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Back-compat medallion view: map steps whose names mention a layer."""
    layers = _empty_layers()
    for step in steps:
        name = (step.get("name") or "").lower()
        layer = next((l for l in _LAYER_ORDER if l in name), None)
        if layer:
            layers[layer] = {
                "status": step["status"],
                "run_id": step.get("run_id"),
                "error": step.get("error"),
            }
    return layers


# --------------------------------------------------------------------------- #
# Master pipeline name discovery
# --------------------------------------------------------------------------- #


def _load_pipelines(run_dir: str) -> Dict[str, Dict[str, Any]]:
    pl_dir = os.path.join(run_dir, "pipelines")
    docs: Dict[str, Dict[str, Any]] = {}
    if os.path.isdir(pl_dir):
        for fname in sorted(os.listdir(pl_dir)):
            if fname.endswith(".json"):
                with open(os.path.join(pl_dir, fname), "r", encoding="utf-8") as fh:
                    doc = json.load(fh)
                docs[doc["name"]] = doc["properties"]
    return docs


def _master_name(run_dir: str) -> str:
    """The pipeline to run: the all-ExecutePipeline master when one exists,
    otherwise a ROOT pipeline (one no other pipeline invokes) — covers copy-only
    and single-pipeline specs that have no master at all."""
    docs = _load_pipelines(run_dir)
    for name, props in docs.items():
        acts = props.get("activities", [])
        if acts and all(a.get("type") == "ExecutePipeline" for a in acts):
            return name
    invoked = set()
    for props in docs.values():
        for act in props.get("activities", []):
            if act.get("type") == "ExecutePipeline":
                ref = act.get("typeProperties", {}).get("pipeline", {}).get("referenceName")
                if ref:
                    invoked.add(ref)
    roots = [n for n in docs if n not in invoked]
    if roots:
        return roots[0]
    return next(iter(docs), _MASTER)


# --------------------------------------------------------------------------- #
# Live status mapping
# --------------------------------------------------------------------------- #


def _step_status_real(
    adf, cfg: AzureConfig, run_id: str, pending: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Live status for every top-level activity of the running pipeline. Activities
    ADF hasn't scheduled yet stay Pending (from the declared activity list)."""
    now = _dt.datetime.utcnow()
    flt = {
        "lastUpdatedAfter": (now - _dt.timedelta(days=1)).isoformat() + "Z",
        "lastUpdatedBefore": (now + _dt.timedelta(minutes=5)).isoformat() + "Z",
    }
    resp = adf.activity_runs.query_by_pipeline_run(
        cfg.resource_group, cfg.factory_name, run_id, filter_parameters=flt
    )
    steps = {s["name"]: dict(s) for s in pending}
    for act in resp.value or []:
        child_run_id = None
        if isinstance(act.output, dict):
            child_run_id = act.output.get("pipelineRunId")
        err = None
        if isinstance(act.error, dict) and act.error.get("message"):
            err = act.error.get("message")
        steps[act.activity_name] = {
            "name": act.activity_name,
            "status": act.status,
            "run_id": child_run_id,
            "error": err,
        }
    # Preserve declared order; append any activity ADF reports that we didn't declare.
    ordered = [steps[s["name"]] for s in pending if s["name"] in steps]
    ordered += [v for k, v in steps.items() if k not in {s["name"] for s in pending}]
    return ordered


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
    pending = _pending_steps(run_dir)
    run = adf.pipelines.create_run(cfg.resource_group, cfg.factory_name, master, parameters=parameters)
    run_id = run.run_id
    on_update({"run_id": run_id, "status": "InProgress", "steps": pending,
               "layers": _steps_to_layers(pending)})

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        info = adf.pipeline_runs.get(cfg.resource_group, cfg.factory_name, run_id)
        steps = _step_status_real(adf, cfg, run_id, pending)
        layers = _steps_to_layers(steps)
        on_update({"run_id": run_id, "status": info.status, "steps": steps, "layers": layers})
        if info.status in _TERMINAL:
            result: Dict[str, Any] = {
                "run_id": run_id, "status": info.status, "steps": steps, "layers": layers,
            }
            if info.status != "Succeeded":
                result["failures"] = _failed_activities(adf, cfg, run_id)
                result["error"] = info.message or "; ".join(m for _, m in result["failures"])
            return result
        time.sleep(poll_seconds)

    steps = _step_status_real(adf, cfg, run_id, pending)
    return {"run_id": run_id, "status": "TimedOut", "steps": steps,
            "layers": _steps_to_layers(steps)}


def _run_mock(run_dir: str, on_update: UpdateFn) -> Dict[str, Any]:
    """Simulate the run step-by-step (no Azure)."""
    run_id = "mock-" + _dt.datetime.utcnow().strftime("%H%M%S")
    steps = _pending_steps(run_dir) or [
        {"name": l.capitalize(), "status": "Pending", "run_id": None, "error": None}
        for l in _LAYER_ORDER
    ]

    def emit(status: str) -> None:
        on_update({"run_id": run_id, "status": status,
                   "steps": [dict(s) for s in steps], "layers": _steps_to_layers(steps)})

    emit("InProgress")
    for step in steps:
        step.update(status="InProgress", run_id=f"{run_id}-{step['name']}")
        emit("InProgress")
        time.sleep(0.4)
        step.update(status="Succeeded")
        emit("InProgress")
    return {"run_id": run_id, "status": "Succeeded", "steps": steps,
            "layers": _steps_to_layers(steps), "mock": True}


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


def _log_heal(run_dir: str, record: Dict[str, Any]) -> None:
    """Append a full audit record to <run_dir>/heals.json so every self-heal is
    inspectable after the fact: what failed, what the model changed, and why."""
    path = os.path.join(run_dir, "heals.json")
    records: List[Dict[str, Any]] = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                records = json.load(fh)
        except Exception:  # noqa: BLE001 — corrupt log never blocks a heal
            records = []
    records.append(record)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)


def read_heal_log(run_dir: str) -> List[Dict[str, Any]]:
    path = os.path.join(run_dir, "heals.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return []


def heal_artifact(
    run_dir: str, category: str, name: str, error_message: str, phase: str = "runtime"
) -> str:
    from pydantic_ai import Agent

    from config import get_model, structured_output

    path = os.path.join(run_dir, category, f"{name}.json")
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    before = doc["properties"]

    agent = Agent(
        get_model(), output_type=structured_output(HealedArtifact), system_prompt=_HEAL_PROMPT
    )
    user_msg = (
        f"Artifact category: {category}\nArtifact name: {name}\n"
        f"Runtime error:\n{error_message}\n\n"
        f"Current properties JSON:\n{json.dumps(before, indent=2)}"
    )
    healed = agent.run_sync(user_msg).output
    doc["properties"] = healed.properties
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)

    _log_heal(
        run_dir,
        {
            "time": _dt.datetime.utcnow().isoformat() + "Z",
            "phase": phase,  # 'deploy' (create_or_update rejected) or 'runtime' (run failed)
            "category": category,
            "name": name,
            "error": error_message,
            "fix": healed.explanation,
            "before": before,
            "after": healed.properties,
        },
    )
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
        report = _run_mock(run_dir, on_update)
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
