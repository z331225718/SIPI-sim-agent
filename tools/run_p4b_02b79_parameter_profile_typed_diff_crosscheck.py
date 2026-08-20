# -*- coding: utf-8 -*-
"""P4B-02b79 typed parameter profile diff cross-check (product vs independent ref).

Drives the product typed diff runner (p4b_02b79_parameter_profile_typed_diff_runner) over
validated profile pairs. An independent Python reference replicates the typed semantic diff:
shared names with typed-equivalent values are matched, typed-inequivalent shared names are changed
(with both sides' types, raw values, and reason key), left-only names are removed, right-only names
are added. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b79-parameter-profile-typed-diff-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b79-parameter-profile-typed-diff-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b79.parameter-profile-typed-diff-v1.typed-profile-diff"


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


def ref_typed_diff(left: dict[str, dict[str, str]], right: dict[str, dict[str, str]]) -> dict[str, Any]:
    matched = 0
    changed = []
    for name in sorted(set(left) & set(right)):
        old_value = left[name]
        new_value = right[name]
        reason = ref_value_equiv_reason(old_value, new_value)
        if reason is None:
            matched += 1
        else:
            changed.append({
                "name": name,
                "old_type": old_value["type"],
                "old_value": old_value["value"],
                "new_type": new_value["type"],
                "new_value": new_value["value"],
                "reason": reason,
            })
    added = sorted(set(right) - set(left))
    removed = sorted(set(left) - set(right))
    return {"valid": True, "matched": matched, "added": added,
            "removed": removed, "changed": changed}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b79_parameter_profile_typed_diff_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b79_parameter_profile_typed_diff_runner-*.exe"))[-1]

    cases = [
        {
            "label": "identical_profiles",
            "left": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "right": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "spelling_variants",
            "left": {"gain": {"type": "Float", "value": "0.5"},
                     "channels": {"type": "List", "value": "(a, b, c)"}},
            "right": {"gain": {"type": "Float", "value": "0.50"},
                      "channels": {"type": "List", "value": "(a,b,c)"}},
        },
        {
            "label": "added_removed",
            "left": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "right": {"gain": {"type": "Float", "value": "0.5"}, "mode": {"type": "String", "value": "Linear"}},
        },
        {
            "label": "typed_changed",
            "left": {"gain": {"type": "Float", "value": "0.5"}},
            "right": {"gain": {"type": "Float", "value": "0.5001"}},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b79-") as tmp:
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
            reference = ref_typed_diff(case["left"], case["right"])

            matched = (product.get("valid") is True
                       and product.get("matched") == reference.get("matched")
                       and product.get("added") == reference.get("added")
                       and product.get("removed") == reference.get("removed")
                       and product.get("changed") == reference.get("changed"))
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
