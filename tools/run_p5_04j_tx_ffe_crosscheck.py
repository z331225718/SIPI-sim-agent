"""P5-04j TX FFE grid cross-check: product runner vs agent-com oracle.

Runs full_grid_matrix / build_txffe_grid / first_strict_best /
select_fom_tracker in fresh external custody (agent-com equalization
tx_ffe module) on fixed inputs and compares every result against the
product runner. Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04j-tx-ffe-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04j.tx-ffe-crosscheck-evidence.v1"
TOLERANCE = 1e-12


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.equalization.tx_ffe import (
        build_txffe_grid as oracle_build,
        first_strict_best as oracle_first_best,
        full_grid_matrix as oracle_full_grid,
        select_fom_tracker as oracle_fom_tracker,
    )

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04j_tx_ffe_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04j_tx_ffe_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04j-crosscheck-") as tmp:
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

        # full grid matrix
        columns = [[0.1, -0.2, 0.3], [0.05, 0.1], [-0.4, 0.2]]
        oracle_grid = oracle_full_grid(tuple(np.asarray(c, dtype=np.float64) for c in columns))
        expected = [[float(v) for v in row] for row in oracle_grid]
        compare("full_grid_3col", {"full_grid": {"columns": columns}}, {"grid": expected},
                lambda o, p: [] if p["full_grid"]["grid"] == o["grid"] else ["grid drift"])

        # build grid with filtering
        values = {
            "tx_ffe_cm2_values": [0.1, -0.2],
            "tx_ffe_cm1_values": [0.05],
            "tx_ffe_cp1_values": [0.02, 0.03],
        }
        oracle = oracle_build({k: np.asarray(v, dtype=np.float64) for k, v in values.items()}, c0_min=0.0)
        expected = {
            "cursor": [float(v) for v in oracle.cursor],
            "taps": [[float(v) for v in row] for row in oracle.taps],
            "source_indices": [[int(v) for v in row] for row in oracle.source_indices],
            "precursor_count": int(oracle.precursor_count),
        }
        compare("build_grid_filtered", {"build_grid": {"values": values, "c0_min": 0.0, "retain_invalid": False}},
                expected,
                lambda o, p: [] if p["build_grid"] == o else ["surface drift"])

        # build grid retaining invalid
        oracle_r = oracle_build({k: np.asarray(v, dtype=np.float64) for k, v in values.items()}, c0_min=0.0, retain_invalid=True)
        expected_r = {
            "cursor": [float(v) for v in oracle_r.cursor],
            "taps": [[float(v) for v in row] for row in oracle_r.taps],
            "source_indices": [[int(v) for v in row] for row in oracle_r.source_indices],
            "precursor_count": int(oracle_r.precursor_count),
        }
        compare("build_grid_retain", {"build_grid": {"values": values, "c0_min": 0.0, "retain_invalid": True}},
                expected_r,
                lambda o, p: [] if p["build_grid"] == o else ["surface drift"])

        # build grid with cm1 only
        values_single = {"tx_ffe_cm1_values": [0.1, -0.2]}
        oracle_s = oracle_build({k: np.asarray(v, dtype=np.float64) for k, v in values_single.items()}, c0_min=0.5)
        expected_s = {
            "cursor": [float(v) for v in oracle_s.cursor],
            "taps": [[float(v) for v in row] for row in oracle_s.taps],
            "source_indices": [[int(v) for v in row] for row in oracle_s.source_indices],
            "precursor_count": int(oracle_s.precursor_count),
        }
        compare("build_grid_cm1", {"build_grid": {"values": values_single, "c0_min": 0.5, "retain_invalid": False}},
                expected_s,
                lambda o, p: [] if p["build_grid"] == o else ["surface drift"])

        # first strict best with ties
        scores = [2.0, 5.0, 5.0, 3.0, 7.0, 6.0]
        expected_best = int(oracle_first_best(np.asarray(scores, dtype=np.float64)))
        compare("first_best_ties", {"first_best": {"scores": scores}}, {"index": expected_best},
                lambda o, p: [] if p["first_best"]["index"] == o["index"] else ["index drift"])

        # fom tracker 2D with mask
        tracker = [1.0, 5.0, 2.0, 4.0, 9.0, 3.0]
        mask = [True, True, True, True, False, True]
        oracle_f = oracle_fom_tracker(np.asarray(tracker, dtype=np.float64).reshape(2, 3), valid=np.asarray(mask, dtype=bool).reshape(2, 3))
        expected_f = {"indices": [int(v) for v in oracle_f.indices], "score": float(oracle_f.score)}
        compare("fom_tracker_masked",
                {"fom_tracker": {"values": tracker, "shape": [2, 3], "valid": mask}},
                expected_f,
                lambda o, p: [] if p["fom_tracker"] == o else ["fom drift"])

        # fom tracker 3D no mask
        tracker_3d = list(range(1, 25))
        oracle_3d = oracle_fom_tracker(np.asarray(tracker_3d, dtype=np.float64).reshape(2, 3, 4))
        expected_3d = {"indices": [int(v) for v in oracle_3d.indices], "score": float(oracle_3d.score)}
        compare("fom_tracker_3d",
                {"fom_tracker": {"values": tracker_3d, "shape": [2, 3, 4]}},
                expected_3d,
                lambda o, p: [] if p["fom_tracker"] == o else ["fom drift"])

    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "tx_ffe_crosscheck_matched" if matched else "tx_ffe_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/equalization/tx_ffe.py",
            "functions": ["full_grid_matrix", "build_txffe_grid", "first_strict_best", "select_fom_tracker"],
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
