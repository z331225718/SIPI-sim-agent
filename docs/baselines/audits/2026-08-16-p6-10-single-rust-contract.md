# P6-10 Single-Rust-Contract Invariant Gate

P6-10 requires future service/GUI layers to call the same Rust contract
and never create a second platform semantic surface. This audit records
the mechanical gate that keeps the product CLI free of python invocation,
subprocess spawning, and legacy-engine fallbacks, and marks P6-10 complete
in PLAN as a continuously enforced design constraint.

## Delivered Gate

- `tools/verify_p6_10_single_rust_contract.py` — verifier for schema
  `sipi.p6-10.single-rust-contract.v1`. It fails closed if
  `crates/sipi-cli/src/main.rs` contains any of: a python invocation
  (word-boundary `python`), a subprocess spawn (`Command::new`,
  `process::Command`, `std::process`), a legacy-engine fallback reference,
  or a pip install/download invocation.
- `tools/test_verify_p6_10_single_rust_contract.py` — 5 tests: live
  validity, no-python, no-process-spawn, no-legacy-fallback, tracking.

## Verification

`python -B tools/verify_p6_10_single_rust_contract.py` returned
`{"patterns_checked": 4, "schema": "sipi.p6-10.single-rust-contract.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p6_10_single_rust_contract` passed 5/5.

## Artifact Hashes (SHA-256)

- verifier: `4AABE0EDDAB94472FC3C23E30456C3284C66B146C387363DC04ADDABB2199E21`
- tests: `2A8E588BBA6F72D433B0DA7413E30EAD116F99BFE00087129B700D59777C7D22`

## Scope and Non-Claims

- This gate enforces the single-contract invariant on the current CLI
  source. It does not implement a service or GUI, does not certify
  platform semantics, and does not by itself complete other P6 items
  (project executor, generic agent API remain open).
- The gate does not certify release readiness.
