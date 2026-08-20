# P4A-04 Semantic Cores Complete — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-04 main item decision-complete (all four semantic surfaces + explicit policy)
- Status: completed by delivery; external acceptance surface unchanged

## Deliverables bound to this completion

| Surface | Slice | Entry points | Evidence |
| --- | --- | --- | --- |
| I-V (DC clamp) | 04b/04c/04d | evaluate_dc_clamps_v1, decode_selected_dc_clamps_v1 | typed evaluator + selected decoder + two-fresh-custody external compare (max abs/rel error 0) |
| V-T | 04f | evaluate_vt_v1, VtTableV1 | charter p4a-04f-vt-table-core.v1.yaml + verifier + 8 Rust tests |
| Ramp | 04g | RampSpecV1 | charter p4a-04g-ramp-package-spec-core.v1.yaml + verifier + Rust tests |
| Package | 04g | PackageSpecV1 | same charter as Ramp |
| Interpolation/extrapolation policy | 04b + 04f | explicit policies (linear within domain, reject out-of-domain) | fixed policy strings in both charters |

## Explicitly NOT granted by this completion

- No external profile acceptance for V-T/ramp/package (matrix keeps the
  external-accepted scope at exactly one entry: selected DC clamp).
- No IBIS text decoding extension (decoder scope remains the selected
  Input/TYP DC clamp).
- No terminal network / termination solve: matrix entry
  `package-pin-vt-ramp-network` stays `unsupported` (completeness gate
  requires it).
- No AMI/algorithmic model, no transient parity, no file/URL route.
- CLI routing remains owned by P4A-06; ramp/package have no CLI slice.

## Bookkeeping

- PLAN.md P4A-04 row: `[x]` with completion note.
- PLAN.md P4A-05 row: added **P4A-05c** matrix-sync note.
- Matrix: added `vt-table-core` and `ramp-package-spec-core` as
  `implemented_self_tested`; unsupported entries unchanged.
- Ledger: P4A-04 removed, `total_open` 33 → 32; ledger test updated.
- Gate coverage keeps P4A-04 mapped (completed-item convention).

## Verification

- `cargo test -p sipi-types -p sipi-ibis`: 37 + 37 passed, 0 failed.
- `python tools/verify_p4a_04f_vt_table_core.py` and
  `python tools/verify_p4a_04g_ramp_package_spec_core.py`: valid.
- Matrix verifiers (`verify_p4a_ibis_conformance_matrix.py`,
  `verify_p4a_05_conformance_matrix_complete.py`): valid with new entries.
- Ledger verifier: valid, 32 items.
