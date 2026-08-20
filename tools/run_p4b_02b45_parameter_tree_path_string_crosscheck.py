# -*- coding: utf-8 -*-
"""P4B-02b45 AMI parameter tree path-string parsing cross-check (product vs independent ref).

Drives the product path-string runner (p4b_02b45_parameter_tree_path_string_runner) over dotted
path strings. An independent Python reference replicates the split rules. Fail closed on any
mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b45-parameter-tree-path-string-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b45-parameter-tree-path-string-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b45.parameter-tree-path-string-v1.dotted-path-parse"


def ref_parse(path: str) -> dict[str, Any]:
    if not path:
        return {"valid": False, "path_error": "EmptyPath"}
    parts = path.split(".")
    if any(part == "" for part in parts):
        return {"valid": False, "path_error": "EmptySegment"}
    return {"valid": True, "segments": parts}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b45_parameter_tree_path_string_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b45_parameter_tree_path_string_runner-*.exe"))[-1]

    cases = [
        {"label": "basic", "path": "root.gain"},
        {"label": "deep", "path": "root.sub.deep"},
        {"label": "empty_path", "path": ""},
        {"label": "double_dot", "path": "a..b"},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b45-") as tmp:
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
            reference = ref_parse(case["path"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if product.get("segments") != reference.get("segments"):
                    matched = False
            else:
                prod_err = product.get("path_error")
                ref_err = reference.get("path_error")
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
