# -*- coding: utf-8 -*-
"""P4A-03bg typed IBIS series pin Model Selector threshold table cross-check (product vs independent ref).

Drives the product series pin Model Selector threshold runner (p4a_03bg_series_pin_table_selector_thresholds_runner) over valid
and invalid series pin selector threshold inputs. An independent Python reference recomputes the lifting rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03bg-series-pin-table-selector-thresholds-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03bg.series-pin-table-selector-thresholds-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03bg.series-pin-table-selector-thresholds-v1.typed-selector-thresholds"


def ref_lift_series_pin_selector_threshold(pf: str, ps: str, ms: str, vthresh: float | None, rseries: float | None,
                                            cseries: float | None, lseries: float | None) -> dict[str, Any]:
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

    if vthresh is not None and not math.isfinite(vthresh):
        return {"valid": False, "lift_error": "NonFiniteValue"}

    for v in (rseries, cseries, lseries):
        if v is not None:
            if not math.isfinite(v):
                return {"valid": False, "lift_error": "NonFiniteValue"}
            if v < 0.0:
                return {"valid": False, "lift_error": "NegativeThresholdParameter"}

    return {
        "valid": True,
        "pin_first": pf,
        "pin_second": ps,
        "model_selector_name": ms,
        "vthreshold_v": vthresh,
        "rseries_ohm": rseries,
        "cseries_farad": cseries,
        "lseries_henry": lseries,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03bg_series_pin_table_selector_thresholds_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03bg_series_pin_table_selector_thresholds_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_selector_threshold_record",
            "pin_first": "P1",
            "pin_second": "P2",
            "model_selector_name": "SEL_SERIES_RES",
            "vthreshold_v": 1.2,
            "rseries_ohm": 50.0,
            "cseries_farad": 1e-12,
            "lseries_henry": 5e-9,
        },
        {
            "label": "minimal_selector_threshold_record",
            "pin_first": "P1",
            "pin_second": "P2",
            "model_selector_name": "SEL_SERIES_RES",
            "vthreshold_v": None,
            "rseries_ohm": None,
            "cseries_farad": None,
            "lseries_henry": None,
        },
        {
            "label": "empty_pin_name",
            "pin_first": "",
            "pin_second": "P2",
            "model_selector_name": "SEL1",
            "vthreshold_v": None,
            "rseries_ohm": None,
            "cseries_farad": None,
            "lseries_henry": None,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03bg-") as tmp:
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
            reference = ref_lift_series_pin_selector_threshold(
                case["pin_first"], case["pin_second"], case["model_selector_name"],
                case["vthreshold_v"], case["rseries_ohm"], case["cseries_farad"], case["lseries_henry"]
            )

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("pin_first") != reference["pin_first"] or
                    product.get("pin_second") != reference["pin_second"] or
                    product.get("model_selector_name") != reference["model_selector_name"] or
                    product.get("vthreshold_v") != reference["vthreshold_v"] or
                    product.get("rseries_ohm") != reference["rseries_ohm"] or
                    product.get("cseries_farad") != reference["cseries_farad"] or
                    product.get("lseries_henry") != reference["lseries_henry"]):
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
