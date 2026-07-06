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
GET  /status/{id}    Live deploy + per-step run state + run IDs + errors + the
                     deploy verification report (intended vs actual factory counts,
                     prune results) + the self-heal audit log.
GET/POST /azure-config       Read / set the deploy target (subscription, resource
                             group, factory, storage) for this server session.
POST /azure-config/test      Read-only connectivity check of the target.
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
    from agent.validator import self_heal_enabled

    return {
        "ok": True,
        "mock": mock_mode(),
        "self_heal": self_heal_enabled(),
        "azure_configured": bool(
            os.environ.get("AZURE_SUBSCRIPTION_ID")
            and os.environ.get("AZURE_RESOURCE_GROUP")
            and os.environ.get("ADF_FACTORY_NAME")
            and os.environ.get("ADLS_ACCOUNT_NAME")
        ),
    }


# --------------------------------------------------------------------------- #
# Azure connection — set from the UI, not hardcoded in the repo
# --------------------------------------------------------------------------- #

# UI field -> environment variable the rest of the system reads.
_AZ_FIELDS = {
    "subscription_id": "AZURE_SUBSCRIPTION_ID",
    "resource_group": "AZURE_RESOURCE_GROUP",
    "factory_name": "ADF_FACTORY_NAME",
    "storage_account": "ADLS_ACCOUNT_NAME",
    "storage_kind": "STORAGE_KIND",  # blob | adls
    "location": "AZURE_LOCATION",
}


class AzureConfigRequest(BaseModel):
    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
    factory_name: Optional[str] = None
    storage_account: Optional[str] = None
    storage_kind: Optional[str] = None
    location: Optional[str] = None


@app.get("/azure-config")
def get_azure_config() -> Dict[str, Any]:
    """Current deploy target (env or values set via POST). Nothing secret here —
    credentials stay in DefaultAzureCredential (az login / Managed Identity)."""
    return {field: os.environ.get(env, "") for field, env in _AZ_FIELDS.items()}


@app.post("/azure-config")
def set_azure_config(req: AzureConfigRequest) -> Dict[str, Any]:
    """Set the deploy target for this server session. Non-empty fields override the
    environment; the .env file is never modified. Clears a stale ADLS_ACCOUNT_URL
    when the storage account changes so the endpoint is re-derived."""
    for field, env in _AZ_FIELDS.items():
        value = (getattr(req, field) or "").strip()
        if value:
            os.environ[env] = value
            if env == "ADLS_ACCOUNT_NAME":
                os.environ.pop("ADLS_ACCOUNT_URL", None)
    return {"saved": True, **get_azure_config()}


