# P3C-04az ADS Exact Common-Node Observation Audit

Reviewer: Orca reused OpenCode terminal `term_2de7cb74-b803-4e20-bb5b-4803777c24f8`.

Scope: preparation commit `4da75e1` and evidence commit `424c1d8`.

Result: no High or Critical findings. The reviewer independently checked the
16-member exact 4:1 mapping, common-node Hdiff indexing, hash-only report,
clean-archive inventory, source identity, historical full-axis mismatch, and
the non-claim that the observed delta is not automatically a passivity
correction. It also reran the evidence verifier and all four local test suites.

Two informational improvements were applied after the review: the specification
now names aggregate non-payload summaries explicitly, and a mutation test now
directly rejects a complete common-node mapping that is not `j = 4k`.
