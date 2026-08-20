# -*- coding: utf-8 -*-
"""P4A-03h typed IBIS package model declaration cross-check (product vs independent ref).

Drives the product package model declaration runner (p4a_03h_package_model_runner)
over valid and invalid package model declaration inputs. An independent Python reference
recomputes the lifting rules. Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03h-package-model-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03h.package-model-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03h.package-model-declaration-v1.typed-package-model"


def ref_lift_package_model(name: str, r_pkg: float | None, l_pkg: float | None, c_pkg: float | None) -> dict[str, Any]:
    if not name or not name.strip():
        return {"valid": False, "lift_error": "EmptyName"}
    trimmed = name.strip()
    if not trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    for v in (r_pkg, l_pkg, c_pkg):
        if v is not None:
            if not math.isfinite(v):
                return {"valid": False, "lift_error": "NonFiniteValue"}
            if v < 0.0:
                return {"valid": False, "lift_error": "NegativeValue"}
    return {
        "valid": True,
        "name": trimmed,
        "r_pkg_ohm": r_pkg,
        "l_pkg_henry": l_pkg,
        "c_pkg_farad": c_pkg,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03h_package_model_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03h_package_model_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_package_model",
            "name": "FBGA84_PKG",
            "r_pkg_ohm": 0.1,
            "l_pkg_henry": 1e-9,
            "c_pkg_farad": 1e-12,
        },
        {
            "label": "minimal_package_model",
            "name": "PKG_MIN",
            "r_pkg_ohm": None,
            "l_pkg_henry": None,
            "c_pkg_farad": None,
        },
        {
            "label": "negative_r_pkg",
            "name": "PKG",
            "r_pkg_ohm": -0.1,
            "l_pkg_henry": None,
            "c_pkg_farad": None,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03h-") as tmp:
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
            reference = ref_lift_package_model(case["name"], case["r_pkg_ohm"], case["l_pkg_henry"], case["c_pkg_farad"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            if product.get("valid"):
                if (product.get("name") != reference["name"] or
                    product.get("r_pkg_ohm") != reference["r_pkg_ohm"] or
                    product.get("l_pkg_henry") != reference["l_pkg_henry"] or
                    product.get("c_pkg_farad") != reference["c_pkg_farad"]):
                    matched = False
            else:
                if product.get("lift_error") != reference["lift_error"]:
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
