# -*- coding: utf-8 -*-
"""P4B-02b92 parameter profile canonical spelling groups cross-check (product vs independent ref).

Drives the product canonical spelling groups runner
(p4b_02b92_parameter_profile_canonical_spelling_groups_runner) over validated profile maps. An
independent Python reference replicates the grouping rule: names whose values normalize to the same
canonical spelling (Integer via parsed int in decimal, List via trimmed items joined with ", ",
Float/String/Boolean raw) form one group. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b92-parameter-profile-canonical-spelling-groups-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b92-parameter-profile-canonical-spelling-groups-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b92.parameter-profile-canonical-spelling-groups-v1.canonical-spelling-groups"


def ref_canonical(type_token: str, value_token: str) -> str:
    if type_token == "Integer":
        return str(int(value_token))
    if type_token == "List":
        inner = value_token[1:-1]
        items = [item.strip() for item in inner.split(",") if item.strip()]
        return "(" + ", ".join(items) + ")"
    return value_token


def ref_groups(profile: dict[str, dict[str, str]]) -> dict[str, Any]:
    by_spelling: dict[str, list[str]] = {}
    for name, entry in profile.items():
        canonical = ref_canonical(entry["type"], entry["value"])
        by_spelling.setdefault(canonical, []).append(name)
    groups = [{"spelling": spelling, "names": sorted(names)}
              for spelling, names in sorted(by_spelling.items())]
    group_count = len(groups)
    singleton_count = sum(1 for g in groups if len(g["names"]) == 1)
    covered_names = sum(len(g["names"]) for g in groups)
    return {"valid": True, "group_count": group_count, "singleton_count": singleton_count,
            "covered_names": covered_names, "groups": groups}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b92_parameter_profile_canonical_spelling_groups_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b92_parameter_profile_canonical_spelling_groups_runner-*.exe"))[-1]

    cases = [
        {
            "label": "integer_grouping",
            "profile": {"a": {"type": "Integer", "value": "007"},
                        "b": {"type": "Integer", "value": "7"},
                        "c": {"type": "Integer", "value": "8"}},
        },
        {
            "label": "float_separate",
            "profile": {"a": {"type": "Float", "value": "0.5"},
                        "b": {"type": "Float", "value": "0.50"}},
        },
        {
            "label": "list_grouping",
            "profile": {"x": {"type": "List", "value": "(a,b,c)"},
                        "y": {"type": "List", "value": "(a, b, c)"}},
        },
        {
            "label": "empty_profile",
            "profile": {},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b92-") as tmp:
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
            reference = ref_groups(case["profile"])

            matched = (product.get("valid") is True
                       and product.get("group_count") == reference.get("group_count")
                       and product.get("singleton_count") == reference.get("singleton_count")
                       and product.get("covered_names") == reference.get("covered_names")
                       and product.get("groups") == reference.get("groups"))
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
