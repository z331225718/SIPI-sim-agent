# -*- coding: utf-8 -*-
"""P4B-02b129 parameter list last-sublist index cross-check (product vs independent ref).

Drives the product last-sublist-index runner (p4b_02b129_parameter_list_last_sublist_index_runner)
over validated (name, type, value, sublist) inputs. An independent Python reference replicates
the position rule: List values trim items and report the last start index of a window equal to
the query sublist element-wise (raw byte equality; query items not trimmed; empty sublist at 0);
absent sublists fail closed with SublistNotFound; non-List values fail closed. Fail closed on
any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b129-parameter-list-last-sublist-index-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b129-parameter-list-last-sublist-index-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b129.parameter-list-last-sublist-index-v1.last-sublist-position"


def ref_last_sublist_index(type_token: str, value_token: str, sublist: list[str]) -> dict[str, Any]:
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
    if not sublist:
        return {"valid": True, "index": 0}
    if len(sublist) > len(items):
        return {"valid": False, "error": "SublistNotFound"}
    last = None
    for start in range(0, len(items) - len(sublist) + 1):
        if all(items[start + offset] == query for offset, query in enumerate(sublist)):
            last = start
    if last is None:
        return {"valid": False, "error": "SublistNotFound"}
    return {"valid": True, "index": last}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b129_parameter_list_last_sublist_index_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b129_parameter_list_last_sublist_index_runner-*.exe"))[-1]

    cases = [
        {"label": "last_start_index", "name": "channels", "type": "List",
         "value": "(x, b, c, b, c)", "sublist": ["b", "c"]},
        {"label": "single_match", "name": "channels", "type": "List",
         "value": "(a, b, c, d)", "sublist": ["c", "d"]},
        {"label": "absent_sublist", "name": "channels", "type": "List",
         "value": "(a, b, c)", "sublist": ["b", "d"]},
        {"label": "non_list", "name": "gain", "type": "Float",
         "value": "0.5", "sublist": ["0.5"]},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b129-") as tmp:
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
            reference = ref_last_sublist_index(case["type"], case["value"], case["sublist"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("index") == reference.get("index")
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
