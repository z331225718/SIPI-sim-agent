# -*- coding: utf-8 -*-
"""P4A-03ah typed IBIS receiver thresholds block keywords cross-check (product vs independent ref).

Drives the product receiver thresholds block runner (p4a_03ah_receiver_thresholds_keywords_runner) over valid
and invalid receiver thresholds block inputs. An independent Python reference recomputes the lifting rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03ah-receiver-thresholds-keywords-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03ah.receiver-thresholds-keywords-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03ah.receiver-thresholds-keywords-v1.typed-receiver-keywords"


def ref_lift_receiver_thresholds_block(vc_low: float | None, vc_high: float | None,
                                        vdiff_ac: float | None, vdiff_dc: float | None,
                                        tskew: float | None, vsens: float | None) -> dict[str, Any]:
    for v in (vc_low, vc_high):
        if v is not None and not math.isfinite(v):
            return {"valid": False, "threshold_error": "NonFiniteValue"}

    for v in (vdiff_ac, vdiff_dc, tskew):
        if v is not None:
            if not math.isfinite(v):
                return {"valid": False, "threshold_error": "NonFiniteValue"}
            if v < 0.0:
                return {"valid": False, "threshold_error": "NegativeThreshold"}

    if vsens is not None:
        if not math.isfinite(vsens):
            return {"valid": False, "lift_error": "NonFiniteValue"}
        if vsens < 0.0:
            return {"valid": False, "lift_error": "NegativeSensitivity"}

    return {
        "valid": True,
        "vcross_low_v": vc_low,
        "vcross_high_v": vc_high,
        "vdiff_ac_v": vdiff_ac,
        "vdiff_dc_v": vdiff_dc,
        "tskew_s": tskew,
        "vsensitivity_v": vsens,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03ah_receiver_thresholds_keywords_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03ah_receiver_thresholds_keywords_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_receiver_thresholds_block",
            "vcross_low_v": 0.8,
            "vcross_high_v": 1.2,
            "vdiff_ac_v": 0.15,
            "vdiff_dc_v": None,
            "tskew_s": None,
            "vsensitivity_v": 0.05,
        },
        {
            "label": "minimal_receiver_thresholds_block",
            "vcross_low_v": None,
            "vcross_high_v": None,
            "vdiff_ac_v": None,
            "vdiff_dc_v": None,
            "tskew_s": None,
            "vsensitivity_v": None,
        },
        {
            "label": "negative_sensitivity",
            "vcross_low_v": 0.8,
            "vcross_high_v": 1.2,
            "vdiff_ac_v": None,
            "vdiff_dc_v": None,
            "tskew_s": None,
            "vsensitivity_v": -0.05,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03ah-") as tmp:
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
            reference = ref_lift_receiver_thresholds_block(
                case["vcross_low_v"], case["vcross_high_v"],
                case["vdiff_ac_v"], case["vdiff_dc_v"], case["tskew_s"], case["vsensitivity_v"]
            )

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("vcross_low_v") != reference["vcross_low_v"] or
                    product.get("vcross_high_v") != reference["vcross_high_v"] or
                    product.get("vdiff_ac_v") != reference["vdiff_ac_v"] or
                    product.get("vdiff_dc_v") != reference["vdiff_dc_v"] or
                    product.get("tskew_s") != reference["tskew_s"] or
                    product.get("vsensitivity_v") != reference["vsensitivity_v"]):
                    matched = False
            else:
                prod_err = product.get("lift_error") or product.get("threshold_error")
                ref_err = reference.get("lift_error") or reference.get("threshold_error")
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
