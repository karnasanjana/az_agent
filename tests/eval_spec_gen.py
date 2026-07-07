"""Eval harness: measure how reliably the CONFIGURED model turns a BRD into a
deployable spec. This is what makes "model-independent" a NUMBER instead of a
hope — run it before and after swapping LLM_MODEL / LLM_PROVIDER and compare.

For each golden BRD it runs the REAL parser N times (LLM calls — costs tokens),
then builds and pre-flights each spec offline (no Azure writes), and reports:

  parse    the model returned a valid PipelineSpec (within Pydantic AI retries)
  build    the deterministic builder produced ADF JSON from it
  preflight  static checks passed (cross-refs, naming, buildability)
  ops%     structured-op adoption: % of transform columns the model expressed
           as {op,...} instead of a raw DSL string (higher = less model risk)

Usage:
    python tests/eval_spec_gen.py [runs-per-brd]        # default 3
    LLM_MODEL=gemini-2.5-flash python tests/eval_spec_gen.py 5

Artifacts go under a temp directory and are deleted afterwards.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402, F401 — loads .env so the header reports the REAL model
from agent import builder, preflight  # noqa: E402
from samples import COVID_BRD  # noqa: E402

RETAIL_BRD = """\
Business Requirement: Retail order analytics on Azure Data Factory.
We receive olist_orders_dataset.csv in the 'landing' container of our data lake.
Build a medallion pipeline:
- Bronze: copy the file as-is from landing to the bronze container.
- Silver: remove rows with a missing order_id, trim order_status, and cast
  order_purchase_timestamp to a timestamp. Store silver as Delta.
- Gold: count orders per order_status into a CSV in the gold container.
Chain bronze -> silver -> gold in a master pipeline.
"""

COPY_ONLY_BRD = """\
Copy the public CSV file at
https://raw.githubusercontent.com/datasets/population/main/data/population.csv
into the 'raw' container of our ADLS account every night at 01:00 UTC.
No transformations - just land the file as population.csv.
"""

BRDS = {"retail-medallion": RETAIL_BRD, "covid-medallion": COVID_BRD, "copy-only": COPY_ONLY_BRD}


def _ops_adoption(spec) -> str:
    """percentage of transform columns expressed as structured ops."""
    total = structured = 0
    for df in spec.dataflows:
        for t in df.transforms:
            for c in t.columns:
                total += 1
                structured += 1 if c.op else 0
            if t.predicates:
                total += 1
                structured += 1
            elif t.condition:
                total += 1
    if total == 0:
        return "-"
    return f"{100 * structured // total}%"


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    root = tempfile.mkdtemp(prefix="adf_eval_")
    model = os.environ.get("LLM_MODEL", "<provider default>")
    provider = os.environ.get("LLM_PROVIDER", "openai")
    print(f"model={model} provider={provider} runs/brd={runs} artifacts={root}\n")
    print(f"{'brd':<18} {'run':>3}  {'parse':<5} {'build':<5} {'preflight':<9} "
          f"{'ops%':>4}  {'sec':>5}  notes")

    passed = total = 0
    for brd_name, brd in BRDS.items():
        for i in range(1, runs + 1):
            total += 1
            run_id = f"{brd_name}-{i}"
            t0 = time.time()
            note = ""
            parse_ok = build_ok = pf_ok = False
            ops = "-"
            try:
                from agent.parser import parse_brd_sync

                spec = parse_brd_sync(brd)
                parse_ok = True
                ops = _ops_adoption(spec)
                if spec.clarifications and not spec.is_buildable():
                    note = f"blocked on clarifications: {spec.clarifications[:1]}"
                else:
                    builder.write_artifacts(spec, run_id, root=root)
                    build_ok = True
                    pf = preflight.validate(run_id, root=root)
                    pf_ok = bool(pf.get("passed"))
                    if not pf_ok:
                        fails = [c["name"] for c in pf.get("checks", []) if not c.get("passed")]
                        note = f"preflight failed: {', '.join(fails[:3])}"
            except Exception as exc:  # noqa: BLE001 — a failure IS the measurement
                note = f"{type(exc).__name__}: {exc}"[:90]
            secs = time.time() - t0
            passed += 1 if pf_ok else 0
            mark = lambda b: "ok" if b else "FAIL"  # noqa: E731
            print(f"{brd_name:<18} {i:>3}  {mark(parse_ok):<5} {mark(build_ok):<5} "
                  f"{mark(pf_ok):<9} {ops:>4}  {secs:>5.1f}  {note}")

    print(f"\npass rate: {passed}/{total} ({100 * passed // max(total, 1)}%)")
    shutil.rmtree(root, ignore_errors=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
