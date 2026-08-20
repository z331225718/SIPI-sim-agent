# -*- coding: utf-8 -*-
"""P5-02l default-set resolver cross-check: product vs oracle _resolve_default."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
COM_SRC = Path(r"C:\Users\z3312\code\COM\src")
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02l-resolve-parameters-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-02l.resolve-parameters-crosscheck-evidence.v1"


def oracle_norm(v):
    if hasattr(v, "tolist"):
        v = v.tolist()
        if isinstance(v, list) and v and isinstance(v[0], list): return {"kind": "matrix", "value": v}
        if isinstance(v, list): return {"kind": "vector", "value": v}
        return {"kind": "scalar", "value": float(v)}
    return {"kind": "scalar", "value": float(v)}


def match_scalar(a, b, tol=1e-9):
    return abs(a - b) < tol

def match_list(a, b):
    return a == b


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.config.materialize import _resolve_default

    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p5_02l_resolve_parameters_runner"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_02l_resolve_parameters_runner-*.exe"))[-1]

    parameters = {"fb": 53.125e9, "ndfe": 2.0, "a_fext": 0.5}
    options = {}
    expressions = {
        "a_fext": "param.a_fext",
        "ctle_fp1": "param.fb/4",
        "tau": "6.191e-3",
        "snp": "[1 3 2 4]",
    }
    input_payload = {"parameters": parameters, "options": options, "expressions": expressions}

    oracle = {name: oracle_norm(_resolve_default(expr, parameters, options)) for name, expr in expressions.items()}

    with tempfile.TemporaryDirectory(prefix="p5-02l-") as tmp:
        work = Path(tmp)
        input_bytes = json.dumps(input_payload, separators=(",", ":")).encode("utf-8")
        input_path = work / "input.json"; input_path.write_bytes(input_bytes)
        report_path = work / "product.json"
        run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
        product = json.loads(report_path.read_text(encoding="utf-8"))

        entries = []; ok_all = True
        prod_values = product.get("values", {})
        for name in expressions:
            ref = oracle[name]
            prod = prod_values.get(name)
            matched = False
            if prod and ref["kind"] == prod["kind"]:
                if ref["kind"] == "scalar":
                    matched = match_scalar(prod["value"], ref["value"])
                else:
                    matched = match_list(prod["value"], ref["value"])
            if not matched: ok_all = False
            entries.append({"name": name, "matched": matched, "product": prod, "reference": ref})

        evidence = {
            "schema": EVIDENCE_SCHEMA,
            "status": "matched_hash_bound" if ok_all else "mis_match",
            "policy": "sipi.p5-02l.resolve-parameters.v1.default-set",
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