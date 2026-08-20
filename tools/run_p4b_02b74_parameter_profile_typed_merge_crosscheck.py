# -*- coding: utf-8 -*-
"""P4B-02b74 typed parameter profile merge cross-check (product vs independent ref).

Drives the product typed merge runner (p4b_02b74_parameter_profile_typed_merge_runner) over
validated profile pairs. An independent Python reference replicates the typed semantic merge:
shared names with typed-equivalent values merge as matched, typed-inequivalent shared names are a
conflict, disjoint names carry over. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b74-parameter-profile-typed-merge-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b74-parameter-profile-typed-merge-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b74.parameter-profile-typed-merge-v1.typed-value-merge"


def ref_list_items(value_token: str):
    if not (value_token.startswith("(") and value_token.endswith(")") and len(value_token) >= 2):
        return None
    inner = value_token[1:-1]
    if not inner:
        return None
    items = [item.strip() for item in inner.split(",")]
    if any(not item for item in items):
        return None
    return items


def ref_value_equiv_reason(left: dict[str, str], right: dict[str, str]) -> str | None:
    """Return None when typed-equivalent, else the reason key."""
    if left["type"] != right["type"]:
        return "TypeMismatch"
    t = left["type"]
    lv, rv = left["value"], right["value"]
    if t == "Float":
        try:
            lf, rf = float(lv), float(rv)
        except ValueError:
            return "MalformedValue"
        return None if lf == rf else "FloatMismatch"
    if t == "Integer":
        try:
            li, ri = int(lv), int(rv)
        except ValueError:
            return "MalformedValue"
        return None if li == ri else "IntegerMismatch"
    if t == "Boolean":
        return None if lv == rv else "BooleanMismatch"
    if t == "String":
        return None if lv == rv else "StringMismatch"
    if t == "List":
        li = ref_list_items(lv)
        ri = ref_list_items(rv)
        if li is None or ri is None:
            return "MalformedValue"
        if len(li) != len(ri):
            return "ListLengthMismatch"
        for a, b in zip(li, ri):
            if a != b:
                return "ListItemMismatch"
        return None
    return "MalformedValue"


def ref_typed_merge(left: dict[str, dict[str, str]], right: dict[str, dict[str, str]]) -> dict[str, Any]:
    parameters: dict[str, dict[str, str]] = {}
    matched = 0
    for name, old_value in left.items():
        if name not in right:
            parameters[name] = dict(old_value)
            continue
        new_value = right[name]
        if ref_value_equiv_reason(old_value, new_value) is None:
            parameters[name] = dict(old_value)
            matched += 1
        else:
            return {
                "valid": False,
                "conflict": {
                    "name": name,
                    "old_type": old_value["type"],
                    "old_value": old_value["value"],
                    "new_type": new_value["type"],
                    "new_value": new_value["value"],
                },
            }
    for name, new_value in right.items():
        if name not in left:
            parameters[name] = dict(new_value)
    return {"valid": True, "matched": matched, "parameters": parameters}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b74_parameter_profile_typed_merge_runner"

    cases = [
        {
            "label": "disjoint_merge",
            "left": {"gain": {"type": "Float", "value": "0.5"}},
            "right": {"steps": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "spelling_variants",
            "left": {"gain": {"type": "Float", "value": "0.5"},
                     "channels": {"type": "List", "value": "(a, b, c)"}},
            "right": {"gain": {"type": "Float", "value": "0.50"},
                      "channels": {"type": "List", "value": "(a,b,c)"}},
        },
        {
            "label": "typed_conflict",
            "left": {"gain": {"type": "Float", "value": "0.5"}},
            "right": {"gain": {"type": "Float", "value": "0.5001"}},
        },
        {
            "label": "empty_profiles",
            "left": {},
            "right": {},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b74-") as tmp:
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
            reference = ref_typed_merge(case["left"], case["right"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("matched") != reference.get("matched") or
                        product.get("parameters") != reference.get("parameters")):
                    matched = False
            else:
                if product.get("conflict") != reference.get("conflict"):
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
