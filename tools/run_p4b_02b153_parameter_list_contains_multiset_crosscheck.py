# -*- coding: utf-8 -*-
"""P4B-02b153 parameter list multiset containment cross-check (product vs independent ref).

Drives the product contains-multiset runner (p4b_02b153_parameter_list_contains_multiset_runner)
over two validated list values. An independent Python reference replicates the containment rule:
both lists trim items and the query is contained when every query item count is at most the
host count by byte equality (order-insensitive); non-List values fail closed. Fail closed on any
mismatch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b153-parameter-list-contains-multiset-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b153-parameter-list-contains-multiset-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b153.parameter-list-contains-multiset-v1.multiset-containment"


def ref_contains_multiset(type_token: str, value_token: str, query_type: str, query_value: str) -> dict[str, Any]:
    if type_token != "List" or query_type != "List":
        return {"valid": False, "error": "NotAList"}
    for candidate in (value_token, query_value):
        if not (candidate.startswith("(") and candidate.endswith(")") and len(candidate) >= 2):
            return {"valid": False, "error": "MalformedList"}
        inner = candidate[1:-1]
        if not inner:
            return {"valid": False, "error": "MalformedList"}
        raw_items = inner.split(",")
        if any(not item_part.strip() for item_part in raw_items):
            return {"valid": False, "error": "MalformedList"}
    host = [item_part.strip() for item_part in value_token[1:-1].split(",")]
    query = [item_part.strip() for item_part in query_value[1:-1].split(",")]
    if len(query) > len(host):
        return {"valid": True, "contains": False}
    for item in query:
        if sum(1 for c in query if c == item) > sum(1 for c in host if c == item):
            return {"valid": True, "contains": False}
    return {"valid": True, "contains": True}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b153_parameter_list_contains_multiset_runner"

    cases = [
        {"label": "sub_multiset", "name": "host", "type": "List",
         "value": "(a, b, a, c)", "query_name": "query", "query_type": "List",
         "query_value": "(a, a, c)"},
        {"label": "count_exceeded", "name": "host", "type": "List",
         "value": "(a, b, a)", "query_name": "query", "query_type": "List",
         "query_value": "(a, a, a)"},
        {"label": "missing_item", "name": "host", "type": "List",
         "value": "(a, b)", "query_name": "query", "query_type": "List",
         "query_value": "(a, c)"},
        {"label": "non_list", "name": "host", "type": "List",
         "value": "(a)", "query_name": "gain", "query_type": "Float",
         "query_value": "0.5"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b153-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / (case["label"] + "_in.json")
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / (case["label"] + "_rep.json")
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_contains_multiset(case["type"], case["value"], case["query_type"], case["query_value"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("contains") == reference.get("contains")
                       and product.get("error") == reference.get("error"))
            if not matched:
                ok_all = False

            entries.append({
                "label": case["label"],
                "matched": matched,
                "product": product,
                "reference": reference,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "product_owned_self_crosscheck_unbound" if ok_all else "mis_match",
        "policy": POLICY,
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
