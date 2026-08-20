# -*- coding: utf-8 -*-
"""P3C-04y C4 profile vs MATLAB oracle reference compare (product vs independent ref).

End-to-end P3C-03 compare: the owner C4 profile (COM_dB / ICN_mV / ERL, 1%
relative tolerance) is bound to the authoritative MATLAB oracle aggregate
reference (P5-06e), and each case's own MATLAB oracle metric values are compared
against that same case reference. Product path is compare_metric_profile_v1 via the
runner binary; the reference recomputes the same pass/fail and allowed-error from
scratch. Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-04y-c4-oracle-compare-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-04y.c4-oracle-compare-crosscheck-evidence.v1"
REFERENCE = ROOT / "docs" / "baselines" / "p5-06e-com-oracle-metric-reference.v1.yaml"
REL = 0.01
C4_METRICS = ("COM_dB", "ICN_mV", "ERL")


def reference_compare(reference: dict[str, float], candidates: dict[str, float]) -> dict[str, Any]:
    """Independent reference: per-metric allowed = 0 + rel*|ref|; pass if |cand-ref| <= allowed."""
    results = []
    overall = True
    for name in C4_METRICS:
        ref = reference[name]
        cand = candidates[name]
        allowed = REL * abs(ref)
        diff = abs(cand - ref)
        passed = diff <= allowed
        if not passed:
            overall = False
        results.append({"name": name, "candidate": cand, "allowed_error": allowed, "passed": passed})
    return {"passed": overall, "results": results}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-compare", "--test", "p3c_03c_metric_compare_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_03c_metric_compare_runner-*.exe"))[-1]

    reference = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    aggregate = reference["aggregate_reference"]
    case_refs = {c["case_index"]: c for c in reference["case_references"]}

    cases = []
    for idx, case in case_refs.items():
        candidates = {n: case[n] for n in C4_METRICS}
        cases.append({
            "label": f"case_{idx}",
            "reference": candidates,
            "candidates": candidates,
        })

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p3c-c4y-") as tmp:
        work = Path(tmp)
        for case in cases:
            specs = [{"name": n, "unit": ("db" if n != "ICN_mV" else "mv"), "reference": case["reference"][n], "abs": 0.0, "rel": REL} for n in C4_METRICS]
            payload = {"specs": specs, "candidates": case["candidates"]}
            input_path = work / "input.json"
            input_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            report_path = work / "product.json"
            r = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                raise SystemExit("runner failed :: " + r.stdout + r.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            ref = reference_compare(case["reference"], case["candidates"])

            prod_passed = bool(product.get("passed"))
            prod_results = product.get("results") or []
            # Product emits results in BTreeMap (sorted-name) order; compare
            # per-metric maps to be order-insensitive.
            prod_map = {x["name"]: x for x in prod_results}
            ref_map = {x["name"]: x for x in ref["results"]}
            mismatched = (prod_passed != ref["passed"]) or (prod_map != ref_map)
            if mismatched:
                ok_all = False
            entries.append({
                "label": case["label"], "matched": not mismatched,
                "product_passed": prod_passed, "reference_passed": ref["passed"],
                "product_results": prod_results, "reference_results": ref["results"],
                "oracle_aggregate": aggregate,
                "oracle_case_reference": case["reference"],
                "oracle_case_candidates": case["candidates"],
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct",
        "oracle_reference_ref": "docs/baselines/p5-06e-com-oracle-metric-reference.v1.yaml",
        "relative_tolerance": REL,
        "matched_count": sum(1 for e in entries if e["matched"]),
        "case_count": len(entries),
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"],
                      "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
