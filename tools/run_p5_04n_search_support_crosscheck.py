"""P5-04n search support cross-check: product runner vs agent-com oracle.

Runs the parameter/frequency-response helpers in fresh external custody
(agent-com equalization search module private helpers) on fixed inputs
and compares every result against the product runner. Hash-only
evidence; no release claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import numpy as np
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
COM_SRC = Path(r"C:\Users\z3312\code\COM\src")
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04n-search-support-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04n.search-support-crosscheck-evidence.v1"
TOLERANCE = 1e-9


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def oracle_params(params: dict[str, object]) -> dict[str, object]:
    return {
        "ctle_gdc_values": np.asarray(params["ctle_gdc_values"], dtype=np.float64),
        "CTLE_fz": np.asarray(params["ctle_fz"], dtype=np.float64),
        "CTLE_fp1": np.asarray(params["ctle_fp1"], dtype=np.float64),
        "CTLE_fp2": np.asarray(params["ctle_fp2"], dtype=np.float64),
        "CTLE_type": params["ctle_type"],
        "f_HP": np.asarray(params["f_hp"], dtype=np.float64),
        "f_HP_Z": np.asarray(params["f_hp_z"], dtype=np.float64),
        "f_HP_P": np.asarray(params["f_hp_p"], dtype=np.float64),
    }


def waveform(seed: float, length: int = 64) -> list[float]:
    return [math.exp(-((i - 32.0) ** 2) / 120.0) * math.sin(i * 0.4 + seed) for i in range(length)]


PARAMS = {
    "ctle_gdc_values": [6.0, 3.0],
    "ctle_fz": [10e9, 8e9],
    "ctle_fp1": [30e9, 25e9],
    "ctle_fp2": [40e9, 45e9],
    "ctle_type": "CL120e",
    "f_hp": [0.0, -3.0],
    "f_hp_z": [5e9, 4e9],
    "f_hp_p": [1e9, 1.5e9],
}


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    from agent_com.equalization import search as oracle

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04n_search_support_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04n_search_support_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04n-crosscheck-") as tmp:
        work = Path(tmp)

        def compare(case_id: str, input_payload: dict[str, object], oracle_payload: dict[str, object], compare_fn) -> None:
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case_id + ".json")
            input_path.write_bytes(input_bytes)
            report_path = work / (case_id + "-product.json")
            run = subprocess.run(
                [str(runner), "--input", str(input_path), "--report", str(report_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if run.returncode != 0:
                raise SystemExit("runner failed: " + case_id + " :: " + run.stdout + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            diffs = compare_fn(oracle_payload, product)
            entries.append({
                "id": case_id,
                "input_sha256": sha256_bytes(input_bytes),
                "matched": not diffs,
                "diffs": diffs[:8],
            })

        # indexed config value (scalar broadcast + indexed)
        for label, payload, oracle_value in (
            ("indexed_scalar", {"values": [2.5], "index": 3}, 2.5),
            ("indexed_index", {"values": [1.0, 2.0, 3.0], "index": 2}, 3.0),
        ):
            expected = float(oracle._indexed_config_value(np.asarray(payload["values"], dtype=np.float64), payload["index"], "x"))
            compare("indexed_" + label, {"indexed": payload}, {"value": expected},
                    lambda o, p: [] if abs(p["indexed"]["value"] - o["value"]) <= TOLERANCE else ["value drift"])

        # high pass candidates
        for ctle_type, gains in (("CL120d", [0.0, -3.0, -6.0]), ("CL120e", []), ("CL120d", [2.0])):
            expected = oracle._high_pass_candidates({**PARAMS, "CTLE_type": ctle_type, "g_DC_HP_values": np.asarray(gains, dtype=np.float64)})
            compare("high_pass_" + ctle_type + "_" + str(len(gains)),
                    {"high_pass": {"ctle_type": ctle_type, "g_dc_hp_values": gains}},
                    {"candidates": [[int(i), float(g)] for i, g in expected]},
                    lambda o, p: [] if p["high_pass"]["candidates"] == o["candidates"] else ["candidates drift"])

        # qualified pair (gdc ceiling + gqual table)
        gqual = [[0.0, 6.0], [-6.0, 0.0]]
        g2qual = [0.0, -6.0]
        for label, payload in (
            ("table_ok", {"ctle_type": "CL120d", "g_dc_hp_values": [0.0, -3.0, -6.0], "ctle_gdc_values": [-3.0], "ctle_index": 0, "high_pass_index": 1, "gdc_min": 0.0, "gqual": gqual, "g2qual": g2qual}),
            ("table_outside", {"ctle_type": "CL120d", "g_dc_hp_values": [0.0, -3.0, -6.0], "ctle_gdc_values": [3.0], "ctle_index": 0, "high_pass_index": 1, "gdc_min": 0.0, "gqual": gqual, "g2qual": g2qual}),
            ("ceiling_over", {"ctle_type": "CL120d", "g_dc_hp_values": [0.0, -3.0], "ctle_gdc_values": [5.0], "ctle_index": 0, "high_pass_index": 1, "gdc_min": 1.0, "gqual": [], "g2qual": []}),
            ("no_table", {"ctle_type": "CL120d", "g_dc_hp_values": [0.0, -3.0], "ctle_gdc_values": [4.0], "ctle_index": 0, "high_pass_index": 1, "gdc_min": 1.0, "gqual": [], "g2qual": []}),
            ("non_cl120d", {"ctle_type": "CL120e", "g_dc_hp_values": [0.0], "ctle_gdc_values": [1.0], "ctle_index": 0, "high_pass_index": 0, "gdc_min": 0.0, "gqual": [], "g2qual": []}),
        ):
            gqual_arr = np.asarray(payload["gqual"], dtype=np.float64) if payload["gqual"] else np.asarray([], dtype=np.float64)
            g2qual_arr = np.asarray(payload["g2qual"], dtype=np.float64) if payload["g2qual"] else np.asarray([], dtype=np.float64)
            expected = bool(oracle._qualified_ctle_pair(
                payload["ctle_index"], payload["high_pass_index"],
                {**PARAMS, "CTLE_type": payload["ctle_type"], "g_DC_HP_values": np.asarray(payload["g_dc_hp_values"], dtype=np.float64),
                 "ctle_gdc_values": np.asarray(payload["ctle_gdc_values"], dtype=np.float64), "GDC_MIN": payload["gdc_min"],
                 "gqual": gqual_arr, "g2qual": g2qual_arr}))
            compare("qualified_" + label, {"qualified": payload}, {"admissible": expected},
                    lambda o, p: [] if p["qualified"]["admissible"] == o["admissible"] else ["admissible drift"])

        # selected sndr / accm
        expected_s = float(oracle._selected_sndr(
            {"SNDR": np.asarray([30.0, 28.0, 32.0])}, {"WC_PORTZ": False, "pkg_len_select": np.asarray([2, 3], dtype=np.int64)}, package_case_index=0))
        compare("sndr_pkg", {"sndr": {"sndr": [30.0, 28.0, 32.0], "wc_portz": False, "tx_rd_sel": 1, "pkg_len_select": [2, 3], "package_case_index": 0}},
                {"value": expected_s}, lambda o, p: [] if abs(p["sndr"]["value"] - o["value"]) <= TOLERANCE else ["sndr drift"])
        expected_wc = float(oracle._selected_sndr(
            {"SNDR": np.asarray([30.0, 28.0, 32.0]), "Tx_rd_sel": 3}, {"WC_PORTZ": True, "pkg_len_select": np.asarray([1], dtype=np.int64)}, package_case_index=0))
        compare("sndr_wc", {"sndr": {"sndr": [30.0, 28.0, 32.0], "wc_portz": True, "tx_rd_sel": 3, "pkg_len_select": [1], "package_case_index": 0}},
                {"value": expected_wc}, lambda o, p: [] if abs(p["sndr"]["value"] - o["value"]) <= TOLERANCE else ["sndr drift"])
        expected_a = float(oracle._selected_accm_rms(
            {"AC_CM_RMS": np.asarray([0.1, 0.2, 0.3])}, {"pkg_len_select": np.asarray([3], dtype=np.int64)}, package_case_index=0))
        compare("accm_pkg", {"accm": {"ac_cm_rms": [0.1, 0.2, 0.3], "pkg_len_select": [3], "package_case_index": 0}},
                {"value": expected_a}, lambda o, p: [] if abs(p["accm"]["value"] - o["value"]) <= TOLERANCE else ["accm drift"])

        # system noise response
        frequency = [0.0, 0.5e9, 1.0e9, 1.5e9, 2.0e9, 3.0e9]
        expected_off = [float(v) for v in oracle._r480_system_noise_response(np.asarray(frequency), {"USE_ETA0_PSD": False})]
        compare("eta0_off", {"system_noise": {"frequency": frequency, "use_eta0_psd": False}},
                {"response": expected_off}, lambda o, p: [] if abs(max([abs(a - b) for a, b in zip(p["system_noise"]["response"], o["response"])])) <= TOLERANCE else ["response drift"])
        expected_on = [float(v) for v in oracle._r480_system_noise_response(np.asarray(frequency), {"USE_ETA0_PSD": True})]
        compare("eta0_on", {"system_noise": {"frequency": frequency, "use_eta0_psd": True}},
                {"response": expected_on}, lambda o, p: [] if abs(max([abs(a - b) for a, b in zip(p["system_noise"]["response"], o["response"])])) <= TOLERANCE else ["response drift"])

        # ctle frequency response (CL120e and CL120d)
        for ctle_type in ("CL120e", "CL120d"):
            params = dict(PARAMS)
            params["ctle_type"] = ctle_type
            if ctle_type == "CL120d":
                params["f_hp"] = [1e9, 2e9]
            expected_fd = [
                {"real": float(v.real), "imag": float(v.imag)}
                for v in oracle._ctle_frequency_response(np.asarray(frequency), 0, 0, -3.0, oracle_params(params))
            ]
            compare("ctle_fd_" + ctle_type,
                    {"ctle_fd": {"frequency": frequency, "ctle_index": 0, "high_pass_index": 0, "high_pass_gain_db": -3.0, "parameters": params}},
                    {"response": expected_fd},
                    lambda o, p: [] if all(
                        abs(a["real"] - b["real"]) <= TOLERANCE and abs(a["imag"] - b["imag"]) <= TOLERANCE
                        for a, b in zip(p["ctle_fd"]["response"], o["response"])
                    ) else ["fd drift"])

        # ctle time-domain candidate
        for ctle_type in ("CL120e", "CL120d"):
            params = dict(PARAMS)
            params["ctle_type"] = ctle_type
            if ctle_type == "CL120d":
                params["f_hp"] = [1e9, 2e9]
            impulse = waveform(0.3)
            expected_td = [float(v) for v in oracle._apply_ctle_candidate(
                np.asarray(impulse), baud_hz=53.125e9, samples_per_ui=4, ctle_index=0,
                ctle_gain_db=6.0, high_pass_index=1, high_pass_gain_db=-3.0, parameters=oracle_params(params))]
            compare("ctle_td_" + ctle_type,
                    {"ctle_td": {"impulse": impulse, "baud_hz": 53.125e9, "samples_per_ui": 4, "ctle_index": 0,
                                 "ctle_gain_db": 6.0, "high_pass_index": 1, "high_pass_gain_db": -3.0, "parameters": params}},
                    {"filtered": expected_td},
                    lambda o, p: [] if all(abs(a - b) <= TOLERANCE for a, b in zip(p["ctle_td"]["filtered"], o["filtered"])) else ["td drift"])

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "search_support_crosscheck_matched" if matched else "search_support_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/equalization/search.py",
            "functions": ["_indexed_config_value", "_high_pass_candidates", "_qualified_ctle_pair", "_selected_sndr", "_selected_accm_rms", "_r480_system_noise_response", "_ctle_frequency_response", "_apply_ctle_candidate"],
            "numpy_version": np.__version__,
        },
        "tolerance": TOLERANCE,
        "entries": entries,
        "non_claims": ["not_receiver_noise", "not_crosstalk_noise", "not_search_loop", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]))
        for diff in entry.get("diffs", []):
            print("  diff:", diff)
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())