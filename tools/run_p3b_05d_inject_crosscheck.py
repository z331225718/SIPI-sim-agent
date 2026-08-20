# -*- coding: utf-8 -*-
"""P3B-05d PRBS9 injection-waveform cross-check: product vs independent ref."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3b-05d-inject-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3b-05d.inject-crosscheck-evidence.v1"

def prbs9_bits(seed, n):
    reg = seed & 0x1FF
    out = []
    for _ in range(n):
        out.append((reg >> 8) & 1)
        fb = ((reg >> 8) ^ (reg >> 4)) & 1
        reg = ((reg << 1) | fb) & 0x1FF
    return out

def ref_waveform(seed, bits, spu, amp):
    bs = prbs9_bits(seed, bits)
    w = []
    for b in bs:
        v = amp if b == 1 else -amp
        w.extend([v] * spu)
    return w

def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-link", "--test", "p3b_05d_inject_runner"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit('runner build failed: ' + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3b_05d_inject_runner-*.exe"))[-1]

    cases = [
        {"id": "seed1_bits4_spu2", "seed": 1, "bits": 4, "spu": 2, "amp": 1.0},
        {"id": "seed1_bits20_spu4", "seed": 1, "bits": 20, "spu": 4, "amp": 0.6},
        {"id": "seed511_bits16_spu8", "seed": 0x1FF, "bits": 16, "spu": 8, "amp": 0.4},
    ]

    entries = []; ok_all = True
    with tempfile.TemporaryDirectory(prefix="p3b-05d-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_payload = {"seed": case["seed"], "bits": case["bits"], "spu": case["spu"], "amp": case["amp"]}
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json"); input_path.write_bytes(input_bytes)
            run = subprocess.run([str(runner), "--input", str(input_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0: raise SystemExit('runner failed :: ' + run.stdout + run.stderr)
            product = json.loads(run.stdout)
            ref = ref_waveform(case["seed"], case["bits"], case["spu"], case["amp"])
            matched = (product["length"] == len(ref)) and all(abs(a - b) < 1e-12 for a, b in zip(product["first_16"], ref[:16]))
            # packed bytes must match sign pattern
            packed_ref = [1 if v > 0 else 0 for v in ref]
            matched = matched and (product["packed"] == packed_ref)
            if not matched: ok_all = False
            entries.append({"id": case["id"], "matched": matched, "product_length": product["length"], "reference_length": len(ref), "product_packed": product["packed"], "reference_packed": packed_ref})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p3b-05d.prbs9-inject.v1.tx-waveform",
            "matched_count": sum(1 for e in entries if e["matched"]),
            "case_count": len(entries),
            "entries": entries,
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
        print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"], "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
        return 0 if ok_all else 1

if __name__ == "__main__":
    raise SystemExit(main())