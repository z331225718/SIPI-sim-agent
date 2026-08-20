"""P5-04g residual-channel PDF cross-check: product runner vs agent-com oracle.

Runs the product residual-channel PDF runner on a fixed case set and
compares each result surface (sampled PDF, residual pulse, selected
phase) against the MIT agent-com implementation imported in fresh
external custody. Hash-only evidence; no release claim.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
COM_SRC = Path(r"C:\Users\z3312\code\COM\src")
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04g-residual-pdf-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04g.residual-pdf-crosscheck-evidence.v1"
TOLERANCE = 1e-12


def pulse64() -> list[float]:
    import math

    return [
        0.5 * math.exp(-((index - 30.0) ** 2) / 60.0) * (1.0 + 0.1 * math.sin(index * 0.7))
        for index in range(64)
    ]


CASES = [
    {"id": "thru_no_dfe", "pulse": pulse64, "channel_type": "THRU", "cursor_index": 30, "samples_per_ui": 8, "levels": 4, "bin_size": 0.01, "dfe_tap_count": 0, "dfe_max": None, "dfe_min": None, "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None, "phase_index": None},
    {"id": "thru_dfe_taps", "pulse": pulse64, "channel_type": "THRU", "cursor_index": 30, "samples_per_ui": 8, "levels": 4, "bin_size": 0.01, "dfe_tap_count": 2, "dfe_max": [0.4, 0.3], "dfe_min": [-0.2, -0.1], "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None, "phase_index": None},
    {"id": "thru_dfe_step_quantize", "pulse": pulse64, "channel_type": "THRU", "cursor_index": 30, "samples_per_ui": 8, "levels": 4, "bin_size": 0.01, "dfe_tap_count": 2, "dfe_max": [0.4, 0.3], "dfe_min": [-0.2, -0.1], "dfe_step": 0.01, "floating_dfe": False, "dfe_max_count": None, "phase_index": None},
    {"id": "thru_floating_dfe", "pulse": pulse64, "channel_type": "THRU", "cursor_index": 30, "samples_per_ui": 8, "levels": 4, "bin_size": 0.01, "dfe_tap_count": 5, "dfe_max": [0.4], "dfe_min": [-0.2], "dfe_step": 0.0, "floating_dfe": True, "dfe_max_count": 1, "phase_index": None},
    {"id": "thru_cursor_phase7", "pulse": pulse64, "channel_type": "THRU", "cursor_index": 31, "samples_per_ui": 8, "levels": 4, "bin_size": 0.01, "dfe_tap_count": 0, "dfe_max": None, "dfe_min": None, "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None, "phase_index": None},
    {"id": "fext_phase_select", "pulse": pulse64, "channel_type": "FEXT", "cursor_index": 0, "samples_per_ui": 8, "levels": 4, "bin_size": 0.01, "dfe_tap_count": 0, "dfe_max": None, "dfe_min": None, "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None, "phase_index": None},
    {"id": "next_phase_select", "pulse": pulse64, "channel_type": "NEXT", "cursor_index": 0, "samples_per_ui": 4, "levels": 2, "bin_size": 0.02, "dfe_tap_count": 0, "dfe_max": None, "dfe_min": None, "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None, "phase_index": None},
    {"id": "fext_forced_phase", "pulse": pulse64, "channel_type": "FEXT", "cursor_index": 0, "samples_per_ui": 8, "levels": 4, "bin_size": 0.01, "dfe_tap_count": 0, "dfe_max": None, "dfe_min": None, "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None, "phase_index": 3},
    {"id": "thru_forced_phase", "pulse": pulse64, "channel_type": "THRU", "cursor_index": 30, "samples_per_ui": 8, "levels": 4, "bin_size": 0.01, "dfe_tap_count": 0, "dfe_max": None, "dfe_min": None, "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None, "phase_index": 6},
    {"id": "fext_large_spu", "pulse": pulse64, "channel_type": "FEXT", "cursor_index": 40, "samples_per_ui": 16, "levels": 3, "bin_size": 0.005, "dfe_tap_count": 0, "dfe_max": None, "dfe_min": None, "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None, "phase_index": None},
]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def sha256_json(value: object) -> str:
    return sha256_bytes(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    import scipy
    from agent_com.noise.discrete_pdf import residual_channel_pdf as oracle_residual_channel_pdf

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04g_residual_pdf_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04g_residual_pdf_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04g-crosscheck-") as tmp:
        work = Path(tmp)
        for case in CASES:
            pulse = case["pulse"]()
            pulse_bytes = json.dumps(pulse, separators=(",", ":")).encode("utf-8")
            pulse_hash = sha256_bytes(pulse_bytes)
            pulse_path = work / (case["id"] + "-pulse.json")
            pulse_path.write_bytes(pulse_bytes)
            dfe_max_path = None
            dfe_min_path = None
            if case["dfe_max"] is not None:
                dfe_max_path = work / (case["id"] + "-dfe-max.json")
                dfe_max_path.write_text(json.dumps(case["dfe_max"], separators=(",", ":")), encoding="utf-8")
            if case["dfe_min"] is not None:
                dfe_min_path = work / (case["id"] + "-dfe-min.json")
                dfe_min_path.write_text(json.dumps(case["dfe_min"], separators=(",", ":")), encoding="utf-8")
            oracle = oracle_residual_channel_pdf(
                np.asarray(pulse, dtype=np.float64),
                channel_type=case["channel_type"],
                cursor_index=case["cursor_index"],
                samples_per_ui=case["samples_per_ui"],
                levels=case["levels"],
                bin_size=case["bin_size"],
                dfe_tap_count=case["dfe_tap_count"],
                dfe_max=None if case["dfe_max"] is None else np.asarray(case["dfe_max"], dtype=np.float64),
                dfe_min=None if case["dfe_min"] is None else np.asarray(case["dfe_min"], dtype=np.float64),
                dfe_step=case["dfe_step"],
                floating_dfe=case["floating_dfe"],
                dfe_max_count=case["dfe_max_count"],
                phase_index=case["phase_index"],
            )
            oracle_payload = {
                "bin_size": float(oracle.pdf.bin_size),
                "min_bin": int(oracle.pdf.min_bin),
                "probability": [float(item) for item in oracle.pdf.probability],
                "residual_pulse": [float(item) for item in oracle.residual_pulse],
                "selected_phase": int(oracle.selected_phase),
            }
            report_path = work / (case["id"] + "-product.json")
            command = [
                str(runner), "--pulse", str(pulse_path),
                "--channel-type", case["channel_type"],
                "--cursor-index", str(case["cursor_index"]),
                "--samples-per-ui", str(case["samples_per_ui"]),
                "--levels", str(case["levels"]),
                "--bin-size", str(case["bin_size"]),
                "--dfe-tap-count", str(case["dfe_tap_count"]),
                "--report", str(report_path),
            ]
            if dfe_max_path is not None:
                command += ["--dfe-max", str(dfe_max_path)]
            if dfe_min_path is not None:
                command += ["--dfe-min", str(dfe_min_path)]
            if case["dfe_step"]:
                command += ["--dfe-step", str(case["dfe_step"])]
            if case["floating_dfe"]:
                command.append("--floating-dfe")
            if case["dfe_max_count"] is not None:
                command += ["--dfe-max-count", str(case["dfe_max_count"])]
            if case["phase_index"] is not None:
                command += ["--phase-index", str(case["phase_index"])]
            run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit("runner failed: " + case["id"] + " :: " + run.stdout + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            pdf = product["pdf"]
            product_payload = {
                "bin_size": float(pdf["bin_size"]),
                "min_bin": int(pdf["min_bin"]),
                "probability": [float(item) for item in pdf["probability"]],
                "residual_pulse": [float(item) for item in product["residual_pulse"]],
                "selected_phase": int(product["selected_phase"]),
            }
            mismatch = None
            max_abs_diff = None
            if product_payload["bin_size"] != oracle_payload["bin_size"]:
                mismatch = "bin_size"
            elif product_payload["min_bin"] != oracle_payload["min_bin"]:
                mismatch = "min_bin"
            elif product_payload["selected_phase"] != oracle_payload["selected_phase"]:
                mismatch = "selected_phase"
            elif len(product_payload["probability"]) != len(oracle_payload["probability"]):
                mismatch = "probability_length"
            elif len(product_payload["residual_pulse"]) != len(oracle_payload["residual_pulse"]):
                mismatch = "residual_length"
            else:
                diffs = [
                    abs(a - b)
                    for a, b in zip(product_payload["probability"], oracle_payload["probability"])
                ] + [
                    abs(a - b)
                    for a, b in zip(product_payload["residual_pulse"], oracle_payload["residual_pulse"])
                ]
                max_abs_diff = max(diffs)
                if max_abs_diff > TOLERANCE:
                    mismatch = "surface max_abs_diff " + format(max_abs_diff, ".3e")
            entries.append({
                "id": case["id"],
                "channel_type": case["channel_type"],
                "samples_per_ui": case["samples_per_ui"],
                "levels": case["levels"],
                "pulse_sha256": pulse_hash,
                "oracle_sha256": sha256_json(oracle_payload),
                "product_sha256": sha256_json(product_payload),
                "selected_phase": oracle_payload["selected_phase"],
                "max_abs_diff": max_abs_diff,
                "matched": mismatch is None,
                "mismatch": mismatch,
            })
    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "residual_pdf_crosscheck_matched" if matched else "residual_pdf_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/noise/discrete_pdf.py",
            "function": "residual_channel_pdf",
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
        },
        "tolerance": TOLERANCE,
        "entries": entries,
        "non_claims": ["not_stage_chain_parity", "not_full_scope_parity", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]), "diff=" + str(entry["max_abs_diff"]), "phase=" + str(entry["selected_phase"]))
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
