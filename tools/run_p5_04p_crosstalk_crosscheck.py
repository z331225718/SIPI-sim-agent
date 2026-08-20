"""P5-04p crosstalk noise cross-check: product runner vs agent-com oracle.

Runs _crosstalk_noise (frequency-domain FEXT/NEXT integration) and
_td_source_crosstalk_noise (TDMODE outer-product path) in fresh external
custody on fixed inputs and compares every result against the product
runner. Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04p-crosstalk-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04p.crosstalk-crosscheck-evidence.v1"
TOLERANCE = 1e-9


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.equalization import search as oracle

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04p_crosstalk_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04p_crosstalk_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04p-crosscheck-") as tmp:
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

        frequency = [index * 1e9 for index in range(32)]
        fb = 26.5625e9
        f2 = 26.5625e9
        sigma_x = 0.03
        taps = [0.5, 1.0, -0.25]
        params = {"fb": fb, "f2": f2, "sigma_x": sigma_x}
        h_ctf = [{"real": math.cos(v * 1e-11), "imag": v * 1e-11} for v in frequency]
        h_ctf_arr = np.asarray([v["real"] + 1j * v["imag"] for v in h_ctf], dtype=np.complex128)
        fext_arr = np.asarray([0.5 * math.cos(v * 1e-10) + 0.1j for v in frequency], dtype=np.complex128)
        next_arr = np.asarray([0.3 * math.sin(v * 1e-10) - 0.05j for v in frequency], dtype=np.complex128)
        fext = [{"real": v.real, "imag": v.imag} for v in fext_arr]
        nextc = [{"real": v.real, "imag": v.imag} for v in next_arr]
        channels = [{"role": "FEXT", "response": fext, "amplitude": 0.5},
                    {"role": "NEXT", "response": nextc, "amplitude": 0.4}]
        channels_tuple = (("FEXT", fext_arr, 0.5), ("NEXT", next_arr, 0.4))

        # frequency-domain integration
        expected = float(oracle._crosstalk_noise(
            np.asarray(frequency), h_ctf_arr, np.asarray(taps), channels_tuple,
            {"fb": fb, "f2": f2, "sigma_X": sigma_x}))
        compare("fext_next_fd",
                {"crosstalk": {"frequency": frequency, "h_ctf": h_ctf, "taps": taps,
                               "channels": channels, "parameters": params,
                               "td_source_outer_product": False, "rx_ffe_taps": None,
                               "rx_ffe_precursor_count": None}},
                {"noise": expected},
                lambda o, p: [] if abs(p["crosstalk"]["noise"] - o["noise"]) <= TOLERANCE else ["noise drift"])

        # with RxFFE taps
        rxffe = [0.1, 1.0, -0.05]
        expected_rx = float(oracle._crosstalk_noise(
            np.asarray(frequency), h_ctf_arr, np.asarray(taps), channels_tuple,
            {"fb": fb, "f2": f2, "sigma_X": sigma_x},
            rx_ffe_taps=np.asarray(rxffe), rx_ffe_precursor_count=1))
        compare("fext_next_rxffe",
                {"crosstalk": {"frequency": frequency, "h_ctf": h_ctf, "taps": taps,
                               "channels": channels, "parameters": params,
                               "td_source_outer_product": False, "rx_ffe_taps": rxffe,
                               "rx_ffe_precursor_count": 1}},
                {"noise": expected_rx},
                lambda o, p: [] if abs(p["crosstalk"]["noise"] - o["noise"]) <= TOLERANCE else ["noise drift"])

        # NEXT only
        channels_next = [{"role": "NEXT", "response": nextc, "amplitude": 0.4}]
        expected_n = float(oracle._crosstalk_noise(
            np.asarray(frequency), h_ctf_arr, np.asarray(taps), (("NEXT", next_arr, 0.4),),
            {"fb": fb, "f2": f2, "sigma_X": sigma_x}))
        compare("next_only",
                {"crosstalk": {"frequency": frequency, "h_ctf": h_ctf, "taps": taps,
                               "channels": channels_next, "parameters": params,
                               "td_source_outer_product": False, "rx_ffe_taps": None,
                               "rx_ffe_precursor_count": None}},
                {"noise": expected_n},
                lambda o, p: [] if abs(p["crosstalk"]["noise"] - o["noise"]) <= TOLERANCE else ["noise drift"])

        # TD outer-product path
        tx_filter_arr = np.asarray([math.cos(v * 1e-10) + 1j * math.sin(v * 1e-10) for v in frequency], dtype=np.complex128)
        tx_filter = [{"real": v.real, "imag": v.imag} for v in tx_filter_arr]
        sinc_arr = np.asarray([1.0 if v == 0 else math.sin(math.pi * v / fb) / (math.pi * v / fb) for v in frequency], dtype=np.float64)
        sinc = [float(v) for v in sinc_arr]
        td_fext = [{"real": 0.4 * math.cos(v * 1e-10), "imag": 0.1} for v in frequency]
        td_fext_arr = np.asarray([v["real"] + 1j * v["imag"] for v in td_fext], dtype=np.complex128)
        expected_td = float(oracle._td_source_crosstalk_noise(
            np.asarray(frequency), h_ctf_arr, tx_filter_arr, sinc_arr,
            (("FEXT", td_fext_arr, 0.5),), {"fb": fb, "f2": f2, "sigma_X": sigma_x}))
        compare("td_outer_product",
                {"td_crosstalk": {"frequency": frequency, "h_ctf": h_ctf, "tx_filter": tx_filter,
                                  "sinc": sinc, "channels": [{"role": "FEXT", "response": td_fext, "amplitude": 0.5}],
                                  "parameters": params}},
                {"noise": expected_td},
                lambda o, p: [] if abs(p["td_crosstalk"]["noise"] - o["noise"]) <= TOLERANCE else ["noise drift"])

        # TD with both roles
        expected_td2 = float(oracle._td_source_crosstalk_noise(
            np.asarray(frequency), h_ctf_arr, tx_filter_arr, sinc_arr,
            (("FEXT", td_fext_arr, 0.5), ("NEXT", next_arr, 0.3)), {"fb": fb, "f2": f2, "sigma_X": sigma_x}))
        compare("td_both_roles",
                {"td_crosstalk": {"frequency": frequency, "h_ctf": h_ctf, "tx_filter": tx_filter,
                                  "sinc": sinc, "channels": [{"role": "FEXT", "response": td_fext, "amplitude": 0.5},
                                                              {"role": "NEXT", "response": nextc, "amplitude": 0.3}],
                                  "parameters": params}},
                {"noise": expected_td2},
                lambda o, p: [] if abs(p["td_crosstalk"]["noise"] - o["noise"]) <= TOLERANCE else ["noise drift"])

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "crosstalk_crosscheck_matched" if matched else "crosstalk_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/equalization/search.py",
            "functions": ["_crosstalk_noise", "_td_source_crosstalk_noise"],
            "numpy_version": np.__version__,
        },
        "tolerance": TOLERANCE,
        "entries": entries,
        "non_claims": ["not_candidate_evaluation", "not_search_loop", "not_release_evidence"],
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
