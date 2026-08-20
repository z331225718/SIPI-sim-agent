# -*- coding: utf-8 -*-
"""P4B-02b48 AMI parameter profile merge cross-check (product vs independent ref).

Drives the product profile merge runner (p4b_02b48_parameter_profile_merge_runner) over two
caller-supplied parameter maps. An independent Python reference replicates the conflict-free
by-name merge. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b48-parameter-profile-merge-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b48-parameter-profile-merge-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b48.parameter-profile-merge-v1.conflict-free-merge"


def ref_merge(a: dict[str, dict[str, str]], b: dict[str, dict[str, str]]) -> dict[str, Any]:
    parameters: dict[str, dict[str, str]] = {}
    matched = 0
    for name in sorted(a.keys()):
        old = a[name]
        if name not in b:
            parameters[name] = dict(old)
        elif b[name] == old:
            parameters[name] = dict(old)
            matched += 1
        else:
            new = b[name]
            return {"valid": False,
                    "merge_error": (f'ConflictingValue {{ name: "{name}", '
                                    f'old_type: "{old["type"]}", old_value: "{old["value"]}", '
                                    f'new_type: "{new["type"]}", new_value: "{new["value"]}" }}')}
    for name in sorted(b.keys()):
        if name not in a:
            parameters[name] = dict(b[name])
    return {"valid": True, "matched": matched, "parameters": parameters}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b48_parameter_profile_merge_runner"

    cases = [
        {
            "label": "disjoint",
            "a": {"gain": {"type": "Float", "value": "0.5"}},
            "b": {"steps": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "overlap_identical",
            "a": {"gain": {"type": "Float", "value": "0.5"}},
            "b": {"gain": {"type": "Float", "value": "0.5"}},
        },
        {
            "label": "value_conflict",
            "a": {"gain": {"type": "Float", "value": "0.5"}},
            "b": {"gain": {"type": "Float", "value": "1.25"}},
        },
        {
            "label": "empty_a",
            "a": {},
            "b": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b48-") as tmp:
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
            reference = ref_merge(case["a"], case["b"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("matched") != reference.get("matched") or
                    product.get("parameters") != reference.get("parameters")):
                    matched = False
            else:
                prod_err = product.get("merge_error")
                ref_err = reference.get("merge_error")
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
