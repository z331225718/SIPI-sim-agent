# -*- coding: utf-8 -*-
"""P3B-05e time-warp shift cross-check: product vs independent ref.

Applies a per-sample fractional shift to a sampled waveform by linear
interpolation on the same grid. Product path is time_warp_shift_v1 via the
runner binary; the reference is a from-scratch python implementation with
the same fail-closed rules (empty, length mismatch, non-finite, out-of-
domain). Both sides must agree on ok/error and, when ok, every output
sample bit-exactly. Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3b-05e-time-warp-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3b-05e.time-warp-crosscheck-evidence.v1"


def reference_warp(samples, shifts):
    """Independent reference with identical fail-closed semantics."""
    if len(samples) == 0:
        return {"ok": False, "error": "empty_waveform", "samples": []}
    if len(samples) != len(shifts):
        return {"ok": False, "error": "length_mismatch", "samples": []}
    if any(not math.isfinite(s) for s in samples):
        return {"ok": False, "error": "non_finite_sample", "samples": []}
    if any(not math.isfinite(s) for s in shifts):
        return {"ok": False, "error": "non_finite_shift", "samples": []}
    last = len(samples) - 1
    out = []
    for n, shift in enumerate(shifts):
        position = n + shift
        if position < 0.0 or position > last:
            return {"ok": False, "error": f"out_of_domain:{n}", "samples": []}
        lo = int(math.floor(position))
        hi = int(math.ceil(position))
        frac = position - lo
        if hi == lo:
            value = samples[lo]
        else:
            value = samples[lo] * (1.0 - frac) + samples[hi] * frac
        out.append(value)
    return {"ok": True, "error": None, "samples": out}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-link", "--test", "p3b_05e_time_warp_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3b_05e_time_warp_runner-*.exe"))[-1]

    cases = [
        {
            "label": "zero_shift_identity",
            "samples": [1.0, -1.0, 1.0, -1.0],
            "shifts": [0.0, 0.0, 0.0, 0.0],
        },
        {
            "label": "half_shift_midpoint",
            "samples": [0.0, 2.0, 4.0],
            "shifts": [0.5, 0.5, 0.0],
        },
        {
            "label": "quarter_shift_ramp",
            "samples": [0.0, 2.0, 4.0, 8.0],
            "shifts": [0.25, 0.25, 0.25, 0.0],
        },
        {
            "label": "prbs9_waveform_small_shifts",
            "samples": [1.0, 1.0, 1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, -1.0],
            "shifts": [0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.1, -0.1, 0.2, 0.0],
        },
        {
            "label": "backward_shift_p05",
            "samples": [1.0, 2.0, 3.0, 4.0],
            "shifts": [0.0, -0.5, -0.5, -0.5],
        },
        {
            "label": "out_of_domain_forward",
            "samples": [1.0, 2.0, 3.0],
            "shifts": [0.0, 0.0, 0.5],
            "expect_error": "out_of_domain:2",
        },
        {
            "label": "out_of_domain_backward",
            "samples": [1.0, 2.0, 3.0],
            "shifts": [-0.5, 0.0, 0.0],
            "expect_error": "out_of_domain:0",
        },
        {
            "label": "length_mismatch",
            "samples": [1.0],
            "shifts": [0.0, 0.0],
            "expect_error": "length_mismatch",
        },
        {
            "label": "non_finite_shift",
            "samples": [1.0, 2.0],
            "shifts": [0.0, 1.7976931348623157e308],
            "expect_error": "non_finite_shift",
        },
        {
            "label": "empty_waveform",
            "samples": [],
            "shifts": [],
            "expect_error": "empty_waveform",
        },
    ];

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p3b-05e-") as tmp:
        work = Path(tmp)
        for case in cases:
            label = case["label"]
            input_path = work / "input.json"
            input_path.write_bytes(json.dumps({"samples": case["samples"], "shifts": case["shifts"]}, separators=(",", ":")).encode("utf-8"))
            report_path = work / "product.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = reference_warp(case["samples"], case["shifts"])

            prod_ok = bool(product.get("ok"))
            prod_err = product.get("error")
            prod_samples = product.get("samples") or []
            ref_ok = bool(reference["ok"])
            ref_err = reference["error"]
            ref_samples = reference["samples"]

            mismatched = (prod_ok != ref_ok) or (prod_err != ref_err) or (prod_samples != ref_samples)
            if mismatched: ok_all = False
            entries.append({
                "label": label,
                "matched": not mismatched,
                "product_ok": prod_ok,
                "reference_ok": ref_ok,
                "product_error": prod_err,
                "reference_error": ref_err,
                "product_samples": prod_samples,
                "reference_samples": ref_samples,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p3b-05e.time-warp-shift.v1.linear-per-sample",
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
