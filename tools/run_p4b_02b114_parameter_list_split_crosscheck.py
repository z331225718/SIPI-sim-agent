# -*- coding: utf-8 -*-
"""P4B-02b114 parameter list split-at-index cross-check (product vs independent ref).

Drives the product split runner (p4b_02b114_parameter_list_split_runner) over validated
(name, type, value, index) inputs. An independent Python reference replicates the split rule:
List values trim items and split at the 0-based index into two canonical tokens; an index beyond
the item count fails closed with IndexOutOfRange; non-List values fail closed. Fail closed on any
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b114-parameter-list-split-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b114-parameter-list-split-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b114.parameter-list-split-v1.split-at-index"


def ref_split(type_token: str, value_token: str, index: int) -> dict[str, Any]:
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
    if index > item_count:
        return {"valid": False, "error": "IndexOutOfRange", "index": index, "item_count": item_count}
    return {"valid": True,
            "left": "(" + ", ".join(items[:index]) + ")",
            "right": "(" + ", ".join(items[index:]) + ")"}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b114_parameter_list_split_runner"

    cases = [
        {"label": "split_middle", "name": "channels", "type": "List",
         "value": "(a, b, c, d)", "index": 2},
        {"label": "split_zero", "name": "channels", "type": "List",
         "value": "(a, b)", "index": 0},
        {"label": "split_end", "name": "channels", "type": "List",
         "value": "(a, b)", "index": 2},
        {"label": "out_of_range", "name": "channels", "type": "List",
         "value": "(a, b)", "index": 3},
        {"label": "non_list", "name": "gain", "type": "Float",
         "value": "0.5", "index": 0},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b114-") as tmp:
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
            reference = ref_split(case["type"], case["value"], case["index"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("left") == reference.get("left")
                       and product.get("right") == reference.get("right")
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
