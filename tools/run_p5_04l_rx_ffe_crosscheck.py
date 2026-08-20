"""P5-04l RX FFE cross-check: product runner vs agent-com oracle.

Runs apply_rx_ffe / force_rx_ffe in fresh external custody (agent-com
equalization rx_ffe module) on fixed waveforms and compares every result
against the product runner. The LU solve surface is compared with a
documented tolerance for equivalent-but-distinct linear algebra
backends. Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04l-rx-ffe-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04l.rx-ffe-crosscheck-evidence.v1"
TOLERANCE = 1e-9  # LU backends (LAPACK dgesv vs partial-pivot LU) are
# mathematically equivalent but not bit-identical.


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def waveform(seed: float, length: int = 48) -> list[float]:
    values = []
    for index in range(length):
        i = float(index)
        values.append(
            math.exp(-((i - 24.0) ** 2) / 100.0) * math.sin(i * 0.4 + seed)
        )
    return values


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.equalization.rx_ffe import (
        apply_rx_ffe as oracle_apply,
        force_rx_ffe as oracle_force,
    )

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04l_rx_ffe_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04l_rx_ffe_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04l-crosscheck-") as tmp:
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

        def close_list(a: list[float], b: list[float], tol: float) -> bool:
            return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))

        # apply with wraparound
        w = waveform(0.5)
        taps = [0.3, 1.0, -0.2, 0.1]
        oracle = oracle_apply(np.asarray(taps), 1, 4, np.asarray(w))
        expected = {"filtered": [float(v) for v in oracle]}
        compare("apply_wraparound",
                {"apply": {"taps": taps, "precursor_count": 1, "samples_per_ui": 4, "waveform": w}},
                expected,
                lambda o, p: [] if close_list(p["apply"]["filtered"], o["filtered"], TOLERANCE) else ["filtered drift"])

        # force basic
        w2 = waveform(1.2)
        oracle = oracle_force(np.asarray(w2), cursor_index=24, precursor_count=1, postcursor_count=2,
                              samples_per_ui=4, dfe_first_max=0.0)
        expected = {
            "taps": [float(v) for v in oracle.taps],
            "filtered": None if oracle.filtered is None else [float(v) for v in oracle.filtered],
            "matrix": [[float(v) for v in row] for row in oracle.matrix],
        }
        compare("force_basic",
                {"force": {"waveform": w2, "cursor_index": 24, "precursor_count": 1, "postcursor_count": 2,
                           "samples_per_ui": 4, "dfe_first_max": 0.0, "unity_cursor": False, "tap_step": 0.0, "return_filtered": True}},
                expected,
                lambda o, p: ([] if close_list(p["force"]["taps"], o["taps"], TOLERANCE)
                              and close_list(p["force"]["filtered"], o["filtered"], TOLERANCE)
                              and p["force"]["matrix"] == o["matrix"] else ["force drift"]))

        # force with dfe_first_max + unity cursor + tap step
        oracle2 = oracle_force(np.asarray(w2), cursor_index=24, precursor_count=2, postcursor_count=2,
                               samples_per_ui=4, dfe_first_max=0.4, unity_cursor=True, tap_step=0.05, return_filtered=False)
        expected2 = {
            "taps": [float(v) for v in oracle2.taps],
            "filtered": None,
            "matrix": [[float(v) for v in row] for row in oracle2.matrix],
        }
        compare("force_dfe_unity_step",
                {"force": {"waveform": w2, "cursor_index": 24, "precursor_count": 2, "postcursor_count": 2,
                           "samples_per_ui": 4, "dfe_first_max": 0.4, "unity_cursor": True, "tap_step": 0.05, "return_filtered": False}},
                expected2,
                lambda o, p: ([] if close_list(p["force"]["taps"], o["taps"], TOLERANCE)
                              and p["force"]["filtered"] is None and o["filtered"] is None
                              and p["force"]["matrix"] == o["matrix"] else ["force drift"]))

        # force no filtered
        oracle3 = oracle_force(np.asarray(w), cursor_index=16, precursor_count=1, postcursor_count=1,
                               samples_per_ui=4, dfe_first_max=0.0, return_filtered=False)
        expected3 = {
            "taps": [float(v) for v in oracle3.taps],
            "filtered": None,
            "matrix": [[float(v) for v in row] for row in oracle3.matrix],
        }
        compare("force_no_filtered",
                {"force": {"waveform": w, "cursor_index": 16, "precursor_count": 1, "postcursor_count": 1,
                           "samples_per_ui": 4, "dfe_first_max": 0.0, "unity_cursor": False, "tap_step": 0.0, "return_filtered": False}},
                expected3,
                lambda o, p: ([] if close_list(p["force"]["taps"], o["taps"], TOLERANCE)
                              and p["force"]["matrix"] == o["matrix"] else ["force drift"]))

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "rx_ffe_crosscheck_matched" if matched else "rx_ffe_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/equalization/rx_ffe.py",
            "functions": ["apply_rx_ffe", "force_rx_ffe"],
            "numpy_version": np.__version__,
        },
        "tolerance": TOLERANCE,
        "tolerance_note": "LU solve backends (LAPACK dgesv vs partial-pivot LU) are mathematically equivalent but not bit-identical",
        "entries": entries,
        "non_claims": ["not_floating_rxffe", "not_wiener_branch", "not_search_integration", "not_release_evidence"],
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
