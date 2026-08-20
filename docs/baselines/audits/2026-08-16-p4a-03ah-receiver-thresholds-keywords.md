# P4A-03ah Typed IBIS Receiver Thresholds Complete Block Required Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ah (typed IBIS [Receiver Thresholds] block composite keywords core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `receiver_thresholds_keywords_v1.rs` in `sipi-ibis`: `TypedReceiverThresholdsBlockV1`
holds a validated `TypedReceiverThresholdsV1` (`thresholds`) and optional sensitivity voltage (`vsensitivity_v`).
`lift_receiver_thresholds_block_v1` validates inputs and returns `Result<TypedReceiverThresholdsBlockV1, ReceiverThresholdsKeywordsErrorV1>`.
Fail-closed: invalid receiver thresholds, non-finite values (`NonFiniteValue`), or negative sensitivity (`NegativeSensitivity`)
are strictly rejected. An independent Python reference recomputes composite block lifting rules over 3 test cases.

## Result

- 3 Rust unit tests green (policy fixed; valid receiver thresholds block; rejects negative sensitivity).
- Cross-check: 3 test cases (full receiver thresholds block, minimal receiver thresholds block, negative sensitivity)
  driven through product runner `p4a_03ah_receiver_thresholds_keywords_runner`; independent Python reference
  matches 100% on valid flags, receiver thresholds, sensitivity values, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ah_receiver_thresholds_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ah-receiver-thresholds-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ah-receiver-thresholds-keywords-stage.v1.yaml`; source map
  `p4a-03ah-mit-source-map.v1.yaml`.
- PLAN **P4A-03ah**; ledger note/gate P4A-03; coverage gates 159 -> 160.

## Scope / Non-Claims

- Not a full IBIS file parser; no receiver threshold simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
