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
from agent.review import find_bronze_copy, load_category, load_script, load_spec
from models.spec import MedallionLayer, PipelineSpec


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

    # 5. Bronze Copy Activity present (and carries no script — that's correct).
    bronze_pl, bronze_act = find_bronze_copy(spec)
    checks.append(
        _check(
            "bronze_copy_present",
            bronze_act is not None,
            f"{bronze_pl}.{bronze_act.name}" if bronze_act else "no Copy Activity found",
        )
    )

    # 6 & 7. Silver and Gold data flow scripts present and non-trivial.
    by_layer = {df.layer: df for df in spec.dataflows}
    for layer in (MedallionLayer.silver, MedallionLayer.gold):
        df = by_layer.get(layer)
        if df is None:
            checks.append(_check(f"{layer.value}_script_present", False, f"no {layer.value} data flow"))
            continue
        script = load_script(run_dir, df.name)
        has_sink = "~>" in script and "sink(" in script
        checks.append(
            _check(
                f"{layer.value}_script_present",
                bool(script) and has_sink,
                f"{df.name}: {len(script.splitlines())} script lines"
                if script
                else f"{df.name}: empty script",
            )
        )

    passed = all(c["passed"] for c in checks)
    return {"run_id": run_id, "passed": passed, "checks": checks}
