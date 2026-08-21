# P1-04B Oracle-Only Fixture Boundary Scoped Closure

## Result

P1-04B is scoped-closed only for its mechanical oracle-only fixture
boundary. The 14 legacy fixture collections remain external observation
material, all remain `blocked_unknown` for distribution, and the existing
owner decision permits comparison only. This additive record does not close
the P1-04B main item or authorize a required profile, custody transfer,
redistribution, product input, runtime, acceptance, or release.

## Manifest reconciliation

The manifest contains 14 assets and nine `required_by` entries marked
`required`; the other five are optional. Those labels are gate-demand labels,
not a selected profile. Each asset is assigned to one responsible domain and
gate in the closure evidence. The source owner and unresolved distribution
status are copied from the manifest without promotion.

## Boundary evidence

The existing P1-04B boundary gate observes 14 external assets, zero legacy
schema identifiers in product Rust, and no asset identity materialized as a
tracked repository path. Product-owned `sipi.contract.v1` fixtures remain a
separate P1-04A surface. No Rust source, PLAN, ledger, owner request, or
publication record is changed by this closure.

## Retained domain blockers

The exact selected profile, external custody identity, rights, and
distribution authority remain domain-owned external facts:

- P3B-02 keeps the explicit CTLE -> FFE API caller-supplied and retains the
  conflicting PyBERT defaults as an external profile/oracle blocker.
- P4A-01/P4A-03 keep the selected-model grammar consumer bounded while the
  official model/profile and rights remain external blockers.
- P4B-02/P4B-08/P4B-09 keep the typed forwarded subset and ADS/AMI runtime
  observation external-only. The observed `ads-pcie-gen5-dual-ami-windows-x64-v1`
  binding is not runtime-admitted; DLL use, compatibility, rights, and dynamic
  closure are not admitted.
- P5-02/P5-06 retain the clean Agent-COM source/run observation without
  fabricating the missing authoritative metric, profile, or distribution
  authority. The observed `r480` tuple remains source/run observation only.

The closure verifier binds these domain records and fails closed if a blocker
is removed or promoted. In particular, the owner comparison permission is
never widened into redistribution or product admission.

## Verification

```text
python -B tools/verify_p1_04b_oracle_only_scope_closure.py
python -B -m unittest tools.test_verify_p1_04b_oracle_only_scope_closure -v
python -B tools/verify_p1_04b_legacy_fixture_boundary.py
python -B tools/verify_p1_legacy_fixture_required_profile_facts.py
python -B tools/verify_p1_04b_comparison_permission_reconciliation.py
```

The closure is valid only while all four domain blocker groups remain
external and the existing P1 gates continue to pass.
