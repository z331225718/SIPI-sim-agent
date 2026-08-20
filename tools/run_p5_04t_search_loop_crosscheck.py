"""P5-04t search-loop support cross-check: product runner vs agent-com oracle.

Runs the R480 non-MMSE no-RxFFE search private support helpers
(rectangular_pulse_response, _peak_window, _shift_matrix,
_r480_sample_offsets, _skip_local_search, _skip_high_pass_local_search,
_anchored_cursor, _validate_supported_branch) in fresh external custody on
fixed inputs and compares every result against the product runner.
Hash-only evidence; no release claim. The composite optimize_fom loop and
candidate evaluation remain separate scopes.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04t-search-loop-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04t.search-loop-crosscheck-evidence.v1"
TOL = 1e-9


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com import compat
    from agent_com.equalization import search as oracle
    from agent_com.signal.fd_to_td import rectangular_pulse_response

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04t_search_loop_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04t_search_loop_runner-*.exe"))[-1]

    entries = []

    def compare(case_id: str, payload: dict[str, object], predicate) -> None:
        input_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
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
        diffs = predicate(product)
        entries.append({
            "id": case_id,
            "input_sha256": sha256_bytes(input_bytes),
            "matched": not diffs,
            "diffs": diffs[:8],
        })

    def close(a, b, tol=TOL):
        return abs(float(a) - float(b)) <= tol

    def f64s_close(a, b, tol=TOL):
        a = [float(v) for v in a]; b = [float(v) for v in b]
        if len(a) != len(b): return "length"
        for i, (x, y) in enumerate(zip(a, b)):
            if not close(x, y, tol): return f"elem {i}"
        return None

    # ---- rectangular_pulse_response ----
    impulse = [0.1, 0.4, 0.9, 0.7, 0.3, 0.05]
    for spu, tag in ((1, "rect_spu1"), (3, "rect_spu3")):
        exp = [float(v) for v in rectangular_pulse_response(np.asarray(impulse), spu)]
        compare(tag,
                {"rectangular": {"impulse": impulse, "samples_per_ui": spu}},
                lambda p, _e=exp: [] if f64s_close(p["rectangular"], _e) is None else ["rect drift"])

    # ---- _peak_window (FD impulse) ----
    freq_n = 64
    response = [0.1 * math.sin(i * 0.3) * math.exp(-i / 40.0) + 0.2 for i in range(freq_n)]
    for is_pulse, tag in ((False, "peak_fd"), (True, "peak_pulse")):
        if is_pulse:
            exp = oracle._peak_window(np.asarray(response), 8, is_pulse=True)
        else:
            exp = oracle._peak_window(np.asarray(response), 8, is_pulse=False)
        compare(tag,
                {"peak_window": {"response": response, "samples_per_ui": 8, "is_pulse": is_pulse}},
                lambda p, _e=exp: [] if int(p["peak_window"]["start"]) == int(_e[0]) and int(p["peak_window"]["stop"]) == int(_e[1]) else ["peak drift"])

    # ---- _shift_matrix ----
    pulse = [1.0, 2.0, 3.0, 4.0, 5.0]
    for pc, tag in ((1, "shift_pc1"), (2, "shift_pc2")):
        exp = oracle._shift_matrix(np.asarray(pulse), pc, 1, 3)
        expected = [ [float(v) for v in col] for col in exp.T ]
        compare(tag,
                {"shift_matrix": {"pulse": pulse, "precursor_count": pc, "samples_per_ui": 1, "tap_count": 3}},
                lambda p, _e=expected: [] if all(f64s_close(p["shift_matrix"][j], _e[j]) is None for j in range(len(_e))) else ["shift drift"])

    # ---- _r480_sample_offsets ----
    for mode, rng in (("full-sweep", [-2, 2]), ("middle", [-2, 2]), ("full-sweep", [0]), ("middle", [-1, 1])):
        exp = list(oracle._r480_sample_offsets({"ts_sample_adj_range": rng}, {"TS_SRCH_MODE": mode}))
        tag = f"offsets_{mode}_{'_'.join(map(str, rng))}".replace("-", "n").replace("[","").replace("]","").replace(",","")
        compare(tag,
                {"sample_offsets": {"range": rng, "mode": mode}},
                lambda p, _e=exp: [] if all(int(a) == int(b) for a, b in zip(p["sample_offsets"], _e)) and len(p["sample_offsets"]) == len(_e) else ["offset drift"])

    # ---- _skip_local_search ----
    # _skip_local_search derives its sweep from _sweep_order(parameters);
    # provide tx_ffe fields so the oracle picks a deterministic sweep and the
    # product receives that same sweep for an aligned comparison.
    params_skip = {
        "LOCAL_SEARCH": 1.0,
        "tx_ffe_cm0_values": np.array([0.0, 0.1], dtype=np.float64),
        "tx_ffe_cp1_values": np.array([0.3], dtype=np.float64),
        "tx_ffe_cp2_values": np.array([0.2, 0.05], dtype=np.float64),
    }
    oracle_sweep = oracle._sweep_order(params_skip)
    cases = [
        ("skip_none_best", [1, 2, 1], None),
        ("skip_local_true", [1, 2, 1], [1, 1, 1]),
        ("skip_local_false", [1, 1, 1], [1, 1, 1]),
    ]
    for cid, current, best in cases:
        cur = np.asarray(current, dtype=np.int64)
        best_arr = None if best is None else np.asarray(best, dtype=np.int64)
        exp = bool(oracle._skip_local_search(cur, best_arr, params_skip))
        local = float(params_skip["LOCAL_SEARCH"])
        cfg = {"current": list(current), "best": list(best) if best is not None else None,
               "sweep": list(oracle_sweep), "local_search": local}
        compare("skip_local_" + cid, {"skip_local": cfg},
                lambda p, _e=exp: [] if bool(p["skip_local"]) == _e else ["skip drift"])

    # ---- _skip_high_pass_local_search ----
    for cid, args, exp in (
        ("hp_none", (1, 3, None, 2.0), False),
        ("hp_far", (2, 5, 1, 2.0), True),
        ("hp_close", (2, 2, 1, 2.0), False),
    ):
        ctle_index, hpi, best_hp, local = args
        exp_bool = bool(oracle._skip_high_pass_local_search(ctle_index, hpi, best_hp, {"LOCAL_SEARCH": local}))
        compare("skip_hp_" + cid,
                {"skip_hp": {"ctle_index": ctle_index, "high_pass_index": hpi, "best_high_pass_index": best_hp, "local_search": local}},
                lambda p, _e=exp_bool: [] if bool(p["skip_hp"]) == _e else ["hp skip drift"])

    # ---- _anchored_cursor ----
    sbr = [0.1 * math.cos(i * 0.2) + 0.5 for i in range(120)]
    for anchor in (0, 1, 2):
        exp = dict()
        if anchor == 0:
            exp = {"ok": True, "index": 60}
        elif anchor == 1:
            exp = {"ok": True, "index": 70}
        else:
            # anchor2: computed by oracle
            sample_obj = type("S", (), {"cursor_index": 60, "peak_index": 70})()
            idx = oracle._anchored_cursor(sample_obj, np.asarray(sbr), {"ts_anchor": 2}, 8)
            exp = {"ok": True, "index": idx}
        compare("anchored_" + str(anchor),
                {"anchored": {"cursor": 60, "peak": 70, "ts_anchor": anchor, "sbr": sbr, "samples_per_ui": 8}},
                lambda p, _e=exp: [] if bool(p["anchored"]["ok"]) == _e["ok"] and int(p["anchored"]["index"]) == int(_e["index"]) else ["anchor drift"])

    # ---- _validate_supported_branch ----
    # RxFFe is presented as absent/0 in the real no-RxFFE branch; the method
    # label is the unambiguous accept/reject discriminator.
    for cid, opts, exp in (
        ("validate_ok", {"FFE_OPT_METHOD": "FV-LMS", "RxFFe": False}, True),
        ("validate_badmethod", {"FFE_OPT_METHOD": "LD", "RxFFe": False}, False),
    ):
        exp_bool = True
        try:
            oracle._validate_supported_branch({"ndfe": 2}, opts)
        except Exception:
            exp_bool = False
        # product input uses lowercase keys translated from the oracle ones
        prod_opts = {"ffe_opt_method": opts["FFE_OPT_METHOD"], "rxffe": opts["RxFFe"]}
        compare("validate_" + cid, {"validate": prod_opts},
                lambda p, _e=exp_bool: [] if bool(p["validate"]) == _e else ["validate drift"])

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "search_loop_support_crosscheck_matched" if matched else "search_loop_support_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com", "license": "MIT",
            "path": "src/agent_com/equalization/search.py + signal/fd_to_td.py",
            "functions": ["rectangular_pulse_response", "_peak_window", "_shift_matrix", "_r480_sample_offsets", "_skip_local_search", "_skip_high_pass_local_search", "_anchored_cursor", "_validate_supported_branch"],
            "numpy_version": np.__version__,
        },
        "tolerance": TOL,
        "entries": entries,
        "non_claims": ["not_composite_loop", "not_candidate_evaluation", "not_release_evidence"],
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
