"""P5-04q candidate-helper cross-check: product runner vs agent-com oracle.

Runs _r480_pdf_bin_size / _r480_bbn_q_factor / _cannot_improve_fom /
_candidate_ber_q / _dfe_candidate_bounds / _jitter_response / _jitter_sigma
in fresh external custody on fixed inputs and compares every result against
the product runner. Hash-only evidence; no release claim. The candidate
evaluation body and the C2M eye search are deliberately not exercised here.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04q-candidate-helpers-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04q.candidate-helpers-crosscheck-evidence.v1"
TOLERANCE = 1e-9


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def pulse(size: int = 200) -> list[float]:
    return [
        0.05 + math.exp(-(i - 80.0) ** 2 / 300.0) * math.sin(i * 0.3)
        for i in range(size)
    ]


def close(a, b, tol: float = TOLERANCE) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= tol


def close_f64s(a, b, tol: float = TOLERANCE) -> str | None:
    a = [float(v) for v in a]
    b = [float(v) for v in b]
    if len(a) != len(b):
        return "length mismatch"
    for i, (x, y) in enumerate(zip(a, b)):
        if abs(x - y) > tol:
            return f"element {i}: {x} vs {y}"
    return None


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.equalization import search as oracle

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04q_candidate_helpers_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04q_candidate_helpers_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04q-crosscheck-") as tmp:
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

        sbr = pulse()
        sbr_arr = np.asarray(sbr, dtype=np.float64)

        # ---- _r480_pdf_bin_size ----
        for force, tag in ((False, "pdf_no_force"), (True, "pdf_force")):
            expected = oracle._r480_pdf_bin_size(0.1, {"BinSize": 1e-3, "force_pdf_bin_size": force})
            compare(tag,
                    {"pdf_bin_size": {"available_signal_v": 0.1, "bin_size": 1e-3, "force_pdf_bin_size": force}},
                    {"value": float(expected)},
                    lambda o, p: [] if close(p["pdf_bin_size"], o["value"]) else ["bin size drift"])

        # ---- _r480_bbn_q_factor (valid override) ----
        expected_q = oracle._r480_bbn_q_factor({"force_BBN_Q_factor": True, "BBN_Q_factor": 3.5})
        compare("bbn_q_forced",
                {"bbn_q": {"force_bbn_q_factor": True, "bbn_q_factor": 3.5}},
                {"value": None if expected_q is None else float(expected_q)},
                lambda o, p: [] if close(p["bbn_q"]["ok"], o["value"]) else ["bbn q drift"])
        expected_none = oracle._r480_bbn_q_factor({"force_BBN_Q_factor": False, "BBN_Q_factor": 3.5})
        compare("bbn_q_off",
                {"bbn_q": {"force_bbn_q_factor": False, "bbn_q_factor": 3.5}},
                {"value": None},
                lambda o, p: [] if p["bbn_q"]["ok"] is None and o["value"] is None else ["bbn q off drift"])

        # ---- _cannot_improve_fom ----
        cases = [
            ("cannot_improve_none", 0.5, 0.1, None, oracle._cannot_improve_fom(0.5, 0.1, None)),
            ("cannot_improve_sigma0", 0.5, 0.0, 10.0, oracle._cannot_improve_fom(0.5, 0.0, 10.0)),
            ("cannot_improve_true", 0.5, 0.1, 14.0, oracle._cannot_improve_fom(0.5, 0.1, 14.0)),
            ("cannot_improve_false", 0.5, 0.1, 13.0, oracle._cannot_improve_fom(0.5, 0.1, 13.0)),
        ]
        for cid, av, sigma, best, expected in cases:
            ib = {"available_signal": av, "sigma": sigma, "best_fom_db": best}
            compare(cid, {"cannot_improve": ib}, {"value": bool(expected)},
                    lambda o, p, _e=expected: [] if bool(p["cannot_improve"]) == _e else ["decision drift"])

        # ---- _candidate_ber_q ----
        params_crest = {"Noise_Crest_Factor": 3.8, "specBER": 1e-4}
        expected_crest = oracle._candidate_ber_q(params_crest)
        compare("ber_q_crest",
                {"ber_q": {"noise_crest_factor": 3.8, "spec_ber": 1e-4}},
                {"value": float(expected_crest)},
                lambda o, p: [] if close(p["ber_q"], o["value"]) else ["crest q drift"])
        params_erfc = {"Noise_Crest_Factor": 0.0, "specBER": 1e-4}
        expected_erfc = oracle._candidate_ber_q(params_erfc)
        compare("ber_q_erfcinv",
                {"ber_q": {"noise_crest_factor": 0.0, "spec_ber": 1e-4}},
                {"value": float(expected_erfc)},
                lambda o, p: [] if close(p["ber_q"], o["value"]) else ["erfcinv q drift"])

        # ---- _dfe_candidate_bounds (fixed) ----
        fixed_params = {"ndfe": 2, "bmax": [0.5, 0.5], "bmin": [-0.5, -0.5],
                        "Floating_DFE": False, "N_bmax": 2, "N_bf": 1, "N_bg": 1, "bmaxg": 0.3}
        exp = oracle._dfe_candidate_bounds(sbr_arr, cursor_index=80, samples_per_ui=8, parameters=fixed_params)
        compare("dfe_bounds_fixed",
                {"dfe_bounds": {"sbr": sbr, "cursor_index": 80, "samples_per_ui": 8,
                                "ndfe": 2, "bmax": [0.5, 0.5], "bmin": [-0.5, -0.5],
                                "floating_dfe": False, "n_bmax": 2, "n_bf": 1, "n_bg": 1, "bmaxg": 0.3}},
                {"res": exp},
                lambda o, p: _compare_bounds(o, p))

        # ---- _dfe_candidate_bounds (floating) ----
        float_params = {"ndfe": 1, "bmax": [0.5], "bmin": [-0.5],
                        "Floating_DFE": True, "N_bmax": 4, "N_bf": 1, "N_bg": 1, "bmaxg": 0.3}
        expf = oracle._dfe_candidate_bounds(sbr_arr, cursor_index=80, samples_per_ui=8, parameters=float_params)
        compare("dfe_bounds_floating",
                {"dfe_bounds": {"sbr": sbr, "cursor_index": 80, "samples_per_ui": 8,
                                "ndfe": 1, "bmax": [0.5], "bmin": [-0.5],
                                "floating_dfe": True, "n_bmax": 4, "n_bf": 1, "n_bg": 1, "bmaxg": 0.3}},
                {"res": expf},
                lambda o, p: _compare_bounds(o, p))

        # ---- _jitter_response ----
        exp_unlimited = oracle._jitter_response(sbr_arr, 80, 8, dfe_tap_count=2, limit_to_dfe_span=False)
        compare("jitter_unlimited",
                {"jitter": {"sbr": sbr, "cursor_index": 80, "samples_per_ui": 8, "dfe_tap_count": 2,
                            "limit_to_dfe_span": False, "num_ui": None}},
                {"values": [float(v) for v in exp_unlimited]},
                lambda o, p: _compare_values(o, p, "jitter"))
        exp_limited = oracle._jitter_response(sbr_arr, 80, 8, dfe_tap_count=2, limit_to_dfe_span=True)
        compare("jitter_limited",
                {"jitter": {"sbr": sbr, "cursor_index": 80, "samples_per_ui": 8, "dfe_tap_count": 2,
                            "limit_to_dfe_span": True, "num_ui": None}},
                {"values": [float(v) for v in exp_limited]},
                lambda o, p: _compare_values(o, p, "jitter"))
        exp_pad = oracle._jitter_response(sbr_arr, 80, 8, dfe_tap_count=2, limit_to_dfe_span=True, num_ui=10)
        compare("jitter_num_ui_pad",
                {"jitter": {"sbr": sbr, "cursor_index": 80, "samples_per_ui": 8, "dfe_tap_count": 2,
                            "limit_to_dfe_span": True, "num_ui": 10}},
                {"values": [float(v) for v in exp_pad]},
                lambda o, p: _compare_values(o, p, "jitter"))

        # ---- _jitter_sigma ----
        exp_sigma = oracle._jitter_sigma(
            sbr_arr, 80, 8,
            {"A_DD": 0.4, "sigma_RJ": 1e-4, "sigma_X": 0.03},
            {"LIMIT_JITTER_CONTRIB_TO_DFE_SPAN": False},
            dfe_tap_count=2)
        compare("jitter_sigma",
                {"jitter_sigma": {"sbr": sbr, "cursor_index": 80, "samples_per_ui": 8,
                                  "a_dd": 0.4, "sigma_rj": 1e-4, "sigma_x": 0.03,
                                  "dfe_tap_count": 2, "limit_to_dfe_span": False}},
                {"sigma": float(exp_sigma)},
                lambda o, p: [] if close(p["jitter_sigma"]["sigma"], o["sigma"]) else ["jitter sigma drift"])

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "candidate_helpers_crosscheck_matched" if matched else "candidate_helpers_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/equalization/search.py",
            "functions": [
                "_r480_pdf_bin_size", "_r480_bbn_q_factor", "_cannot_improve_fom",
                "_candidate_ber_q", "_dfe_candidate_bounds", "_jitter_response", "_jitter_sigma",
            ],
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


def _compare_bounds(o, p) -> list[str]:
    if not p.get("dfe_bounds", {}).get("ok", False):
        return ["product reported error"]
    exp_count, exp_max, exp_min, exp_loc = o["res"]
    prod = p["dfe_bounds"]
    diffs: list[str] = []
    if int(prod["count"]) != int(exp_count):
        diffs.append("count drift")
    for label, a, b in (("maximum", exp_max, prod["maximum"]), ("minimum", exp_min, prod["minimum"])):
        d = close_f64s(a, b)
        if d:
            diffs.append(f"{label}: {d}")
    for i, (a, b) in enumerate(zip([int(v) for v in exp_loc], [int(v) for v in prod["locations"]])):
        if a != b:
            diffs.append(f"location {i}: {a} vs {b}")
    if len(exp_loc) != len(prod["locations"]):
        diffs.append("location length mismatch")
    return diffs


def _compare_values(o, p, key) -> list[str]:
    if not p.get(key, {}).get("ok", False):
        return ["product reported error"]
    d = close_f64s(o["values"], p[key]["values"])
    return [] if d is None else [d]


if __name__ == "__main__":
    raise SystemExit(main())
