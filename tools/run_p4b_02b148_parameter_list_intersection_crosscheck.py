# -*- coding: utf-8 -*-
"""P4B-02b148 parameter list intersection cross-check (product vs independent ref).

Drives the product intersection runner (p4b_02b148_parameter_list_intersection_runner) over two
validated list values. An independent Python reference replicates the intersection rule: both
lists trim items and the left value's items that equal some right value's item are kept in left
order with duplicates preserved; an empty intersection yields the empty token (); non-List
values fail closed. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b148-parameter-list-intersection-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b148-parameter-list-intersection-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b148.parameter-list-intersection-v1.value-intersection"


def ref_intersection(type_token: str, value_token: str, other_type: str, other_value: str) -> dict[str, Any]:
    if type_token != "List" or other_type != "List":
        return {"valid": False, "error": "NotAList"}
    for candidate in (value_token, other_value):
        if not (candidate.startswith("(") and candidate.endswith(")") and len(candidate) >= 2):
            return {"valid": False, "error": "MalformedList"}
        inner = candidate[1:-1]
        if not inner:
            return {"valid": False, "error": "MalformedList"}
        raw_items = inner.split(",")
        if any(not item_part.strip() for item_part in raw_items):
            return {"valid": False, "error": "MalformedList"}
    left = [item_part.strip() for item_part in value_token[1:-1].split(",")]
    right = [item_part.strip() for item_part in other_value[1:-1].split(",")]
    kept = [candidate for candidate in left if candidate in right]
    return {"valid": True, "token": "(" + ", ".join(kept) + ")"}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b148_parameter_list_intersection_runner"

    cases = [
        {"label": "intersection", "name": "left", "type": "List",
         "value": "(a, b, a, c)", "other_name": "right", "other_type": "List",
         "other_value": "(b, c, d)"},
        {"label": "duplicates", "name": "left", "type": "List",
         "value": "(a, a, b)", "other_name": "right", "other_type": "List",
         "other_value": "(a)"},
        {"label": "disjoint", "name": "left", "type": "List",
         "value": "(a, b)", "other_name": "right", "other_type": "List",
         "other_value": "(x, y)"},
        {"label": "non_list", "name": "gain", "type": "Float",
         "value": "0.5", "other_name": "right", "other_type": "List",
         "other_value": "(a)"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b148-") as tmp:
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
            reference = ref_intersection(case["type"], case["value"], case["other_type"], case["other_value"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("token") == reference.get("token")
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
