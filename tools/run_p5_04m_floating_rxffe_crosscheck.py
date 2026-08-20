"""P5-04m floating RxFFE cross-check: product runner vs agent-com oracle.

Runs force_floating_rx_ffe in fresh external custody (agent-com
equalization rx_ffe module) on fixed waveforms and compares taps,
filtered output, matrix, and the one-based floating-bank locations
against the product runner. The LU solve surface is compared with the
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-04m-floating-rxffe-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-04m.floating-rxffe-crosscheck-evidence.v1"
TOLERANCE = 1e-9  # LU backends are mathematically equivalent, not bit-identical.


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def waveform(seed: float, length: int = 96) -> list[float]:
    values = []
    for index in range(length):
        i = float(index)
        values.append(
            math.exp(-((i - 48.0) ** 2) / 400.0) * math.sin(i * 0.3 + seed)
            + 0.05 * math.sin(i * 0.9 + seed * 2.0)
        )
    return values


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.equalization.rx_ffe import force_floating_rx_ffe as oracle_floating

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_04l_rx_ffe_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed")
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_04l_rx_ffe_runner-*.exe"))[-1]

    cases = [
        {"id": "floating_taps_selector", "seed": 0.5, "cursor_index": 48, "precursor_count": 1,
         "fixed_postcursor_count": 1, "maximum_postcursor_count": 8, "samples_per_ui": 4,
         "dfe_first_max": 0.0, "unity_cursor": False, "tap_step": 0.0, "floating_start": 3,
         "taps_per_bank": 2, "bank_count": 2, "coefficient_limit": 0.5, "selection": "taps",
         "return_filtered": True},
        {"id": "floating_isi_selector", "seed": 1.2, "cursor_index": 48, "precursor_count": 2,
         "fixed_postcursor_count": 1, "maximum_postcursor_count": 10, "samples_per_ui": 4,
         "dfe_first_max": 0.3, "unity_cursor": True, "tap_step": 0.05, "floating_start": 2,
         "taps_per_bank": 3, "bank_count": 1, "coefficient_limit": 0.4, "selection": "ISI",
         "return_filtered": True},
        {"id": "floating_no_filtered", "seed": 0.9, "cursor_index": 40, "precursor_count": 1,
         "fixed_postcursor_count": 2, "maximum_postcursor_count": 6, "samples_per_ui": 8,
         "dfe_first_max": 0.0, "unity_cursor": False, "tap_step": 0.0, "floating_start": 2,
         "taps_per_bank": 1, "bank_count": 2, "coefficient_limit": 0.6, "selection": "taps",
         "return_filtered": False},
    ]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-04m-crosscheck-") as tmp:
        work = Path(tmp)
        for case in cases:
            w = waveform(case["seed"])
            oracle_rejected = False
            locations = None
            try:
                oracle, locations = oracle_floating(
                np.asarray(w),
                cursor_index=case["cursor_index"],
                precursor_count=case["precursor_count"],
                fixed_postcursor_count=case["fixed_postcursor_count"],
                maximum_postcursor_count=case["maximum_postcursor_count"],
                samples_per_ui=case["samples_per_ui"],
                dfe_first_max=case["dfe_first_max"],
                unity_cursor=case["unity_cursor"],
                tap_step=case["tap_step"],
                floating_start=case["floating_start"],
                taps_per_bank=case["taps_per_bank"],
                bank_count=case["bank_count"],
                coefficient_limit=case["coefficient_limit"],
                selection=case["selection"],
                return_filtered=case["return_filtered"],
            )
            except Exception as error:
                oracle_rejected = True
            input_payload = {"force_floating": {**case, "waveform": w}}
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json")
            input_path.write_bytes(input_bytes)
            report_path = work / (case["id"] + "-product.json")
            run = subprocess.run(
                [str(runner), "--input", str(input_path), "--report", str(report_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            product_rejected = run.returncode != 0
            if oracle_rejected != product_rejected:
                raise SystemExit("rejection parity drift: " + case["id"] + " oracle=" + str(oracle_rejected) + " product=" + str(product_rejected))
            if oracle_rejected:
                entries.append({
                    "id": case["id"],
                    "input_sha256": sha256_bytes(input_bytes),
                    "rejected_parity": True,
                    "locations": None,
                    "taps_len": None,
                    "matched": True,
                    "diffs": [],
                })
                continue
            product = json.loads(report_path.read_text(encoding="utf-8"))["force_floating"]
            expected_taps = [float(v) for v in oracle.taps]
            expected_filtered = None if oracle.filtered is None else [float(v) for v in oracle.filtered]
            expected_matrix = [[float(v) for v in row] for row in oracle.matrix]
            expected_locations = [int(v) for v in locations]
            diffs = []
            if not (len(product["taps"]) == len(expected_taps) and all(abs(a - b) <= TOLERANCE for a, b in zip(product["taps"], expected_taps))):
                diffs.append("taps drift")
            if (product["filtered"] is None) != (expected_filtered is None):
                diffs.append("filtered presence")
            elif expected_filtered is not None and not all(abs(a - b) <= TOLERANCE for a, b in zip(product["filtered"], expected_filtered)):
                diffs.append("filtered drift")
            if product["matrix"] != expected_matrix:
                diffs.append("matrix drift")
            if product["locations_one_based"] != expected_locations:
                diffs.append("locations " + str(product["locations_one_based"]) + " vs " + str(expected_locations))
            entries.append({
                "id": case["id"],
                "input_sha256": sha256_bytes(input_bytes),
                "locations": expected_locations,
                "taps_len": len(expected_taps),
                "matched": not diffs,
                "diffs": diffs[:8],
            })
    matched = all(entry["matched"] for entry in entries)
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "floating_rxffe_crosscheck_matched" if matched else "floating_rxffe_crosscheck_mismatch",
        "oracle": {
            "repo": "agent-com",
            "license": "MIT",
            "path": "src/agent_com/equalization/rx_ffe.py",
            "function": "force_floating_rx_ffe",
            "numpy_version": np.__version__,
        },
        "tolerance": TOLERANCE,
        "tolerance_note": "LU solve backends are mathematically equivalent but not bit-identical",
        "entries": entries,
        "non_claims": ["not_search_integration", "not_release_evidence"],
    }
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    for entry in entries:
        print(entry["id"], "matched=" + str(entry["matched"]), "locations=" + str(entry["locations"]))
        for diff in entry.get("diffs", []):
            print("  diff:", diff)
    print("all_matched=" + str(matched))
    print("evidence written: " + str(EVIDENCE))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())