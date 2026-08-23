# Upstream Rust Parity Ledger v3 Audit

Date: 2026-08-23  
Ledger: `docs/baselines/upstream-rust-parity-ledger.v3.yaml`  
Verifier: `tools/verify_upstream_rust_parity_ledger_v3.py`

This is an additive successor to the retained v1 and v2 ledgers. It binds
evidence commit `025ef934ff79e1231bd6f80e2be3d12207e814d6`, tree
`bc14798cae8d6a912881264044dae3f272aa338a`, and its clean archive. The
candidate preparation parent is `9914a23dc747d94405f2fed9227538ae7aea8629`;
the ancestry contains the PyBERT fix `d3154093` and the Agent-Spice fix
`9914a23`.

The ledger binds the current AS-01/02/03 numeric-mismatch evidence, the
current PB-01/02 fixture/workflow payload evidence and PB-03 eighteen-branch
Rust-only probe, and the hardened COM-02/04 upstream-only portable-leaf
observation. AS-04/05/06 remain externally blocked. PB-04/05 remain
externally blocked. COM-01/03 are historical-only in this successor.

All fifteen completion values remain open and product capability remains
`not_claimed`. AS-01/02/03 remain numeric mismatch open. PB-01/02 are only
fixed-fixture/workflow scoped parity passes and do not close their rows. PB-03
records Rust branch coverage only with `oracle: not_run`. COM-02/04 observed
portable upstream leaves, but the full entrypoint timed out and no
candidate-versus-upstream parity was executed. No row is release-ready or
globally accepted.

The verifier mechanically checks the predecessor, evidence commit/tree/archive,
candidate and upstream source identities, current manifests and audit hashes,
clean-archive/no-overlay markers, report custody where present, governance
artifact hashes, row count, row states, scope boundaries, and promotion
claims. Mutation tests cover row omission, source/archive drift, manifest and
audit drift, historical rebinding, PB globalisation, COM parity promotion,
and completion/product-capability promotion.

Verification commands:

```text
python -B tools/verify_upstream_rust_parity_ledger_v3.py
python -B -m unittest tools.test_verify_upstream_rust_parity_ledger_v3
python -B tools/verify_upstream_rust_candidate_coverage_v2.py
```

The session-health, product-boundary, license-preflight, and source-map gates
remain separate governance checks. This audit does not authorize a release or
promote any product capability.
