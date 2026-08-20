# P4B-02b183 Parameter List Run Boundaries Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b183 (value-level run boundaries on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_run_boundaries_v1.rs` in `sipi-ami-text`:
`parameter_list_run_boundaries_v1` returns the `(start_index, end_index)` boundary pairs of
every maximal run of equal adjacent trimmed items of a validated List-typed
`AmiParameterValueV1` value under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty), both indices 0-based and inclusive, in run order (raw byte equality, per the
P4B-02b0 raw-byte binding). The list is non-empty by rule so at least one run exists (a
single-item list yields the zero-extent pair `(0, 0)`); the pair count equals the 02b168 run
count, each pair spans the same consecutive-equal decomposition as 02b119 run-length-encode,
and the first run always starts at 0 while the last run always ends at `item_count - 1`. This
is the boundary companion of 02b119 run-length-encode (which returns `(item, run_length)`),
of 02b171 longest-run-start-index (whose result is the start index of the maximum-extent pair
in this slice's output), and of 02b168 run-count (the pair count). Fail-closed: the value not
declared List yields `NotAList`; the token not matching the List shape yields `MalformedList`
(unreachable for values built via `AmiParameterValueV1::try_new`, kept defensive instead of
panicking). An independent Python reference replicates the rule over 4 test cases, comparing
the `(start, end)` arrays for bit-exact equality per run.

## Result

- 6 Rust unit tests green (mixed runs, all equal single run, all distinct singleton runs,
  single item zero extent, spacing canonicalized, non-list).
- Cross-check: 4 test cases (mixed, all equal, all distinct, non-list) driven through product
  runner `p4b_02b183_parameter_list_run_boundaries_runner`; independent Python reference
  matches 100% on run-boundary arrays and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b183_parameter_list_run_boundaries.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b183-parameter-list-run-boundaries-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b183-parameter-list-run-boundaries-stage.v1.yaml`; source map
  `p4b-02b183-mit-source-map.v1.yaml`.
- PLAN **P4B-02b183**; ledger note/gate P4B-02; coverage gates 352 -> 353.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes run boundaries on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
