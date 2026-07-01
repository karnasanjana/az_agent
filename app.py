"""FastAPI orchestration + UI for the BRD -> ADF medallion agent.

Endpoints
---------
POST /plan           BRD (text, .txt/.md, or PDF upload) -> parse + build +
                     pre-flight. Returns run_id, summary, preflight, clarifications,
                     review, graph, and the human-readable governance plan. No
                     Azure writes.
POST /chat           Continue the conversation for a run: answer the agent's
                     clarifying questions or request small changes. Re-parses with
                     full memory, rebuilds, re-runs pre-flight, returns the updated
                     review/graph/plan. No Azure writes.
GET  /preview/{id}        review JSON.
GET  /preview/{id}/text   plain-text governance plan (the approval-gate artifact).
GET  /graph/{id}          graph JSON.
POST /approve        Requires a prior preview AND a passing pre-flight, THEN
                     connects to Azure (or the MOCK tenant), builds all objects,
                     and runs the master pipeline.
GET  /status/{id}    Live deploy + Bronze->Silver->Gold run state + run IDs + errors.
GET  /               The single-page UI.

The single agent reasons in a few tight places — parsing the BRD (/plan), refining
it on request (/chat), and (behind SELF_HEAL) self-healing a failed artifact
(/approve). Every reasoning step returns a validated PipelineSpec.
"""

from __future__ import annotations

import os
import shutil
import uuid
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from agent import builder, graph, preflight, review
from config import mock_mode
from models.spec import PipelineSpec
from ui import INDEX_HTML

app = FastAPI(title="BRD -> ADF Medallion Agent")

# In-memory run store (swap for a DB in production).
_RUNS: Dict[str, Dict[str, Any]] = {}


class ApproveRequest(BaseModel):
    run_id: str


class ChatRequest(BaseModel):
    run_id: str
    message: str


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "mock": mock_mode()}


# --------------------------------------------------------------------------- #
# /plan — parse + build + pre-flight (NO Azure writes)
# --------------------------------------------------------------------------- #


def _summary(spec: PipelineSpec) -> Dict[str, Any]:
    return {
        "name": spec.name,
        "source": spec.source.model_dump() if spec.source else None,
        "linked_services": [ls.name for ls in spec.linked_services],
        "datasets": [ds.name for ds in spec.datasets],
        "dataflows": [df.name for df in spec.dataflows],
        "pipelines": [pl.name for pl in spec.pipelines],
        "triggers": [tr.name for tr in spec.triggers],
    }


def _store_and_respond(
    run_id: str, spec: PipelineSpec, messages: Any
) -> Dict[str, Any]:
    """Persist conversation state and build the /plan|/chat response payload.

    If the spec is incomplete the agent returns ``clarifications`` instead of
    inventing components — we surface those as questions and keep the run open so
    the user can answer them over /chat.
    """
    if spec.clarifications:
        prev = _RUNS.get(run_id, {})
        _RUNS[run_id] = {
            **prev,
            "status": "NEEDS_CLARIFICATION",
            "clarifications": spec.clarifications,
            "messages": messages,
            # Drop any stale build — the spec isn't complete yet.
            "spec": spec.model_dump(),
            "previewed": False,
        }
        _RUNS[run_id].pop("run_dir", None)
        return {
            "run_id": run_id,
            "status": "NEEDS_CLARIFICATION",
            "clarifications": spec.clarifications,
            "mock": mock_mode(),
        }

    # Rebuild from a clean directory so renamed/removed objects don't linger.
    run_dir = builder.artifacts_dir(run_id)
    if os.path.isdir(run_dir):
        shutil.rmtree(run_dir, ignore_errors=True)
    try:
        run_dir = builder.write_artifacts(spec, run_id)
        pf = preflight.validate(run_id)
    except Exception as exc:  # build error -> clean message, not a raw 500
        raise HTTPException(
            status_code=502, detail=f"Could not build pipelines from the spec: {exc}"
        ) from exc
    _RUNS[run_id] = {
        "status": "AWAITING_APPROVAL" if pf["passed"] else "PREFLIGHT_FAILED",
        "run_dir": run_dir,
        "spec": spec.model_dump(),
        "messages": messages,
        "preflight": pf,
        "previewed": True,  # the response carries the full review
        "mock": mock_mode(),
    }
    return {
        "run_id": run_id,
        "status": _RUNS[run_id]["status"],
        "mock": mock_mode(),
        "summary": _summary(spec),
        "preflight": pf,
        "clarifications": [],
        "review": review.render(run_id),
        "graph": graph.graph(run_id),
        "plan_text": review.render_text(run_id),
    }


