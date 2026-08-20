# -*- coding: utf-8 -*-
"""P4B-02b81 parameter profile canonical serialization cross-check (product vs independent ref).

Drives the product serialization runner (p4b_02b81_parameter_profile_serialization_runner) over
validated profile maps. An independent Python reference serializes the profile to the same
canonical compact JSON with sorted names. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b81-parameter-profile-serialization-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b81-parameter-profile-serialization-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b81.parameter-profile-serialization-v1.canonical-profile-json"


def ref_serialize(profile: dict[str, dict[str, str]]) -> dict[str, Any]:
    return {"valid": True, "serialized": json.dumps(profile, sort_keys=True,
                                                    separators=(",", ":"),
                                                    ensure_ascii=False)}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b81_parameter_profile_serialization_runner"

    cases = [
        {
            "label": "simple_profile",
            "profile": {"gain": {"type": "Float", "value": "0.5"}},
        },
        {
            "label": "sorted_order",
            "profile": {"zeta": {"type": "Float", "value": "1.0"},
                        "alpha": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "mixed_types",
            "profile": {"on": {"type": "Boolean", "value": "True"},
                        "mode": {"type": "String", "value": "Linear"},
                        "channels": {"type": "List", "value": "(a, b)"}},
        },
        {
            "label": "empty_profile",
            "profile": {},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b81-") as tmp:
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
            reference = ref_serialize(case["profile"])

            matched = (product.get("valid") is True
                       and product.get("serialized") == reference.get("serialized"))
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
