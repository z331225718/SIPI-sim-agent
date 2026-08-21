# P4A-01 / P4A-02 Semantics Gap Audit

## P4A-01: Selected IBIS Asset

The owner-selected asset remains the exact product fixture
`fixtures/ibis/as4c512m16md4v-053bin.ibs`, SHA-256
`d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b`.
Existing observer facts are 67 `[Model]` blocks and four `[Model Selector]`
blocks. The new library-level typed inventory consumer does not select a
branch; it rejects the asset at the first missing selector branch model:

```text
DQ_PIN -> DQ_60OHM_60OHM_PREEMP_ON
```

This is an asset completeness fact, not permission to synthesize a model.
After this gap is resolved, the next observed unresolved pin reference is
not yet admissible as a model/corner decision. The owner still must explicitly
choose selector-branch and corner/PVT semantics before electrical evaluation.

P4A-01 therefore remains `semantics_not_implemented`; the new slice only
improves the bounded structural-to-typed declaration boundary.

## P4A-02: Behavior and Dynamic Composition

The existing authorized Gen5 observation remains observation-only:

- TX probe status: `success_all`;
- RX probe status: `probe_crash_all`;
- DLL identity: authorized matched record;
- product runtime invocation: false.

The existing dynamic endpoint contract still blocks admission on the exact
fields below:

- channel return/reference binding and IBIS-to-load terminal map;
- supply and power-clamp binding;
- retained capacitor initial state and operating-point/UIC policy;
- integration method, internal stepping, timebase, output grid, and alignment;
- stimulus ownership, return binding, and derivative source;
- output/stimulus/table/breakpoint/work resource caps; and
- dynamic time/voltage/current/state tolerances and acceptance evidence.

Consequently P4A-02 remains behavior-spec/contract work only. No
quasi-static route is re-labeled as transient, no model/corner/reference is
guessed, and no external profile, runtime, parity, or release state is raised.

## Machine Gates

- `tools/verify_p4a_01_required_profile_inventory.py`
- `tools/verify_p4a_02b_gen5_behavior_spec.py`
- `tools/verify_p4a_dynamic_endpoint_transient_composition_contract.py`
- `tools/verify_p4a_03_typed_inventory_consumer.py`
