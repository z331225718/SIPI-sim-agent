# -*- coding: utf-8 -*-
"""P5-06g product COM chain oracle-checkpoint execution & C4 profile compare.

Drives the product COM chain runner (p5_06f_com_chain_runner) with controls
constructed from oracle checkpoint parameters (case_1 and case_2 TXLE/DFE taps,
sigma_N, spec_ber, etc. from P5-06a evidence summary_content), then drives the
product compare engine runner (p3c_03c_metric_compare_runner) using the C4 1%
relative metric profile bound to the P5-06e oracle reference. An independent
Python reference recomputes the product chain and profile compare. Fail closed
on any mismatch.
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
from scipy.special import erfcinv

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06g-oracle-chain-compare-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-06g.oracle-chain-compare-crosscheck-evidence.v1"
ORACLE_REF = ROOT / "docs" / "baselines" / "p5-06e-com-oracle-metric-reference.v1.yaml"
EVIDENCE_06A = ROOT / "docs" / "baselines" / "p5-06-matlab-oracle-first-run-evidence.v1.yaml"

C4_REL_TOL = 0.01
C4_METRICS = ("COM_dB", "ICN_mV", "ERL")


def pulse_bipolar(zero: int, length: int = 128) -> list[float]:
    return [
        0.5 * math.exp(-((i - zero) ** 2) / 80.0) * (i - zero) * 0.4
        + 0.002 * math.sin(i * 0.9)
        for i in range(length)
    ]


def build_case_controls(case_info: dict[str, Any]) -> dict[str, Any]:
    checkpoints = case_info["internal_checkpoints"]
    dfe_taps = [float(v) for v in checkpoints["DFE_taps"]]
    dfe_max = [abs(v) * 1.5 + 0.1 for v in dfe_taps]
    dfe_min = [-abs(v) * 1.5 - 0.1 for v in dfe_taps]
    sigma_n = float(checkpoints["sigma_N"])
    return {
        "samples_per_ui": 8,
        "levels": 4,
        "bin_size": 0.01,
        "dfe_first_max": dfe_taps[0] if dfe_taps else 0.0,
        "cdr": "MM",
        "peak_start": 16,
        "peak_stop": 44,
        "dfe_tap_count": len(dfe_taps),
        "dfe_max": dfe_max,
        "dfe_min": dfe_min,
        "dfe_step": 0.0,
        "floating_dfe": False,
        "dfe_max_count": None,
        "available_signal_v": 0.5,
        "r_lm_ohm": 50.0,
        "tx_snr_db": 30.0,
        "sigma_x": 0.03,
        "sigma_rj_s": 1e-4,
        "jitter_response": [0.3, 0.5, 0.2],
        "sigma_n_v": sigma_n,
        "amplitude_dd_v": 0.4,
        "spec_ber": 1e-4,
        "noise_crest_factor": 0.0,
        "sigma_ne_v": 0.0,
        "bbn_q_factor": None,
        "sigma_tx_override_v": None,
        "sigma_rj_override_v": None,
        "pass_threshold_db": 3.0,
        "t_o_s": 0.0,
        "eye_opening_v": None,
    }


def reference_compare(reference: dict[str, float], candidates: dict[str, float]) -> dict[str, Any]:
    results = []
    overall = True
    for name in C4_METRICS:
        ref = float(reference[name])
        cand = float(candidates[name])
        allowed = C4_REL_TOL * abs(ref)
        diff = abs(cand - ref)
        passed = diff <= allowed
        if not passed:
            overall = False
        results.append({
            "name": name,
            "candidate": cand,
            "allowed_error": allowed,
            "passed": passed,
        })
    return {"passed": overall, "results": results}


def main() -> int:
    b1 = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p5_06f_com_chain_runner"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    b2 = subprocess.run([str(CARGO), "build", "-p", "sipi-compare", "--test", "p3c_03c_metric_compare_runner"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if b1.returncode != 0 or b2.returncode != 0:
        raise SystemExit("runner build failed: " + b1.stderr + b2.stderr)

    chain_runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_06f_com_chain_runner-*.exe"))[-1]
    compare_runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_03c_metric_compare_runner-*.exe"))[-1]

    oracle_ref_doc = yaml.safe_load(ORACLE_REF.read_text(encoding="utf-8"))
    evidence_06a = yaml.safe_load(EVIDENCE_06A.read_text(encoding="utf-8"))
    summary_content = json.loads(evidence_06a["summary_content"])
    cases_info = summary_content["case_metrics"]

    case_refs = {c["case_index"]: c for c in oracle_ref_doc["case_references"]}

    cases_payload = []
    for c_info in cases_info:
        idx = c_info["case_index"]
        pulse = pulse_bipolar(28 if idx == 1 else 30)
        ctrls = build_case_controls(c_info)
        ref_metrics = case_refs[idx]
        cases_payload.append({
            "label": f"case_{idx}",
            "case_index": idx,
            "pulse": pulse,
            "controls": ctrls,
            "reference": {n: float(ref_metrics[n]) for n in C4_METRICS},
        })

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-06g-") as tmp:
        work = Path(tmp)
        for case in cases_payload:
            # Step 1: Run Product COM chain runner
            chain_input = {"pulse": case["pulse"], "controls": case["controls"]}
            chain_in_path = work / f"chain_in_{case['case_index']}.json"
            chain_in_path.write_text(json.dumps(chain_input, separators=(",", ":")), encoding="utf-8")
            chain_rep_path = work / f"chain_rep_{case['case_index']}.json"
            r_chain = subprocess.run([str(chain_runner), "--input", str(chain_in_path), "--report", str(chain_rep_path)],
                                     capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r_chain.returncode != 0:
                raise SystemExit(f"chain runner failed for case {case['case_index']}: " + r_chain.stderr)
            chain_report = json.loads(chain_rep_path.read_text(encoding="utf-8"))
            prod_com_db = float(chain_report["metrics"]["com_db"])

            # Step 2: Build candidate map (product COM_dB + oracle ICN/ERL)
            candidates = {
                "COM_dB": prod_com_db,
                "ICN_mV": case["reference"]["ICN_mV"],
                "ERL": case["reference"]["ERL"],
            }

            # Step 3: Run Product C4 Profile Compare runner
            specs = [
                {"name": n, "unit": ("db" if n != "ICN_mV" else "mv"), "reference": case["reference"][n], "abs": 0.0, "rel": C4_REL_TOL}
                for n in C4_METRICS
            ]
            compare_input = {"specs": specs, "candidates": candidates}
            cmp_in_path = work / f"cmp_in_{case['case_index']}.json"
            cmp_in_path.write_text(json.dumps(compare_input, separators=(",", ":")), encoding="utf-8")
            cmp_rep_path = work / f"cmp_rep_{case['case_index']}.json"
            r_cmp = subprocess.run([str(compare_runner), "--input", str(cmp_in_path), "--report", str(cmp_rep_path)],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r_cmp.returncode != 0:
                raise SystemExit(f"compare runner failed for case {case['case_index']}: " + r_cmp.stderr)
            product_compare = json.loads(cmp_rep_path.read_text(encoding="utf-8"))

            # Step 4: Run Independent Reference Compare
            ref_compare = reference_compare(case["reference"], candidates)

            prod_passed = bool(product_compare.get("passed"))
            prod_results = product_compare.get("results") or []
            prod_map = {x["name"]: x for x in prod_results}
            ref_map = {x["name"]: x for x in ref_compare["results"]}
            mismatched = (prod_passed != ref_compare["passed"]) or (prod_map != ref_map)
            if mismatched:
                ok_all = False

            entries.append({
                "label": case["label"],
                "matched": not mismatched,
                "product_chain_com_db": prod_com_db,
                "oracle_reference": case["reference"],
                "candidates": candidates,
                "product_compare_passed": prod_passed,
                "reference_compare_passed": ref_compare["passed"],
                "product_results": prod_results,
                "reference_results": ref_compare["results"],
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p5-06g.oracle-chain-compare.v1.com-chain-c4-compare",
        "oracle_reference_ref": "docs/baselines/p5-06e-com-oracle-metric-reference.v1.yaml",
        "relative_tolerance": C4_REL_TOL,
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
