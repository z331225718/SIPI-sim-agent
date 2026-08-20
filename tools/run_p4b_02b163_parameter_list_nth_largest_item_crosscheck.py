# -*- coding: utf-8 -*-
"""P4B-02b163 parameter list nth-largest item cross-check (product vs independent ref).

Drives the product nth-largest runner (p4b_02b163_parameter_list_nth_largest_item_runner)
over one validated list value and a zero-based rank. An independent Python reference
replicates the descending order-statistic rule: the list trims items and the item at the
given rank in descending sorted order (byte lexicographic order, duplicates counted as
separate positions) is reported; a rank beyond the item count fails closed with
IndexOutOfRange; non-List values fail closed. Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b163-parameter-list-nth-largest-item-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b163-parameter-list-nth-largest-item-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b163.parameter-list-nth-largest-item-v1.nth-largest-item"


def ref_nth_largest(type_token: str, value_token: str, nth: int) -> dict[str, Any]:
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
    if nth >= item_count:
        return {"valid": False, "error": "IndexOutOfRange", "index": nth, "item_count": item_count}
    return {"valid": True, "item": sorted(items, reverse=True)[nth]}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b163_parameter_list_nth_largest_item_runner"

    cases = [
        {"label": "middle_rank", "name": "param", "type": "List", "value": "(c, a, b)", "nth": 1},
        {"label": "rank_zero_max", "name": "param", "type": "List", "value": "(c, a, b)", "nth": 0},
        {"label": "duplicates", "name": "param", "type": "List", "value": "(b, a, b)", "nth": 2},
        {"label": "rank_out_of_range", "name": "param", "type": "List", "value": "(a, b)", "nth": 2},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b163-") as tmp:
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
            reference = ref_nth_largest(case["type"], case["value"], case["nth"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("item") == reference.get("item")
                       and product.get("error") == reference.get("error")
                       and product.get("index") == reference.get("index")
                       and product.get("item_count") == reference.get("item_count"))
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
