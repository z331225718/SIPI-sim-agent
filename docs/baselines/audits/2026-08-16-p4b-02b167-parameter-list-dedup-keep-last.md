# P4B-02b167 Parameter List Dedup Keep-Last Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b167 (value-level keep-last dedup on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_dedup_keep_last_v1.rs` in `sipi-ami-text`:
`parameter_list_dedup_keep_last_v1` returns the canonical list token of a validated
List-typed `AmiParameterValueV1` value under the P4B-02b1 list rule (`(item, item, ...)`,
items trimmed, non-empty) keeping only the last occurrence of each distinct trimmed item (raw
byte equality, per the P4B-02b0 raw-byte binding), ordered by last occurrence in the value's
trimmed item sequence. Every item appears exactly once in the result; the result order is the
last-occurrence order (distinct from the 02b98 first-occurrence order in general). This is
the keep-last companion of 02b98 parameter-list-dedup and of 02b107 distinct-count (the
result item count equals the distinct count). Fail-closed: the value not declared List yields
`NotAList`; the token not matching the List shape yields `MalformedList` (unreachable for
values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the keep-last rule over 4 test cases.

## Result

- 6 Rust unit tests green (keep-last order, all distinct unchanged, single item, adjacent
  duplicates, spacing canonicalized, non-list).
- Cross-check: 4 test cases (keep-last order, all distinct, adjacent duplicates, non-list)
  driven through product runner `p4b_02b167_parameter_list_dedup_keep_last_runner`;
  independent Python reference matches 100% on canonical tokens and error keys; 4/4
  product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b167_parameter_list_dedup_keep_last.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b167-parameter-list-dedup-keep-last-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b167-parameter-list-dedup-keep-last-stage.v1.yaml`; source map
  `p4b-02b167-mit-source-map.v1.yaml`.
- PLAN **P4B-02b167**; ledger note/gate P4B-02; coverage gates 336 -> 337.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes keep-last dedup on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
