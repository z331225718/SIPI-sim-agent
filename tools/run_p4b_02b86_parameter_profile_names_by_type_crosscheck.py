# -*- coding: utf-8 -*-
"""P4B-02b86 parameter profile names-by-type cross-check (product vs independent ref).

Drives the product names-by-type runner (p4b_02b86_parameter_profile_names_by_type_runner) over
validated profile maps plus a type token. An independent Python reference replicates the name
listing rule: names whose entries carry the requested declared type, sorted; unknown type tokens
fail closed. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b86-parameter-profile-names-by-type-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b86-parameter-profile-names-by-type-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b86.parameter-profile-names-by-type-v1.names-by-declared-type"

KNOWN_TYPES = ("Float", "Integer", "Boolean", "String", "List")


def ref_names_by_type(profile: dict[str, dict[str, str]], type_token: str) -> dict[str, Any]:
    if type_token not in KNOWN_TYPES:
        return {"valid": False, "error": "UnknownTypeToken"}
    names = sorted(name for name, entry in profile.items() if entry["type"] == type_token)
    return {"valid": True, "names": names}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b86_parameter_profile_names_by_type_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b86_parameter_profile_names_by_type_runner-*.exe"))[-1]

    cases = [
        {
            "label": "float_names",
            "profile": {"gain": {"type": "Float", "value": "0.5"},
                        "steps": {"type": "Integer", "value": "7"},
                        "offset": {"type": "Float", "value": "1.25"}},
            "type": "Float",
        },
        {
            "label": "integer_names",
            "profile": {"zeta": {"type": "Integer", "value": "3"},
                        "alpha": {"type": "Integer", "value": "1"},
                        "beta": {"type": "Integer", "value": "2"}},
            "type": "Integer",
        },
        {
            "label": "no_match",
            "profile": {"gain": {"type": "Float", "value": "0.5"}},
            "type": "List",
        },
        {
            "label": "unknown_type",
            "profile": {"gain": {"type": "Float", "value": "0.5"}},
            "type": "Nope",
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b86-") as tmp:
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
            reference = ref_names_by_type(case["profile"], case["type"])

            matched = (product.get("valid") == reference.get("valid")
                       and product.get("names") == reference.get("names")
                       and product.get("error") == reference.get("error"))
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
