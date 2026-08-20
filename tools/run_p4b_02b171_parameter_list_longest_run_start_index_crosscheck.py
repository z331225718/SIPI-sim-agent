# -*- coding: utf-8 -*-
"""P4B-02b171 parameter list longest run start index cross-check (product vs independent ref).

Drives the product longest-run-start-index runner
(p4b_02b171_parameter_list_longest_run_start_index_runner) over one validated list value. An
independent Python reference replicates the rule: the list trims items and the zero-based
start index of the earliest maximal run achieving the longest length (raw byte equality,
left-to-right scan) is reported; non-List values fail closed. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b171-parameter-list-longest-run-start-index-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b171-parameter-list-longest-run-start-index-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b171.parameter-list-longest-run-start-index-v1.longest-run-start-index"


def ref_longest_run_start_index(type_token: str, value_token: str) -> dict[str, Any]:
    if type_token != "List":
        return {"valid": False, "error": "NotAList"}
    if not (value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2):
        return {"valid": False, "error": "MalformedList"}
    inner = value_token[1:-1]
    if not inner:
        return {"valid": False, "error": "MalformedList"}
    raw_items = inner.split(",")
    if any(not item_part.strip() for item_part in raw_items):
        return {"valid": False, "error": "MalformedList"}
    items = [item_part.strip() for item_part in raw_items]
    best_start = 0
    best_len = 1
    current_start = 0
    current_len = 1
    for index in range(1, len(items)):
        if items[index] == items[index - 1]:
            current_len += 1
        else:
            if current_len > best_len:
                best_len = current_len
                best_start = current_start
            current_start = index
            current_len = 1
    if current_len > best_len:
        best_start = current_start
    return {"valid": True, "start_index": best_start}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b171_parameter_list_longest_run_start_index_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b171_parameter_list_longest_run_start_index_runner-*.exe"))[-1]

    cases = [
        {"label": "longest_run", "name": "param", "type": "List", "value": "(a, b, b, b, c)"},
        {"label": "tie_earliest", "name": "param", "type": "List", "value": "(a, a, b, b, c)"},
        {"label": "all_distinct", "name": "param", "type": "List", "value": "(c, a, b)"},
        {"label": "non_list", "name": "gain", "type": "Float", "value": "0.5"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b171-") as tmp:
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
            reference = ref_longest_run_start_index(case["type"], case["value"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("start_index") == reference.get("start_index")
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
        "status": "matched_hash_bound" if ok_all else "mis_match",
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
