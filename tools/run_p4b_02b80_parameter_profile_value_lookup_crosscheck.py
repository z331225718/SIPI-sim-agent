# -*- coding: utf-8 -*-
"""P4B-02b80 parameter profile value reverse lookup cross-check (product vs independent ref).

Drives the product value lookup runner (p4b_02b80_parameter_profile_value_lookup_runner) over
validated profile maps plus a query value. An independent Python reference replicates the typed
semantic matching (cross-type never matches, Float/Integer on parsed values, Boolean on exact
True/False tokens, String on raw bytes, List on trimmed item sequences) and the fail-closed query
validation. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b80-parameter-profile-value-lookup-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b80-parameter-profile-value-lookup-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b80.parameter-profile-value-lookup-v1.typed-value-reverse-lookup"


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
        return ref_list_items(value_token) is not None
    return False


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


def ref_lookup(profile: dict[str, dict[str, str]], query: dict[str, str]) -> dict[str, Any]:
    if not ref_value_valid(query["type"], query["value"]):
        return {"valid": False, "error": "InvalidQueryValue"}
    matches = []
    for name, entry in profile.items():
        if ref_value_equiv_reason(query, entry) is None:
            matches.append(name)
    return {"valid": True, "matches": sorted(matches)}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b80_parameter_profile_value_lookup_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b80_parameter_profile_value_lookup_runner-*.exe"))[-1]

    cases = [
        {
            "label": "match_found",
            "profile": {"gain": {"type": "Float", "value": "0.50"},
                        "steps": {"type": "Integer", "value": "7"}},
            "query": {"name": "q", "type": "Float", "value": "0.5"},
        },
        {
            "label": "no_match",
            "profile": {"gain": {"type": "Float", "value": "0.5"}},
            "query": {"name": "q", "type": "Float", "value": "0.5001"},
        },
        {
            "label": "multiple_matches",
            "profile": {"b": {"type": "Integer", "value": "007"},
                        "a": {"type": "Integer", "value": "7"},
                        "c": {"type": "Integer", "value": "8"}},
            "query": {"name": "q", "type": "Integer", "value": "7"},
        },
        {
            "label": "invalid_query",
            "profile": {"gain": {"type": "Float", "value": "0.5"}},
            "query": {"name": "q", "type": "Float", "value": "abc"},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b80-") as tmp:
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
            reference = ref_lookup(case["profile"], case["query"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("matches") == reference.get("matches")
                       and (product.get("error") is not None) == (reference.get("error") is not None))
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
