"""P5-04f sampled-signal PDF cross-check: product runner vs agent-com oracle.

Runs the product sampled-signal PDF runner on a fixed case set and
compares each discrete PDF against the MIT agent-com implementation
imported in fresh external custody (numpy/scipy versions recorded).
Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04f-sampled-signal-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04f.sampled-signal-crosscheck-evidence.v1"
TOLERANCE = 1e-12

CASES = [
    {"id": "pam4_direct", "samples": [0.42, -0.15, 0.03, -0.42, 0.15, -0.03, 0.42, 0.42, -0.42, 0.15], "levels": 4, "bin_size": 0.01, "sparse": False},
    {"id": "pam4_sparse", "samples": [0.42, -0.15, 0.03, -0.42, 0.15, -0.03, 0.42, 0.42, -0.42, 0.15], "levels": 4, "bin_size": 0.01, "sparse": True},
    {"id": "filter_and_zero", "samples": [0.05, 0.004, -0.02, 0.001, 0.0], "levels": 4, "bin_size": 0.01, "sparse": False},
    {"id": "all_zero", "samples": [0.0, 0.0], "levels": 4, "bin_size": 0.01, "sparse": False},
    {"id": "small_only", "samples": [0.005, -0.003], "levels": 4, "bin_size": 0.01, "sparse": False},
    {"id": "pam2_direct", "samples": [0.42, -0.15, 0.03, -0.42, 0.15, -0.03, 0.42, 0.42, -0.42, 0.15], "levels": 2, "bin_size": 0.01, "sparse": False},
    {"id": "pam2_sparse", "samples": [0.42, -0.15, 0.03, -0.42, 0.15, -0.03, 0.42, 0.42, -0.42, 0.15], "levels": 2, "bin_size": 0.01, "sparse": True},
    {"id": "pam3_direct", "samples": [0.42, -0.15, 0.03, -0.42, 0.15, -0.03, 0.42, 0.42, -0.42, 0.15], "levels": 3, "bin_size": 0.01, "sparse": False},
    {"id": "pam3_sparse", "samples": [0.42, -0.15, 0.03, -0.42, 0.15, -0.03, 0.42, 0.42, -0.42, 0.15], "levels": 3, "bin_size": 0.01, "sparse": True},
    {"id": "negative_max", "samples": [-0.2, 0.005], "levels": 4, "bin_size": 0.01, "sparse": False},
    {"id": "negative_max_sparse", "samples": [-0.2, 0.005], "levels": 4, "bin_size": 0.01, "sparse": True},
    {"id": "half_bin_boundary", "samples": [0.015, -0.015, 0.004999, -0.004999], "levels": 4, "bin_size": 0.01, "sparse": False},
]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def sha256_json(value: object) -> str:
    return sha256_bytes(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    import scipy
    from agent_com.noise.discrete_pdf import sampled_signal_pdf as oracle_sampled_signal_pdf

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04f_sampled_signal_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04f_sampled_signal_runner-*.exe"))[-1]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04f-crosscheck-") as tmp:
        work = Path(tmp)
        for case in CASES:
            samples_bytes = json.dumps(case["samples"], separators=(",", ":")).encode("utf-8")
            samples_hash = sha256_bytes(samples_bytes)
            samples_path = work / (case["id"] + ".json")
            samples_path.write_bytes(samples_bytes)
            oracle = oracle_sampled_signal_pdf(
                np.asarray(case["samples"], dtype=np.float64),
                levels=case["levels"],
                bin_size=case["bin_size"],
                sparse_pam=case["sparse"],
            )
            oracle_payload = {
                "bin_size": float(oracle.bin_size),
                "min_bin": int(oracle.min_bin),
                "probability": [float(item) for item in oracle.probability],
            }
            report_path = work / (case["id"] + "-product.json")
            command = [
                str(runner), "--samples", str(samples_path),
                "--levels", str(case["levels"]),
                "--bin-size", str(case["bin_size"]),
                "--report", str(report_path),
            ]
            if case["sparse"]:
                command.append("--sparse")
            run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit("runner failed: " + case["id"])
            product = json.loads(report_path.read_text(encoding="utf-8"))
            product_payload = {
                "bin_size": float(product["bin_size_out"]),
                "min_bin": int(product["min_bin"]),
                "probability": [float(item) for item in product["probability"]],
            }
            mismatch = None
            max_abs_diff = None
            if product_payload["bin_size"] != oracle_payload["bin_size"]:
                mismatch = "bin_size"
            elif product_payload["min_bin"] != oracle_payload["min_bin"]:
                mismatch = "min_bin"
            elif len(product_payload["probability"]) != len(oracle_payload["probability"]):
                mismatch = "length"
            else:
                max_abs_diff = max(
                    abs(a - b)
                    for a, b in zip(product_payload["probability"], oracle_payload["probability"])
                )
                if max_abs_diff > TOLERANCE:
                    mismatch = "probability max_abs_diff " + format(max_abs_diff, ".3e") + " > " + format(TOLERANCE, ".0e")
            entries.append({
                "id": case["id"],
                "levels": case["levels"],
                "bin_size": case["bin_size"],
                "sparse_pam": case["sparse"],
                "samples_sha256": samples_hash,
                "oracle_sha256": sha256_json(oracle_payload),
                "product_sha256": sha256_json(product_payload),
                "oracle_min_bin": oracle_payload["min_bin"],
                "product_min_bin": product_payload["min_bin"],
                "probability_len": len(oracle_payload["probability"]),
                "max_abs_diff": max_abs_diff,
                "matched": mismatch is None,
                "mismatch": mismatch,
            })
    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "sampled_signal_pdf_crosscheck_matched" if matched else "sampled_signal_pdf_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/noise/discrete_pdf.py",
            "function": "sampled_signal_pdf",
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
        },
        "tolerance": TOLERANCE,
        "entries": entries,
        "non_claims": ["not_stage_chain_parity", "not_full_scope_parity", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]), "diff=" + str(entry["max_abs_diff"]))
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