@app.post("/azure-config/test")
def test_azure_config() -> Dict[str, Any]:
    """Verify the target before anyone approves a deploy: credential resolves, the
    Data Factory exists, the storage account answers. Read-only."""
    if mock_mode():
        return {"ok": True, "checks": [{"name": "mock_mode", "passed": True,
                                        "detail": "MOCK=true — no Azure calls"}]}
    from config import AzureConfig, get_datafactory_client

    checks = []
    try:
        cfg = AzureConfig.from_env()
        checks.append({"name": "config_present", "passed": True,
                       "detail": f"factory '{cfg.factory_name}' in '{cfg.resource_group}'"})
    except RuntimeError as exc:
        return {"ok": False, "checks": [{"name": "config_present", "passed": False,
                                         "detail": str(exc)}]}
    try:
        adf = get_datafactory_client(cfg)
        adf.factories.get(cfg.resource_group, cfg.factory_name)
        checks.append({"name": "data_factory_reachable", "passed": True,
                       "detail": cfg.factory_name})
    except Exception as exc:  # noqa: BLE001
        hint = _azure_error_hint(exc)
        checks.append({"name": "data_factory_reachable", "passed": False,
                       "detail": f"{type(exc).__name__}: {exc}" + (f" — {hint}" if hint else "")})
    try:
        from config import get_blob_service_client

        get_blob_service_client(cfg).get_account_information()
        checks.append({"name": "storage_reachable", "passed": True,
                       "detail": cfg.adls_account_name})
    except Exception as exc:  # noqa: BLE001
        blob = f"{exc}".lower()
        if "403" in blob or "authorizationpermissionmismatch" in blob:
            # Account exists; deploy identity just lacks a data-plane role (fine —
            # the ADF Managed Identity does the runtime reads/writes).
            checks.append({"name": "storage_reachable", "passed": True,
                           "detail": f"{cfg.adls_account_name} (exists; no data-plane role on deploy identity)"})
        else:
            checks.append({"name": "storage_reachable", "passed": False,
                           "detail": f"{type(exc).__name__}: {exc}"})
    return {"ok": all(c["passed"] for c in checks), "checks": checks}


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

    Clarifications only BLOCK when the spec is genuinely unbuildable (no pipeline
    or no datasets). A buildable spec with open questions still builds, previews,
    and can be approved — the questions ride along as answerable notes. This is
    what stops "the agent asks a lot of questions and nothing happens".
    """
    if spec.clarifications and not spec.is_buildable():
        prev = _RUNS.get(run_id, {})
        _RUNS[run_id] = {
            **prev,
            "status": "NEEDS_CLARIFICATION",
            "clarifications": spec.clarifications[:2],  # hard cap: max 2 questions
            "messages": messages,
            # Drop any stale build — the spec isn't complete yet.
            "spec": spec.model_dump(),
            "previewed": False,
        }
        _RUNS[run_id].pop("run_dir", None)
        return {
            "run_id": run_id,
            "status": "NEEDS_CLARIFICATION",
            "clarifications": spec.clarifications[:2],
            "assumptions": spec.assumptions,
            "suggestions": spec.suggestions,
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
        # Non-blocking: the plan is buildable, these are optional questions the
        # user MAY answer via chat before approving.
        "clarifications": spec.clarifications[:2],
        "assumptions": spec.assumptions,
        "suggestions": spec.suggestions,
        "review": review.render(run_id),
        "graph": graph.graph(run_id),
        "plan_text": review.render_text(run_id),
        "plan_markdown": review.render_markdown(run_id),
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


@app.get("/preview/{run_id}/markdown", response_class=PlainTextResponse)
def preview_markdown(run_id: str) -> str:
    """Human-readable architecture plan (Markdown, no raw JSON)."""
    _require_built(run_id)
    return review.render_markdown(run_id)


@app.get("/graph/{run_id}")
def graph_view(run_id: str) -> Dict[str, Any]:
    _require_built(run_id)
    return graph.graph(run_id)


# --------------------------------------------------------------------------- #
# /approve — the gate: deploy + run (Azure or MOCK)
# --------------------------------------------------------------------------- #


def _azure_error_hint(exc: Exception) -> str:
    """Map a raw Azure SDK error to a one-line, actionable RBAC/config hint. Most
    deploy/run failures are missing role assignments, not code bugs — surface the
    fix instead of a bare stack trace."""
    blob = f"{type(exc).__name__}: {exc}".lower()
    if "authorizationpermissionmismatch" in blob or "authorizationfailure" in blob or "403" in blob:
        if "dfs.core.windows.net" in blob or "blob.core.windows.net" in blob or "filesystem" in blob or "container" in blob:
            return ("403 on storage — the DEPLOY identity needs 'Storage Blob Data "
                    "Contributor' on the storage account (control-plane roles don't grant data access).")
        return ("403 — identity lacks a role. Deploy identity needs 'Data Factory "
                "Contributor' on the resource group; the ADF Managed Identity needs "
                "'Storage Blob Data Contributor' on the storage account.")
    if "defaultazurecredential" in blob or "credentialunavailable" in blob or "no credential" in blob:
        return ("No Azure credential found — run 'az login', or set AZURE_CLIENT_ID / "
                "AZURE_TENANT_ID / AZURE_CLIENT_SECRET for a service principal.")
    if "notfound" in blob or "resourcenotfound" in blob or "404" in blob:
        return ("404 — check AZURE_RESOURCE_GROUP, ADF_FACTORY_NAME, and ADLS_ACCOUNT_NAME "
                "match real resources in AZURE_SUBSCRIPTION_ID.")
    if "storageaccountnotfound" in blob or "accountbeingcreated" in blob:
        return "Storage account not reachable — verify ADLS_ACCOUNT_NAME and STORAGE_KIND (blob vs adls)."
    if "blobstorageevents" in blob or "softdelete" in blob or "409" in blob:
        return ("409 from storage — likely a .dfs (ADLS/HNS) endpoint against a plain Blob "
                "account. Set STORAGE_KIND=blob (or enable hierarchical namespace).")
    return ""


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
        # Verification: intended vs actual factory contents + what prune did.
        run["deploy_report"] = {
            "intended_counts": getattr(deploy_artifacts, "last_intended_counts", {}),
            "factory_counts": getattr(deploy_artifacts, "last_factory_counts", None),
            "pruned": getattr(deploy_artifacts, "last_pruned", []),
            "prune_error": getattr(deploy_artifacts, "last_prune_error", None),
        }

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
        hint = _azure_error_hint(exc)
        run["error"] = f"{type(exc).__name__}: {exc}" + (f"\n\nHINT: {hint}" if hint else "")
    finally:
        if heals:
            run["heals"] = heals
        # Full self-heal audit (deploy + runtime), with before/after bodies.
        try:
            from agent.validator import read_heal_log

            log = read_heal_log(run["run_dir"])
            if log:
                run["heal_log"] = log
        except Exception:  # noqa: BLE001 — audit must not break status
            pass


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
    # Real deploys need a target — fail here with a clear message, not mid-deploy.
    if not mock_mode():
        missing = [
            env for env in ("AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP",
                            "ADF_FACTORY_NAME", "ADLS_ACCOUNT_NAME")
            if not os.environ.get(env)
        ]
        if missing:
            raise HTTPException(
                status_code=409,
                detail="Azure connection not set — fill in the 'Azure connection' "
                       f"panel first (missing: {', '.join(missing)}).",
            )

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
        "deploy_report",
        "run",
        "report",
        "heals",
        "heal_log",
        "error",
        "preflight",
        "clarifications",
    )
    return {"run_id": run_id, **{k: run[k] for k in keep if k in run}}
