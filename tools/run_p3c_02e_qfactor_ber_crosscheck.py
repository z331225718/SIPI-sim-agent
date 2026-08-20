# -*- coding: utf-8 -*-
"""P3C-02e Q-factor/BER cross-check: product vs scipy reference.

Runs the product Q-factor<->BER conversions and compares against scipy
special.erfc/erfcinv at the same points (IEEE 802.3 relation).
Hash-only evidence; no release claim.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy.special as sp
import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-02e-qfactor-ber-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-02e.qfactor-ber-crosscheck-evidence.v1"
Q_TOL = 1e-9


def main() -> int:
    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p3c_02e_qfactor_ber_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_02e_qfactor_ber_runner-*.exe"))[-1]

    q_values = [3.5, 4.5, 6.0, 7.0, 7.5]
    ber_values = [1e-3, 1e-6, 1e-10, 1e-12, 1e-15]
    input_payload = {"q_values": q_values, "ber_values": ber_values}

    # scipy reference
    scipy_ref = {}
    for q in q_values:
        scipy_ref[f"q:{q}"] = 0.5 * sp.erfc(q / np.sqrt(2))
    for ber in ber_values:
        scipy_ref[f"ber:{ber}"] = np.sqrt(2) * sp.erfcinv(2.0 * ber)

    entries = []
    with tempfile.TemporaryDirectory(prefix="p3c-02e-") as tmp:
        work = Path(tmp)
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
        cases = product["cases"]

        ok_all = True
        for case in cases:
            matched = True
            diffs = []
            if "ber" in case and "q" in case:
                q = case["q"]
                ref = 0.5 * sp.erfc(q / np.sqrt(2))
                product_val = float(case["ber"])
                if abs(product_val - ref) > 1e-12:
                    matched = False; diffs.append("ber_drift"); ok_all = False
            if "q_inv" in case and "ber" in case:
                ber = case["ber"]
                ref = np.sqrt(2) * sp.erfcinv(2.0 * ber)
                product_val = float(case["q_inv"])
                if abs(product_val - ref) > Q_TOL:
                    matched = False; diffs.append("qinv_drift"); ok_all = False
            entries.append({"case": case, "matched": matched, "diffs": diffs})

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p3c-02e.qfactor-ber.v1.estimator",
        "matched_count": sum(1 for e in entries if e["matched"]),
        "case_count": len(entries),
        "reference": "scipy.special erfc/erfcinv, IEEE 802.3 relation",
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"], "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())