"""Pre-flight validation — the offline safety guard that gates approval.

Phase 1 of the three-phase plan ("Local dry-run"): JSON valid? spec correct?
naming ok? cross-references resolve? Bronze Copy present? Silver/Gold scripts
present? No Azure access required. Approval is blocked unless this passes.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from agent.builder import DEPLOY_ORDER
from agent.review import load_script, load_spec
from models.spec import PipelineSpec


def _check(name: str, passed: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def validate(run_id: str, root: str = "artifacts") -> Dict[str, Any]:
    run_dir = os.path.join(root, run_id)
    checks: List[Dict[str, Any]] = []

    # 1. spec.json present and re-validates against the contract.
    spec: PipelineSpec | None = None
    try:
        spec = load_spec(run_dir)
        checks.append(_check("spec_valid", True, "spec.json validates against PipelineSpec"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("spec_valid", False, f"{type(exc).__name__}: {exc}"))
        return {"run_id": run_id, "passed": False, "checks": checks}

    # 2. Naming conventions.
    violations = spec.naming_violations()
    checks.append(
        _check("naming_ok", not violations, "; ".join(violations) or "ls_/ds_/df_/pl_ ok")
    )

    # 3. Cross-references resolve.
    xref = spec.cross_reference_errors()
    checks.append(
        _check("cross_references_resolve", not xref, "; ".join(xref) or "all references resolve")
    )

    # 4. Every artifact JSON file is well-formed.
    bad_json: List[str] = []
    for category in DEPLOY_ORDER:
        cat_dir = os.path.join(run_dir, category)
        if not os.path.isdir(cat_dir):
            continue
        for fname in os.listdir(cat_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(cat_dir, fname), "r", encoding="utf-8") as fh:
                    json.load(fh)
            except Exception as exc:  # noqa: BLE001
                bad_json.append(f"{category}/{fname}: {exc}")
    checks.append(_check("json_well_formed", not bad_json, "; ".join(bad_json) or "all JSON parses"))

    # 5. At least one pipeline with real, executable work.
    work = [
        f"{pl.name}.{act.name}"
        for pl in spec.pipelines
        for act in pl.activities
        if act.type in ("Copy", "ExecuteDataFlow")
    ]
    checks.append(
        _check(
            "executable_work_present",
            bool(work),
            "; ".join(work[:5]) or "no Copy or ExecuteDataFlow activity anywhere",
        )
    )

    # 6. Every declared data flow has a non-trivial script with a sink.
    for df in spec.dataflows:
        script = load_script(run_dir, df.name)
        has_sink = "~>" in script and "sink(" in script
        checks.append(
            _check(
                f"script_{df.name}",
                bool(script) and has_sink,
                f"{len(script.splitlines())} script lines" if script else "empty script",
            )
        )

    passed = all(c["passed"] for c in checks)
    return {"run_id": run_id, "passed": passed, "checks": checks}
