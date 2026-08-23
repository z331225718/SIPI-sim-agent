# PB-03 Python Oracle Matrix Audit

This additive audit binds PB-03 to two clean archive replays from candidate
`884b430bee61d365793a3810beaeb76f58bee25c` and pinned PyBERT
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe`. The candidate archive SHA is
`1b19a54bd4a3517a698a55b85b316e1e85658b611b3674881930303df1fb56dd`; the
upstream archive SHA is `e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25`.

The oracle command was the upstream `PythonSimulationBackend`, not
`sim-rust`, and each report records the source-field bindings used to create
the compressed NumPy payload. The candidate and oracle were materialized
from separate immutable archives; the inline S2P fixtures are content
addressed by the corpus hash and are not source overlays.

## Replay Results

Two fresh runs were executed with distinct run IDs and nonces:

| Case | Result | Evidence |
| --- | --- | --- |
| NRZ base | passed | 13 arrays compared |
| PAM4 noise/DFE | passed | 13 arrays compared |
| Duo-binary noise/DFE | blocked | immutable candidate `884b430bee61d365793a3810beaeb76f58bee25c` exits before artifact emission in jitter crossing analysis |
| PAM4 Viterbi ISI | blocked | state-path and symbol telemetry differ |
| PAM4 Viterbi FEC | blocked | pinned Python source raises its decoder binding error |
| NRZ S2P | blocked | both payloads exist but channel/receiver arrays differ |
| NRZ analytic CTLE | blocked | CTLE and dependent receiver arrays differ |

The matrix is intentionally open. `global_branch_parity`, promotion, and
release approval remain false. AMI/IBIS/DLL/GetWave and exact class-pickle
restoration remain separately blocked. The aggregate also binds the additive
18-branch manifest identity digest and this audit SHA; report entries include
their actual path, SHA, run ID, and fresh nonce.

## Bound Artifacts

- Corpus: `docs/baselines/pb-03-python-oracle-corpus-d3154093.v1.json`, SHA256 `1b20fb24beec541067d58238efa8aec568cb9e7a181cdf23a41e973da3defdc7`.
- Replay 1: `docs/baselines/pb-03-python-oracle-matrix-d315-run-01.v1.json`, SHA256 `2f9a9c206cb8c249045dd5617f6c179a206466d01fbaa00fdeb6a4d7f08ede54`.
- Replay 2: `docs/baselines/pb-03-python-oracle-matrix-d315-run-02.v1.json`, SHA256 `63d470294e0b47e06ee186f31ed060f948a95db6f345b98b41972346eac15af4`.
- Aggregate: `docs/baselines/pb-03-python-oracle-matrix-d315-aggregate.v1.json`, SHA256 bound by the manifest and aggregate verifier.
- Verifier: `tools/verify_pb_03_python_oracle_matrix.py`.
- Mutation tests: `tools/test_verify_pb_03_python_oracle_matrix.py`.

Focused mutation tests passed (`8` tests). No historical PB-03 v1/v2 evidence
was rewritten.
