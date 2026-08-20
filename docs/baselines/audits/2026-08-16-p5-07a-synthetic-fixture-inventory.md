# P5-07a Synthetic Fixture Set Inventory — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-07 sub-slice 07a (synthetic fixture set inventory)
- Status: delivered and mechanically bound; property/negative fixtures
  pending

## Method

Registered the full COM synthetic fixture set (14 files) into the
authorized-material-registry (now 33 materials) and inventoried them
hash-bound; recorded manifest facts and manifest-vs-current hash
differences.

## Result

- 14 fixtures inventoried, hashes verified against the registry.
- Manifest facts: generator tools/generate_synthetic_s4p.py; target
  26.56 GHz; grid 0-80 GHz, 10 MHz step; file_port_order
  [TX+, RX+, TX-, RX-]; com_internal_port_order [TX+, TX-, RX+, RX-].
- 3 manifest-declared hashes differ from current files (generation-time
  records; differences noted, not silently reconciled).
- Oracle binding: the set feeds the P5-06a MATLAB oracle run.

## Scope discipline

No compare, no product fixture admission; property and negative fixtures
(the anti-single-truth surface) remain later P5-07 slices.

## Binding

- Inventory `p5-07-synthetic-fixture-inventory.v1.yaml`;
- Verifier `verify_p5_07a_fixture_inventory.py` + 4 tests;
- PLAN **P5-07a**; ledger note/gate; coverage gates 86 -> 87.
