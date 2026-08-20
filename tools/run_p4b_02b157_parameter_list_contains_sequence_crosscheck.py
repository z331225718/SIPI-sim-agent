# -*- coding: utf-8 -*-
"""P4B-02b157 parameter list sequence containment cross-check (product vs independent ref).

Drives the product contains-sequence runner (p4b_02b157_parameter_list_contains_sequence_runner)
over two validated list values. An independent Python reference replicates the sequence rule:
both lists trim items and the host contains the query when a window equals the query items
element-wise (byte equality); a longer query is never contained; non-List values fail closed.
Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b157-parameter-list-contains-sequence-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b157-parameter-list-contains-sequence-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b157.parameter-list-contains-sequence-v1.sequence-containment"


def ref_contains_sequence(type_token: str, value_token: str, query_type: str, query_value: str) -> dict[str, Any]:
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
    for start in range(0, len(host) - len(query) + 1):
        if all(host[start + offset] == q for offset, q in enumerate(query)):
            return {"valid": True, "contains": True}
    return {"valid": True, "contains": False}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b157_parameter_list_contains_sequence_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b157_parameter_list_contains_sequence_runner-*.exe"))[-1]

    cases = [
        {"label": "contiguous_contained", "name": "host", "type": "List",
         "value": "(a, b, c, d)", "query_name": "query", "query_type": "List",
         "query_value": "(b, c)"},
        {"label": "non_contiguous", "name": "host", "type": "List",
         "value": "(a, x, b, y, c)", "query_name": "query", "query_type": "List",
         "query_value": "(a, b, c)"},
        {"label": "longer_query", "name": "host", "type": "List",
         "value": "(a, b)", "query_name": "query", "query_type": "List",
         "query_value": "(a, b, c)"},
        {"label": "non_list", "name": "host", "type": "List",
         "value": "(a)", "query_name": "gain", "query_type": "Float",
         "query_value": "0.5"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b157-") as tmp:
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
            reference = ref_contains_sequence(case["type"], case["value"], case["query_type"], case["query_value"])

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
