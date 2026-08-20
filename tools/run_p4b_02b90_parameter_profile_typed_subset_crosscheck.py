# -*- coding: utf-8 -*-
"""P4B-02b90 parameter profile typed subset check cross-check (product vs independent ref).

Drives the product typed subset runner (p4b_02b90_parameter_profile_typed_subset_runner) over
validated profile pairs. An independent Python reference replicates the typed subset rule: every
subset entry must be present in the superset under the same name with a typed-equivalent value;
missing names and typed mismatches break the subset. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b90-parameter-profile-typed-subset-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b90-parameter-profile-typed-subset-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b90.parameter-profile-typed-subset-v1.typed-subset-check"


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


def ref_typed_subset(subset: dict[str, dict[str, str]], superset: dict[str, dict[str, str]]) -> dict[str, Any]:
    missing = []
    mismatched = []
    for name in sorted(subset.keys()):
        if name not in superset:
            missing.append(name)
            continue
        reason = ref_value_equiv_reason(subset[name], superset[name])
        if reason is not None:
            mismatched.append({"name": name, "reason": reason})
    is_subset = not missing and not mismatched
    return {"valid": True, "is_subset": is_subset, "missing": missing,
            "mismatched": mismatched}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b90_parameter_profile_typed_subset_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b90_parameter_profile_typed_subset_runner-*.exe"))[-1]

    cases = [
        {
            "label": "subset_ok",
            "subset": {"gain": {"type": "Float", "value": "0.5"}},
            "superset": {"gain": {"type": "Float", "value": "0.5"},
                         "steps": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "spelling_variants",
            "subset": {"gain": {"type": "Float", "value": "0.5"}},
            "superset": {"gain": {"type": "Float", "value": "0.50"}},
        },
        {
            "label": "missing_name",
            "subset": {"gain": {"type": "Float", "value": "0.5"},
                       "nope": {"type": "Float", "value": "1.0"}},
            "superset": {"gain": {"type": "Float", "value": "0.5"}},
        },
        {
            "label": "mismatched_value",
            "subset": {"gain": {"type": "Float", "value": "0.5"}},
            "superset": {"gain": {"type": "Float", "value": "0.5001"}},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b90-") as tmp:
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
            reference = ref_typed_subset(case["subset"], case["superset"])

            matched = (product.get("valid") is True
                       and product.get("is_subset") == reference.get("is_subset")
                       and product.get("missing") == reference.get("missing")
                       and product.get("mismatched") == reference.get("mismatched"))
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
