# P5-04x Search-Loop Helpers Explicit Cross-Check - Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-04 hardening slice 04x (explicit cross-check of search-loop helpers)
- Status: delivered. Explicitly binds the three pure-numeric search-loop
  helpers that feed the composite non-MMSE loop (P5-04t), which was
  previously verified only implicitly via the bit-exact fom check.

## Method

Write independent reference implementations for rectangular_pulse_response_v1
(zero-state samples_per_ui-window running sum, NO averaging), peak_window
(first argmax then [peak-20spu, peak+20spu+1) clamped), and shift_matrix
(circular column roll by (tap-precursor)*spu). Run the product runner on a
fixed 200-point Gaussian pulse (spu=4, taps=3, precursor=1) and compare
pulse / window / matrix elementwise against the references.

## Result

- 1/1 matched_hash_bound: pulse, window=[2,163], and 3-column matrix all
  match the independent references elementwise.
- Initial reference for the rectangular pulse divided by spu (averaging);
  corrected after reading the product: it is a running sum with no
  division. Documented, not masked.

## Binding

- Verifier verify_p5_04x_search_helpers.py + 6 tests; crosscheck evidence
  docs/baselines/p5-04t-search-helpers-crosscheck-evidence.v1.yaml.
- Charter p5-04x-search-helpers-verification.v1.yaml; source map
  p5-04x-mit-source-map.v1.yaml.
- PLAN **P5-04x** (hardening slice of completed P5-04; no new open gate).
