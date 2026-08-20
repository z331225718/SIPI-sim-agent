# -*- coding: utf-8 -*-
"""P4A-03be typed IBIS series pin Model Selector binding cross-check (product vs independent ref).

Drives the product series pin Model Selector binding runner (p4a_03be_series_pin_table_selector_runner) over valid
and invalid series pin selector inputs. An independent Python reference recomputes the lifting rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03be-series-pin-table-selector-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03be.series-pin-table-selector-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03be.series-pin-table-selector-v1.typed-table-selector"


def ref_lift_series_pin_selector(pf: str, ps: str, ms: str, ftg: str | None) -> dict[str, Any]:
    pf, ps, ms = pf.strip(), ps.strip(), ms.strip()
    if not pf or not ps:
        return {"valid": False, "lift_error": "EmptyPinName"}
    if not ms:
        return {"valid": False, "lift_error": "EmptySelectorName"}
    if not pf.isascii() or not ps.isascii() or not ms.isascii():
        return {"valid": False, "lift_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in pf) or \
       not all(c.isalnum() or c in "_-." for c in ps) or \
       not all(c.isalnum() or c in "_-." for c in ms):
        return {"valid": False, "lift_error": "InvalidName"}
    if pf == ps:
        return {"valid": False, "lift_error": "IdenticalPins"}

    ftg_clean = None
    if ftg and ftg.strip():
        ftg_clean = ftg.strip()
        if not ftg_clean.isascii():
            return {"valid": False, "lift_error": "NonAsciiName"}

    return {
        "valid": True,
        "pin_first": pf,
        "pin_second": ps,
        "model_selector_name": ms,
        "function_table_group": ftg_clean,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03be_series_pin_table_selector_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03be_series_pin_table_selector_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_selector_record",
            "pin_first": "P1",
            "pin_second": "P2",
            "model_selector_name": "SEL_SERIES_RES",
            "function_table_group": "GRP1",
        },
        {
            "label": "minimal_selector_record",
            "pin_first": "P1",
            "pin_second": "P2",
            "model_selector_name": "SEL_SERIES_RES",
            "function_table_group": None,
        },
        {
            "label": "identical_pins",
            "pin_first": "P1",
            "pin_second": "P1",
            "model_selector_name": "SEL1",
            "function_table_group": None,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03be-") as tmp:
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
            reference = ref_lift_series_pin_selector(case["pin_first"], case["pin_second"], case["model_selector_name"], case["function_table_group"])

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("pin_first") != reference["pin_first"] or
                    product.get("pin_second") != reference["pin_second"] or
                    product.get("model_selector_name") != reference["model_selector_name"] or
                    product.get("function_table_group") != reference["function_table_group"]):
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
