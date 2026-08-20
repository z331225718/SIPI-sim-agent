# -*- coding: utf-8 -*-
"""P4B-02b96 parameter profile fingerprint cross-check (product vs independent ref).

Drives the product fingerprint runner (p4b_02b96_parameter_profile_fingerprint_runner) over
validated profile maps. An independent Python reference serializes the profile with sorted keys
and compact separators (matching 02b81) and applies FNV-1a 64. Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b96-parameter-profile-fingerprint-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b96-parameter-profile-fingerprint-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b96.parameter-profile-fingerprint-v1.fnv1a64-canonical-profile"

FNV1A64_OFFSET_BASIS = 14695981039346656037
FNV1A64_PRIME = 1099511628211
MASK64 = (1 << 64) - 1


def ref_fnv1a64(data: bytes) -> int:
    h = FNV1A64_OFFSET_BASIS
    for b in data:
        h ^= b
        h = (h * FNV1A64_PRIME) & MASK64
    return h


def ref_hash(profile: dict[str, dict[str, str]]) -> dict[str, Any]:
    serialized = json.dumps(profile, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False)
    return {"valid": True, "hash": ref_fnv1a64(serialized.encode("utf-8"))}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--test", "p4b_02b96_parameter_profile_fingerprint_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4b_02b96_parameter_profile_fingerprint_runner-*.exe"))[-1]

    cases = [
        {
            "label": "simple_profile",
            "profile": {"gain": {"type": "Float", "value": "0.5"},
                        "steps": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "sorted_order",
            "profile": {"zeta": {"type": "Float", "value": "1.0"},
                        "alpha": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "empty_profile",
            "profile": {},
        },
        {
            "label": "spelling_differs",
            "profile": {"gain": {"type": "Float", "value": "0.50"}},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b96-") as tmp:
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
            reference = ref_hash(case["profile"])

            matched = (product.get("valid") is True
                       and product.get("hash") == reference.get("hash"))
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
