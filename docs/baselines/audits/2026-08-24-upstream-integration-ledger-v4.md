# Upstream Integration Ledger v4 Audit

Schema: `sipi.upstream-integration-ledger.v4`; status:
`current_clean_candidate_open_no_release`.

This additive successor is a governance view over the fifteen pinned upstream
workflow rows. It does not rewrite v1-v3 ledgers and does not promote any row
to release or global parity.

Candidate binding: commit `e1a9ca876c57bdf196974ae7b640e5ae73b6f18c`, tree
`ab34cc91ff482fa7494f0b3c36842345ad46e519`, clean archive SHA-256
`d4c576ddf6ded979896c47dca8142aed7c57555ac1977edc924088e7bf939311`.

The four row fields are intentionally orthogonal:

- `integration_disposition` describes whether the candidate is a direct Rust
  port, retained external runtime, external asset, oracle-only observation, or
  explicit fail-closed exclusion.
- `runtime_availability` records portable versus caller-owned solver/asset
  requirements and is not a parity claim.
- `parity_evidence` records the narrow evidence actually observed. Scoped
  numeric or fixture observations remain scoped; external solver observations
  do not close a workflow.
- `release_state` is `open_no_release` or `scoped_only_no_release` for every
  row in this successor.

Agent-Spice AS-05 and AS-06 have direct Rust control/artifact branches, but
their complete workflows remain externally runtime-bound. Their disposition is
therefore direct Rust port while workflow evidence remains external-blocked.
AS-01 through AS-03 retain numeric mismatch-open evidence. PB-03 is recorded
as a direct Rust port while retaining its oracle/not-run scoped evidence; this
is not a parity closure. COM-01 through COM-04 likewise have direct Rust
candidate branches, while their historical, timeout, and scoped evidence
remains non-parity evidence.

The PB-02 metallic-grid manifest and COM TD crosstalk-stage replay manifest are
mechanically hash-bound as supplemental scoped observations only. The COM TD
manifest is explicitly environment-local and scoped, not formal or portable.
Neither supplement promotes parity or release state.

Pinned source authorities are Agent-Spice commit
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5` / tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402`, PyBERT commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe` / tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`, and Agent-COM commit
`5272ffe74702cd585054d975559b06f8afae7b6e` / tree
`7094ab6e84989b218730c52432c70da10261f8ea`. License and source provenance is
bound by the documents listed in the ledger.

Audit conclusion: 15 rows remain open, 0 release-ready, 0 globally parity
accepted, and no external runtime is represented as portable parity.
