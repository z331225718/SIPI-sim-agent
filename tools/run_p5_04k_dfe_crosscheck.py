"""P5-04k DFE bank cross-check: product runner vs agent-com oracle.

Runs apply_tail_rss_bounds / clip_dfe / find_dfe_bank_locations /
apply_dfe_bank in fresh external custody (agent-com equalization dfe
module) on fixed inputs and compares every result against the product
runner. Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04k-dfe-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04k.dfe-crosscheck-evidence.v1"
TOLERANCE = 1e-12


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.equalization.dfe import (
        apply_dfe_bank as oracle_bank,
        apply_tail_rss_bounds as oracle_tail,
        clip_dfe as oracle_clip,
        find_dfe_bank_locations as oracle_locations,
    )

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04k_dfe_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04k_dfe_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04k-crosscheck-") as tmp:
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

        def close(a: object, b: object) -> bool:
            if isinstance(a, float) and isinstance(b, float):
                return abs(a - b) <= TOLERANCE
            if isinstance(a, list) and isinstance(b, list):
                return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
            return a == b

        # tail rss rewrite (exceeding)
        taps = [0.1, 0.2, 0.3, 0.4]
        maximum = [0.5, 0.5, 0.5, 0.5]
        minimum = [-0.5, -0.5, -0.5, -0.5]
        oracle = oracle_tail(np.asarray(taps), np.asarray(maximum), np.asarray(minimum), tail_start_index=2, rss_max=0.25)
        expected = {
            "tail_rss": float(oracle.tail_rss),
            "maximum": [float(v) for v in oracle.maximum],
            "minimum": [float(v) for v in oracle.minimum],
        }
        compare("tail_rss_exceed",
                {"tail_rss": {"taps": taps, "maximum": maximum, "minimum": minimum, "tail_start_index": 2, "rss_max": 0.25}},
                expected,
                lambda o, p: [] if close(p["tail_rss"], o) else ["surface drift"])

        # tail rss none
        oracle_n = oracle_tail(np.asarray(taps), np.asarray(maximum), np.asarray(minimum), tail_start_index=None, rss_max=0.25)
        expected_n = {
            "tail_rss": float(oracle_n.tail_rss),
            "maximum": [float(v) for v in oracle_n.maximum],
            "minimum": [float(v) for v in oracle_n.minimum],
        }
        compare("tail_rss_none",
                {"tail_rss": {"taps": taps, "maximum": maximum, "minimum": minimum, "rss_max": 0.25}},
                expected_n,
                lambda o, p: [] if close(p["tail_rss"], o) else ["surface drift"])

        # tail rss below max (unchanged)
        oracle_b = oracle_tail(np.asarray(taps), np.asarray(maximum), np.asarray(minimum), tail_start_index=3, rss_max=10.0)
        expected_b = {
            "tail_rss": float(oracle_b.tail_rss),
            "maximum": [float(v) for v in oracle_b.maximum],
            "minimum": [float(v) for v in oracle_b.minimum],
        }
        compare("tail_rss_below",
                {"tail_rss": {"taps": taps, "maximum": maximum, "minimum": minimum, "tail_start_index": 3, "rss_max": 10.0}},
                expected_b,
                lambda o, p: [] if close(p["tail_rss"], o) else ["surface drift"])

        # clip
        values = [0.8, -0.8, 0.0, 0.3, -0.1]
        upper = [0.5, 0.5, 0.5, 0.5, 0.5]
        lower = [-0.2, -0.2, -0.2, -0.2, -0.2]
        oracle_c = oracle_clip(np.asarray(values), np.asarray(upper), np.asarray(lower))
        expected_c = {"clipped": [float(v) for v in oracle_c]}
        compare("clip_5",
                {"clip": {"values": values, "maximum": upper, "minimum": lower}},
                expected_c,
                lambda o, p: [] if close(p["clip"], o) else ["clip drift"])

        # bank locations: two banks on a structured waveform
        hisi = [1.0, 0.9, 0.1, 0.05, 0.8, 0.85, 0.05, 0.02, 0.1, 0.08, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        oracle_l = oracle_locations(np.asarray(hisi), start_index=0, end_index=15, taps_per_bank=2, cursor=1.0, coefficient_limit=0.0, bank_count=2)
        expected_l = {"locations": [int(v) for v in oracle_l]}
        compare("bank_locations_two",
                {"bank_locations": {"hisi": hisi, "start_index": 0, "end_index": 15, "taps_per_bank": 2, "cursor": 1.0, "coefficient_limit": 0.0, "bank_count": 2}},
                expected_l,
                lambda o, p: [] if p["bank_locations"] == o else ["locations drift"])

        # bank locations: single bank with offset start
        hisi2 = [0.0, 0.0, 1.0, 0.9, 0.1, 0.05, 0.0, 0.0]
        oracle_l2 = oracle_locations(np.asarray(hisi2), start_index=2, end_index=7, taps_per_bank=2, cursor=1.0, coefficient_limit=0.0, bank_count=1)
        expected_l2 = {"locations": [int(v) for v in oracle_l2]}
        compare("bank_locations_offset",
                {"bank_locations": {"hisi": hisi2, "start_index": 2, "end_index": 7, "taps_per_bank": 2, "cursor": 1.0, "coefficient_limit": 0.0, "bank_count": 1}},
                expected_l2,
                lambda o, p: [] if p["bank_locations"] == o else ["locations drift"])

        # apply bank with quantization
        hisi_a = [0.08, 0.06, 0.12, 0.01]
        hisi_ref = [0.0, 0.0, 0.0, 0.0]
        oracle_a = oracle_bank(np.asarray(hisi_a), np.asarray(hisi_ref), start_index=0, tap_count=3, cursor=0.1, coefficient_limit=1.0, quantization_step=0.5)
        expected_a = {
            "residual": [float(v) for v in oracle_a.residual],
            "reference": [float(v) for v in oracle_a.reference],
            "coefficients": [float(v) for v in oracle_a.coefficients],
        }
        compare("apply_bank_quantized",
                {"apply_bank": {"hisi": hisi_a, "hisi_ref": hisi_ref, "start_index": 0, "tap_count": 3, "cursor": 0.1, "coefficient_limit": 1.0, "quantization_step": 0.5}},
                expected_a,
                lambda o, p: [] if close(p["apply_bank"], o) else ["bank drift"])

        # apply bank without quantization
        oracle_p = oracle_bank(np.asarray(hisi_a), np.asarray(hisi_ref), start_index=0, tap_count=3, cursor=0.1, coefficient_limit=0.9)
        expected_p = {
            "residual": [float(v) for v in oracle_p.residual],
            "reference": [float(v) for v in oracle_p.reference],
            "coefficients": [float(v) for v in oracle_p.coefficients],
        }
        compare("apply_bank_plain",
                {"apply_bank": {"hisi": hisi_a, "hisi_ref": hisi_ref, "start_index": 0, "tap_count": 3, "cursor": 0.1, "coefficient_limit": 0.9}},
                expected_p,
                lambda o, p: [] if close(p["apply_bank"], o) else ["bank drift"])

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "dfe_crosscheck_matched" if matched else "dfe_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/equalization/dfe.py",
            "functions": ["apply_tail_rss_bounds", "clip_dfe", "find_dfe_bank_locations", "apply_dfe_bank"],
            "numpy_version": np.__version__,
        },
        "tolerance": TOLERANCE,
        "entries": entries,
        "non_claims": ["not_search_integration", "not_release_evidence"],
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
