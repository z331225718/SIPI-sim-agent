# -*- coding: utf-8 -*-
"""P4B-02b146 parameter list starts-with cross-check (product vs independent ref).

Drives the product starts-with runner (p4b_02b146_parameter_list_starts_with_runner) over two
validated list values. An independent Python reference replicates the prefix rule: both lists
trim items and the value starts with the prefix when the prefix items equal the value's first
items element-wise (byte equality); a longer prefix is never a prefix; non-List values fail
closed. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b146-parameter-list-starts-with-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b146-parameter-list-starts-with-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b146.parameter-list-starts-with-v1.prefix-check"


def ref_starts_with(type_token: str, value_token: str, prefix_type: str, prefix_value: str) -> dict[str, Any]:
    if type_token != "List" or prefix_type != "List":
        return {"valid": False, "error": "NotAList"}
    for candidate in (value_token, prefix_value):
        if not (candidate.startswith("(") and candidate.endswith(")") and len(candidate) >= 2):
            return {"valid": False, "error": "MalformedList"}
        inner = candidate[1:-1]
        if not inner:
            return {"valid": False, "error": "MalformedList"}
        raw_items = inner.split(",")
        if any(not item_part.strip() for item_part in raw_items):
            return {"valid": False, "error": "MalformedList"}
    items = [item_part.strip() for item_part in value_token[1:-1].split(",")]
    prefix = [item_part.strip() for item_part in prefix_value[1:-1].split(",")]
    if len(prefix) > len(items):
        return {"valid": True, "starts": False}
    return {"valid": True, "starts": all(candidate == query for candidate, query in zip(items, prefix))}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b146_parameter_list_starts_with_runner"

    cases = [
        {"label": "prefix_holds", "name": "channels", "type": "List",
         "value": "(a, b, c, d)", "prefix_name": "prefix", "prefix_type": "List",
         "prefix_value": "(a, b)"},
        {"label": "full_prefix", "name": "channels", "type": "List",
         "value": "(a, b)", "prefix_name": "prefix", "prefix_type": "List",
         "prefix_value": "(a, b)"},
        {"label": "longer_prefix", "name": "channels", "type": "List",
         "value": "(a, b)", "prefix_name": "prefix", "prefix_type": "List",
         "prefix_value": "(a, b, c)"},
        {"label": "non_list", "name": "channels", "type": "List",
         "value": "(a)", "prefix_name": "gain", "prefix_type": "Float",
         "prefix_value": "0.5"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b146-") as tmp:
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
            reference = ref_starts_with(case["type"], case["value"], case["prefix_type"], case["prefix_value"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("starts") == reference.get("starts")
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
