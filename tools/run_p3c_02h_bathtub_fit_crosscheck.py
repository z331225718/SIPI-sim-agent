# -*- coding: utf-8 -*-
"""P3C-02h bathtub curve fit cross-check (product vs independent ref).

Drives the product bathtub fit runner (p3c_02h_bathtub_fit_runner) over bathtub samples plus a
fit order. An independent Python reference replicates the least-squares polynomial fit in the
log10(BER) domain with the same Gaussian elimination (partial pivoting, identical arithmetic).
Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02h-bathtub-curve-fit-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-02h-bathtub-curve-fit-crosscheck-evidence.v1"
POLICY = "sipi.p3c-02h.bathtub-curve-fit.v1.log-ber-poly-fit"
MAX_ORDER = 3


def gaussian_solve(augmented: list[list[float]]) -> list[float] | None:
    n = len(augmented)
    for col in range(n):
        pivot_row = col
        pivot_value = abs(augmented[col][col])
        for row in range(col + 1, n):
            candidate = abs(augmented[row][col])
            if candidate > pivot_value:
                pivot_value = candidate
                pivot_row = row
        if pivot_value == 0.0:
            return None
        augmented[col], augmented[pivot_row] = augmented[pivot_row], augmented[col]
        for row in range(col + 1, n):
            factor = augmented[row][col] / augmented[col][col]
            for entry in range(col, n + 1):
                augmented[row][entry] -= factor * augmented[col][entry]
    solution = [0.0] * n
    for row in range(n - 1, -1, -1):
        total = augmented[row][n]
        for entry in range(row + 1, n):
            total -= augmented[row][entry] * solution[entry]
        solution[row] = total / augmented[row][row]
    return solution


def ref_fit(samples: list[dict[str, float]], fit_order: int) -> dict[str, Any]:
    if len(samples) < 3:
        return {"valid": False, "fit_error": "TooFewSamples"}
    if fit_order == 0 or fit_order > MAX_ORDER:
        return {"valid": False, "fit_error": "InvalidFitOrder"}
    if len(samples) < fit_order + 1:
        return {"valid": False,
                "fit_error": f'InsufficientSamplesForOrder {{ order: {fit_order}, samples: {len(samples)} }}'}
    times = [s["t"] for s in samples]
    bers = [s["ber"] for s in samples]
    for i in range(len(samples) - 1):
        if times[i] >= times[i + 1]:
            return {"valid": False, "fit_error": "TimeNotAscending"}
        if not math.isfinite(bers[i]) or bers[i] <= 0.0 or bers[i] >= 1.0:
            return {"valid": False, "fit_error": "InvalidBer"}
    if not math.isfinite(bers[-1]) or bers[-1] <= 0.0 or bers[-1] >= 1.0:
        return {"valid": False, "fit_error": "InvalidBer"}

    degree = fit_order
    gram = [[0.0] * (degree + 1) for _ in range(degree + 1)]
    rhs = [0.0] * (degree + 1)
    for s in samples:
        t = s["t"]
        y = math.log10(s["ber"])
        powers = [1.0] * (degree + 1)
        for p in range(1, degree + 1):
            powers[p] = powers[p - 1] * t
        for row in range(degree + 1):
            for entry in range(degree + 1):
                gram[row][entry] += powers[row] * powers[entry]
            rhs[row] += powers[row] * y
    augmented = [gram[row] + [rhs[row]] for row in range(degree + 1)]
    coefficients = gaussian_solve(augmented)
    if coefficients is None:
        return {"valid": False, "fit_error": "NumericFailure"}
    if any(not math.isfinite(c) for c in coefficients):
        return {"valid": False, "fit_error": "NumericFailure"}

    max_abs_residual = 0.0
    for s in samples:
        t = s["t"]
        y = math.log10(s["ber"])
        fitted = sum(c * (t ** i) for i, c in enumerate(coefficients))
        residual = abs(y - fitted)
        if residual > max_abs_residual:
            max_abs_residual = residual
    return {"valid": True, "fit_order": fit_order,
            "coefficients": [f"{c:.12f}" for c in coefficients],
            "sample_count": len(samples),
            "max_abs_residual": f"{max_abs_residual:.12f}"}


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p3c_02h_bathtub_fit_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_02h_bathtub_fit_runner-*.exe"))[-1]

    cases = [
        {
            "label": "linear_fit",
            "samples": [
                {"t": 0.0, "ber": 1e-2},
                {"t": 1.0, "ber": 1e-5},
                {"t": 2.0, "ber": 1e-8},
                {"t": 3.0, "ber": 1e-11},
            ],
            "fit_order": 1,
        },
        {
            "label": "quadratic_fit",
            "samples": [
                {"t": 0.5, "ber": 10 ** (0.25 - 2.0 + 1.0)},
                {"t": 1.0, "ber": 10 ** (1.0 - 4.0 + 1.0)},
                {"t": 1.5, "ber": 10 ** (2.25 - 6.0 + 1.0)},
                {"t": 2.0, "ber": 10 ** (4.0 - 8.0 + 1.0)},
                {"t": 2.5, "ber": 10 ** (6.25 - 10.0 + 1.0)},
            ],
            "fit_order": 2,
        },
        {
            "label": "insufficient_samples",
            "samples": [
                {"t": 0.0, "ber": 1e-2},
                {"t": 1.0, "ber": 1e-5},
                {"t": 2.0, "ber": 1e-8},
            ],
            "fit_order": 3,
        },
        {
            "label": "invalid_ber",
            "samples": [
                {"t": 0.0, "ber": 0.0},
                {"t": 1.0, "ber": 1e-5},
                {"t": 2.0, "ber": 1e-8},
            ],
            "fit_order": 1,
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p3c-02h-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / f"{case['label']}_in.json"
            input_path.write_text(json.dumps(case), encoding="utf-8")
            report_path = work / f"{case['label']}_rep.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0:
                raise SystemExit(f"runner failed for {case['label']}: " + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = ref_fit(case["samples"], case["fit_order"])

            matched = True
            if product.get("valid") != reference.get("valid"):
                matched = False
            elif product.get("valid"):
                if (product.get("fit_order") != reference.get("fit_order") or
                    product.get("coefficients") != reference.get("coefficients") or
                    product.get("sample_count") != reference.get("sample_count") or
                    product.get("max_abs_residual") != reference.get("max_abs_residual")):
                    matched = False
            else:
                prod_err = product.get("fit_error")
                ref_err = reference.get("fit_error")
                if str(prod_err) != str(ref_err):
                    matched = False

            if not matched:
                ok_all = False

            entries.append({
                "label": case["label"],
                "matched": matched,
                "product": product,
                "reference": reference,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": POLICY,
        "matched_count": sum(1 for e in entries if e["matched"]),
        "case_count": len(entries),
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"],
                      "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
