# Upstream Rust Parity Ledger v2 Audit

Date: 2026-08-23  
Ledger: `docs/baselines/upstream-rust-parity-ledger.v2.yaml`  
Verifier: `tools/verify_upstream_rust_parity_ledger_v2.py`

This is an additive successor to the historical v1 ledger. It binds the
immutable evidence commit `fa15b90c916ee27090d6a68a38f75f481aec270f`, whose
parent/preparation candidate is `64b783f66d7e986d0975be5ac3946b453b15c4ed`
and whose candidate tree is
`0e11721f2bb5b564002820cc7a5aaab45e30ba3b`. The replay manifests are checked
against the immutable commit and against their report, aggregate, audit, and
candidate-source hashes. The verifier also rejects working-tree overlays,
missing report references, duplicate run identity, absolute-path leakage, and
promotion of an observation into upstream numeric parity.

The ledger intentionally keeps all fifteen migration rows open. AS-02 and
AS-03 are portable observations only; AS-04 through AS-06 remain externally
blocked. PB-01 and PB-02 remain payload-parity blocked. PB-03 is a
fixed-fixture scoped replay pass with branch scope still open, not a global
row close. PB-04 and PB-05 remain externally blocked. COM-02 and COM-04 are
archive-derived internal semantic observations only: the upstream object is
metadata-only and no numeric parity was executed. COM-01 and COM-03 have no
new evidence in this round. No row is completion, parity accepted, release
ready, or product-capability evidence.

Verification performed for this audit:

```text
python tools/verify_upstream_rust_parity_ledger_v2.py
python -m unittest tools.test_verify_upstream_rust_parity_ledger_v2
python tools/verify_upstream_rust_candidate_coverage_v2.py
```

The session-health, product-boundary, license-preflight, and source-map gates
are separate gates because this audit is itself included in the governance
inventory. Their current results are reported with the handoff that integrates
the successor.