@app.post("/plan")
async def plan(
    brd: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
) -> Dict[str, Any]:
    from agent.ingest import extract_brd_text
    from agent.parser import parse_brd  # lazy: only /plan needs Foundry

    text = (brd or "").strip()
    if file is not None:
        data = await file.read()
        if data:
            try:
                text = extract_brd_text(file.filename or "", data)
            except RuntimeError as exc:  # unreadable PDF / missing pypdf
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not text:
        raise HTTPException(status_code=422, detail="Provide BRD text or upload a file.")

    run_id = uuid.uuid4().hex[:12]
    try:
        spec, messages = await parse_brd(text)
    except RuntimeError as exc:  # missing Foundry config
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # parse / model error — surface, don't 500
        raise HTTPException(status_code=502, detail=f"BRD parse failed: {exc}") from exc

    return _store_and_respond(run_id, spec, messages)


@app.post("/chat")
async def chat(req: ChatRequest) -> Dict[str, Any]:
    """Refine an existing run: answer the agent's questions or request changes."""
    from agent.parser import refine_spec

    run = _RUNS.get(req.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    if "messages" not in run:
        raise HTTPException(status_code=409, detail="This run has no conversation to continue.")
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="Type a change or an answer.")

    try:
        spec, messages = await refine_spec(message, run["messages"])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Refine failed: {exc}") from exc

    return _store_and_respond(req.run_id, spec, messages)


# --------------------------------------------------------------------------- #
# Preview / graph (read-only)
# --------------------------------------------------------------------------- #


def _require_built(run_id: str) -> Dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    if "run_dir" not in run:
        raise HTTPException(status_code=409, detail=f"Run is '{run['status']}'")
    return run


@app.get("/preview/{run_id}")
def preview(run_id: str) -> Dict[str, Any]:
    run = _require_built(run_id)
    run["previewed"] = True
    return {"run_id": run_id, "preflight": run["preflight"], "review": review.render(run_id)}


@app.get("/preview/{run_id}/text", response_class=PlainTextResponse)
def preview_text(run_id: str) -> str:
    _require_built(run_id)
    return review.render_text(run_id)


@app.get("/graph/{run_id}")
def graph_view(run_id: str) -> Dict[str, Any]:
    _require_built(run_id)
    return graph.graph(run_id)


# --------------------------------------------------------------------------- #
# /approve — the gate: deploy + run (Azure or MOCK)
# --------------------------------------------------------------------------- #


def _deploy_and_run(run_id: str) -> None:
    from agent.deployer import deploy_artifacts, provision_containers
    from agent.validator import execute

    run = _RUNS[run_id]
    spec = PipelineSpec.model_validate(run["spec"])
    containers = (spec.storage.containers if spec.storage else None) or ["bronze", "silver", "gold"]

    # Live run state the UI polls.
    run["run"] = {"status": "Pending", "run_id": None, "layers": None}

    def on_update(rec: Dict[str, Any]) -> None:
        run["run"] = rec

    heals: list = []
    try:
        run["status"] = "PROVISIONING"
        run["containers_created"] = provision_containers(containers)

        run["status"] = "DEPLOYING"
        run["deployed"] = deploy_artifacts(run["run_dir"])
        heals += list(getattr(deploy_artifacts, "last_heals", []) or [])

        run["status"] = "RUNNING"
        report = execute(run["run_dir"], on_update=on_update)
        run["report"] = report
        # Collect any runtime artifact fixes from the self-heal loop.
        for att in report.get("attempts", []):
            if att.get("healed"):
                heals.append(att["healed"])
        run["status"] = "SUCCEEDED" if report["status"] == "Succeeded" else "FAILED"
    except Exception as exc:  # surface deploy/runtime errors in /status
        run["status"] = "ERROR"
        run["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if heals:
            run["heals"] = heals


@app.post("/approve")
def approve(req: ApproveRequest, background: BackgroundTasks) -> Dict[str, Any]:
    run = _RUNS.get(req.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    if run["status"] not in {"AWAITING_APPROVAL"}:
        raise HTTPException(status_code=409, detail=f"Run is '{run['status']}', not approvable")
    # Gate: must have been previewed AND pre-flight must pass.
    if not run.get("previewed"):
        raise HTTPException(status_code=409, detail="Preview the plan before approving.")
    if not run.get("preflight", {}).get("passed"):
        raise HTTPException(status_code=409, detail="Pre-flight failed — cannot approve.")

    run["status"] = "APPROVED"
    background.add_task(_deploy_and_run, req.run_id)
    return {"run_id": req.run_id, "status": "APPROVED", "mock": mock_mode()}


# --------------------------------------------------------------------------- #
# /status
# --------------------------------------------------------------------------- #


@app.get("/status/{run_id}")
def status(run_id: str) -> Dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    keep = (
        "status",
        "mock",
        "containers_created",
        "deployed",
        "run",
        "report",
        "heals",
        "error",
        "preflight",
        "clarifications",
    )
    return {"run_id": run_id, **{k: run[k] for k in keep if k in run}}
