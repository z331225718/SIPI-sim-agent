# Gate Coverage Binding: P4A-04f/04g and P4B-02b1/02b2 Slice Gates — Audit Record

- Date (UTC): 2026-08-16
- Scope: bind the four slice gates delivered in rounds 41-43 into the
  mechanical coverage machinery
- Status: complete; coverage sweep now includes all new gates

## Gap found

The slice verifiers `verify_p4a_04f_vt_table_core.py`,
`verify_p4a_04g_ramp_package_spec_core.py`,
`verify_p4b_02b1_parameter_value_core.py` and
`verify_p4b_02b2_parameter_form_binding.py` existed and passed on their
own, but were not listed in the open-item gate coverage map
(`tools/verify_plan_open_items_gate_coverage.py`), so the classified
sweep could not detect their regression.

## Resolution

- `OPEN_ITEM_GATES["P4A-04"]` now lists the 04f and 04g gates alongside
  the 04a charter gate (completed-item convention: P4A-04 stays mapped).
- `OPEN_ITEM_GATES["P4B-02"]` now lists the 02b1 and 02b2 gates alongside
  the asset-set gate.
- Coverage test assertion updated: 66 → 70 gates (49 items unchanged).
- Ledger P4B-02 entry gate list updated to the same three gates.

## Verification

- `verify_plan_open_items_gate_coverage.py`: valid, 49 items / 70 gates.
- `verify_plan_remaining_items_ledger.py`: valid, 32 items.
- Coverage + ledger test suites: 9 tests OK.
- Classified sweep over the coverage map: 49 unique gate files,
  VALID_KEY=34 (was 30), RC0_ALT_KEY=7, RC2_NEEDS_ARGS=8, BAD=0.
