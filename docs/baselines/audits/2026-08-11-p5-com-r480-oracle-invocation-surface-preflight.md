# P5-02d1 COM R480 Oracle Invocation-Surface Preflight Audit

## Scope

Reviewed commit `0147339`. The slice reads the hash-pinned external Git object
`agent-com@5272ffe:tools/run_matlab_oracle.py` through Python AST only. It does
not import or execute that runner, and it does not run MATLAB or read any
workbook, fixture, input, default, result, or formula material.

## Result

Orca reviewer message `msg_0c42cb1982f3` reported **0 P1 / 0 P2**.

The reviewer independently reproduced the Git-object identity and the external
report hash. The report records only bounded invocation-surface facts. Its
status remains `runner_interface_partially_observed`; dynamic invocation is
`not_authorized_or_not_safe`, and the R480 authoritative-reference gate remains
`reference_generation_blocked`.

## Verification

```
.venv\Scripts\python.exe -B tools\test_observe_com_r480_oracle_invocation_surface.py
.venv\Scripts\python.exe -B tools\test_verify_com_r480_oracle_invocation_surface_preflight.py
.venv\Scripts\python.exe -B tools\verify_com_r480_oracle_invocation_surface_preflight.py --external-report <external-report>
.venv\Scripts\python.exe -B tools\verify_product_boundary.py
.venv\Scripts\python.exe -B tools\verify_clean_room_register.py
.venv\Scripts\python.exe -B tools\verify_release_license_preflight.py
.venv\Scripts\python.exe -B tools\verify_rust_candidate_source_map.py
```

All checks passed. This is static runner-interface evidence only. It does not
authorize execution, establish an authoritative reference, establish MATLAB
parity, or create a product MATLAB dependency.
