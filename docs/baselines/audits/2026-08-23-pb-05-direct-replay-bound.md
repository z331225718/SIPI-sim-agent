# PB-05 Direct Replay Audit

Date: 2026-08-23  
Status: **open / blocked**

## Scope

- Leaf: `run_sim_compare_file` through the explicit `sim-compare` CLI.
- Fixed corpus: `crates/sipi-pybert-direct/fixtures/pb-03-legacy-nrz.yaml` (1170 bytes, SHA-256 `2d6b5ca8aad9e293e675afbbb34e032d335be7148bd0aef7340c41a3aabf605f`).
- Oracle: Py-bert-agent commit `5bf6d7ea0ace261aaeb611ffc1c267e160afe`, tree `5faef6bdb341d444ad65d82a11c0018b15805e24`.
- Candidate replay identity: commit `eb2a13f53fb54f09956a0ec8196fad9bc3da220f`, tree `cba5db1a594115f1859c23b67d20f4da5f356f53`.

## Payload Evidence

Both independent replays exercised the no-reference fail-closed branch. The candidate returned a typed `reference_unavailable` error with `pybert.engine-compare.v1` diagnostics: `reason: not_evaluated`, `reference_required: external_python_reference_required`, and `status_only_comparison: false`. No same-crate Rust reference was generated and no parity result was emitted. The pinned Python oracle still produced an actual array and metadata comparison, which remains separate evidence and is not substituted for the missing independent candidate reference. The candidate archive was overlaid only with the content-addressed PB direct-port lane.

- `pb-05-direct-replay-bound-run-13.v1.json`: `1ab177f67ed18ad950304312289b5668ba131ec78baaf8169b01ada54d4576fd` (nonce `3a8a8e8b576740fc82aebeaba2841e59`)
- `pb-05-direct-replay-bound-run-14.v1.json`: `e0a8ccbba3bf199069214c5a474150b984a245b5b19f25fcd9b18f9f47711af7` (nonce `ad9bad897de14ac3b0f625c97668991b`)
- `pb-05-direct-replay-bound-aggregate.v1.json`: `82403db6b377e02a88ef783145e05b2fa8aaaf6098d8047f9a449c96c1bd5bd4`

## Gates and Mutations

Rust tests mutate waveform and scalar payloads and require comparison failure; they also
exercise strict float64 decision names without integer-value inference, explicit bool /
int64 / float64 result-adapter arrays, nested two-dimensional shapes, and actual NPY
dtype headers under Deflate compression. Malformed external reference JSON is rejected
before use. The replay verifier requires `status_only_comparison: false`, both
independent reports, exact source/toolchain identity, and preserves the explicit
`not_evaluated`/`external_python_reference_required` contract when no independent
reference is supplied. The external result-adapter shape is accepted only after typed
output validation. Mutating comparison status, array/metric summaries, report hashes,
or closure claims is fail-closed.

No compare parity, row closure, release approval, or license decision is claimed. The current evidence binds the content-addressed source overlay and exercises the independent-reference-required fail-closed path; the pinned Python result-adapter payload gate remains blocked. External AMI/IBIS DLL branches and any unprojectable upstream controls remain typed fail-closed blockers.
