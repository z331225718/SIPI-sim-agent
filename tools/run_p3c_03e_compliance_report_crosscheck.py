# -*- coding: utf-8 -*-
"""P3C-03e compliance report cross-check: product vs independent ref."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p3c-03e-compliance-report-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p3c-03e.compliance-report-crosscheck-evidence.v1"

def ref_check(reference, candidate, tolerance):
    diff = abs(candidate - reference)
    eps = abs(tolerance) * 1e-12 + 1e-12
    return diff, (diff <= tolerance + eps)

def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p3c_03e_compliance_runner"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit('runner build failed: ' + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p3c_03e_compliance_runner-*.exe"))[-1]

    cases = [
        {"id": "fom_pass", "profile": [{"name": "fom", "reference": 53.426, "tolerance": 0.1, "unit": "db"}], "candidates": {"fom": 53.45}},
        {"id": "fom_fail", "profile": [{"name": "fom", "reference": 53.426, "tolerance": 0.1, "unit": "db"}], "candidates": {"fom": 54.0}},
        {"id": "multi", "profile": [{"name": "fom", "reference": 53.426, "tolerance": 0.1, "unit": "db"}, {"name": "crossing", "reference": 90.0, "tolerance": 0.5, "unit": "deg"}], "candidates": {"fom": 53.4265, "crossing": 89.9}},
    ]

    entries = []; ok_all = True
    with tempfile.TemporaryDirectory(prefix="p3c-03e-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_payload = {"profile": case["profile"], "candidates": case["candidates"]}
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json")
            input_path.write_bytes(input_bytes)
            run = subprocess.run([str(runner), "--input", str(input_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0: raise SystemExit('runner failed :: ' + run.stdout + run.stderr)
            product = json.loads(run.stdout)
            match_all = True; ref_pass_all = True
            for spec in case["profile"]:
                _, ref_pass = ref_check(spec["reference"], case["candidates"][spec["name"]], spec["tolerance"])
                if not ref_pass: ref_pass_all = False
            if not product.get("ok"):
                match_all = False
            else:
                for res, spec in zip(product.get("results", []), case["profile"]):
                    ref_diff, ref_pass = ref_check(spec["reference"], case["candidates"][spec["name"]], spec["tolerance"])
                    if abs(res["difference_db"] - ref_diff) > 1e-9 or res["passed"] != ref_pass:
                        match_all = False
                if product.get("passed") != ref_pass_all: match_all = False
            if not match_all: ok_all = False
            entries.append({"id": case["id"], "matched": match_all, "product": product, "reference_pass_all": ref_pass_all})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p3c-03e.compliance-report.v1.profile",
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