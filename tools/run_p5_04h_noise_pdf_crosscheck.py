"""P5-04h r4.80 noise-PDF build cross-check: product runner vs agent-com oracle.

Builds the non-MMSE Gaussian/dual-Dirac noise PDF in fresh external
custody (agent-com build_r480_noise_pdf) on fixed PDF/jitter inputs and
compares the full surface (sigmas, ber_q, combined/gaussian/jitter PDFs)
against the product runner. The ber_q comparison exercises the ported
erfcinv against scipy.special at several spec_ber values. Hash-only
evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04h-noise-pdf-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04h.noise-pdf-crosscheck-evidence.v1"
TOLERANCE = 1e-12
BER_TOLERANCE = 1e-11

CASES = [
    {"id": "ber1e4_no_xtalk", "spec_ber": 1e-4, "levels": 4, "available_signal_v": 0.6, "r_lm_ohm": 50.0, "tx_snr_db": 30.0, "sigma_x": 0.03, "sigma_rj_s": 1e-4, "sigma_n_v": 0.01, "amplitude_dd_v": 0.4, "sigma_ne_v": 0.0, "noise_crest_factor": 0.0, "h_j": [0.3, 0.5, 0.2], "fext": True, "next": True},
    {"id": "ber1e5_with_ne", "spec_ber": 1e-5, "levels": 4, "available_signal_v": 0.5, "r_lm_ohm": 55.0, "tx_snr_db": 28.0, "sigma_x": 0.025, "sigma_rj_s": 8e-5, "sigma_n_v": 0.008, "amplitude_dd_v": 0.35, "sigma_ne_v": 0.002, "noise_crest_factor": 0.0, "h_j": [0.2, 0.4, 0.3, 0.1], "fext": False, "next": True},
    {"id": "ber1e12_crest_override", "spec_ber": 1e-12, "levels": 2, "available_signal_v": 0.7, "r_lm_ohm": 60.0, "tx_snr_db": 32.0, "sigma_x": 0.02, "sigma_rj_s": 6e-5, "sigma_n_v": 0.005, "amplitude_dd_v": 0.45, "sigma_ne_v": 0.001, "noise_crest_factor": 3.9, "h_j": [0.4, 0.3], "fext": True, "next": False},
    {"id": "ber3e4_overrides", "spec_ber": 3e-4, "levels": 4, "available_signal_v": 0.55, "r_lm_ohm": 50.0, "tx_snr_db": 31.0, "sigma_x": 0.03, "sigma_rj_s": 9e-5, "sigma_n_v": 0.009, "amplitude_dd_v": 0.38, "sigma_ne_v": 0.0, "noise_crest_factor": 0.0, "h_j": [0.25, 0.45, 0.3], "fext": False, "next": False, "sigma_tx_override_v": 0.0015, "sigma_rj_override_v": 0.0008, "bbn_q_factor": 3.5},
]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def pdf_payload(pdf) -> dict[str, object]:
    return {
        "bin_size": float(pdf.bin_size),
        "min_bin": int(pdf.min_bin),
        "probability": [float(item) for item in pdf.probability],
    }


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.noise.discrete_pdf import (
        build_r480_noise_pdf as oracle_build,
        normal_pdf as oracle_normal,
    )

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04h_noise_pdf_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04h_noise_pdf_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04h-crosscheck-") as tmp:
        work = Path(tmp)
        for case in CASES:
            bin_size = 1e-4
            sci = oracle_normal(0.001, 3.0, bin_size)
            fext_pdfs = [oracle_normal(0.002, 3.0, bin_size)] if case["fext"] else []
            next_pdfs = [oracle_normal(0.0015, 3.0, bin_size)] if case["next"] else []
            input_payload = {
                "sci_pdf": pdf_payload(sci),
                "fext_pdfs": [pdf_payload(p) for p in fext_pdfs],
                "next_pdfs": [pdf_payload(p) for p in next_pdfs],
                "levels": case["levels"],
                "available_signal_v": case["available_signal_v"],
                "r_lm_ohm": case["r_lm_ohm"],
                "tx_snr_db": case["tx_snr_db"],
                "sigma_x": case["sigma_x"],
                "sigma_rj_s": case["sigma_rj_s"],
                "jitter_response": case["h_j"],
                "sigma_n_v": case["sigma_n_v"],
                "amplitude_dd_v": case["amplitude_dd_v"],
                "spec_ber": case["spec_ber"],
                "noise_crest_factor": case["noise_crest_factor"],
                "sigma_ne_v": case["sigma_ne_v"],
            }
            for key in ("sigma_tx_override_v", "sigma_rj_override_v", "bbn_q_factor"):
                if key in case:
                    input_payload[key] = case[key]
            oracle = oracle_build(
                sci_pdf=sci,
                fext_pdfs=tuple(fext_pdfs),
                next_pdfs=tuple(next_pdfs),
                levels=case["levels"],
                available_signal_v=case["available_signal_v"],
                r_lm_ohm=case["r_lm_ohm"],
                tx_snr_db=case["tx_snr_db"],
                sigma_x=case["sigma_x"],
                sigma_rj_s=case["sigma_rj_s"],
                jitter_response=np.asarray(case["h_j"], dtype=np.float64),
                sigma_n_v=case["sigma_n_v"],
                amplitude_dd_v=case["amplitude_dd_v"],
                spec_ber=case["spec_ber"],
                noise_crest_factor=case["noise_crest_factor"],
                sigma_ne_v=case["sigma_ne_v"],
                bbn_q_factor=case.get("bbn_q_factor"),
                sigma_tx_override_v=case.get("sigma_tx_override_v"),
                sigma_rj_override_v=case.get("sigma_rj_override_v"),
            )
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
            product = json.loads(report_path.read_text(encoding="utf-8"))
            oracle_payload = {
                "sigma_tx_v": float(oracle.sigma_tx_v),
                "sigma_rj_v": float(oracle.sigma_rj_v),
                "sigma_gaussian_v": float(oracle.sigma_gaussian_v),
                "ber_q": float(oracle.ber_q),
                "combined": pdf_payload(oracle.result.combined),
                "gaussian_pdf": pdf_payload(oracle.gaussian_pdf),
                "jitter_pdf": pdf_payload(oracle.jitter_pdf),
                "peak_interference_v": float(oracle.result.peak_interference_v),
            }
            diffs = []
            for key in ("sigma_tx_v", "sigma_rj_v", "sigma_gaussian_v"):
                if abs(product[key] - oracle_payload[key]) > 1e-14 * max(1.0, abs(oracle_payload[key])):
                    diffs.append(key + " drift")
            if abs(product["ber_q"] - oracle_payload["ber_q"]) > BER_TOLERANCE:
                diffs.append("ber_q " + str(product["ber_q"]) + " vs " + str(oracle_payload["ber_q"]))
            for surface in ("combined", "gaussian_pdf", "jitter_pdf"):
                expected = oracle_payload[surface]
                actual = product[surface]
                if expected["bin_size"] != actual["bin_size"] or expected["min_bin"] != actual["min_bin"]:
                    diffs.append(surface + " support drift")
                    continue
                if len(expected["probability"]) != len(actual["probability"]):
                    diffs.append(surface + " length")
                    continue
                max_diff = max(
                    abs(a - b)
                    for a, b in zip(expected["probability"], actual["probability"])
                )
                if max_diff > TOLERANCE:
                    diffs.append(surface + " max_abs_diff " + format(max_diff, ".3e"))
            if abs(product["peak_interference_v"] - oracle_payload["peak_interference_v"]) > TOLERANCE:
                diffs.append("peak_interference drift")
            entries.append({
                "id": case["id"],
                "spec_ber": case["spec_ber"],
                "input_sha256": sha256_bytes(input_bytes),
                "ber_q_product": product["ber_q"],
                "ber_q_oracle": oracle_payload["ber_q"],
                "sigma_tx_v": oracle_payload["sigma_tx_v"],
                "combined_len": len(oracle_payload["combined"]["probability"]),
                "matched": not diffs,
                "diffs": diffs[:8],
            })
    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "noise_pdf_crosscheck_matched" if matched else "noise_pdf_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/noise/discrete_pdf.py",
            "function": "build_r480_noise_pdf",
            "numpy_version": __import__("numpy").__version__,
            "scipy_version": __import__("scipy").__version__,
        },
        "tolerances": {"pdf": TOLERANCE, "ber_q": BER_TOLERANCE},
        "entries": entries,
        "non_claims": ["not_mmse_path", "not_equalizer_search", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]),
              "ber_q=" + str(round(entry["ber_q_product"], 8)),
              "oracle=" + str(round(entry["ber_q_oracle"], 8)),
              "combined_len=" + str(entry["combined_len"]))
        for diff in entry.get("diffs", []):
            print("  diff:", diff)
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
