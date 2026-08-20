# -*- coding: utf-8 -*-
"""P4B-02b5 AMI runtime-parameter-table cross-check: product vs independent ref.

Builds the ordered runtime parameter table from a catalog plus optional
candidate values. The product path is build_ami_runtime_params_v1 via the
runner binary; the reference is a from-scratch python merge that does not
depend on product code. Both sides produce the resolved
(name, usage, type, value-token) triples, which must match exactly.
Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p4b-02b5-ami-runtime-params-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p4b-02b5.ami-runtime-params-crosscheck-evidence.v1"


def reference_merge(catalog, candidates):
    """Independent reference: names sorted (product catalog is a sorted map).

    Returns {"ok": bool, "error": str|None, "params": [...]}.
    """
    by_name = {e["name"]: e for e in catalog}
    params = []
    for name in sorted(by_name):
        entry = by_name[name]
        cand = candidates.get(name)
        if cand is not None:
            if cand["type"] != entry["type"]:
                return {"ok": False, "error": "type_mismatch:" + name, "params": []}
            params.append({"name": name, "usage": entry["usage"], "type": entry["type"], "value": cand["value"]})
            continue
        usage = entry["usage"]
        default = entry.get("default")
        if usage == "In":
            if default is None:
                return {"ok": False, "error": "missing_runtime_value:" + name, "params": []}
            params.append({"name": name, "usage": "In", "type": entry["type"], "value": default})
    return {"ok": True, "error": None, "params": params}


def token_valid_float(value):
    try:
        v = float(value)
        return v == v and v not in (float("inf"), float("-inf"))
    except ValueError:
        return False


def candidate_value_ok(type_token, value):
    if type_token == "Float": return token_valid_float(value)
    if type_token == "Integer":
        try: int(value); return True
        except ValueError: return False
    if type_token == "Boolean": return value in ("True", "False")
    if type_token == "String": return len(value) > 0
    if type_token == "List": return value.startswith("(") and value.endswith(")") and len(value[1:-1].strip()) > 0
    return False


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-ami-text", "--bin", "p4b_02b_crosscheck_runner", "--features", "p4b-self-crosscheck"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = ROOT / "target" / "debug" / ("p4b_02b_crosscheck_runner.exe" if os.name == "nt" else "p4b_02b_crosscheck_runner")
    os.environ["SIPI_P4B_RUNNER"] = "p4b_02b5_ami_runtime_params_runner"

    cases = [
        {
            "label": "candidate_overrides_default_in",
            "catalog": [{"name": "swing", "usage": "In", "type": "Float", "default": "0.5"}],
            "candidates": {"swing": {"type": "Float", "value": "0.9"}},
        },
        {
            "label": "default_used_when_no_candidate_in",
            "catalog": [{"name": "swing", "usage": "In", "type": "Float", "default": "0.5"}],
            "candidates": {},
        },
        {
            "label": "mixed_roles_sorted_order",
            "catalog": [
                {"name": "zeta", "usage": "In", "type": "Float", "default": "1.0"},
                {"name": "alpha", "usage": "In", "type": "Float", "default": "2.0"},
                {"name": "out_x", "usage": "Out", "type": "Float"},
                {"name": "info_y", "usage": "Info", "type": "String"},
            ],
            "candidates": {"out_x": {"type": "Float", "value": "3.0"}},
        },
        {
            "label": "out_and_info_omitted_without_candidate",
            "catalog": [
                {"name": "out_x", "usage": "Out", "type": "Float"},
                {"name": "info_y", "usage": "Info", "type": "String"},
            ],
            "candidates": {},
        },
        {
            "label": "missing_in_without_default",
            "catalog": [{"name": "swing", "usage": "In", "type": "Float"}],
            "candidates": {},
        },
        {
            "label": "candidate_type_mismatch",
            "catalog": [{"name": "swing", "usage": "In", "type": "Float", "default": "0.5"}],
            "candidates": {"swing": {"type": "Integer", "value": "5"}},
        },
        {
            "label": "integer_and_boolean_types",
            "catalog": [
                {"name": "pre", "usage": "In", "type": "Integer", "default": "2"},
                {"name": "flag", "usage": "In", "type": "Boolean", "default": "True"},
            ],
            "candidates": {},
        },
        {
            "label": "unknown_candidate_ignored",
            "catalog": [{"name": "swing", "usage": "In", "type": "Float", "default": "0.5"}],
            "candidates": {"bogus": {"type": "Float", "value": "1.0"}},
        },
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p4b-02b5-") as tmp:
        work = Path(tmp)
        for case in cases:
            label = case["label"]
            input_payload = {"catalog": case["catalog"], "candidates": case["candidates"]}
            input_path = work / "input.json"; input_path.write_bytes(json.dumps(input_payload, separators=(",", ":")).encode("utf-8"))
            report_path = work / "product.json"
            run = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            if run.returncode != 0: raise SystemExit("runner failed :: " + run.stdout + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = reference_merge(case["catalog"], case["candidates"])

            prod_ok = bool(product.get("ok"))
            prod_err = product.get("error")
            prod_params = product.get("params") or []
            ref_ok = bool(reference["ok"])
            ref_err = reference.get("error")
            ref_params = reference["params"]

            mismatched = (prod_ok != ref_ok) or (prod_params != ref_params) or (prod_err != ref_err)
            if mismatched: ok_all = False
            entries.append({
                "label": label,
                "matched": not mismatched,
                "product_ok": prod_ok,
                "reference_ok": ref_ok,
                "product_params": prod_params,
                "reference_params": ref_params,
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "product_owned_self_crosscheck_unbound" if ok_all else "mis_match",
        "policy": "sipi.p4b-02b5.ami-runtime-params.v1.typed",
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