# -*- coding: utf-8 -*-
"""P4A-03ae typed IBIS package model keywords cross-check (product vs independent ref).

Drives the product package model keywords runner (p4a_03ae_package_model_keywords_runner) over valid
and invalid package model inputs. An independent Python reference recomputes the lifting rules.
Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03ae-package-model-keywords-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03ae.package-model-keywords-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03ae.package-model-keywords-v1.typed-package-keywords"


def ref_lift_package_model_keywords(pname: str, npins: int, pins: list[str]) -> dict[str, Any]:
    if not pname or not pname.strip():
        return {"valid": False, "lift_error": "EmptyPackageModelName"}
    p_trimmed = pname.strip()
    if not p_trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in p_trimmed):
        return {"valid": False, "lift_error": "InvalidName"}
    if npins == 0:
        return {"valid": False, "lift_error": "InvalidNumberOfPins"}
    if not pins:
        return {"valid": False, "lift_error": "EmptyPinNumbers"}

    seen = set()
    clean_pins = []
    for pin in pins:
        pt = pin.strip()
        if not pt:
            return {"valid": False, "lift_error": "EmptyPackageModelName"}
        if not pt.isascii():
            return {"valid": False, "lift_error": "NonAsciiName"}
        if not all(c.isalnum() or c in "_-." for c in pt):
            return {"valid": False, "lift_error": "InvalidName"}
        if pt in seen:
            return {"valid": False, "lift_error": f'DuplicatePinNumber("{pt}")'}
        seen.add(pt)
        clean_pins.append(pt)

    return {
        "valid": True,
        "package_model_name": p_trimmed,
        "number_of_pins": npins,
        "pin_numbers": clean_pins,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03ae_package_model_keywords_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03ae_package_model_keywords_runner-*.exe"))[-1]

    cases = [
        {
            "label": "valid_package_model_keywords",
            "package_model_name": "PKG_BGA_100",
            "number_of_pins": 2,
            "pin_numbers": ["A1", "A2"],
        },
        {
            "label": "zero_number_of_pins",
            "package_model_name": "PKG_BGA",
            "number_of_pins": 0,
            "pin_numbers": ["A1"],
        },
        {
            "label": "duplicate_pin_number",
            "package_model_name": "PKG_BGA",
            "number_of_pins": 2,
            "pin_numbers": ["A1", "A1"],
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03ae-") as tmp:
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
            reference = ref_lift_package_model_keywords(case["package_model_name"], case["number_of_pins"], case["pin_numbers"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("package_model_name") != reference["package_model_name"] or
                    product.get("number_of_pins") != reference["number_of_pins"] or
                    product.get("pin_numbers") != reference["pin_numbers"]):
                    matched = False
            else:
                if str(product.get("lift_error")) != str(reference.get("lift_error")):
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
