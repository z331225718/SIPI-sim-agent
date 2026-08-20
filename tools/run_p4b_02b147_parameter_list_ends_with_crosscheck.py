# -*- coding: utf-8 -*-
"""P4B-02b147 parameter list ends-with cross-check (product vs independent ref).

Drives the product ends-with runner (p4b_02b147_parameter_list_ends_with_runner) over two
validated list values. An independent Python reference replicates the suffix rule: both lists
trim items and the value ends with the suffix when the suffix items equal the value's final
items element-wise (byte equality); a longer suffix is never a suffix; non-List values fail
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b147-parameter-list-ends-with-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b147-parameter-list-ends-with-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b147.parameter-list-ends-with-v1.suffix-check"


def ref_ends_with(type_token: str, value_token: str, suffix_type: str, suffix_value: str) -> dict[str, Any]:
    if type_token != "List" or suffix_type != "List":
        return {"valid": False, "error": "NotAList"}
    for candidate in (value_token, suffix_value):
        if not (candidate.startswith("(") and candidate.endswith(")") and len(candidate) >= 2):
            return {"valid": False, "error": "MalformedList"}
        inner = candidate[1:-1]
        if not inner:
            return {"valid": False, "error": "MalformedList"}
        raw_items = inner.split(",")
        if any(not item_part.strip() for item_part in raw_items):
            return {"valid": False, "error": "MalformedList"}
    items = [item_part.strip() for item_part in value_token[1:-1].split(",")]
    suffix = [item_part.strip() for item_part in suffix_value[1:-1].split(",")]
    if len(suffix) > len(items):
        return {"valid": True, "ends": False}
    offset = len(items) - len(suffix)
    return {"valid": True, "ends": all(candidate == query for candidate, query in zip(items[offset:], suffix))}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b147_parameter_list_ends_with_runner"

    cases = [
        {"label": "suffix_holds", "name": "channels", "type": "List",
         "value": "(a, b, c, d)", "suffix_name": "suffix", "suffix_type": "List",
         "suffix_value": "(c, d)"},
        {"label": "full_suffix", "name": "channels", "type": "List",
         "value": "(a, b)", "suffix_name": "suffix", "suffix_type": "List",
         "suffix_value": "(a, b)"},
        {"label": "longer_suffix", "name": "channels", "type": "List",
         "value": "(a, b)", "suffix_name": "suffix", "suffix_type": "List",
         "suffix_value": "(x, a, b)"},
        {"label": "non_list", "name": "channels", "type": "List",
         "value": "(a)", "suffix_name": "gain", "suffix_type": "Float",
         "suffix_value": "0.5"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b147-") as tmp:
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
            reference = ref_ends_with(case["type"], case["value"], case["suffix_type"], case["suffix_value"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("ends") == reference.get("ends")
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
