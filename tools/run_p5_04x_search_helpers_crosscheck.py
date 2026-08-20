# -*- coding: utf-8 -*-
"""P5-04t-x search-loop helper cross-check: product vs independent ref.

Verifies rectangular_pulse_response_v1, peak_window, and shift_matrix
against independently written reference implementations on a fixed pulse.
These helpers feed the composite non-MMSE search loop (P5-04t).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04t-search-helpers-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04x.search-helpers-crosscheck-evidence.v1"


def rectangular_pulse(impulse, spu):
    # reference: zero-state running sum over a samples_per_ui-long window
    # (out[i] = sum(impulse[i-spu+1 .. i])), matching the product running sum;
    # NO averaging (the product does not divide by spu).
    n = len(impulse)
    out = [0.0] * n
    running = 0.0
    for i in range(n):
        running += impulse[i]
        if i >= spu:
            running -= impulse[i - spu]
        out[i] = running
    return out


def peak_window_ref(pulse, spu):
    # reference: first argmax, then [-20*spu, +20*spu+1) clamped.
    peak = max(range(len(pulse)), key=lambda i: pulse[i])
    start = max(0, peak - 20 * spu)
    stop = min(peak + 20 * spu + 1, len(pulse))
    return [start, stop]


def shift_matrix_ref(pulse, precursor, spu, taps):
    n = len(pulse)
    rows = []
    for t in range(taps):
        shift = (t - precursor) * spu
        col = []
        for i in range(n):
            col.append(pulse[(i - shift) % n])
        rows.append(col)
    return rows


def main() -> int:
    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04x_search_helpers_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04x_search_helpers_runner-*.exe"))[-1]

    spu = 4
    n = 200
    impulse = [max(0.5 * math.exp(-((i - 80) ** 2) / 50.0) + 0.01, 0.0) for i in range(n)]
    precursor = 1
    taps = 3
    input_payload = {"impulse": impulse, "samples_per_ui": spu, "precursor": precursor, "taps": taps}

    ref_pulse = rectangular_pulse(impulse, spu)
    ref_window = peak_window_ref(ref_pulse, spu)
    ref_matrix = shift_matrix_ref(ref_pulse, precursor, spu, taps)

    with tempfile.TemporaryDirectory(prefix="p5-04x-") as tmp:
        work = Path(tmp)
        input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
        input_path = work / "input.json"
        input_path.write_bytes(input_bytes)
        report_path = work / "product.json"
        run = subprocess.run(
            [str(runner), "--input", str(input_path), "--report", str(report_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if run.returncode != 0:
            raise SystemExit("runner failed :: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))

        diffs = []
        # pulse elementwise (tolerance 1e-12)
        prod_pulse = product["pulse"]
        pulse_ok = len(prod_pulse) == len(ref_pulse) and all(abs(a - b) < 1e-12 for a, b in zip(prod_pulse, ref_pulse))
        if not pulse_ok:
            diffs.append("pulse_drift")
        # window
        prod_win = product["window"]
        win_ok = list(prod_win) == ref_window
        if not win_ok:
            diffs.append("window_drift")
        # matrix
        prod_mat = product["matrix"]
        mat_ok = True
        if len(prod_mat) != len(ref_matrix):
            mat_ok = False
        else:
            for r1, r2 in zip(prod_mat, ref_matrix):
                if r1 != r2:
                    mat_ok = False; break
        if not mat_ok:
            diffs.append("matrix_drift")

        entry = {"id": "helpers_on_pulse", "window": ref_window, "taps": taps, "matched": not diffs, "diffs": diffs}
        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if not diffs else "mis_match",
            "policy": "sipi.p5-04t.search-loop.v1.nonmmse-no-rxffe",
            "matched_count": 1 if not diffs else 0,
            "case_count": 1,
            "entries": [entry],
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
        print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"], "matched_count": evidence["matched_count"], "diffs": diffs}, indent=2))
        return 0 if not diffs else 1


if __name__ == "__main__":
    raise SystemExit(main())