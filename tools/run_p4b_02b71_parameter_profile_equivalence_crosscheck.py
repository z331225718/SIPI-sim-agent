# -*- coding: utf-8 -*-
"""P4B-02b71 parameter profile semantic equivalence cross-check (product vs independent ref).

Drives the product profile equivalence runner (p4b_02b71_parameter_profile_equivalence_runner) over
validated profile pairs. An independent Python reference replicates the typed semantic comparison at
the profile-map level: exact name sets plus typed-value equivalence for every shared name (cross-type
never equivalent, Float/Integer on parsed values, Boolean on exact True/False tokens, String on raw
bytes, List on trimmed item sequences). Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b71-parameter-profile-equivalence-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b71-parameter-profile-equivalence-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b71.parameter-profile-equivalence-v1.typed-profile-equivalence"


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


def ref_profiles_equivalent(left: dict[str, dict[str, str]], right: dict[str, dict[str, str]]) -> dict[str, Any]:
    left_only = sorted(set(left) - set(right))
    right_only = sorted(set(right) - set(left))
    mismatches = []
    for name in sorted(set(left) & set(right)):
        reason = ref_value_equiv_reason(left[name], right[name])
        if reason is not None:
            mismatches.append({"name": name, "reason": reason})
    equivalent = not left_only and not right_only and not mismatches
    return {"equivalent": equivalent, "left_only": left_only,
            "right_only": right_only, "mismatches": mismatches}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b71_parameter_profile_equivalence_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b71_parameter_profile_equivalence_runner-*.exe"))[-1]

    cases = [
        {
            "label": "identical_profiles",
            "left": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "right": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "spelling_variants",
            "left": {"gain": {"type": "Float", "value": "0.5"}, "channels": {"type": "List", "value": "(a, b, c)"}},
            "right": {"gain": {"type": "Float", "value": "0.50"}, "channels": {"type": "List", "value": "(a,b,c)"}},
        },
        {
            "label": "missing_name",
            "left": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "right": {"gain": {"type": "Float", "value": "0.5"}},
        },
        {
            "label": "value_mismatch",
            "left": {"gain": {"type": "Float", "value": "0.5"}},
            "right": {"gain": {"type": "Float", "value": "0.5001"}},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b71-") as tmp:
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
            reference = ref_profiles_equivalent(case["left"], case["right"])

            matched = (product.get("valid") is True
                       and product.get("equivalent") == reference.get("equivalent")
                       and product.get("left_only") == reference.get("left_only")
                       and product.get("right_only") == reference.get("right_only")
                       and product.get("mismatches") == reference.get("mismatches"))
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
