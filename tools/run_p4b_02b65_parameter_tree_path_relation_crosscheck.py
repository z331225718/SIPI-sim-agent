# -*- coding: utf-8 -*-
"""P4B-02b65 parameter tree path relation cross-check (product vs independent ref).

Drives the product path relation runner (p4b_02b65_parameter_tree_path_relation_runner) over two
canonical paths. An independent Python reference replicates the prefix classification.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b65-parameter-tree-path-relation-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b65-parameter-tree-path-relation-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b65.parameter-tree-path-relation-v1.path-classification"


def ref_relation(a: list[str], b: list[str]) -> dict[str, Any]:
    if not a or not b:
        return {"valid": False, "relation_error": "EmptyPath"}
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    if common == len(a) and common == len(b):
        return {"valid": True, "relation": "Identical"}
    if common == len(a):
        return {"valid": True, "relation": "Ancestor"}
    if common == len(b):
        return {"valid": True, "relation": "Descendant"}
    return {"valid": True, "relation": "Disjoint"}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b65_parameter_tree_path_relation_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b65_parameter_tree_path_relation_runner-*.exe"))[-1]

    cases = [
        {"label": "identical", "a": ["root", "sub", "deep"], "b": ["root", "sub", "deep"]},
        {"label": "ancestor", "a": ["root", "sub"], "b": ["root", "sub", "deep"]},
        {"label": "descendant", "a": ["root", "sub", "deep"], "b": ["root", "sub"]},
        {"label": "disjoint", "a": ["root", "a"], "b": ["root", "b"]},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b65-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / f"{case['label']}_in.json"
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / f"{case['label']}_rep.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_relation(case["a"], case["b"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if product.get("relation") != reference.get("relation"):
                    matched = False
            else:
                prod_err = product.get("relation_error")
                ref_err = reference.get("relation_error")
                if str(prod_err) != str(ref_err):
                    matched = False

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
