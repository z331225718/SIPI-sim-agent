# -*- coding: utf-8 -*-
"""P4A-03r typed IBIS test data cross-check (product vs independent ref).

Drives the product test data runner (p4a_03r_test_data_runner) over valid
and invalid test fixture inputs. An independent Python reference recomputes the lifting rules.
Fail closed on any mismatch.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03r-test-data-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03r.test-data-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03r.test-data-declaration-v1.typed-test-data"


def ref_lift_test_data(fname: str, r_fix: float | None, c_fix: float | None,
                        l_fix: float | None, v_fix: float | None) -> dict[str, Any]:
    if not fname or not fname.strip():
        return {"valid": False, "lift_error": "EmptyFixtureName"}
    trimmed = fname.strip()
    if not trimmed.isascii():
        return {"valid": False, "lift_error": "NonAsciiFixtureName"}
    if not all(c.isalnum() or c in "_-." for c in trimmed):
        return {"valid": False, "lift_error": "InvalidFixtureName"}

    for v in (r_fix, c_fix, l_fix):
        if v is not None:
            if not math.isfinite(v):
                return {"valid": False, "lift_error": "NonFiniteValue"}
            if v < 0.0:
                return {"valid": False, "lift_error": "NegativeFixtureParameter"}

    if v_fix is not None and not math.isfinite(v_fix):
        return {"valid": False, "lift_error": "NonFiniteValue"}

    return {
        "valid": True,
        "fixture_name": trimmed,
        "r_fixture_ohm": r_fix,
        "c_fixture_farad": c_fix,
        "l_fixture_henry": l_fix,
        "v_fixture_volts": v_fix,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03r_test_data_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03r_test_data_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_test_data",
            "fixture_name": "FIX_DUT_1",
            "r_fixture_ohm": 50.0,
            "c_fixture_farad": 2e-12,
            "l_fixture_henry": 1e-9,
            "v_fixture_volts": 1.5,
        },
        {
            "label": "minimal_test_data",
            "fixture_name": "FIX_MIN",
            "r_fixture_ohm": None,
            "c_fixture_farad": None,
            "l_fixture_henry": None,
            "v_fixture_volts": None,
        },
        {
            "label": "negative_r_fixture",
            "fixture_name": "FIX",
            "r_fixture_ohm": -50.0,
            "c_fixture_farad": None,
            "l_fixture_henry": None,
            "v_fixture_volts": None,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03r-") as tmp:
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
            reference = ref_lift_test_data(
                case["fixture_name"], case["r_fixture_ohm"],
                case["c_fixture_farad"], case["l_fixture_henry"], case["v_fixture_volts"]
            )

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("fixture_name") != reference["fixture_name"] or
                    product.get("r_fixture_ohm") != reference["r_fixture_ohm"] or
                    product.get("c_fixture_farad") != reference["c_fixture_farad"] or
                    product.get("l_fixture_henry") != reference["l_fixture_henry"] or
                    product.get("v_fixture_volts") != reference["v_fixture_volts"]):
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
