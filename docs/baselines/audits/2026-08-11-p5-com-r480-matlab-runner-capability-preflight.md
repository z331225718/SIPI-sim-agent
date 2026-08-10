# P5-02c COM R480 MATLAB Runner Capability Preflight Audit

## Scope

Reviewed commit `cb08cec`, which adds an oracle-only, bounded MATLAB built-in
version probe. The probe takes no `agent-com`, MATLAB source, workbook, fixture,
parameter, or R480 input path, and it does not create a product COM API.

## Result

Orca reviewer message `msg_0e014d14376f` reported **0 P1 / 0 P2**.

The reviewer independently reproduced the hash-pinned MATLAB launcher and the
external report hash. The isolated probe observed a version sentinel, but its
startup isolation is explicitly unproven. Its only valid status is therefore
`indeterminate`; the R480 reference gate remains
`reference_generation_blocked`.

## Verification

```
.venv\Scripts\python.exe -B tools\test_observe_com_r480_matlab_runner.py
.venv\Scripts\python.exe -B tools\test_verify_com_r480_matlab_runner_preflight.py
.venv\Scripts\python.exe -B tools\verify_com_r480_matlab_runner_preflight.py --external-report <external-report>
.venv\Scripts\python.exe -B tools\verify_product_boundary.py
.venv\Scripts\python.exe -B tools\verify_clean_room_register.py
.venv\Scripts\python.exe -B tools\verify_release_license_preflight.py
.venv\Scripts\python.exe -B tools\verify_rust_candidate_source_map.py
```

All checks passed. This is runner-capability evidence only: it does not prove
MATLAB use rights, an authorized R480 oracle, a reference output, parity, or a
product MATLAB dependency.
