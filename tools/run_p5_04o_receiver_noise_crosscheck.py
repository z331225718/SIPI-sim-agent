"""P5-04o receiver noise cross-check: product runner vs agent-com oracle.

Runs the filter chain, RxFFE frequency response, and receiver-noise
integration in fresh external custody (agent-com signal/filters.py and
search._receiver_noise) on fixed inputs and compares every result
against the product runner. Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04o-receiver-noise-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04o.receiver-noise-crosscheck-evidence.v1"
TOLERANCE = 1e-9


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def complex_list(values) -> list[dict[str, float]]:
    return [{"real": float(v.real), "imag": float(v.imag)} for v in values]


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.signal.filters import (
        bessel_thomson_filter as oracle_bessel,
        butterworth_filter as oracle_butterworth,
        raised_cosine_filter as oracle_rc,
    )
    from agent_com.equalization import search as oracle_search

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04o_receiver_noise_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04o_receiver_noise_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04o-crosscheck-") as tmp:
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

        frequency = [index * 1e9 for index in range(64)]

        # bessel variants
        for label, order, cutoff, enabled in (("o3_on", 3, 0.75, True), ("o5_on", 5, 0.9, True), ("off", 3, 0.75, False)):
            expected = complex_list(oracle_bessel(np.asarray(frequency), order=order, cutoff_multiplier=cutoff, baud_hz=53.125e9, enabled=enabled))
            compare("bessel_" + label,
                    {"bessel": {"frequency": frequency, "order": order, "cutoff_multiplier": cutoff, "baud_hz": 53.125e9, "enabled": enabled}},
                    {"response": expected},
                    lambda o, p: [] if all(
                        abs(a["real"] - b["real"]) <= TOLERANCE and abs(a["imag"] - b["imag"]) <= TOLERANCE
                        for a, b in zip(p["bessel"]["response"], o["response"])
                    ) else ["bessel drift"])

        # butterworth
        expected_bw = complex_list(oracle_butterworth(np.asarray(frequency), cutoff_multiplier=0.75, baud_hz=53.125e9, enabled=True))
        compare("butterworth_on",
                {"butterworth": {"frequency": frequency, "cutoff_multiplier": 0.75, "baud_hz": 53.125e9, "enabled": True}},
                {"response": expected_bw},
                lambda o, p: [] if all(
                    abs(a["real"] - b["real"]) <= TOLERANCE and abs(a["imag"] - b["imag"]) <= TOLERANCE
                    for a, b in zip(p["butterworth"]["response"], o["response"])
                ) else ["bw drift"])

        # raised cosine
        expected_rc = [float(v) for v in oracle_rc(np.asarray(frequency), start_hz=8e9, end_hz=12e9, enabled=True)]
        compare("raised_cosine_on",
                {"raised_cosine": {"frequency": frequency, "start_hz": 8e9, "end_hz": 12e9, "enabled": True}},
                {"response": expected_rc},
                lambda o, p: [] if all(abs(a - b) <= TOLERANCE for a, b in zip(p["raised_cosine"]["response"], o["response"])) else ["rc drift"])

        # rxffe frequency response
        taps = [0.3, 1.0, -0.2, 0.1]
        expected_rx = complex_list(oracle_search._rx_ffe_frequency_response(np.asarray(frequency), np.asarray(taps), precursor_count=1, baud_hz=53.125e9))
        compare("rxffe_fd",
                {"rxffe_fd": {"frequency": frequency, "taps": taps, "precursor_count": 1, "baud_hz": 53.125e9}},
                {"response": expected_rx},
                lambda o, p: [] if all(
                    abs(a["real"] - b["real"]) <= TOLERANCE and abs(a["imag"] - b["imag"]) <= TOLERANCE
                    for a, b in zip(p["rxffe_fd"]["response"], o["response"])
                ) else ["rxffe drift"])

        # receiver noise integration cases
        base_params = {
            "fb": 53.125e9, "btorder": 3, "fb_bt_cutoff": 0.75, "fb_bw_cutoff": 0.75,
            "rc_start": 8e9, "rc_end": 12e9, "eta_0": 1e-3, "accm_max_freq": 30e9,
            "ac_cm_rms": [0.05, 0.1],
            "ctle_gdc_values": [6.0], "ctle_fz": [10e9], "ctle_fp1": [30e9], "ctle_fp2": [40e9],
            "ctle_type": "CL120e", "f_hp": [0.0], "f_hp_z": [5e9], "f_hp_p": [1e9],
        }
        base_options = {
            "Bessel_Thomson": True, "Butterworth": True, "Raised_Cosine": True,
            "USE_ETA0_PSD": True, "WC_PORTZ": False, "pkg_len_select": np.asarray([2], dtype=np.int64),
        }
        oracle_params = {
            "fb": base_params["fb"], "BTorder": base_params["btorder"], "fb_BT_cutoff": base_params["fb_bt_cutoff"],
            "fb_BW_cutoff": base_params["fb_bw_cutoff"], "RC_Start": base_params["rc_start"], "RC_end": base_params["rc_end"],
            "eta_0": base_params["eta_0"], "ACCM_MAX_Freq": base_params["accm_max_freq"],
            "AC_CM_RMS": np.asarray(base_params["ac_cm_rms"]),
            "ctle_gdc_values": np.asarray(base_params["ctle_gdc_values"]),
            "CTLE_fz": np.asarray(base_params["ctle_fz"]), "CTLE_fp1": np.asarray(base_params["ctle_fp1"]),
            "CTLE_fp2": np.asarray(base_params["ctle_fp2"]), "CTLE_type": base_params["ctle_type"],
            "f_HP": np.asarray(base_params["f_hp"]), "f_HP_Z": np.asarray(base_params["f_hp_z"]),
            "f_HP_P": np.asarray(base_params["f_hp_p"]),
        }

        def product_params() -> dict[str, object]:
            return dict(base_params)

        # eta0 only
        expected_eta0 = float(oracle_search._receiver_noise(
            np.asarray(frequency), ctle_index=0, high_pass_index=0, high_pass_gain_db=0.0,
            parameters=oracle_params, options=base_options, include_accm=False,
        ))
        compare("receiver_eta0_only",
                {"receiver_noise": {"frequency": frequency, "ctle_index": 0, "high_pass_index": 0,
                                    "high_pass_gain_db": 0.0, "parameters": product_params(),
                                    "options": {"bessel_thomson": True, "butterworth": True, "raised_cosine": True,
                                                "use_eta0_psd": True, "wc_portz": False, "pkg_len_select": [2]},
                                    "ac_common_mode_transfers": [], "package_case_index": 0,
                                    "rx_ffe_taps": None, "rx_ffe_precursor_count": None, "include_accm": False}},
                {"noise": expected_eta0},
                lambda o, p: [] if abs(p["receiver_noise"]["noise"] - o["noise"]) <= TOLERANCE else ["eta0 drift"])

        # with RxFFE taps
        rxffe_taps = [0.1, 1.0, -0.05]
        expected_eta0_rx = float(oracle_search._receiver_noise(
            np.asarray(frequency), ctle_index=0, high_pass_index=0, high_pass_gain_db=0.0,
            parameters=oracle_params, options=base_options, include_accm=False,
            rx_ffe_taps=np.asarray(rxffe_taps), rx_ffe_precursor_count=1,
        ))
        compare("receiver_eta0_rxffe",
                {"receiver_noise": {"frequency": frequency, "ctle_index": 0, "high_pass_index": 0,
                                    "high_pass_gain_db": 0.0, "parameters": product_params(),
                                    "options": {"bessel_thomson": True, "butterworth": True, "raised_cosine": True,
                                                "use_eta0_psd": True, "wc_portz": False, "pkg_len_select": [2]},
                                    "ac_common_mode_transfers": [], "package_case_index": 0,
                                    "rx_ffe_taps": rxffe_taps, "rx_ffe_precursor_count": 1, "include_accm": False}},
                {"noise": expected_eta0_rx},
                lambda o, p: [] if abs(p["receiver_noise"]["noise"] - o["noise"]) <= TOLERANCE else ["eta0 rx drift"])

        # ACCM component with a common-mode transfer
        acm = [{"real": 0.5, "imag": -0.1} for _ in range(len(frequency))]
        acm_arr = np.asarray([[v["real"] + 1j * v["imag"] for v in acm]], dtype=np.complex128).reshape(-1)
        expected_accm = float(oracle_search._receiver_noise(
            np.asarray(frequency), ctle_index=0, high_pass_index=0, high_pass_gain_db=0.0,
            parameters=oracle_params, options=base_options, include_accm=True,
            ac_common_mode_transfers=(acm_arr,),
        ))
        compare("receiver_accm",
                {"receiver_noise": {"frequency": frequency, "ctle_index": 0, "high_pass_index": 0,
                                    "high_pass_gain_db": 0.0, "parameters": product_params(),
                                    "options": {"bessel_thomson": True, "butterworth": True, "raised_cosine": True,
                                                "use_eta0_psd": True, "wc_portz": False, "pkg_len_select": [2]},
                                    "ac_common_mode_transfers": [acm], "package_case_index": 0,
                                    "rx_ffe_taps": None, "rx_ffe_precursor_count": None, "include_accm": True}},
                {"noise": expected_accm},
                lambda o, p: [] if abs(p["receiver_noise"]["noise"] - o["noise"]) <= TOLERANCE else ["accm drift"])

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "receiver_noise_crosscheck_matched" if matched else "receiver_noise_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "paths": ["src/agent_com/signal/filters.py", "src/agent_com/equalization/search.py"],
            "functions": ["bessel_thomson_filter", "butterworth_filter", "raised_cosine_filter", "_rx_ffe_frequency_response", "_receiver_noise"],
            "numpy_version": np.__version__,
        },
        "tolerance": TOLERANCE,
        "entries": entries,
        "non_claims": ["not_crosstalk_noise", "not_candidate_evaluation", "not_search_loop", "not_release_evidence"],
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
