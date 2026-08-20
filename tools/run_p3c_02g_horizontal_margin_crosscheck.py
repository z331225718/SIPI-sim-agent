# -*- coding: utf-8 -*-
"""P3C-02g horizontal-margin cross-check: product vs independent ref."""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02g-horizontal-margin-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-02g.horizontal-margin-crosscheck-evidence.v1"

def crossing(left, right, target):
    lt = max(left[1], 1e-300); rt = max(right[1], 1e-300); tt = max(target, 1e-300)
    fl = math.log10(lt); fr = math.log10(rt); ft = math.log10(tt)
    f = (ft - fl) / (fr - fl) if abs(fr - fl) > 1e-300 else float('nan')
    return left[0] + f * (right[0] - left[0])

def reference_margins(samples, target, sample_off):
    in_span = [s[1] <= target for s in samples]
    if not any(in_span): return None, "no_opening"
    first = in_span.index(True); last = len(samples) - 1 - in_span[::-1].index(True)
    left = samples[0][0] if first == 0 else crossing(samples[first - 1], samples[first], target)
    right = samples[last][0] if last == len(samples) - 1 else crossing(samples[last], samples[last + 1], target)
    width = right - left
    if width < 0: return None, "no_opening"
    if sample_off < 0 or sample_off > width: return None, "sample_outside_eye"
    return (width, sample_off, width - sample_off), None

def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p3c_02g_margin_runner"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_02g_margin_runner-*.exe"))[-1]

    cases = [
        {"id": "sym_center", "samples": [[-0.5, 1e-3], [0.0, 1e-9], [0.5, 1e-3]], "target": 1e-4, "sample_offset": 0.5},
        {"id": "asym_left", "samples": [[-0.6, 1e-2], [-0.3, 1e-6], [0.1, 1e-8], [0.4, 1e-3]], "target": 1e-4, "sample_offset": 0.2},
        {"id": "outside", "samples": [[-0.5, 1e-3], [0.0, 1e-3], [0.5, 1e-3]], "target": 1e-6, "sample_offset": 0.3},
    ]

    entries = []; ok_all = True
    with tempfile.TemporaryDirectory(prefix="p3c-02g-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_payload = {"samples": case["samples"], "target_ber": case["target"], "sample_offset_ui": case["sample_offset"]}
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json"); input_path.write_bytes(input_bytes)
            run = subprocess.run([str(runner), "--input", str(input_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
            product = json.loads(run.stdout)
            ref_m, ref_err = reference_margins(case["samples"], case["target"], case["sample_offset"])
            matched = False
            if ref_err is not None:
                matched = (not product.get("ok")) and product.get("error") is not None
            else:
                w, l, rgt = ref_m
                matched = product.get("ok") and abs(product["eye_width"] - w) < 1e-9 and abs(product["left"] - l) < 1e-9 and abs(product["right"] - rgt) < 1e-9
            if not matched: ok_all = False
            entries.append({"id": case["id"], "matched": matched, "product": product, "reference_width": (ref_m[0] if ref_m else None)})

        matched_count = sum(1 for e in entries if e["matched"])
        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p3c-02g.horizontal-margin.v1.timing",
            "matched_count": matched_count,
            "case_count": len(entries),
            "entries": entries,
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
        print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"], "matched_count": matched_count, "case_count": len(entries)}, indent=2))
        return 0 if ok_all else 1

if __name__ == "__main__":
    raise SystemExit(main())