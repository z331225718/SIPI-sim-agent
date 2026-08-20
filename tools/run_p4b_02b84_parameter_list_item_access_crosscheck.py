# -*- coding: utf-8 -*-
"""P4B-02b84 parameter list item access cross-check (product vs independent ref).

Drives the product list item access runner (p4b_02b84_parameter_list_item_access_runner) over
validated (name, type, value, index) inputs. An independent Python reference replicates the item
reading rule: List values return the trimmed item at the index, out-of-range indices and non-List
values fail closed. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b84-parameter-list-item-access-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b84-parameter-list-item-access-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b84.parameter-list-item-access-v1.list-item-access"


def ref_get_item(type_token: str, value_token: str, index: int) -> dict[str, Any]:
    if type_token != "List":
        return {"valid": False, "error": "NotAList"}
    if not (value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2):
        return {"valid": False, "error": "MalformedList"}
    inner = value_token[1:-1]
    if not inner:
        return {"valid": False, "error": "MalformedList"}
    raw_items = inner.split(",")
    if any(not item.strip() for item in raw_items):
        return {"valid": False, "error": "MalformedList"}
    items = [item.strip() for item in raw_items]
    if index >= len(items):
        return {"valid": False, "error": "IndexOutOfRange",
                "index": index, "item_count": len(items)}
    return {"valid": True, "item": items[index]}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b84_parameter_list_item_access_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b84_parameter_list_item_access_runner-*.exe"))[-1]

    cases = [
        {"label": "middle_item", "name": "channels", "type": "List",
         "value": "(a, b, c)", "index": 1},
        {"label": "spacing", "name": "channels", "type": "List",
         "value": "( a , b )", "index": 1},
        {"label": "out_of_range", "name": "channels", "type": "List",
         "value": "(a, b)", "index": 2},
        {"label": "non_list", "name": "gain", "type": "Float",
         "value": "0.5", "index": 0},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b84-") as tmp:
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
            reference = ref_get_item(case["type"], case["value"], case["index"])

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
