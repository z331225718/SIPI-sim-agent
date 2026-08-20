"""P3B-05c PRBS9 sequence cross-check: product core vs independent reference.

Runs the product PRBS9 LFSR (seed 0b000000001) for 1000 bits and compares
against an independently written ITU-T O.150 PRBS9 reference (x^9+x^5+1,
bit-8 output, bit8^bit4 feedback). Hash-only evidence; the sequence core
is deterministic and seed-replayable. Injection position, time-warp units,
observables and tolerance remain out of scope of this slice.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p3b-05c-prbs9-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3b-05c.prbs9-crosscheck-evidence.v1"
SEED = 0x001
BITS = 1000


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


def bits_to_bytes(bits):
    arr = bytearray()
    for i in range(0, len(bits), 8):
        byte = 0
        for j, b in enumerate(bits[i:i + 8]):
            byte |= b << j
        arr.append(byte)
    return bytes(arr)


def reference_prbs9(seed, n):
    """Independent ITU-T O.150 PRBS9 (x^9+x^5+1) bit stream."""
    register = seed & 0x1FF
    out = []
    for _ in range(n):
        out.append((register >> 8) & 1)
        feedback = ((register >> 8) ^ (register >> 4)) & 1
        register = ((register << 1) | feedback) & 0x1FF
    return out


def main() -> int:
    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-link", "--test", "p3b_05c_prbs9_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3b_05c_prbs9_runner-*.exe"))[-1]

    reference_bits = reference_prbs9(SEED, BITS)
    reference_hash = sha256_bytes(bits_to_bytes(reference_bits))
    reference_first16 = reference_bits[:16]

    entries = []
    with tempfile.TemporaryDirectory(prefix="p3b-05c-prbs9-") as tmp:
        work = Path(tmp)
        input_payload = {"seed": SEED, "bits": BITS}
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
        product_bytes = bytes(product["bytes"])
        product_hash = sha256_bytes(product_bytes)
        product_first16 = product["first_16"]

        diffs = []
        if product_first16 != reference_first16:
            diffs.append("first16_drift")
        if product_hash != reference_hash:
            diffs.append("stream_hash_drift")
        entry = {
            "id": "prbs9_seed001_1000bits",
            "seed": SEED,
            "bits": BITS,
            "policy": product.get("policy"),
            "input_sha256": sha256_bytes(input_bytes),
            "reference_first16": reference_first16,
            "product_first16": product_first16,
            "reference_sha256": reference_hash,
            "product_sha256": product_hash,
            "matched": not diffs,
            "diffs": diffs,
        }
        entries.append(entry)

    matched = sum(1 for e in entries if e["matched"])
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if matched == len(entries) else "mis_match",
        "reference": "ITU-T O.150 PRBS9 x^9+x^5+1, independent LFSR implementation",
        "policy": "sipi.p3b-05c.prbs9-sequence.v1.deterministic-core",
        "seed": SEED,
        "bits": BITS,
        "matched_count": matched,
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items() if k in ("schema", "status", "matched_count")}, indent=2))
    return 0 if matched == len(entries) else 1


if __name__ == "__main__":
    raise SystemExit(main())