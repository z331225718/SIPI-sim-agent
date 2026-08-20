# -*- coding: utf-8 -*-
"""P3C-03d dB-tolerance cross-check: product vs independent reference."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-03d-db-tolerance-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-03d.db-tolerance-crosscheck-evidence.v1"


def reference_check(reference, candidate, tolerance):
    diff = abs(candidate - reference)
    epsilon = abs(tolerance) * 1e-12 + 1e-12
    return diff, (diff <= tolerance + epsilon)


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p3c_03d_db_tolerance_runner"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_03d_db_tolerance_runner-*.exe"))[-1]

    triples = [
        (53.426, 53.45, 0.1),
        (53.426, 53.6, 0.1),
        (10.0, 10.05, 0.1),
        (1.0, 1.1, 0.1),  # float boundary
        (20.0, 20.3, 0.5),
        (0.0, 0.0, 0.1),
    ]
    cases = [{"reference": r, "candidate": c, "tolerance": t} for r, c, t in triples]
    input_payload = {"cases": cases}

    with tempfile.TemporaryDirectory(prefix="p3c-03d-") as tmp:
        work = Path(tmp)
        input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
        input_path = work / "input.json"; input_path.write_bytes(input_bytes)
        report_path = work / "product.json"
        run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))

        ok_all = True; entries = []
        for idx, case in enumerate(product["cases"]):
            r = case["reference"]; c = case["candidate"]; t = case["tolerance"]
            ref_diff, ref_pass = reference_check(r, c, t)
            res = case["result"]
            matched = res["ok"] and abs(res["diff"] - ref_diff) < 1e-9 and res["passed"] == ref_pass
            if not matched: ok_all = False
            entries.append({"id": f"case{idx}", "matched": matched, "reference": r, "candidate": c, "tolerance": t, "product": res, "reference_pass": ref_pass})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p3c-03d.db-tolerance.v1.0p1db",
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