# P4B-02b119 Parameter List Run-Length Encoding Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b119 (consecutive-run compression on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_run_length_encode_v1.rs` in `sipi-ami-text`:
`run_length_encode_parameter_list_v1` run-length encodes the trimmed items of a validated
List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty): returns the list of `(item, run_length)` pairs of the consecutive equal
trimmed items, in order (raw byte equality, per the P4B-02b0 raw-byte binding). The sum of all
run lengths equals the item count; the number of pairs equals the number of runs. This is the
compression companion of 02b98 dedup (which removes duplicate runs) and of 02b107 distinct
counting. Fail-closed: a non-List value yields `NotAList`; a token that does not match the List
shape yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`,
kept defensive instead of panicking). An independent Python reference replicates the RLE rule
over 4 test cases.

## Result

- 6 Rust unit tests green (consecutive runs, all distinct, non-adjacent duplicates, single item,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (consecutive runs, all distinct, non-adjacent duplicates, non-list)
  driven through product runner `p4b_02b119_parameter_list_run_length_encode_runner`;
  independent Python reference matches 100% on run pairs and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b119_parameter_list_run_length_encode.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b119-parameter-list-run-length-encode-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b119-parameter-list-run-length-encode-stage.v1.yaml`; source map
  `p4b-02b119-mit-source-map.v1.yaml`.
- PLAN **P4B-02b119**; ledger note/gate P4B-02; coverage gates 288 -> 289.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Compresses list tokens on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
