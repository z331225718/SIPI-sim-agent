# -*- coding: utf-8 -*-
"""P3C-02f bathtub opening-width cross-check: product vs independent ref.

Verifies bathtub_opening_width_v1 (log-BER threshold crossing interpolation)
against an independently written reference on a V-shaped bathtub.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02f-bathtub-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-02f.bathtub-crosscheck-evidence.v1"


def crossing(left, right, target):
    lt = max(left[1], 1e-300)
    rt = max(right[1], 1e-300)
    tt = max(target, 1e-300)
    fl = math.log10(lt); fr = math.log10(rt); ft = math.log10(tt)
    f = (ft - fl) / (fr - fl) if abs(fr - fl) > 1e-300 else float('inf')
    return left[0] + f * (right[0] - left[0])


def reference_width(samples, target):
    n = len(samples)
    if n < 3: return None, "too_few"
    for i in range(n - 1):
        if samples[i][0] >= samples[i + 1][0]: return None, "time_not_ascending"
        if not (0 < samples[i][1] < 1): return None, "invalid_ber"
    if not (0 < samples[-1][1] < 1): return None, "invalid_ber"
    in_span = [s[1] <= target for s in samples]
    if not any(in_span): return None, "no_opening"
    first = in_span.index(True)
    last = n - 1 - in_span[::-1].index(True)
    left = samples[0][0] if first == 0 else crossing(samples[first - 1], samples[first], target)
    right = samples[last][0] if last == n - 1 else crossing(samples[last], samples[last + 1], target)
    if right - left < 0: return None, "no_opening"
    return (right - left), None


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p3c_02f_bathtub_runner"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_02f_bathtub_runner-*.exe"))[-1]

    cases = [
        {"id": "sym_small", "samples": [[-0.5, 1e-3], [0.0, 1e-9], [0.5, 1e-3]], "target": 1e-4},
        {"id": "asym_wide", "samples": [[-0.6, 1e-2], [-0.3, 1e-6], [0.1, 1e-8], [0.4, 1e-3]], "target": 1e-4},
        {"id": "no_opening", "samples": [[-0.5, 1e-3], [0.0, 1e-3], [0.5, 1e-3]], "target": 1e-6},
    ]

    entries = []
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="p3c-02f-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_payload = {"samples": case["samples"], "target_ber": case["target"]}
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json")
            input_path.write_bytes(input_bytes)
            run = subprocess.run([str(runner), "--input", str(input_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
            product = json.loads(run.stdout)
            ref_w, ref_err = reference_width(case["samples"], case["target"])
            product_w = product.get("width");
            if ref_err is not None:
                # Both must report an error (the exact Rust/Python spelling differs;
                # the semantic error set is what is compared).
                matched = product_w is None and product.get("error") is not None
            else:
                matched = product_w is not None and abs(product_w - ref_w) < 1e-9
            if not matched: ok_all = False
            entries.append({"id": case["id"], "matched": matched, "product_width": product_w, "reference_width": ref_w, "product_error": product.get("error"), "reference_error": ref_err})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p3c-02f.bathtub-opening.v1.threshold",
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