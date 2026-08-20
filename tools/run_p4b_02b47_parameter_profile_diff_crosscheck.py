# -*- coding: utf-8 -*-
"""P4B-02b47 AMI parameter profile diff cross-check (product vs independent ref).

Drives the product profile diff runner (p4b_02b47_parameter_profile_diff_runner) over two
caller-supplied parameter maps. An independent Python reference replicates the by-name comparison.
Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b47-parameter-profile-diff-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b47-parameter-profile-diff-crosscheck-evidence.v1"
POLICY = "sipi.p4b-02b47.parameter-profile-diff-v1.profile-comparison"


def ref_diff(a: dict[str, dict[str, str]], b: dict[str, dict[str, str]]) -> dict[str, Any]:
    matched = 0
    added: list[str] = []
    removed: list[str] = []
    changed: list[dict[str, Any]] = []
    for name in sorted(a.keys()):
        old = a[name]
        if name not in b:
            removed.append(name)
        elif b[name] == old:
            matched += 1
        else:
            changed.append({"name": name, "old": dict(old), "new": dict(b[name])})
    for name in sorted(b.keys()):
        if name not in a:
            added.append(name)
    return {"valid": True, "matched": matched, "added": added,
            "removed": removed, "changed": changed}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b47_parameter_profile_diff_runner"

    cases = [
        {
            "label": "identical",
            "a": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "b": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
        },
        {
            "label": "added_and_removed",
            "a": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
            "b": {"gain": {"type": "Float", "value": "0.5"}, "enabled": {"type": "Boolean", "value": "True"}},
        },
        {
            "label": "value_change",
            "a": {"gain": {"type": "Float", "value": "0.5"}},
            "b": {"gain": {"type": "Float", "value": "1.25"}},
        },
        {
            "label": "empty_a",
            "a": {},
            "b": {"gain": {"type": "Float", "value": "0.5"}, "steps": {"type": "Integer", "value": "7"}},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b47-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / f"{case['label']}_in.json"
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / f"{case['label']}_rep.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_diff(case["a"], case["b"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("matched") != reference.get("matched") or
                    product.get("added") != reference.get("added") or
                    product.get("removed") != reference.get("removed") or
                    product.get("changed") != reference.get("changed")):
                    matched = False
            else:
                prod_err = product.get("input_error")
                ref_err = "invalid_profile" if not reference.get("valid") else None
                if str(prod_err) != str(ref_err):
                    matched = False

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
