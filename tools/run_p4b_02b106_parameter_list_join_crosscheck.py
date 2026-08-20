# -*- coding: utf-8 -*-
"""P4B-02b106 parameter list value join cross-check (product vs independent ref).

Drives the product list join runner (p4b_02b106_parameter_list_join_runner) over validated
left/right value inputs. An independent Python reference replicates the join rule: List values
trim items, concatenate left then right (duplicates preserved), and rejoin with ", "; non-List
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b106-parameter-list-join-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b106-parameter-list-join-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b106.parameter-list-join-v1.list-value-join"


def ref_items(type_token: str, value_token: str) -> list[str] | None:
    if type_token != "List":
        return None
    if not (value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2):
        return None
    inner = value_token[1:-1]
    if not inner:
        return None
    raw_items = inner.split(",")
    if any(not item.strip() for item in raw_items):
        return None
    return [item.strip() for item in raw_items]


def ref_join(left: dict[str, str], right: dict[str, str]) -> dict[str, Any]:
    left_items = ref_items(left["type"], left["value"])
    right_items = ref_items(right["type"], right["value"])
    if left_items is None or right_items is None:
        if left["type"] != "List" or right["type"] != "List":
            return {"valid": False, "error": "NotAList"}
        return {"valid": False, "error": "MalformedList"}
    items = left_items + right_items
    return {"valid": True, "joined": "(" + ", ".join(items) + ")"}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b106_parameter_list_join_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b106_parameter_list_join_runner-*.exe"))[-1]

    cases = [
        {"label": "join_multi",
         "left": {"name": "left", "type": "List", "value": "(a, b)"},
         "right": {"name": "right", "type": "List", "value": "(c, d)"}},
        {"label": "join_single",
         "left": {"name": "left", "type": "List", "value": "( a )"},
         "right": {"name": "right", "type": "List", "value": "(b)"}},
        {"label": "right_non_list",
         "left": {"name": "left", "type": "List", "value": "(a)"},
         "right": {"name": "gain", "type": "Float", "value": "0.5"}},
        {"label": "left_non_list",
         "left": {"name": "gain", "type": "Float", "value": "0.5"},
         "right": {"name": "right", "type": "List", "value": "(c)"}},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b106-") as tmp:
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
            reference = ref_join(case["left"], case["right"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("joined") == reference.get("joined")
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
