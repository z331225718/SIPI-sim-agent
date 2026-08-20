# -*- coding: utf-8 -*-
"""P4B-02b55 parameter profile completeness check cross-check (product vs independent ref).

Drives the product completeness runner (p4b_02b55_parameter_profile_completeness_runner) over a
parameter map and a required-name set. An independent Python reference replicates the name-presence
check. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b55-parameter-profile-completeness-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b55-parameter-profile-completeness-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b55.parameter-profile-completeness-check-v1.required-name-check"


def ref_check(parameters: dict[str, dict[str, str]], required: list[str]) -> dict[str, Any]:
    if not required:
        return {"valid": False, "completeness_error": "EmptyRequired"}
    missing = sorted(name for name in required if name not in parameters)
    present = len(required) - len(missing)
    return {"valid": True, "expected": len(required), "present": present,
            "missing": missing, "complete": not missing}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b55_parameter_profile_completeness_runner"

    cases = [
        {
            "label": "complete",
            "parameters": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "required": ["gain", "steps"],
        },
        {
            "label": "missing_sorted",
            "parameters": {"gain": {"type": "Float", "value": "0.5"}},
            "required": ["mode", "gain", "steps"],
        },
        {
            "label": "extra_ignored",
            "parameters": {"gain": {"type": "Float", "value": "0.5"}, "extra": {"type": "Integer", "value": "1"}},
            "required": ["gain"],
        },
        {
            "label": "empty_required",
            "parameters": {"gain": {"type": "Float", "value": "0.5"}},
            "required": [],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b55-") as tmp:
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
            reference = ref_check(case["parameters"], case["required"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("expected") != reference.get("expected") or
                    product.get("present") != reference.get("present") or
                    product.get("missing") != reference.get("missing") or
                    product.get("complete") != reference.get("complete")):
                    matched = False
            else:
                prod_err = product.get("completeness_error")
                ref_err = reference.get("completeness_error")
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
