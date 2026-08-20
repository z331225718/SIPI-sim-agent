"""P5-04r C2M vertical-eye cross-check: product runner vs agent-com oracle.

Runs metrics.c2m.calculate_c2m_vertical_eye in fresh external custody on
fixed inputs and compares every result against the product runner. The
oracle is called on its default (direct full-convolution, non-FFT,
non-accelerated) path so it matches the product port's direct convolution
and non-sparse sampled-signal PDFs. Hash-only evidence; no release claim.
The full-contour public eye and the equalizer candidate/loop are separate.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04r-c2m-eye-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04r.c2m-eye-crosscheck-evidence.v1"
TOL = 2e-6


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def pulse(size: int = 400) -> list[float]:
    return [
        max(0.5 * math.exp(-((i - 160.0) ** 2) / 800.0) + 0.03, 0.01)
        for i in range(size)
    ]


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.metrics.c2m import calculate_c2m_vertical_eye
    from agent_com.noise.discrete_pdf import DiscretePdf, normal_pdf

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04r_c2m_eye_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04r_c2m_eye_runner-*.exe"))[-1]

    entries = []

    def pdf_dict(pdf) -> dict[str, object]:
        return {"bin_size": float(pdf.bin_size), "min_bin": int(pdf.min_bin), "probability": [float(v) for v in pdf.probability]}

    with tempfile.TemporaryDirectory(prefix="p5-04r-crosscheck-") as tmp:
        work = Path(tmp)

        def compare(case_id: str, c2m_input: dict[str, object], oracle_payload: dict[str, object]):
            input_bytes = json.dumps({"c2m": c2m_input}, separators=(",", ":")).encode("utf-8")
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
            diffs = []
            if not product.get("ok"):
                diffs.append("product error: " + product.get("error", "?"))
            else:
                if product["top"] is None or oracle_payload["top"] is None:
                    if product["top"] != oracle_payload["top"]:
                        diffs.append("top-none drift")
                elif abs((product["top"] or 0.0) - (oracle_payload["top"] or 0.0)) > TOL:
                    diffs.append("top drift")
                if product["bottom"] is None or oracle_payload["bottom"] is None:
                    if product["bottom"] != oracle_payload["bottom"]:
                        diffs.append("bottom-none drift")
                elif abs((product["bottom"] or 0.0) - (oracle_payload["bottom"] or 0.0)) > TOL:
                    diffs.append("bottom drift")
            entries.append({
                "id": case_id,
                "input_sha256": sha256_bytes(input_bytes),
                "matched": not diffs,
                "diffs": diffs[:8],
            })

        bin_size = 1e-3
        # Build several pulse/DFE configurations.
        configs = [
            ("pam4_tp1a", dict(bin_size=1e-3, samples_per_ui=10, samples_for_c2m=8, levels=4,
                               cursor_index=160, dfe_tap_count=2, dfe_max=[0.5, 0.3], dfe_min=[-0.5, -0.3],
                               dfe_step=1e-3, sigma_rj_s=1e-4, sigma_x=0.03, sigma_n_v=1e-4, sigma_tx_v=1.2e-3,
                               ber_q=3.7, amplitude_dd_v=0.1, spec_ber=1e-4, t_o_mui=0.5, histogram_window="rectangle", ql=1.0)),
            ("pam4_gaussian_window", dict(bin_size=1e-3, samples_per_ui=10, samples_for_c2m=8, levels=4,
                               cursor_index=160, dfe_tap_count=2, dfe_max=[0.5, 0.3], dfe_min=[-0.5, -0.3],
                               dfe_step=1e-3, sigma_rj_s=1e-4, sigma_x=0.03, sigma_n_v=1e-4, sigma_tx_v=1.2e-3,
                               ber_q=3.7, amplitude_dd_v=0.1, spec_ber=1e-4, t_o_mui=0.5, histogram_window="gaussian", ql=1.3)),
            ("pam2_triangle", dict(bin_size=1e-3, samples_per_ui=8, samples_for_c2m=8, levels=2,
                               cursor_index=160, dfe_tap_count=1, dfe_max=[0.5], dfe_min=[-0.5],
                               dfe_step=1e-3, sigma_rj_s=5e-5, sigma_x=0.02, sigma_n_v=1e-4, sigma_tx_v=1e-3,
                               ber_q=3.5, amplitude_dd_v=0.08, spec_ber=1e-5, t_o_mui=0.75, histogram_window="triangle", ql=1.0)),
        ]
        for cfg_id, cfg in configs:
            c2m_pulse = pulse()
            p_arr = np.asarray(c2m_pulse, dtype=np.float64)
            ne = normal_pdf(0.0, cfg["ber_q"], cfg["bin_size"])
            cci = DiscretePdf.delta(cfg["bin_size"])
            top, bottom = calculate_c2m_vertical_eye(
                p_arr,
                cursor_index=cfg["cursor_index"],
                samples_per_ui=cfg["samples_per_ui"],
                samples_for_c2m=cfg["samples_for_c2m"],
                levels=cfg["levels"],
                bin_size=cfg["bin_size"],
                r_lm_ohm=50.0,
                dfe_tap_count=cfg["dfe_tap_count"],
                dfe_max=np.asarray(cfg["dfe_max"], dtype=np.float64),
                dfe_min=np.asarray(cfg["dfe_min"], dtype=np.float64),
                dfe_step=cfg["dfe_step"],
                sigma_rj_s=cfg["sigma_rj_s"],
                sigma_x=cfg["sigma_x"],
                sigma_n_v=cfg["sigma_n_v"],
                sigma_tx_v=cfg["sigma_tx_v"],
                ber_q=cfg["ber_q"],
                ne_noise_pdf=ne,
                cci_pdf=cci,
                amplitude_dd_v=cfg["amplitude_dd_v"],
                spec_ber=cfg["spec_ber"],
                t_o_mui=cfg["t_o_mui"],
                histogram_window=cfg["histogram_window"],
                ql=cfg["ql"],
            )
            c2m_input = {
                "pulse": c2m_pulse,
                "bin_size": cfg["bin_size"],
                "samples_per_ui": cfg["samples_per_ui"],
                "samples_for_c2m": cfg["samples_for_c2m"],
                "levels": cfg["levels"],
                "r_lm_ohm": 50.0,
                "dfe_tap_count": cfg["dfe_tap_count"],
                "dfe_max": cfg["dfe_max"],
                "dfe_min": cfg["dfe_min"],
                "dfe_step": cfg["dfe_step"],
                "sigma_rj_s": cfg["sigma_rj_s"],
                "sigma_x": cfg["sigma_x"],
                "sigma_n_v": cfg["sigma_n_v"],
                "sigma_tx_v": cfg["sigma_tx_v"],
                "ber_q": cfg["ber_q"],
                "ne_noise_pdf": pdf_dict(ne),
                "cci_pdf": pdf_dict(cci),
                "amplitude_dd_v": cfg["amplitude_dd_v"],
                "spec_ber": cfg["spec_ber"],
                "t_o_mui": cfg["t_o_mui"],
                "histogram_window": cfg["histogram_window"],
                "ql": cfg["ql"],
                "cursor_index": cfg["cursor_index"],
            }
            compare(cfg_id, c2m_input, {"top": top, "bottom": bottom})

        # t_o == 0 -> (None, None)
        cfg = configs[0][1]
        ne = normal_pdf(0.0, cfg["ber_q"], cfg["bin_size"])
        cci = DiscretePdf.delta(cfg["bin_size"])
        top, bottom = calculate_c2m_vertical_eye(
            np.asarray(pulse(), dtype=np.float64), cursor_index=cfg["cursor_index"],
            samples_per_ui=cfg["samples_per_ui"], samples_for_c2m=cfg["samples_for_c2m"],
            levels=cfg["levels"], bin_size=cfg["bin_size"], r_lm_ohm=50.0,
            dfe_tap_count=cfg["dfe_tap_count"], dfe_max=np.asarray(cfg["dfe_max"], dtype=np.float64),
            dfe_min=np.asarray(cfg["dfe_min"], dtype=np.float64), dfe_step=cfg["dfe_step"],
            sigma_rj_s=cfg["sigma_rj_s"], sigma_x=cfg["sigma_x"], sigma_n_v=cfg["sigma_n_v"],
            sigma_tx_v=cfg["sigma_tx_v"], ber_q=cfg["ber_q"], ne_noise_pdf=ne, cci_pdf=cci,
            amplitude_dd_v=cfg["amplitude_dd_v"], spec_ber=cfg["spec_ber"], t_o_mui=0.0,
            histogram_window="rectangle", ql=1.0,
        )
        c2m_input = dict(cfg); c2m_input["pulse"] = pulse(); c2m_input["bin_size"] = cfg["bin_size"]
        c2m_input["r_lm_ohm"] = 50.0; c2m_input["t_o_mui"] = 0.0; c2m_input["histogram_window"] = "rectangle"
        c2m_input["ne_noise_pdf"] = pdf_dict(ne); c2m_input["cci_pdf"] = pdf_dict(cci)
        c2m_input["cursor_index"] = cfg["cursor_index"]
        compare("t_o_zero", c2m_input, {"top": top, "bottom": bottom})

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "c2m_eye_crosscheck_matched" if matched else "c2m_eye_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com", "license": "MIT",
            "path": "src/agent_com/metrics/c2m.py",
            "functions": ["calculate_c2m_vertical_eye"],
            "numpy_version": np.__version__,
        },
        "tolerance": TOL,
        "entries": entries,
        "non_claims": ["not_full_contour_eye", "not_candidate_evaluation", "not_search_loop", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]))
        for diff in entry.get("diffs", []):
            print("  diff:", diff)
    print("all_matched=" + str(matched))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
