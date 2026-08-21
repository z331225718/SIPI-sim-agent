# P3C selected high-loss current-head DFT

## Scope

This record covers one no-decision slice of P3C-03: rebinding the existing
strict residual DFT observer to the current clean product archive. It does not
select a source, receiver, causality, interpolation, delay, fit, tolerance, or
acceptance policy.

## Original-project custody

- ADS selected S4P: 1,834,156 bytes, SHA-256
  `25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47`.
- ADS canonical triple payload: 1,177,344 bytes, SHA-256
  `5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726`.
- Fresh external report: 3,605 bytes, SHA-256
  `24256d63b269aec2e130903dc88efc0a928fd3c49aa99241506afe6edd21ff85`;
  report bytes and waveform data were not retained in the repository.
- Product clean archive: commit
  `97b0f271abcb7df02a3a9b259c4dafee86f3a783`, tree
  `7ae439ec366e30e050931ecb1f18f360e66540c1`.
- The external DFT runner source path is
  `crates/sipi-p3c/tests/p3c_external_ads_selected_highloss_residual_dft_runner.rs`.

Two fresh runs used distinct sealed source manifests and matched on the
reference RX payload, candidate prefix, fixed DFT digests, Parseval check, and
all four band summaries. The strict third-period NRMSE is
`0x3f9dd184cd51df98` (`0.02911956313297956`); the frequency value differs by
one ULP (`0x3f9dd184cd51df99`) and the maximum residual-energy bin is 65.

## Evidence binding

The current-head evidence and fail-closed verifier are:

- `docs/baselines/p3c-selected-highloss-residual-dft-v2-current-head-observation-evidence.v1.yaml`
- `tools/verify_p3c_selected_highloss_residual_dft_v2_current_head_observation_evidence.py`

The verifier binds the exact S4P/payload/reference/candidate/spectrum digests,
all four fixed band bit patterns, clean archive tree, authority, blockers, and
non-claims; mutation tests cover each of those identity and gate surfaces.

## Verification

- `cargo test --locked --offline -p sipi-compare selected_highloss`: 6 passed.
- `python -B tools/verify_p3c_selected_highloss_residual_dft_v2_current_head_observation_evidence.py`: valid, not accepted.
- `python -B -m unittest tools/test_verify_p3c_selected_highloss_residual_dft_v2_current_head_observation_evidence.py`: 1 passed.
- The two-fresh external DFT runner passed against the recorded clean archive; its report bytes and source inventory remain unchanged.

## Remaining gates

The fixed 1% waveform gate remains false. This observation does not identify or
exclude the physical root cause, does not establish ADS/COM parity, and does
not satisfy receiver, statistical eye contour, exact replay identity, or
release requirements; product self-tests remain non-oracle.
