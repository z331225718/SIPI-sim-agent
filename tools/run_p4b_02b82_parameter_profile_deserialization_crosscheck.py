# -*- coding: utf-8 -*-
"""P4B-02b82 parameter profile canonical deserialization cross-check (product vs independent ref).

Drives the product deserialization runner (p4b_02b82_parameter_profile_deserialization_runner)
over canonical profile JSON documents. An independent Python reference replicates the parsing and
the fail-closed validation: invalid JSON, non-object root, non-object entry, missing type/value,
and invalid values are all rejected with distinct error keys. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b82-parameter-profile-deserialization-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b82-parameter-profile-deserialization-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b82.parameter-profile-deserialization-v1.canonical-profile-json-parse"


def ref_value_valid(type_token: str, value_token: str) -> bool:
    if type_token == "Float":
        try:
            v = float(value_token)
        except ValueError:
            return False
        import math
        return math.isfinite(v)
    if type_token == "Integer":
        try:
            int(value_token)
            return True
        except ValueError:
            return False
    if type_token == "Boolean":
        return value_token in ("True", "False")
    if type_token == "String":
        return bool(value_token)
    if type_token == "List":
        if not (value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2):
            return False
        inner = value_token[1:-1]
        if not inner:
            return False
        items = [item.strip() for item in inner.split(",")]
        return all(bool(item) for item in items)
    return False


def ref_deserialize(json_text: str) -> dict[str, Any]:
    try:
        value = json.loads(json_text)
    except Exception:
        return {"valid": False, "error": "InvalidJson"}
    if not isinstance(value, dict):
        return {"valid": False, "error": "NotAnObject"}
    profile: dict[str, dict[str, str]] = {}
    for name, entry in value.items():
        if not isinstance(entry, dict):
            return {"valid": False, "error": "EntryNotObject", "name": name}
        if "type" not in entry or not isinstance(entry["type"], str):
            return {"valid": False, "error": "MissingType", "name": name}
        if "value" not in entry or not isinstance(entry["value"], str):
            return {"valid": False, "error": "MissingValue", "name": name}
        if not ref_value_valid(entry["type"], entry["value"]):
            return {"valid": False, "error": "InvalidValue", "name": name}
        profile[name] = {"type": entry["type"], "value": entry["value"]}
    return {"valid": True, "profile": profile}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b82_parameter_profile_deserialization_runner"

    cases = [
        {
            "label": "valid_profile",
            "json": '{"gain":{"type":"Float","value":"0.5"},"steps":{"type":"Integer","value":"7"}}',
        },
        {
            "label": "invalid_json",
            "json": "not json",
        },
        {
            "label": "missing_value",
            "json": '{"gain":{"type":"Float"}}',
        },
        {
            "label": "unknown_type",
            "json": '{"gain":{"type":"Nope","value":"0.5"}}',
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b82-") as tmp:
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
            reference = ref_deserialize(case["json"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("profile") == reference.get("profile")
                       and product.get("error") == reference.get("error")
                       and product.get("name") == reference.get("name"))
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
