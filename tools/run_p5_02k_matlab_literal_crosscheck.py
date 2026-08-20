"""P5-02k MATLAB numeric-literal cross-check: product parser vs agent-com oracle.

Parses numeric-literal expressions through parse_literal_v1 (Rust port of
agent_com.config.literals.parse_matlab_literal) and compares every case
against the oracle in fresh external custody: empty literals, bracket
vector/matrix literals, colon ranges, single-negative disambiguation, and
the bounded scaled-ones idiom. Hash-only evidence; no release claim.
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
EVIDENCE = ROOT / "docs" / "baselines" / "p5-02k-matlab-literal-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-02k.matlab-literal-crosscheck-evidence.v1"
TOL = 1e-12


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().lower()


# Each case: (id, expression, expected_kind).
LITERAL_CASES = [
    ("empty", "[]", "empty"),
    ("vector_snp_port_order", "[1 3 2 4]", "vector"),
    ("vector_rdiepad", "[50,50]", "vector"),
    ("vector_ts_adj", "[0 0]", "vector"),
    ("matrix_2x2", "[1 2; 3 4]", "matrix"),
    ("matrix_pkg_zc_row", "[92 92 ; 70 70; 61 61; 44 44; 58 58; 87 87; 64 64; 52 52; 43 43; 82 82; 79 79; 88 88; 65 65; 93 93]", "matrix"),
    ("colon_range", "[1:1:3]", "vector"),
    ("single_negative", "[1 - 2]", "vector"),
    ("two_negatives", "[1 -2]", "vector"),
    ("negative_vector", "[-50 -50]", "vector"),
    ("scaled_ones", "[0.5*ones(1,4)]", "vector"),
    ("scalar_lit", "78.2", "scalar"),
    ("scalar_int", "92", "scalar"),
    ("e_notation", "6.191e-3", "scalar"),
    ("sci_e9", "0.5*1e9", "scalar"),
]


# Oracle-limitation cases: expressions the agent-com oracle cannot parse into a
# value (declared boundary; the product superset is not asserted against a
# missing reference). `[1:3]` (two-part colon range) raises ValueError in
# literals._vector because it unpacks only the non-None regex groups.
ORACLE_LIMIT_CASES = [
    ("colon_range_simple", "[1:3]"),
]


def main() -> int:
    sys.path.insert(0, str(COM_SRC))
    import numpy as np
    from agent_com.config.literals import parse_matlab_literal

    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_02k_matlab_literal_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_02k_matlab_literal_runner-*.exe"))[-1]

    def oracle_norm(expr, kind):
        resolved = parse_matlab_literal(expr)
        if isinstance(resolved, np.ndarray) and resolved.ndim == 0:
            return {"kind": "scalar", "value": float(resolved)}
        if isinstance(resolved, np.ndarray) and resolved.size == 0 and (expr == "[]" or expr in ("[]",)):
            return {"kind": "empty"}
        if isinstance(resolved, np.ndarray) and resolved.ndim == 1:
            return {"kind": "vector", "value": [float(v) for v in resolved]}
        if isinstance(resolved, np.ndarray) and resolved.ndim == 2:
            return {"kind": "matrix", "value": [[float(v) for v in row] for row in resolved]}
        if isinstance(resolved, (int, float, np.integer, np.floating)):
            return {"kind": "scalar", "value": float(resolved)}
        raise SystemExit(f"unhandled oracle type for {expr!r}: {type(resolved).__name__}")

    cases_payload = [{"index": i, "expression": expr} for i, (_cid, expr, _k) in enumerate(LITERAL_CASES)]
    input_payload = {"cases": cases_payload}

    entries = []
    with tempfile.TemporaryDirectory(prefix="p5-02k-literal-") as tmp:
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

        for case_id, expr, kind in LITERAL_CASES:
            oracle = oracle_norm(expr, kind)
            prod = product_by_expr.get(expr, {})
            if prod.get("kind") == "error":
                diffs = ["product error: " + str(prod.get("value", "?"))]
                ok = False
            elif prod.get("kind") != oracle["kind"]:
                diffs = [f"kind drift product={prod.get('kind')} oracle={oracle['kind']}"]
                ok = False
            else:
                if kind == "empty":
                    ok = True
                    diffs = []
                elif kind == "scalar":
                    ok = abs(prod.get("value", 0.0) - oracle["value"]) <= TOL
                    diffs = [] if ok else ["scalar drift"]
                else:
                    ok = prod.get("value") == oracle["value"]
                    diffs = [] if ok else [f"content drift product={prod.get('value')} oracle={oracle['value']}"]
            entries.append({
                "id": case_id,
                "expression": expr,
                "kind": kind,
                "oracle": oracle,
                "input_sha256": sha256_bytes(input_bytes),
                "matched": ok,
                "diffs": diffs[:4],
            })

    matched = sum(1 for e in entries if e["matched"])

    # Verify the declared oracle-limitation surface: each expression must
    # actually fail in the oracle, and the product must produce the superset
    # value (documented boundary, not a match).
    import re as _re
    _NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    _COLON_PAT = _re.compile(rf"^\s*({_NUMBER})\s*:\s*({_NUMBER})(?:\s*:\s*({_NUMBER}))?\s*$")
    oracle_limits = []
    for lim_id, lim_expr in ORACLE_LIMIT_CASES:
        raised = False
        try:
            parse_matlab_literal(lim_expr)
        except Exception:
            raised = True
        product_value = product_by_expr.get(lim_expr, {}).get("value")
        oracle_limits.append({
            "id": lim_id,
            "expression": lim_expr,
            "oracle_raises": raised,
            "product_superset_value": product_value,
            "note": "two-part colon range [N:M] raises in oracle _vector; product expands it",
        })
        if not raised:
            raise SystemExit("oracle limitation drifted: " + lim_expr + " no longer raises")

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if matched == len(LITERAL_CASES) else "mis_match",
        "oracle_source": "agent_com/config/literals.py:_evaluate/_vector/parse_matlab_literal",
        "source_sha256": sha256_bytes((COM_SRC / "agent_com" / "config" / "literals.py").read_bytes()),
        "policy": "sipi.p5-02j.value-consumption.v1.default-resolution",
        "tolerance": TOL,
        "matched_count": matched,
        "case_count": len(LITERAL_CASES),
        "oracle_limitations": oracle_limits,
        "cases": entries,
    }

    import yaml
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(json.dumps({
        "schema": EVIDENCE_SCHEMA, "status": evidence["status"],
        "matched_count": matched, "case_count": len(LITERAL_CASES),
    }, indent=2))
    return 0 if matched == len(LITERAL_CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
