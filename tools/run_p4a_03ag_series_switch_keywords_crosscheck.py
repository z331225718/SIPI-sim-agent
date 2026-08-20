# -*- coding: utf-8 -*-
"""P4A-03ag typed IBIS series switch block keywords cross-check (product vs independent ref).

Drives the product series switch block runner (p4a_03ag_series_switch_keywords_runner) over valid
and invalid series switch block inputs. An independent Python reference recomputes the lifting rules.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p4a-03ag-series-switch-keywords-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4a-03ag.series-switch-keywords-crosscheck-evidence.v1"
POLICY = "sipi.p4a-03ag.series-switch-keywords-v1.typed-switch-keywords"


def ref_lift_series_switch_block(on_g: str, off_g: str,
                                  vthresh: float | None, rseries: float | None,
                                  cseries: float | None, lseries: float | None) -> dict[str, Any]:
    on_g, off_g = on_g.strip(), off_g.strip()
    if not on_g or not off_g:
        return {"valid": False, "record_error": "EmptyGroupName"}
    if not on_g.isascii() or not off_g.isascii():
        return {"valid": False, "record_error": "NonAsciiName"}
    if not all(c.isalnum() or c in "_-." for c in on_g) or \
       not all(c.isalnum() or c in "_-." for c in off_g):
        return {"valid": False, "record_error": "InvalidName"}
    if on_g == off_g:
        return {"valid": False, "record_error": "IdenticalGroups"}

    has_thresh = (vthresh is not None or rseries is not None or cseries is not None or lseries is not None)
    thresh_clean = None

    if has_thresh:
        if vthresh is not None and not math.isfinite(vthresh):
            return {"valid": False, "threshold_error": "NonFiniteValue"}
        for v in (rseries, cseries, lseries):
            if v is not None:
                if not math.isfinite(v):
                    return {"valid": False, "threshold_error": "NonFiniteValue"}
                if v < 0.0:
                    return {"valid": False, "threshold_error": "NegativeThresholdParameter"}
        thresh_clean = {
            "vthreshold_v": vthresh,
            "rseries_ohm": rseries,
            "cseries_farad": cseries,
            "lseries_henry": lseries,
        }

    return {
        "valid": True,
        "on_group_name": on_g,
        "off_group_name": off_g,
        "thresholds": thresh_clean,
    }


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ibis", "--test", "p4a_03ag_series_switch_keywords_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p4a_03ag_series_switch_keywords_runner-*.exe"))[-1]

    cases = [
        {
            "label": "full_series_switch_block",
            "on_group_name": "GROUP_ON_1",
            "off_group_name": "GROUP_OFF_1",
            "vthreshold_v": 1.8,
            "rseries_ohm": 10.0,
            "cseries_farad": None,
            "lseries_henry": None,
        },
        {
            "label": "minimal_series_switch_block",
            "on_group_name": "GROUP_ON_1",
            "off_group_name": "GROUP_OFF_1",
            "vthreshold_v": None,
            "rseries_ohm": None,
            "cseries_farad": None,
            "lseries_henry": None,
        },
        {
            "label": "identical_groups_switch",
            "on_group_name": "GROUP_1",
            "off_group_name": "GROUP_1",
            "vthreshold_v": None,
            "rseries_ohm": None,
            "cseries_farad": None,
            "lseries_henry": None,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4a-03ag-") as tmp:
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
            reference = ref_lift_series_switch_block(
                case["on_group_name"], case["off_group_name"],
                case["vthreshold_v"], case["rseries_ohm"], case["cseries_farad"], case["lseries_henry"]
            )

            matched = True
            if product.get("valid") != reference["valid"]:
                matched = False
            elif product.get("valid"):
                if (product.get("on_group_name") != reference["on_group_name"] or
                    product.get("off_group_name") != reference["off_group_name"] or
                    product.get("thresholds") != reference["thresholds"]):
                    matched = False
            else:
                prod_err = product.get("lift_error") or product.get("record_error") or product.get("threshold_error")
                ref_err = reference.get("lift_error") or reference.get("record_error") or reference.get("threshold_error")
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
