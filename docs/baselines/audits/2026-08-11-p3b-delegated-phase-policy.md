# P3B Delegated Phase Policy

Commit `aae8bbd` adds a project-owner delegated, profile-scoped phase-policy
amendment for `channel-rfm-block-2-current-drive-v1`. The historical v1
unique-winner path is unchanged. A finite positive but insufficiently unique
score instead chooses the lowest phase among scores at least `best / 1.01` and
reports `policy_selected_not_locked`.

Two fresh external RFM handoffs produced matching waveform and reference-bit
hashes. The independent evaluator and the test-only Rust runner agreed on
phase selection, decision hash, error count, BER denominator, center,
amplitude, and taps. External report SHA-256:
`23aeee39f9c09e05512ef8636a1933e4b2ea2d18568a286064e31f9ce58ea225`.
The report status is `delegated_policy_semantic_agreement_observed`.

Orca read-only review concluded `0 P1 / 0 P2`. It checked preservation of v1,
the bounded tie-break, unqualified rejection, the non-lock output boundary,
oracle-only runner/comparator isolation, and P0 registration.

This is not a CDR lock claim, retained receiver parity, RFM solver parity,
Link parity, or required-profile acceptance.
