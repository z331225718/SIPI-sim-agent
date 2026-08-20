# -*- coding: utf-8 -*-
"""P4B-02b76 typed parameter profile override merge cross-check (product vs independent ref).

Drives the product override merge runner (p4b_02b76_parameter_profile_override_merge_runner) over
validated profile pairs. An independent Python reference replicates the typed override merge:
shared names with typed-equivalent values keep the base entry (matched), typed-inequivalent shared
names are overridden by the second profile, disjoint names carry over. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b76-parameter-profile-override-merge-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b76-parameter-profile-override-merge-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b76.parameter-profile-override-merge-v1.typed-override-merge"


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


def ref_override_merge(base: dict[str, dict[str, str]], override: dict[str, dict[str, str]]) -> dict[str, Any]:
    parameters: dict[str, dict[str, str]] = {}
    matched = 0
    overridden = 0
    for name, base_value in base.items():
        if name not in override:
            parameters[name] = dict(base_value)
            continue
        override_value = override[name]
        if ref_value_equiv_reason(base_value, override_value) is None:
            parameters[name] = dict(base_value)
            matched += 1
        else:
            parameters[name] = dict(override_value)
            overridden += 1
    for name, override_value in override.items():
        if name not in base:
            parameters[name] = dict(override_value)
    return {"valid": True, "matched": matched, "overridden": overridden,
            "parameters": parameters}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b76_parameter_profile_override_merge_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b76_parameter_profile_override_merge_runner-*.exe"))[-1]

    cases = [
        {
            "label": "disjoint_merge",
            "base": {"gain": {"type": "Float", "value": "0.5"}},
            "override": {"steps": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "spelling_variants",
            "base": {"gain": {"type": "Float", "value": "0.5"},
                     "channels": {"type": "List", "value": "(a, b, c)"}},
            "override": {"gain": {"type": "Float", "value": "0.50"},
                         "channels": {"type": "List", "value": "(a,b,c)"}},
        },
        {
            "label": "override_conflict",
            "base": {"gain": {"type": "Float", "value": "0.5"},
                     "keep": {"type": "Integer", "value": "7"}},
            "override": {"gain": {"type": "Float", "value": "0.5001"}},
        },
        {
            "label": "empty_profiles",
            "base": {},
            "override": {},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b76-") as tmp:
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
            reference = ref_override_merge(case["base"], case["override"])

            matched = (product.get("valid") is True
                       and product.get("matched") == reference.get("matched")
                       and product.get("overridden") == reference.get("overridden")
                       and product.get("parameters") == reference.get("parameters"))
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
