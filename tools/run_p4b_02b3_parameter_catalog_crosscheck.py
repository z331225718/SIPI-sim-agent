# -*- coding: utf-8 -*-
"""P4B-02b3 parameter-catalog cross-check: product vs independent reference.

Validates candidate parameter sets against a compiled catalog (Usage=In
required, unknown rejected, type checked) and compares the product and an
independent Python reference across several negative/positive cases.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b3-parameter-catalog-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b3.parameter-catalog-crosscheck-evidence.v1"

CATALOG = [
    {"name": "swing", "usage": "In", "type": "Float", "default": "0.5"},
    {"name": "pre", "usage": "In", "type": "Integer"},
    {"name": "comment", "usage": "Info", "type": "String"},
]


def reference_validate(catalog, candidates):
    cat_map = {e["name"]: e for e in catalog}
    # Missing required (Usage=In).
    for name, entry in cat_map.items():
        if entry["usage"] == "In" and name not in candidates:
            return (False, "missing_required:" + name)
    # Unknown parameter.
    for name in candidates:
        if name not in cat_map:
            return (False, "unknown_parameter:" + name)
    # Type check.
    for name, cand in candidates.items():
        if cand["type"] != cat_map[name]["type"]:
            return (False, "type_mismatch:" + name)
    return (True, None)


def main() -> int:
    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b3_param_catalog_runner"

    cases = []
    # positive
    cases.append({"id": "valid", "candidates": {"swing": {"type": "Float", "value": "0.6"}, "pre": {"type": "Integer", "value": "2"}}});
    # missing required swing
    cases.append({"id": "missing_required", "candidates": {"pre": {"type": "Integer", "value": "2"}}});
    # unknown param
    cases.append({"id": "unknown", "candidates": {"swing": {"type": "Float", "value": "0.5"}, "pre": {"type": "Integer", "value": "2"}, "bogus": {"type": "Float", "value": "1"}}});
    # type mismatch
    cases.append({"id": "type_mismatch", "candidates": {"swing": {"type": "Integer", "value": "5"}, "pre": {"type": "Integer", "value": "2"}}});

    entries = []
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="p4b-02b3-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_payload = {"catalog": CATALOG, "candidates": case["candidates"]}
            input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
            input_path = work / (case["id"] + ".json")
            input_path.write_bytes(input_bytes)
            run = subprocess.run(
                [str(runner), "--input", str(input_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if run.returncode != 0:
                raise SystemExit("runner failed :: " + run.stdout + run.stderr)
            product = json.loads(run.stdout)
            ref_ok, ref_err = reference_validate(CATALOG, case["candidates"])
            product_ok = product.get("ok", False)
            matched = (product_ok == ref_ok)
            if not matched:
                ok_all = False
            entries.append({"id": case["id"], "matched": matched, "product_ok": product_ok, "reference_ok": ref_ok, "product_error": product.get("error"), "reference_error": ref_err})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "product_owned_self_crosscheck_unbound" if ok_all else "mis_match",
            "policy": "sipi.p4b-02b3.parameter-catalog.v1.typed",
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