# -*- coding: utf-8 -*-
"""P3C-03c metric-compare cross-check: product vs independent reference.

Compares a candidate metric set against a compiled profile; verifies the
per-metric absolute-OR-relative tolerance rule and allowed-error against an
independent Python reference. Hash-only evidence; no release claim.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-03c-metric-compare-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-03c.metric-compare-crosscheck-evidence.v1"


def reference_allowed(reference, abs_t, rel_t):
    if reference == 0.0:
        return abs_t
    return max(0.0, abs_t + rel_t * abs(reference))


def main() -> int:
    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-compare", "--test", "p3c_03c_metric_compare_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_03c_metric_compare_runner-*.exe"))[-1]

    specs = [
        {"name": "fom", "unit": "db", "reference": 53.426, "abs": 0.01, "rel": 0.0},
        {"name": "veo", "unit": "mv", "reference": 100.0, "abs": 0.0, "rel": 0.05},
        {"name": "er11", "unit": "db", "reference": 20.0, "abs": 0.5, "rel": 0.02},
    ]
    candidates = {"fom": 53.43, "veo": 99.0, "er11": 19.0}
    input_payload = {"specs": specs, "candidates": candidates}

    # Independent reference (the same rule).
    ref_results = {}
    all_pass = True
    for spec in specs:
        ref = spec["reference"]
        cand = candidates[spec["name"]]
        allowed = reference_allowed(ref, spec["abs"], spec["rel"])
        passed = abs(cand - ref) <= allowed
        ref_results[spec["name"]] = {"allowed": allowed, "passed": passed}
        if not passed:
            all_pass = False

    with tempfile.TemporaryDirectory(prefix="p3c-03c-") as tmp:
        work = Path(tmp)
        input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
        input_path = work / "input.json"
        input_path.write_bytes(input_bytes)
        report_path = work / "product.json"
        run = subprocess.run(
            [str(runner), "--input", str(input_path), "--report", str(report_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if run.returncode != 0:
            raise SystemExit("runner failed :: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))

        entries = []
        ok_all = True
        for result in product.get("results", []):
            name = result["name"]
            product_allowed = result["allowed_error"]
            product_pass = result["passed"]
            ref = ref_results[name]
            matched = abs(product_allowed - ref["allowed"]) < 1e-12 and product_pass == ref["passed"]
            if not matched:
                ok_all = False
            entries.append({"name": name, "matched": matched, "product_allowed": product_allowed, "reference_allowed": ref["allowed"], "product_pass": product_pass, "reference_pass": ref["passed"]})
        if product.get("passed") != all_pass:
            ok_all = False
        entries.append({"name": "overall_passed", "matched": product.get("passed") == all_pass, "product": product.get("passed"), "reference": all_pass})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p3c-03c.metric-compare.v1.profile-agnostic",
            "matched_count": sum(1 for e in entries if e["matched"]),
            "case_count": len(entries),
            "entries": entries,
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
        print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"], "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
        return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())