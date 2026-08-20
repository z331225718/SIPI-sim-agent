# -*- coding: utf-8 -*-
"""P4B-02b4 catalog-default validity cross-check: product vs independent ref."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b4-catalog-default-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b4.catalog-default-crosscheck-evidence.v1"

def token_valid(type_token, default):
    if default is None: return True
    if type_token == "Float":
        try: return float(default) == float(default)  # finite check is approximated
        except ValueError: return False
    if type_token == "Integer":
        try: int(default); return True
        except ValueError: return False
    if type_token == "Boolean": return default in ("True", "False")
    if type_token == "String": return len(default) > 0
    if type_token == "List": return default.startswith("(") and default.endswith(")") and len(default[1:-1].strip()) > 0
    return False

def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b4_catalog_default_runner"

    cases = [
        {"name": "swing", "type": "Float", "default": "0.5"},
        {"name": "pre", "type": "Integer", "default": "2"},
        {"name": "flag", "type": "Boolean", "default": "True"},
        {"name": "bad_float", "type": "Float", "default": "not-a-float"},
        {"name": "bad_bool", "type": "Boolean", "default": "true"},
        {"name": "no_default", "type": "Float"},
        {"name": "list_ok", "type": "List", "default": "(1, 2, 3)"},
        {"name": "bad_list", "type": "List", "default": "()"},
    ]
    input_payload = {"cases": cases}

    with tempfile.TemporaryDirectory(prefix="p4b-02b4-") as tmp:
        work = Path(tmp)
        input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
        input_path = work / "input.json"; input_path.write_bytes(input_bytes)
        report_path = work / "product.json"
        run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))

        ref_expected_all = all(token_valid(c["type"], c.get("default")) for c in cases)
        prod_per = {e["name"]: e["valid"] for e in product["per_case"]}
        ok_all = product.get("valid") == ref_expected_all
        entries = []
        for c in cases:
            ref = token_valid(c["type"], c.get("default"))
            prod = prod_per.get(c["name"]);
            matched = prod == ref
            if not matched: ok_all = False
            entries.append({"name": c["name"], "type": c["type"], "default": c.get("default"), "matched": matched, "product_valid": prod, "reference_valid": ref})
        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "product_owned_self_crosscheck_unbound" if ok_all else "mis_match",
            "policy": "sipi.p4b-02b4.catalog-default.v1.validity",
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