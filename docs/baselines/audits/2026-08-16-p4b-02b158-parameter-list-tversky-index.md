# P4B-02b158 Parameter List Tversky Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b158 (parameterized set-similarity on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_tversky_index_v1.rs` in `sipi-ami-text`:
`list_tversky_index_v1` computes the Tversky index of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns
`|A & B| / (|A & B| + alpha * |A \ B| + beta * |B \ A|)` over the distinct trimmed item
sets of the two values (raw byte equality, per the P4B-02b0 raw-byte binding) with
non-negative parameters alpha and beta, formatted as f64. With alpha = beta = 1 it reduces to
the 02b154 Jaccard index; alpha = beta = 1/2 gives the 02b155 Dice index; alpha = beta = 0
gives 1. This is the parameterized companion of 02b154 Jaccard, 02b155 Dice, and 02b156
overlap coefficient. Fail-closed: either value not declared List yields `NotAList`; either
token not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); a negative alpha or
beta yields `InvalidParameters`. An independent Python reference replicates the Tversky rule
over 4 test cases.

## Result

- 6 Rust unit tests green (jaccard-parameter equivalence, dice-parameter equivalence,
  zero-parameters one, asymmetric parameters, negative parameter, non-list).
- Cross-check: 4 test cases (jaccard parameters, asymmetric parameters, disjoint,
  negative parameter) driven through product runner
  `p4b_02b158_parameter_list_tversky_index_runner`; independent Python reference matches
  100% on 12-decimal index strings and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b158_parameter_list_tversky_index.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b158-parameter-list-tversky-index-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b158-parameter-list-tversky-index-stage.v1.yaml`; source map
  `p4b-02b158-mit-source-map.v1.yaml`.
- PLAN **P4B-02b158**; ledger note/gate P4B-02; coverage gates 327 -> 328.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes the Tversky index on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
