# T08 P3C Exact Impulse Replay

## Result

T08 is recorded as a structured blocked external-input observation. The exact
selected S4P was present in external custody at 1,834,156 bytes with SHA-256
`25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47`.

The exact ADS canonical little-endian binary64 triple payload was not found.
The required identity remains 1,177,344 bytes and SHA-256
`5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726`.
The search found zero exact logical-name matches and zero exact-length matches
in the recorded external search scope. No bytes were reconstructed from the
hash, and no historical summary or report was substituted.

A release `sipi` executable was built from clean archive commit
`805ebb6bbaf588dec08685be4eb78a8ce2fff563` with the pinned Rust toolchain,
`--release --locked --offline`, and an external target. Its hash-only identity
is 3,975,168 bytes and SHA-256
`11c4ff6c81a4420ed95317b211d474c49ce55ab8224cf0d9e6a44efb50156c02`.

The T07 observer was invoked with the exact external S4P, expected external
ADS payload name, and external release executable. It rejected at
`external_input_preflight` before materializing the replay runner, so no
candidate/reference payload digest and no strict-index NRMSE exist. They are
recorded as `null` in the evidence; the rejection is
`t08_external_ads_reference_exact_bytes_missing`.

The same ignored Rust runner was then exercised from a fresh clean archive and
external target with the exact S4P and missing reference path. It rejected at
`reference_identity` with `reference_open`; no report was written.

## Boundaries

No ADS simulator, rational fit, alignment/delay or output-strobe search, gain,
DC or polarity transform, parameter sweep, or tolerance relaxation was used.
No S4P, ADS payload, executable, candidate bytes, reference bytes, waveform
arrays, or absolute paths are retained in the repository.

Evidence: `docs/baselines/p3c-exact-impulse-current-replay-evidence.v1.yaml`.
Verifier: `tools/verify_p3c_exact_impulse_current_replay_evidence.py`.
Mutation tests: `tools/test_verify_p3c_exact_impulse_current_replay_evidence.py`
(`6` tests passing), plus the T07 preparation verifier/tests (`4` tests
passing). `git diff --check` passes for the T08 files.
