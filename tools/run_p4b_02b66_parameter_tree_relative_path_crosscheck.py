# -*- coding: utf-8 -*-
"""P4B-02b66 parameter tree relative path cross-check (product vs independent ref).

Drives the product relative path runner (p4b_02b66_parameter_tree_relative_path_runner) over an
ancestor and a target path. An independent Python reference replicates the suffix derivation.
Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b66-parameter-tree-relative-path-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b66-parameter-tree-relative-path-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b66.parameter-tree-relative-path-v1.suffix-derivation"


def ref_relative(ancestor: list[str], path: list[str]) -> dict[str, Any]:
    if not ancestor or not path:
        return {"valid": False, "relative_error": "EmptyPath"}
    if len(ancestor) >= len(path):
        if ancestor == path:
            return {"valid": False, "relative_error": "EmptySuffix"}
        return {"valid": False, "relative_error": "NotAncestor"}
    if path[:len(ancestor)] != ancestor:
        return {"valid": False, "relative_error": "NotAncestor"}
    return {"valid": True, "relative": path[len(ancestor):]}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b66_parameter_tree_relative_path_runner"

    cases = [
        {"label": "simple_suffix", "ancestor": ["root", "sub"], "path": ["root", "sub", "deep"]},
        {"label": "multi_suffix", "ancestor": ["root"], "path": ["root", "a", "b"]},
        {"label": "equal_paths", "ancestor": ["root", "a"], "path": ["root", "a"]},
        {"label": "non_ancestor", "ancestor": ["root", "a"], "path": ["root", "b", "x"]},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b66-") as tmp:
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
            reference = ref_relative(case["ancestor"], case["path"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if product.get("relative") != reference.get("relative"):
                    matched = False
            else:
                prod_err = product.get("relative_error")
                ref_err = reference.get("relative_error")
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
