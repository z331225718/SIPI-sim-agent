# -*- coding: utf-8 -*-
"""P4B-02b64 parameter profile selection cross-check (product vs independent ref).

Drives the product profile selection runner (p4b_02b64_parameter_profile_select_runner) over a
parameter map and a selection name set. An independent Python reference replicates the name-set
selection. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b64-parameter-profile-select-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b64-parameter-profile-select-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b64.parameter-profile-select-v1.name-set-selection"


def ref_select(parameters: dict[str, dict[str, str]], select: list[str]) -> dict[str, Any]:
    if not select:
        return {"valid": False, "selection_error": "EmptySelection"}
    selected: dict[str, dict[str, str]] = {}
    for name in select:
        if name not in parameters:
            return {"valid": False, "selection_error": f'MissingParameter("{name}")'}
        selected[name] = dict(parameters[name])
    return {"valid": True, "selected_count": len(selected), "selected": selected}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b64_parameter_profile_select_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b64_parameter_profile_select_runner-*.exe"))[-1]

    cases = [
        {
            "label": "select_subset",
            "parameters": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "select": ["gain"],
        },
        {
            "label": "select_all",
            "parameters": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "select": ["gain", "steps"],
        },
        {
            "label": "missing_parameter",
            "parameters": {"gain": {"type": "Float", "value": "0.5"}},
            "select": ["nope"],
        },
        {
            "label": "empty_selection",
            "parameters": {"gain": {"type": "Float", "value": "0.5"}},
            "select": [],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b64-") as tmp:
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
            reference = ref_select(case["parameters"], case["select"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("selected_count") != reference.get("selected_count") or
                    product.get("selected") != reference.get("selected")):
                    matched = False
            else:
                prod_err = product.get("selection_error")
                ref_err = reference.get("selection_error")
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
