"""P5-04i equalizer front-end cross-check: product runner vs agent-com oracle.

Runs cursor_sample_index / fd_ctle / td_ctle in fresh external custody
(agent-com equalization modules) on fixed waveforms and compares every
result against the product runner. Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04i-frontend-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04i.frontend-crosscheck-evidence.v1"
TOLERANCE = 1e-12


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def pulse(seed: float, length: int = 256) -> list[float]:
    values = []
    for index in range(length):
        i = float(index)
        values.append(
            math.exp(-((i - 80.0) ** 2) / 300.0) * math.sin(i * 0.3 + seed)
            + 0.02 * math.sin(i * 0.9 + 2.0 * seed)
        )
    return values


CURSOR_CASES = [
    {"id": "mm_default", "cdr": "MM", "samples_per_ui": 8, "dfe_first_max": 0.0},
    {"id": "modmm_dfefirst", "cdr": "Mod-MM", "samples_per_ui": 8, "dfe_first_max": 0.3},
    {"id": "mm_peakrange", "cdr": "MM", "samples_per_ui": 16, "dfe_first_max": 0.0, "peak_start": 32, "peak_stop": 200},
]

FD_CTLE_CASES = [
    {"id": "fdctle_a", "fz_multiplier": 0.5, "fp1_multiplier": 1.5, "fp2_multiplier": 2.0, "dc_gain_db": 6.0},
    {"id": "fdctle_b", "fz_multiplier": 0.3, "fp1_multiplier": 1.2, "fp2_multiplier": 3.5, "dc_gain_db": -3.0},
]

TD_CTLE_CASES = [
    {"id": "tdctle_a", "fz_hz": 10e9, "fp1_hz": 30e9, "fp2_hz": 40e9, "dc_gain_db": 6.0, "samples_per_ui": 8},
    {"id": "tdctle_b", "fz_hz": 5e9, "fp1_hz": 20e9, "fp2_hz": 50e9, "dc_gain_db": 0.0, "samples_per_ui": 4},
]


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.equalization.cursor import cursor_sample_index as oracle_cursor
    from agent_com.equalization.ctle import fd_ctle as oracle_fd_ctle
    from agent_com.equalization.ctle import td_ctle as oracle_td_ctle

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04i_frontend_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04i_frontend_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04i-crosscheck-") as tmp:
        work = Path(tmp)
        for case in CURSOR_CASES:
            pulse_values = pulse(0.7)
            input_payload = {
                "pulse": pulse_values,
                "cursor": {
                    "samples_per_ui": case["samples_per_ui"],
                    "dfe_first_max": case["dfe_first_max"],
                    "cdr": case["cdr"],
                    "peak_start": case.get("peak_start", 0),
                    "peak_stop": case.get("peak_stop"),
                },
            }
            oracle = oracle_cursor(
                np.asarray(pulse_values, dtype=np.float64),
                samples_per_ui=case["samples_per_ui"],
                dfe_first_max=case["dfe_first_max"],
                cdr=case["cdr"],
                peak_start=case.get("peak_start", 0),
                peak_stop=case.get("peak_stop"),
            )
            oracle_payload = {
                "cursor_index": None if oracle.cursor_index is None else int(oracle.cursor_index),
                "no_zero_crossing": bool(oracle.no_zero_crossing),
                "peak_index": int(oracle.peak_index),
                "zero_crossing_index": None if oracle.zero_crossing_index is None else int(oracle.zero_crossing_index),
            }
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json")
            input_path.write_bytes(input_bytes)
            report_path = work / (case["id"] + "-product.json")
            run = subprocess.run(
                [str(runner), "--input", str(input_path), "--report", str(report_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if run.returncode != 0:
                raise SystemExit("runner failed: " + case["id"] + " :: " + run.stdout + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))["cursor"]
            diffs = []
            for key in ("cursor_index", "no_zero_crossing", "peak_index", "zero_crossing_index"):
                if product[key] != oracle_payload[key]:
                    diffs.append(key + " " + str(product[key]) + " vs " + str(oracle_payload[key]))
            entries.append({
                "id": case["id"],
                "kind": "cursor",
                "input_sha256": sha256_bytes(input_bytes),
                "cursor_index": oracle_payload["cursor_index"],
                "peak_index": oracle_payload["peak_index"],
                "matched": not diffs,
                "diffs": diffs[:6],
            })
        for case in FD_CTLE_CASES:
            frequencies = [index * 1.25e9 for index in range(16)]
            input_payload = {
                "pulse": [0.0],
                "fd_ctle": {
                    "frequencies_hz": frequencies,
                    "baud_hz": 53.125e9,
                    "fz_multiplier": case["fz_multiplier"],
                    "fp1_multiplier": case["fp1_multiplier"],
                    "fp2_multiplier": case["fp2_multiplier"],
                    "dc_gain_db": case["dc_gain_db"],
                },
            }
            oracle = oracle_fd_ctle(
                np.asarray(frequencies, dtype=np.float64),
                baud_hz=53.125e9,
                fz_multiplier=case["fz_multiplier"],
                fp1_multiplier=case["fp1_multiplier"],
                fp2_multiplier=case["fp2_multiplier"],
                dc_gain_db=case["dc_gain_db"],
            )
            oracle_payload = [
                {"real": float(value.real), "imag": float(value.imag)}
                for value in oracle
            ]
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json")
            input_path.write_bytes(input_bytes)
            report_path = work / (case["id"] + "-product.json")
            run = subprocess.run(
                [str(runner), "--input", str(input_path), "--report", str(report_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if run.returncode != 0:
                raise SystemExit("runner failed: " + case["id"])
            product = json.loads(report_path.read_text(encoding="utf-8"))["fd_ctle"]["response"]
            diffs = []
            if len(product) != len(oracle_payload):
                diffs.append("length")
            else:
                for expected, actual in zip(oracle_payload, product):
                    if abs(expected["real"] - actual["real"]) > TOLERANCE or abs(expected["imag"] - actual["imag"]) > TOLERANCE:
                        diffs.append("point drift")
                        break
            entries.append({
                "id": case["id"],
                "kind": "fd_ctle",
                "input_sha256": sha256_bytes(input_bytes),
                "points": len(oracle_payload),
                "matched": not diffs,
                "diffs": diffs[:6],
            })
        for case in TD_CTLE_CASES:
            pulse_values = pulse(0.3)
            input_payload = {
                "pulse": pulse_values,
                "td_ctle": {
                    "baud_hz": 53.125e9,
                    "fz_hz": case["fz_hz"],
                    "fp1_hz": case["fp1_hz"],
                    "fp2_hz": case["fp2_hz"],
                    "dc_gain_db": case["dc_gain_db"],
                    "samples_per_ui": case["samples_per_ui"],
                },
            }
            oracle = oracle_td_ctle(
                np.asarray(pulse_values, dtype=np.float64),
                baud_hz=53.125e9,
                fz_hz=case["fz_hz"],
                fp1_hz=case["fp1_hz"],
                fp2_hz=case["fp2_hz"],
                dc_gain_db=case["dc_gain_db"],
                samples_per_ui=case["samples_per_ui"],
            )
            oracle_payload = [float(value) for value in oracle]
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json")
            input_path.write_bytes(input_bytes)
            report_path = work / (case["id"] + "-product.json")
            run = subprocess.run(
                [str(runner), "--input", str(input_path), "--report", str(report_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if run.returncode != 0:
                raise SystemExit("runner failed: " + case["id"])
            product = json.loads(report_path.read_text(encoding="utf-8"))["td_ctle"]["filtered"]
            diffs = []
            if len(product) != len(oracle_payload):
                diffs.append("length")
            else:
                max_diff = max(abs(a - b) for a, b in zip(oracle_payload, product))
                if max_diff > TOLERANCE:
                    diffs.append("max_abs_diff " + format(max_diff, ".3e"))
            entries.append({
                "id": case["id"],
                "kind": "td_ctle",
                "input_sha256": sha256_bytes(input_bytes),
                "points": len(oracle_payload),
                "matched": not diffs,
                "diffs": diffs[:6],
            })
    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "frontend_crosscheck_matched" if matched else "frontend_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "paths": ["src/agent_com/equalization/cursor.py", "src/agent_com/equalization/ctle.py"],
            "functions": ["cursor_sample_index", "fd_ctle", "td_ctle"],
            "numpy_version": np.__version__,
            "scipy_version": __import__("scipy").__version__,
        },
        "tolerance": TOLERANCE,
        "entries": entries,
        "non_claims": ["not_tx_ffe", "not_dfe", "not_rx_ffe", "not_equalizer_search", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], entry["kind"], "matched=" + str(entry["matched"]),
              "points=" + str(entry.get("points", "-")))
        for diff in entry.get("diffs", []):
            print("  diff:", diff)
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
