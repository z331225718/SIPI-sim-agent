# -*- coding: utf-8 -*-
"""P4B-02b75 parameter value spelling normalization cross-check (product vs independent ref).

Drives the product normalization runner (p4b_02b75_parameter_value_spelling_normalization_runner)
over validated (name, type, value) triples. An independent Python reference replicates the
canonical spelling rules: Integer via parsed int in decimal, List via trimmed items joined with
", ", Boolean/Float/String raw. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b75-parameter-value-spelling-normalization-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b75-parameter-value-spelling-normalization-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b75.parameter-value-spelling-normalization-v1.canonical-non-float-spelling"


def ref_canonical(type_token: str, value_token: str) -> dict[str, Any]:
    if type_token == "Integer":
        try:
            return {"valid": True, "canonical": str(int(value_token))}
        except ValueError:
            return {"valid": False, "input_error": "invalid_value"}
    if type_token == "List":
        if value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2:
            inner = value_token[1:-1]
            items = [item.strip() for item in inner.split(",") if item.strip()]
            return {"valid": True, "canonical": "(" + ", ".join(items) + ")"}
        return {"valid": False, "input_error": "invalid_value"}
    if type_token in ("Boolean", "Float", "String"):
        return {"valid": True, "canonical": value_token}
    return {"valid": False, "input_error": "invalid_value"}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b75_parameter_value_spelling_normalization_runner"

    cases = [
        {"label": "integer_normalization",
         "name": "steps", "type": "Integer", "value": "007"},
        {"label": "list_normalization",
         "name": "channels", "type": "List", "value": "( a , b , c )"},
        {"label": "float_raw",
         "name": "gain", "type": "Float", "value": "0.50"},
        {"label": "string_raw",
         "name": "mode", "type": "String", "value": "Linear "},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b75-") as tmp:
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
            reference = ref_canonical(case["type"], case["value"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("canonical") == reference.get("canonical"))
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
