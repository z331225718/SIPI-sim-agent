# PB-03 Direct Replay Audit

Date: 2026-08-23  
Status: **open / blocked**

## Scope

- Leaf: `run_sim_rust_file` through the explicit `sim-rust` CLI.
- Fixed corpus: `crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml` (1170 bytes, SHA-256 `2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f`).
- Oracle: Py-bert-agent commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree `5faef6bdb341d444ad65d82a11c0018b15805e24`.
- Candidate replay identity: commit `eb2a13f53fb54f09956a0ec8196fad9bc3da220f`, tree `cba5db1a594115f1859c23b67d20f4da5f356f53`.

## Evidence

Two independent replays were executed with distinct run IDs and nonces. Each run materialized the immutable candidate archive, then overlaid only the PB direct-port crate and fixture from the working tree with per-file SHA-256 records. Both candidate and pinned oracle `sim-rust` processes passed and their 44 stable native array payload digests matched exactly; the aggregate passed the bounded fixture gate while the row remains open for branch-complete promotion.

- `pb-03-direct-replay-bound-run-13.v1.json`: `b8c966b969ec144f797830efffadb9001c6aacd2ae0ae1d1af12366c0c318dc5` (nonce `7c5cd1b603ff42508b9ff584bec9d64e`)
- `pb-03-direct-replay-bound-run-14.v1.json`: `20a7202b1d3cecf26c5a66ed33d2b7417449e1a6f697061cf3c301e0a16a21bc` (nonce `59f4d54ce3ed4f648b0b0f759bf373cc`)
- `pb-03-direct-replay-bound-aggregate.v1.json`: `6537353959d94c3b28ec8e9bcd404dd881bf409e2a73f1b840532c72345067c5`

## Gates and Mutations

The Rust tests cover strict projection, the non-default legacy `thresh` flow into
`analysis.jitter_rel_thresh`, artifact publication, malformed reference rejection,
and waveform/scalar payload mutations. The replay aggregate requires two distinct
reports, identical toolchain/source identity, and candidate/oracle payload equality;
a blocked candidate cannot be upgraded by the verifier. Any report digest, run ID,
nonce, source identity, or status mutation is fail-closed.

No row closure, release approval, or license decision is implied. Remaining work is a preparation-commit-bound replay plus coverage for all legacy branches and external AMI/IBIS/DLL boundaries, followed by the same verifier and mutation suite.
