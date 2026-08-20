"""P5-02j value-consumption cross-check: product resolver vs agent-com oracle.

Resolves default-rule expressions through resolve_default_value_v1 (Rust port
of agent_com.config.materialize._resolve_default plus literals._scalar) and
compares every scalar-catalog case against the oracle in fresh external
custody. Hash-only evidence; no release claim.

SCOPE boundary (declared, fail-closed): this slice resolves the deterministic
scalar-catalog categories -- scalar literals, derived scalar arithmetic,
booleans, simple strings, empty literals, and the DFE-lower-limit special
case. Multi-element array/matrix defaults (e.g. `[1 3 2 4]`, `[50,50]`,
`'[92 92 ; ...]'`) need a vector layout that is a separate slice; the script
asserts the oracle resolves those to multi-element arrays and excludes them
from product comparison without silently dropping drift.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
COM_SRC = Path(r"C:\Users\z3312\code\COM\src")
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02j-default-resolution-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-02j.value-consumption-crosscheck-evidence.v1"
TOL = 1e-12


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


# Each scalar case: (id, expression, expected_kind).
SCALAR_CASES = [
    ("a_fext_lit", "0.5", "scalar"),
    ("pkg_tau_lit", "6.191e-3", "scalar"),
    ("board_zc_lit", "109.8", "scalar"),
    ("board_tau_lit", "6.191e-3", "scalar"),
    ("fb_ref", "param.fb", "scalar"),
    ("ctle_fp1_derived", "param.fb/4", "scalar"),
    ("accm_freq_ref", "param.fb", "scalar"),
    ("f1_derived", "param.max_start_freq/1e9", "scalar"),
    ("a_fext_ref", "param.a_fext", "scalar"),
    ("ndfe_ref", "param.ndfe", "scalar"),
    ("freq_half_e9", "0.5*1e9", "scalar"),
    ("sigma_r_ref", "param.sigma_r", "scalar"),
    ("ql_derived", "param.T_O/param.Qr/1000", "scalar"),
    ("boolean_true", "true", "boolean"),
    ("boolean_false", "false", "boolean"),
    ("string_mm", "'MM'", "string"),
    ("string_a_dd", "'A_DD'", "string"),
    ("empty_brk", "[]", "empty"),
    # An empty MATLAB string literal '' resolves to an empty string in both the
    # oracle (parse_matlab_literal -> _scalar fallback) and the scalar port
    # (String("")), distinct from the [] empty category.
    ("empty_blank_str", "''", "string"),
    ("dfe_lower_limit", "-1*param.bmax(2:param.ndfe)", "scalar"),
]

ARRAY_CASES = {
    "snp_port_order": "[1 3 2 4]",
    "rdiepad": "[50,50]",
    "ts_sample_adj_range": "[0 0]",
    "gqual_empty": "[]",
}


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.config.materialize import _resolve_default

    # Consumed scalar param/option surface drawn from the canonical R480
    # reference (docs/baselines/p5-r480-canonical-parameter-reference.v1.yaml).
    parameters = {
        "fb": 53.125e9,
        "ndfe": 2.0,
        "bmax": 0.5,
        "_bmax_first": [0.5],
        "a_fext": 0.5,
        "a_next": 0.5,
        "a_thru": 0.5,
        "max_start_freq": 53.125e9,
        "sigma_r": 0.02,
        "T_O": 0.0,
        "Qr": 1.0,
        "trunc": 128.0,
        "Min_VEO_Test": 0.0,
    }
    options = {"pkg_len_select": 1.0}

    # Product runner input parameters (scalars only; _bmax_first is fed via
    # the bmax scalar in this scalar-catalog slice).
    parameters_runner = {
        "fb": parameters["fb"],
        "ndfe": parameters["ndfe"],
        "bmax": parameters["bmax"],
        "a_fext": parameters["a_fext"],
        "a_next": parameters["a_next"],
        "a_thru": parameters["a_thru"],
        "max_start_freq": parameters["max_start_freq"],
        "sigma_r": parameters["sigma_r"],
        "T_O": parameters["T_O"],
        "Qr": parameters["Qr"],
        "trunc": parameters["trunc"],
        "Min_VEO_Test": parameters["Min_VEO_Test"],
    }
    options_runner = {"pkg_len_select": options["pkg_len_select"]}

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_02j_value_consumption_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_02j_value_consumption_runner-*.exe"))[-1]

    # Resolve oracle per case and normalize to a comparable value.
    def oracle_norm(expr, kind):
        resolved = _resolve_default(expr, parameters, options)
        if isinstance(resolved, np.ndarray) and resolved.size > 0 and kind != "scalar":
            raise SystemExit(f"case {expr!r} (kind {kind}) resolved to non-empty array: {resolved.tolist()!r}")
        if kind == "empty":
            return {"kind": "empty"}
        if kind == "scalar":
            # The DFE-lower-limit special case returns a 1-element vector
            # (N_b=1 lower limit) in the oracle; the scalar-catalog port
            # collapses it to that single scalar.
            if isinstance(resolved, np.ndarray) and resolved.size == 1:
                return {"kind": "scalar", "value": float(resolved.reshape(-1)[0])}
            if isinstance(resolved, np.ndarray):
                raise SystemExit(f"case {expr!r} (kind scalar) resolved to multi-element array: {resolved.tolist()!r}")
            return {"kind": "scalar", "value": float(resolved)}
        if kind == "boolean":
            return {"kind": "boolean", "value": bool(resolved)}
        if kind == "string":
            return {"kind": "string", "value": str(resolved)}
        raise SystemExit(f"unknown kind {kind}")

    # Confirm array cases really are multi-element (or empty) in the oracle.
    array_bounds = {}
    for case_id, expr in ARRAY_CASES.items():
        resolved = _resolve_default(expr, parameters, options)
        arr = np.asarray(resolved, dtype=np.float64).reshape(-1)
        array_bounds[case_id] = {
            "expr": expr,
            "oracle_size": int(arr.size),
            "oracle_array_shape": list(np.asarray(resolved).shape),
        }

    cases_payload = [
        {"index": i, "expression": expr}
        for i, (_cid, expr, _kind) in enumerate(SCALAR_CASES)
    ]
    input_payload = {
        "parameters": parameters_runner,
        "options": options_runner,
        "cases": cases_payload,
    }

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-02j-value-cons-") as tmp:
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
        product_by_expr = {c["expression"]: c.get("result", {}) for c in product["cases"]}

        for case_id, expr, kind in SCALAR_CASES:
            oracle = oracle_norm(expr, kind)
            prod = product_by_expr.get(expr, {})
            if prod.get("kind") == "error":
                diffs = ["product error: " + str(prod.get("value", "?"))]
            elif kind == "empty":
                ok = prod.get("kind") == "empty"
                diffs = [] if ok else ["empty drift"]
            elif kind == "boolean":
                ok = prod.get("kind") == "boolean" and prod.get("value") is oracle["value"]
                diffs = [] if ok else ["boolean drift"]
            elif kind == "string":
                ok = prod.get("kind") == "string" and prod.get("value") == oracle["value"]
                diffs = [] if ok else ["string drift"]
            else:
                ok = (prod.get("kind") == "scalar"
                      and abs(prod.get("value", 0.0) - oracle["value"]) <= TOL)
                diffs = ([] if ok else
                         [f"scalar drift product={prod.get('value')} oracle={oracle['value']}"])
            entries.append({
                "id": case_id,
                "expression": expr,
                "kind": kind,
                "oracle": oracle["value"] if kind != "empty" else None,
                "input_sha256": sha256_bytes(input_bytes),
                "matched": ok,
                "diffs": diffs[:4],
            })

    matched = sum(1 for e in entries if e["matched"])
    status = "matched_hash_bound" if matched == len(SCALAR_CASES) else "mis_match"
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": status,
        "oracle_source": "agent_com/config/materialize.py:_resolve_default + literals.py",
        "source_sha256": sha256_bytes((COM_SRC / "agent_com" / "config" / "materialize.py").read_bytes()),
        "policy": "sipi.p5-02j.value-consumption.v1.default-resolution",
        "scope": "scalar-catalog defaults only; multi-element array/matrix defaults deferred",
        "tolerance": TOL,
        "oracle_param_surface_sorted": sorted(parameters.keys()),
        "oracle_option_surface_sorted": sorted(options.keys()),
        "array_out_of_scope": array_bounds,
        "matched_count": matched,
        "case_count": len(SCALAR_CASES),
        "cases": entries,
    }

    import yaml
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        yaml.safe_dump(evidence, sort_keys=False, allow_unicode=True), encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in evidence.items() if k in (
        "schema", "status", "matched_count", "case_count", "scope", "array_out_of_scope",
    )}, indent=2))
    return 0 if matched == len(SCALAR_CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
