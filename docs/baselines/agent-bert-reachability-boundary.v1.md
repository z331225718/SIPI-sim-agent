# Agent-BERT reachable Rust boundary

## Purpose

This record is the formalization boundary for the Agent-BERT lane.  It joins
three independently source-bound PyBERT compatibility leaves without turning
them into a claim of whole-PyBERT, product, or release parity.  PB-02 has an
immutable two-run archive record; PB-01 and PB-03 still require equivalent
archive-built records before this lane can be called complete.

The sole upstream reference is PyBERT commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`.  The direct executable is
`sipi-pybert-direct`; it is a real Rust binary, but remains outside the product
workspace under the explicit license boundary in
`crates/sipi-pybert-direct/NOTICE-PYBERT-LICENSE-BOUNDARY.md`.

## Reachable leaves

| Upstream command | Rust command | Evidence | Accepted scope |
| --- | --- | --- | --- |
| `pybert sim` | `sipi-pybert-direct sim` | `SOURCE-MAP-PB01-CLASS-PICKLE.md`; `legacy_runtime.rs` pinned-source class-pickle test | Development evidence: bound legacy NRZ configuration, source-loadable `PyBertData` graph, 22 numeric plot arrays, and `tx_out` object placeholder. Archive replay pending. |
| `pybert sim-native` | `sipi-pybert-direct sim-native` | `pb-02-pinned-native-source-corpus.v1.yaml` and its two archive-built reports | Every successful configuration in pinned `native/pybert-core/tests/simulation.rs`, plus its reachable additive-noise length rejection; full metadata, diagnostics, and all NPZ logical members. |
| `pybert sim-rust` | `sipi-pybert-direct sim-rust` | `SOURCE-MAP-PB03-PAYLOAD.md`; `pb03_payload.rs` pinned-source tests | Development evidence: full 150-member payload and metadata for the admitted legacy NRZ metallic-line configuration and its analytic-CTLE variant. Archive replay pending. |

The PB-02 formal candidate is `d2047cd1977f76aecb81c1674c031672bac5ff13`.
At the creation of this record, `git diff` from that candidate through
`d5ff90a6` is empty for `crates/sipi-pybert-direct/src`, `Cargo.toml`, and
`Cargo.lock`; the later commit only strengthens the source-compatible CTLE
metadata regression test.  The archive record is therefore still evidence for
the current runtime implementation, rather than a historical substitute for
it.

## Explicit non-admission

- `sim-auto` retains the pinned source-selection rule and fails closed when an
  external Python reference is required.  It is not a silent Rust fallback.
- `sim-compare` consumes an independently supplied reference JSON and never
  treats the Rust result as its own oracle.
- AMI, IBIS, TS4/GetWave and vendor DLL/model paths, GUI/Desktop, FastAPI,
  Redis/operational storage, and whole-Web family parity are not admitted.
- S-parameter files, local CTLE impulse and tap-limit extensions may have
  typed diagnostic handling in the lane, but are outside the source-compatible
  PB-02 corpus and are not parity claims.
- No byte identity for Python pickle streams, no whole-branch PyBERT parity,
  no root `sipi` product-route replacement, no distribution decision, and no
  release approval follows from this record.

## Verification entry points

```powershell
python tools\verify_pb_02_native_source_corpus.py `
  --prep-commit 11bb6eddb90def8b17163182ba850a3b60951988 `
  --record docs\baselines\pb-02-pinned-native-source-corpus.v1.yaml
python -m unittest tools.test_pb_02_native_source_corpus
cargo test --manifest-path crates\sipi-pybert-direct\Cargo.toml `
  --features pinned-python-tests --test legacy_runtime `
  pinned_pybert_sim_matches_the_complete_class_result_shape_and_numeric_tolerance -- --exact
cargo test --manifest-path crates\sipi-pybert-direct\Cargo.toml `
  --features pinned-python-tests --test pb03_payload
```
