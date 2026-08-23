# PB-04 Direct Replay Audit

Date: 2026-08-23  
Status: **open / blocked**

## Scope

- Leaf: `run_sim_auto_file` through the explicit `sim-auto` CLI.
- Fixed corpus: `crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml` (1170 bytes, SHA-256 `2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f`).
- Oracle: Py-bert-agent commit `5bf6d7ea0ace261aaeb611ffc1c267e160afe`, tree `5faef6bdb341d444ad65d82a11c0018b15805e24`.
- Candidate replay identity: commit `eb2a13f53fb54f09956a0ec8196fad9bc3da220f`, tree `cba5db1a594115f1859c23b67d20f4da5f356f53`.

## Selection Evidence

Both independent oracle runs returned `pybert.cli-auto-result.v1` with the real Python selection payload: requested `auto`, selected `python`, fallback reason `native Web result contract parity is incomplete`, and parity gate status `blocked`. The candidate archive was materialized at the pinned candidate commit and overlaid only with the content-addressed PB direct-port lane. Its Rust-only `sim-auto` path now preserves that selection and fails closed with `implementation: external_python_reference_required`; it does not publish a substituted Rust artifact. The candidate/oracle payload gate remains blocked because the external Python backend is unavailable to the Rust lane; unprojectable external controls remain typed fail-closed errors.

- `pb-04-direct-replay-bound-run-13.v1.json`: `0be330e69546bec90c70a78d0671e97e900c4ac6a8f76f16d2cfd2c9a8ce6f41` (nonce `5c49d91114414fd284d64b626393e986`)
- `pb-04-direct-replay-bound-run-14.v1.json`: `c81b86611032bfafd2869158a53d3c361df7250a277266a8522e63430ba7e1b4` (nonce `cabfc9b805ca470195a855d5993e2fb4`)
- `pb-04-direct-replay-bound-aggregate.v1.json`: `7795c09c39b4592ac8f9b985b40ab70a5e87ba04c453ffbee97601a76e5d25be`

## Gates and Mutations

Selection semantics are verified from candidate and oracle payload fields, not exit status.
The admitted portable projection also carries the legacy spectral threshold through
the independent reference path, while the candidate/oracle gate remains explicit.
The aggregate and verifier require distinct reports/nonces and reject any attempt to
erase the blocked gate, relabel the independent Rust reference as Python parity, or
omit the implementation marker. Rust tests cover portable artifact publication,
external projection failure, and result-adapter selection payloads. Mutating selected
engine, implementation, parity-gate status, report digest, or global/release claims
remains fail-closed.

No auto promotion or row closure is claimed. A future candidate replay must prove the selected engine and fallback behavior against the same pinned upstream contract before any promotion discussion.
