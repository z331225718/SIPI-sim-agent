# P3A-16 Matched S2P CLI Current-Evidence Rebinding v5

P3A-16 replays the selected external-only `channel_16ghz_3db.s2p` profile
against clean-archive product commit
`b5935dd2816987135343e0346eece68c4863299a`. It is an evidence rebinding
only: the parser, resolver, CLI semantics, tolerance, and release state do
not change.

The oracle-only comparator built `sipi` with locked offline Cargo resolution,
materialized the external Git object twice in fresh temporary custody, and
compared the independently observed 400-sample kernel with `sipi channel run`.
The external report remains outside this repository; its SHA-256 is
`ab1c50f451a307415d073ca7b019fc7be957366d076066bb964bedc68963f47a`.
It contains no tracked S2P bytes, waveform data, or absolute paths.

The replay passed the frozen pointwise gate: maximum absolute error was
`9.792141327392284e-15`; maximum normalized error ratio was
`7.789698985496182e-6`. The v5 evidence binds the five channel CLI product
trees, `Cargo.lock`, executable identity, and the report hash. The earlier v4
record remains historical and must still fail the exact
`evidence_product_source_drift` gate. Its v2 core record is retained only as a
hash-bound historical lineage anchor; v5's current claim comes from the new
external observer and CLI replay.

The channel publication row remains `specified` and `external_oracle: false`.
It restores only selected matched-S21 periodic-kernel observed evidence; caller
input remains unattested and this is not general Touchstone, Link/eye/BER,
artifact, or release evidence.

## Verification

- `python -B tools/verify_channel_s2p_matched_cli_current_external_compare_evidence_v4.py`
  returned the expected `evidence_product_source_drift` rejection.
- `python -B tools/verify_channel_s2p_matched_cli_current_external_compare_evidence_v5.py --report <external report>` passed.
- `python -B -m unittest tools.test_verify_channel_s2p_matched_cli_current_external_compare_evidence` passed: 8 tests.
- `python -B -m unittest tools.test_verify_release_capability_publication` passed: 23 tests, including the real product command-manifest check.

## Independent Audit

The existing Orca OMP reviewer terminal
`term_fa7831f5-ec22-4b3d-8737-25a919226b8b` performed a read-only audit of the
staged P3A-16 scope. Result: **0 High / 0 Critical findings; no mandatory
fixes**. The reviewer confirmed the historical v2/v4 boundaries, v5 custody
and hash binding, the limited publication semantics, and that neither
`uv.lock` nor the user's uncommitted Rust changes were touched.
