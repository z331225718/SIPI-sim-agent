# P4A-01g Owner-Selected Required-Profile IBIS Inventory — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-01 sub-slice 01g (required IBIS profile inventory)
- Status: delivered. Owner selected the required profile (A6 decision:
  IBIS 5.0; file fixtures/ibis/as4c512m16md4v-053bin.ibs). The observer-only
  structural inventory is bound to the file hash; no product parser or
  runtime is involved.

## Method

Hash-bind the physical .ibs file, then scan the ASCII text for structural
facts: IBIS version, component, manufacturer, unique keyword set (including
Model Selector), model-block names, and table-family keywords. The scan is
explicitly observer-only and is not a product IBIS parser (P4A-03 owns the
parser). Corner typ/min/max enumeration is bounded to rows whose first token
is typ/min/max; this file reports 0 for that convention and the limitation
is recorded as a non-claim, not asserted.

## Result

- file: fixtures/ibis/as4c512m16md4v-053bin.ibs
  sha256 d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b,
  4,215,925 bytes.
- facts: IBIS 5.0; component AS4C512M16MD4V-053BIN; manufacturer Alliance
  Memory Inc.; 26 unique keywords (Model Selector present); 67 model blocks;
  4 table families (GND Clamp, Ramp, Rising Waveform, Falling Waveform;
  POWER Clamp/Pulldown/Pullup present in keyword set).
- Material registered in authorized-material-registry.v1.yaml as
  external_reference_only (bound_items P4A-01).
- Verifier verify_p4a_01_required_profile_inventory.py + 7 tests green.

## Binding

- Inventory doc docs/baselines/p4a-01-required-profile-inventory.v1.yaml.
- Owner decision ref docs/baselines/owner-decision-checklist.v1.md (A6).
- PLAN **P4A-01g**; ledger note/gate P4A-01; coverage gates 89 -> 90.
