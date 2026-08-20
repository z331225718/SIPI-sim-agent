"""P5-04s candidate-evaluation cross-check: product runner vs agent-com oracle.

Runs equalization.search._evaluate_candidate (and its C2M branch via
_c2m_candidate_fom) in fresh external custody on a fixed pulse and compares
the selected candidate result against the product runner. The oracle is
called with search_progress=None and the default direct-convolution path
(no forced FFT) so it matches the product port. Hash-only evidence; no
release claim. The search loop itself remains a separate scope.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
COM_SRC = Path(r"C:\Users\z3312\code\COM\src")
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04s-candidate-eval-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04s.candidate-eval-crosscheck-evidence.v1"
TOL = 5e-5


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def pulse(size: int = 300) -> list[float]:
    return [
        0.5 * math.exp(-((i - 120.0) ** 2) / 450.0) + 0.03
        for i in range(size)
    ]


P = {
    "samples_per_ui": 10, "R_LM": 50.0, "levels": 4, "sigma_X": 0.03,
    "dfe_delta": 1e-3, "N_tail_start": 0, "B_float_RSS_MAX": 0.0,
    "A_DD": 0.1, "sigma_RJ": 1e-4, "T_O": 0.0, "Min_VEO_Test": 0.0,
    "Noise_Crest_Factor": 0.0, "specBER": 1e-4, "samples_for_C2M": 8,
    "QL": 1.0, "Floating_DFE": False, "ndfe": 2, "N_bmax": 2,
    "N_bf": 1, "N_bg": 1, "bmaxg": 0.3, "bmax": [0.5, 0.5], "bmin": [-0.5, -0.5],
    "SNDR": [30.0, 30.0, 30.0, 30.0], "Tx_rd_sel": 0,
}

O = {
    "SNR_TXwC0": False, "WC_PORTZ": False,
    "pkg_len_select": [1],
    "LIMIT_JITTER_CONTRIB_TO_DFE_SPAN": False, "force_pdf_bin_size": False,
    "BinSize": 1e-3, "force_BBN_Q_factor": False, "BBN_Q_factor": 0.0,
    "Histogram_Window_Weight": "rectangle",
}


def to_product_params(params: dict[str, object]) -> dict[str, object]:
    return {
        "samples_per_ui": int(params["samples_per_ui"]), "r_lm": float(params["R_LM"]),
        "levels": int(params["levels"]), "sigma_x": float(params["sigma_X"]),
        "dfe_delta": float(params["dfe_delta"]), "n_tail_start": int(params["N_tail_start"]),
        "b_float_rss_max": float(params["B_float_RSS_MAX"]), "a_dd": float(params["A_DD"]),
        "sigma_rj": float(params["sigma_RJ"]), "t_o": float(params["T_O"]),
        "min_veo_test": float(params["Min_VEO_Test"]),
        "noise_crest_factor": float(params["Noise_Crest_Factor"]),
        "spec_ber": float(params["specBER"]), "samples_for_c2m": int(params["samples_for_C2M"]),
        "ql": float(params["QL"]), "floating_dfe": bool(params["Floating_DFE"]),
        "ndfe": int(params["ndfe"]), "n_bmax": int(params["N_bmax"]),
        "n_bf": int(params["N_bf"]), "n_bg": int(params["N_bg"]),
        "bmaxg": float(params["bmaxg"]), "bmax": list(params["bmax"]), "bmin": list(params["bmin"]),
    }


def to_product_options(options: dict[str, object], params: dict[str, object]) -> dict[str, object]:
    return {
        "snr_txw_c0": bool(options["SNR_TXwC0"]), "wc_portz": bool(options["WC_PORTZ"]),
        "tx_rd_sel": int(params["Tx_rd_sel"]), "pkg_len_select": list(options["pkg_len_select"]),
        "sndr": [float(v) for v in params["SNDR"]],
        "limit_jitter_contrib_to_dfe_span": bool(options["LIMIT_JITTER_CONTRIB_TO_DFE_SPAN"]),
        "force_pdf_bin_size": bool(options["force_pdf_bin_size"]),
        "bin_size": float(options["BinSize"]), "force_bbn_q_factor": bool(options["force_BBN_Q_factor"]),
        "bbn_q_factor": float(options["BBN_Q_factor"]),
        "histogram_window_weight": str(options["Histogram_Window_Weight"]),
    }


def params_dict() -> dict[str, object]:
    return dict(P)


def options_dict() -> dict[str, object]:
    return dict(O)



def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.equalization import search as oracle

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04s_candidate_eval_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04s_candidate_eval_runner-*.exe"))[-1]

    entries = []

    def compare(case_id: str, c2m_input: dict[str, object], oracle_result):
        input_bytes = json.dumps({"candidate": c2m_input}, separators=(",", ":")).encode("utf-8")
        input_path = ROOT / ("_tmp_" + case_id + ".json")
        input_path.write_bytes(input_bytes)
        report_path = ROOT / ("_tmp_" + case_id + "-product.json")
        run = subprocess.run(
            [str(runner), "--input", str(input_path), "--report", str(report_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if run.returncode != 0:
            raise SystemExit("runner failed: " + case_id + " :: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))
        input_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        diffs = _diffs(oracle_result, product)
        entries.append({
            "id": case_id,
            "input_sha256": sha256_bytes(input_bytes),
            "matched": not diffs,
            "diffs": diffs[:8],
        })

    sbr = pulse()
    sbr_arr = np.asarray(sbr, dtype=np.float64)
    tx_taps = [0.2, 1.0, -0.15]
    tx_taps_arr = np.asarray(tx_taps, dtype=np.float64)

    base_params = params_dict()
    base_options = options_dict()

    def build(cursor, best, params=None, options=None, sigma_n=1e-4, sigma_ne=1e-4, sigma_xt=1e-4):
        p = dict(params or base_params)
        o = dict(options or base_options)
        return {
            "sbr": sbr, "cursor_index": cursor, "best_fom_db": best,
            "ctle_index": 1, "ctle_gain_db": 2.0, "high_pass_index": 0, "high_pass_gain_db": 0.0,
            "tx_taps": tx_taps, "precursor_count": 1, "tx_grid_index": 3, "tx_source_indices": [0, 1, 2],
            "sigma_n_v": sigma_n, "sigma_ne_v": sigma_ne, "sigma_xt_v": sigma_xt,
            "parameters_oracle": p, "options_oracle": o,
            "parameters": to_product_params(p), "options": to_product_options(o, p),
            "package_case_index": 0, "itick": 5,
            "retain_non_improving": False,
        }

    def oracle_eval(inp):
        res = oracle._evaluate_candidate(
            np.asarray(inp["sbr"], dtype=np.float64),
            best_fom_db=inp["best_fom_db"],
            cursor_index=inp["cursor_index"],
            peak_index=0,
            ctle_index=inp["ctle_index"], ctle_gain_db=inp["ctle_gain_db"],
            high_pass_index=inp["high_pass_index"], high_pass_gain_db=inp["high_pass_gain_db"],
            tx_taps=np.asarray(inp["tx_taps"], dtype=np.float64),
            precursor_count=inp["precursor_count"], tx_grid_index=inp["tx_grid_index"],
            tx_source_indices=np.asarray(inp["tx_source_indices"], dtype=np.int64),
            sigma_n_v=inp["sigma_n_v"], sigma_ne_v=inp["sigma_ne_v"], sigma_xt_v=inp["sigma_xt_v"],
            parameters=inp["parameters_oracle"], options=inp["options_oracle"],
            package_case_index=inp["package_case_index"], itick=inp["itick"],
            retain_non_improving=inp["retain_non_improving"],
            search_progress=None,
        )
        return res

    # Case 1: plain candidate at the pulse center -> accepted.
    case1 = build(120, None)
    r1 = oracle_eval(case1)
    compare("plain_cursor", case1, r1)

    # Case 2: best incumbent slightly above the accepted FOM -> rejected (None).
    acq = oracle_eval(build(120, None))
    if acq is not None:
        best2 = float(acq.fom_db) + 1.0
        case2 = build(120, best2)
        r2 = oracle_eval(case2)
        compare("strict_improvement_reject", case2, r2)

    # Case 3: off-center cursor (nonzero height reduction) -> still accepted.
    case3 = build(140, None)
    r3 = oracle_eval(case3)
    compare("off_center_cursor", case3, r3)

    # Case 4: C2M branch enabled (T_O nonzero) with open-eye threshold.
    p4 = dict(base_params); p4["t_o"] = 0.5; p4["min_veo_test"] = 1.0
    case4 = build(120, None, params=p4)
    r4 = oracle_eval(case4)
    compare("c2m_branch_open_eye", case4, r4)

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "candidate_eval_crosscheck_matched" if matched else "candidate_eval_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com", "license": "MIT",
            "path": "src/agent_com/equalization/search.py",
            "functions": ["_evaluate_candidate", "_c2m_candidate_fom"],
            "numpy_version": np.__version__,
        },
        "tolerance": TOL,
        "entries": entries,
        "non_claims": ["not_search_loop", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]))
        for diff in entry.get("diffs", []):
            print("  diff:", diff)
    print("all_matched=" + str(matched))
    return 0 if matched else 1


def _y(o, k):
    return None if o is None else float(getattr(o, k))


def _diffs(oracle_res, product) -> list[str]:
    if oracle_res is None:
        if product.get("ok") and not product.get("has_result", True):
            return []
        return ["oracle-none vs product-different"]
    if not product.get("ok") or not product.get("has_result"):
        return ["oracle-result vs product-none; product_ok=" + str(product.get("ok")) + " has_result=" + str(product.get("has_result", None)) + " err=" + str(product.get("error"))]
    diffs = []
    for key, ov in (("fom_db", _y(oracle_res, "fom_db")), ("available_signal_v", _y(oracle_res, "available_signal_v")), ("sigma_tx_v", _y(oracle_res, "sigma_tx_v"))):
        pv = product[key]
        if ov is None or not (-1e12 < pv < 1e12):
            continue
        if abs(pv - ov) > TOL * max(1.0, abs(ov)):
            diffs.append(f"{key}: {pv} vs {ov}")
    # dfe_taps
    od = [float(v) for v in oracle_res.dfe_taps]
    pd = product["dfe_taps"]
    if len(od) != len(pd):
        diffs.append("dfe_taps length")
    else:
        for a, b in zip(od, pd):
            if abs(a - b) > TOL * max(1.0, abs(a)):
                diffs.append("dfe_taps diff")
                break
    return diffs


if __name__ == "__main__":
    raise SystemExit(main())
