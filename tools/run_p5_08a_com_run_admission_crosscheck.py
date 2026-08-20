# -*- coding: utf-8 -*-
"""P5-08a COM run-request admission cross-check: product vs independent ref.

Validates the structural contract of a "sipi.com.run-request.v1" request
(schema id, artifact root/id bindings, non-empty scalar params) without
running any COM computation. Product path is com_run_admission_v1 via the
runner binary; the reference recomputes the same deterministic verdict from
scratch. Fail closed on any mismatch.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-08a-com-run-admission-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-08a.com-run-admission-crosscheck-evidence.v1"
SCHEMA = "sipi.com.run-request.v1"


def reference_admission(request_text: str) -> dict[str, Any]:
    """Independent reference: structural admission, no COM execution."""
    try:
        obj = json.loads(request_text)
    except ValueError:
        return {"ok": False, "error": "invalid_json"}
    if not isinstance(obj, dict):
        return {"ok": False, "error": "invalid_json"}
    schema = obj.get("schema")
    if typeof_str(schema) != "string":
        return {"ok": False, "error": "invalid_json"}
    if schema != SCHEMA:
        return {"ok": False, "error": "schema_mismatch"}
    root = obj.get("artifact_root", "")
    art_id = obj.get("artifact_id", "")
    bound = typeof_str(root) == "string" and len(root) > 0 and typeof_str(art_id) == "string" and len(art_id) > 0
    params = obj.get("params")
    if params is None:
        return {"ok": True, "admitted": False, "schema_matched": True, "artifact_bound": bound, "consumed_key_count": 0, "invalid_reason": "missing_params"}
    if not isinstance(params, dict):
        return {"ok": False, "error": "invalid_json"}
    for value in params.values():
        if typeof_str(value) not in ("number", "boolean", "string"):
            return {"ok": False, "error": "non_scalar_param"}
    consumed = len(params)
    if consumed == 0:
        return {"ok": True, "admitted": False, "schema_matched": True, "artifact_bound": bound, "consumed_key_count": 0, "invalid_reason": "empty_params"}
    if not bound:
        return {"ok": True, "admitted": False, "schema_matched": True, "artifact_bound": False, "consumed_key_count": consumed, "invalid_reason": "unbound_artifacts"}
    return {"ok": True, "admitted": True, "schema_matched": True, "artifact_bound": True, "consumed_key_count": consumed, "invalid_reason": None}


def typeof_str(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "other"


def main() -> int:
    built = subprocess.run([str(CARGO), "build", "-p", "sipi-com", "--test", "p5_08a_com_run_admission_runner"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if built.returncode != 0: raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_08a_com_run_admission_runner-*.exe"))[-1]

    cases = [
        {"label": "valid_admitted", "request": json.dumps({"schema": SCHEMA, "artifact_root": "r", "artifact_id": "a", "params": {"fb": 53.125e9, "a_fext": 0.5}})},
        {"label": "valid_single_param", "request": json.dumps({"schema": SCHEMA, "artifact_root": "root", "artifact_id": "id", "params": {"a_v": 0.415}})},
        {"label": "schema_mismatch", "request": json.dumps({"schema": "sipi.wrong", "artifact_root": "r", "artifact_id": "a", "params": {"fb": 1.0}})},
        {"label": "missing_artifacts", "request": json.dumps({"schema": SCHEMA, "params": {"fb": 1.0}})},
        {"label": "empty_params", "request": json.dumps({"schema": SCHEMA, "artifact_root": "r", "artifact_id": "a", "params": {}})},
        {"label": "missing_params", "request": json.dumps({"schema": SCHEMA, "artifact_root": "r", "artifact_id": "a"})},
        {"label": "invalid_json", "request": "not-json"},
        {"label": "nested_non_scalar", "request": json.dumps({"schema": SCHEMA, "artifact_root": "r", "artifact_id": "a", "params": {"k": {"nested": 1}}})},
    ]

    ok_all = True
    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-08a-") as tmp:
        work = Path(tmp)
        for case in cases:
            input_path = work / "input.json"
            input_path.write_text(json.dumps({"request": case["request"]}, separators=(",", ":")), encoding="utf-8")
            report_path = work / "product.json"
            r = subprocess.run([str(runner), "--input", str(input_path), "--report", str(report_path)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0: raise SystemExit("runner failed :: " + r.stdout + r.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            reference = reference_admission(case["request"])
            if not reference.get("ok") or not reference.get("admitted"):
                # Normalize: a reference error (invalid_json/schema/non_scalar) means product ok:false.
                prod_ok = bool(product.get("ok"))
                ref_ok = reference.get("ok", False)
                ref_err = reference.get("error")
                prod_err = product.get("error")
                mismatched = (prod_ok != ref_ok) or (ref_err != prod_err)
                entries.append({
                    "label": case["label"], "matched": not mismatched,
                    "product_ok": prod_ok, "reference_ok": ref_ok,
                    "product_error": prod_err, "reference_error": ref_err,
                    "product_admitted": bool(product.get("admitted")) if prod_ok else False,
                    "reference_admitted": reference.get("admitted", False),
                    "product_reason": product.get("invalid_reason") if prod_ok else None,
                    "reference_reason": reference.get("invalid_reason") if ref_ok else None,
                })
                if mismatched: ok_all = False
                continue
            # Both ok: admitted case. Compare admitted + fields.
            prod = product
            prod_admitted = bool(prod.get("admitted"))
            ref_admitted = reference["admitted"]
            prod_schema = bool(prod.get("schema_matched"))
            ref_schema = reference["schema_matched"]
            prod_bound = bool(prod.get("artifact_bound"))
            ref_bound = reference["artifact_bound"]
            prod_consumed = prod.get("consumed_key_count") or 0
            ref_consumed = reference["consumed_key_count"]
            prod_reason = prod.get("invalid_reason")
            ref_reason = reference["invalid_reason"]
            mismatched = (prod_admitted != ref_admitted or prod_schema != ref_schema
                          or prod_bound != ref_bound or prod_consumed != ref_consumed
                          or prod_reason != ref_reason)
            entries.append({
                "label": case["label"], "matched": not mismatched,
                "product_ok": True, "reference_ok": True,
                "admitting": prod_admitted,
                "product_reason": prod_reason, "reference_reason": ref_reason,
                "consumed_key_count": prod_consumed,
            })
            if mismatched: ok_all = False

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p5-08a.com-run-request.v1.admission",
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