# P4A-03 Complete Typed Inventory Consumer

## Closed Bounded Scope

The product library now composes bounded ASCII structural parsing, the lexical
semantic envelope, typed `[Model]`, `[Model Selector]`, and `[Pin]`
declarations, complete-document `[End]` validation, and caller-owned pin
reference classification in one fail-closed pass.

The complete-document boundary requires exactly one payload-free `[End]` as
the final structural record. The tracked selected object is therefore rejected
as `missing_end` before its incidental selector gap is interpreted. P4A-01
separately proves that object is an exact truncated prefix and disposes it as
unusable for a semantic or electrical profile.

## External-Custody Observation

The test-only `p4a_03_typed_inventory_runner` was run against the exact Alliance
Memory object outside the worktree with explicit caller markers `GND`, `NC`,
and `POWER`. The declaration/linkage pass succeeded with:

- 6,138,000 bytes and SHA-256
  `53e27609dbb81e7685456a48c611111fed34ca14477623e46a9a9a582a7a646b`;
- IBIS version `5.0`, component `AS4C512M16MD4V-053BIN`;
- 95 models, four selectors, and 200 pins; and
- 3 direct-model pins, 31 selector pins, and 166 explicit-marker pins.

This observation closes only the bounded declaration/linkage consumer scope.
The runner is a test-only explicit-path tool; it is not a public CLI or product
asset route. The external bytes remain outside the worktree and do not become a
fixture, accepted profile, runtime default, or release input.

## Non-Claims

No selector branch, model, corner, PVT, supply, reference node, or electrical
profile is selected. No table is decoded or evaluated. No quasi-static result
is promoted to transient behavior, and no transient solver, AMI runtime,
general IBIS compatibility, external profile acceptance, or release claim is
made.
