# P4B-02b3 Parameter Catalog Typed Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b3 (AMI parameter-catalog typed core)
- Status: delivered and cross-checked against an independent reference.
  Profile-agnostic: the specific AMI profile (owner B2 authorized) is fed
  as data later; no reserved-name catalog / AMI runtime.

## Method

Implement a parameter-catalog core in sipi-ami-text parameter_catalog_v1.rs
on top of the P4B-02b1 value core. compile() builds a BTreeMap of
CatalogEntryV1 (name, Usage In/Out/Info, type, optional default);
validate_candidate_set_v1 enforces Usage=In required, unknown rejection,
and per-entry type matching.

## Result

- 4 cross-check scenarios matched an independent reference (valid,
  missing-required, unknown, type-mismatch).
- sipi-ami-text unit suite 24 tests green (7 new catalog tests).
- Profile-agnostic; no AMI profile selected, no runtime.

## Binding

- Verifier verify_p4b_02b3_parameter_catalog.py + 7 tests; crosscheck
  evidence docs/baselines/p4b-02b3-parameter-catalog-crosscheck-evidence.v1.yaml.
- Charter p4b-02b3-parameter-catalog-stage.v1.yaml; source map
  p4b-02b3-mit-source-map.v1.yaml.
- PLAN **P4B-02b3**; ledger note/gate P4B-02; coverage gates 95 -> 96.
