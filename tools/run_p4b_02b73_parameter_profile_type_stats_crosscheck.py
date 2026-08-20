# -*- coding: utf-8 -*-
"""P4B-02b73 parameter profile type statistics cross-check (product vs independent ref).

Drives the product type stats runner (p4b_02b73_parameter_profile_type_stats_runner) over validated
profile maps. An independent Python reference counts entries by declared type token. Fail closed on
any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b73-parameter-profile-type-stats-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b73-parameter-profile-type-stats-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b73.parameter-profile-type-stats-v1.profile-type-stats"


def ref_type_stats(profile: dict[str, dict[str, str]]) -> dict[str, Any]:
    counts = {"Float": 0, "Integer": 0, "Boolean": 0, "String": 0, "List": 0}
    for entry in profile.values():
        t = entry["type"]
        if t in counts:
            counts[t] += 1
        else:
            raise SystemExit(f"unexpected type token: {t}")
    return {
        "valid": True,
        "total": len(profile),
        "float_count": counts["Float"],
        "integer_count": counts["Integer"],
        "boolean_count": counts["Boolean"],
        "string_count": counts["String"],
        "list_count": counts["List"],
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b73_parameter_profile_type_stats_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b73_parameter_profile_type_stats_runner-*.exe"))[-1]

    cases = [
        {
            "label": "mixed_types",
            "profile": {
                "gain": {"type": "Float", "value": "0.5"},
                "steps": {"type": "Integer", "value": "7"},
                "on": {"type": "Boolean", "value": "True"},
                "mode": {"type": "String", "value": "Linear"},
                "channels": {"type": "List", "value": "(a, b)"},
            },
        },
        {
            "label": "only_float",
            "profile": {
                "a": {"type": "Float", "value": "0.5"},
                "b": {"type": "Float", "value": "1.25"},
                "c": {"type": "Float", "value": "9.9"},
            },
        },
        {
            "label": "empty_profile",
            "profile": {},
        },
        {
            "label": "large_mixed",
            "profile": {
                "f1": {"type": "Float", "value": "0.5"},
                "f2": {"type": "Float", "value": "1.0"},
                "i1": {"type": "Integer", "value": "1"},
                "i2": {"type": "Integer", "value": "2"},
                "i3": {"type": "Integer", "value": "3"},
                "b": {"type": "Boolean", "value": "False"},
                "s": {"type": "String", "value": "Mode"},
                "l1": {"type": "List", "value": "(x)"},
                "l2": {"type": "List", "value": "(y, z)"},
            },
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b73-") as tmp:
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
            reference = ref_type_stats(case["profile"])

            matched = (product.get("valid") is True
                       and product.get("total") == reference.get("total")
                       and product.get("float_count") == reference.get("float_count")
                       and product.get("integer_count") == reference.get("integer_count")
                       and product.get("boolean_count") == reference.get("boolean_count")
                       and product.get("string_count") == reference.get("string_count")
                       and product.get("list_count") == reference.get("list_count"))
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
