# -*- coding: utf-8 -*-
"""P4B-02b178 parameter list normalized entropy cross-check (product vs independent ref).

Drives the product normalized-entropy runner
(p4b_02b178_parameter_list_normalized_entropy_runner) over one validated list value. An
independent Python reference replicates the rule: the list trims items and the normalized
Shannon entropy (evenness) -sum(p_i * log2(p_i)) / log2(len) with p_i = count_i / len (raw
byte equality) is computed and formatted with 12 decimals; non-List values fail closed. Fail
closed on any mismatch.
"""

from __future__ import annotations

import json
import os
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b178-parameter-list-normalized-entropy-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b178-parameter-list-normalized-entropy-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b178.parameter-list-normalized-entropy-v1.normalized-entropy"


def ref_evenness(type_token: str, value_token: str) -> dict[str, Any]:
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
    item_count = len(items)
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    entropy = 0.0
    for count in counts.values():
        p = count / item_count
        entropy -= p * math.log2(p)
    evenness = entropy / math.log2(item_count)
    return {"valid": True, "evenness": f"{evenness:.12f}"}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b178_parameter_list_normalized_entropy_runner"

    cases = [
        {"label": "all_equal", "name": "param", "type": "List", "value": "(a, a, a)"},
        {"label": "all_distinct", "name": "param", "type": "List", "value": "(c, a, b)"},
        {"label": "unbalanced", "name": "param", "type": "List", "value": "(a, a, a, b, c)"},
        {"label": "non_list", "name": "gain", "type": "Float", "value": "0.5"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b178-") as tmp:
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
            reference = ref_evenness(case["type"], case["value"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("evenness") == reference.get("evenness")
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
