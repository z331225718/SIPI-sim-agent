# -*- coding: utf-8 -*-
"""P5-02m warning-detector cross-check: product vs independent reference."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02m-warning-detector-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-02m.warning-detector-crosscheck-evidence.v1"

def ref_fraction(impulse, exclusion):
    total = sum(v * v for v in impulse)
    if total <= 0: return 0.0
    n = len(impulse)
    if n <= 2 * exclusion: return 0.0
    peak = max(range(n), key=lambda i: impulse[i])
    if peak < exclusion: return 0.0
    pre = sum(v * v for v in impulse[peak - exclusion:peak])
    return pre / total

def ref_non_decay(mag, tail):
    n = len(mag)
    start = max(0, n - tail)
    tail_avg = sum(mag[start:]) / (n - start)
    head = mag[start - 1]
    return tail_avg >= head

def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p5_02m_warning_detector_runner"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_02m_warning_detector_runner-*.exe"))[-1]

    cases = [
        {"id": "causal", "impulse": [0,0,0,0,1,0.05,0.02], "exclusion": 2, "threshold": 0.05, "mag": [-10,-15,-20,-25,-30], "tail": 2},
        {"id": "anti_causal", "impulse": [0,0,0.4,1,0.1], "exclusion": 2, "threshold": 0.05, "mag": [-10,-15,-20,-20,-22], "tail": 2},
        {"id": "non_decay", "impulse": [0,0,0,0,1,0.02], "exclusion": 2, "threshold": 0.05, "mag": [-30,-25,-20,-15,-10], "tail": 2},
    ]

    entries = []; ok_all = True
    with tempfile.TemporaryDirectory(prefix="p5-02m-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_payload = {"impulse": case["impulse"], "exclusion": case["exclusion"], "threshold": case["threshold"], "mag": case["mag"], "tail": case["tail"]}
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json"); input_path.write_bytes(input_bytes)
            run = subprocess.run([str(runner), "--input", str(input_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
            product = json.loads(run.stdout)
            ref_frac = ref_fraction(case["impulse"], case["exclusion"])
            ref_anti = ref_frac > case["threshold"]
            ref_decay = ref_non_decay(case["mag"], case["tail"])
            matched = abs(product["fraction"] - ref_frac) < 1e-12 and product["anti_causal"] == ref_anti and product["non_decay"] == ref_decay
            if not matched: ok_all = False
            entries.append({"id": case["id"], "matched": matched, "product": product, "reference_fraction": ref_frac, "reference_anti": ref_anti, "reference_decay": ref_decay})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p5-02m.warning-detector.v1.deterministic",
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