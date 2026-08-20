# -*- coding: utf-8 -*-
"""P4B-02b95 parameter profile canonical spelling check cross-check (product vs independent ref).

Drives the product canonical spelling check runner
(p4b_02b95_parameter_profile_canonical_spelling_check_runner) over validated profile maps. An
independent Python reference replicates the canonical check: each entry's raw value token is
compared to its canonical spelling (Integer via parsed int in decimal, List via trimmed items
joined with ", ", Float/String/Boolean raw) and every non-canonical entry is reported with name,
type, raw value, and canonical value. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b95-parameter-profile-canonical-spelling-check-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b95-parameter-profile-canonical-spelling-check-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b95.parameter-profile-canonical-spelling-check-v1.canonical-profile-spelling-check"


def ref_canonical(type_token: str, value_token: str) -> str:
    if type_token == "Integer":
        return str(int(value_token))
    if type_token == "List":
        inner = value_token[1:-1]
        items = [item.strip() for item in inner.split(",") if item.strip()]
        return "(" + ", ".join(items) + ")"
    return value_token


def ref_check(profile: dict[str, dict[str, str]]) -> dict[str, Any]:
    non_canonical = []
    for name in sorted(profile.keys()):
        entry = profile[name]
        canonical = ref_canonical(entry["type"], entry["value"])
        if canonical != entry["value"]:
            non_canonical.append({
                "name": name,
                "type_token": entry["type"],
                "value_token": entry["value"],
                "canonical": canonical,
            })
    return {"valid": True, "entries": len(profile), "canonical": not non_canonical,
            "non_canonical": non_canonical}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b95_parameter_profile_canonical_spelling_check_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b95_parameter_profile_canonical_spelling_check_runner-*.exe"))[-1]

    cases = [
        {
            "label": "canonical_profile",
            "profile": {"gain": {"type": "Float", "value": "0.5"},
                        "steps": {"type": "Integer", "value": "7"},
                        "on": {"type": "Boolean", "value": "True"}},
        },
        {
            "label": "non_canonical_integer",
            "profile": {"steps": {"type": "Integer", "value": "007"},
                        "gain": {"type": "Float", "value": "0.5"}},
        },
        {
            "label": "non_canonical_list",
            "profile": {"channels": {"type": "List", "value": "(a,b,c)"}},
        },
        {
            "label": "empty_profile",
            "profile": {},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b95-") as tmp:
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
            reference = ref_check(case["profile"])

            matched = (product.get("valid") is True
                       and product.get("entries") == reference.get("entries")
                       and product.get("canonical") == reference.get("canonical")
                       and product.get("non_canonical") == reference.get("non_canonical"))
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
