# PB-01 legacy runtime leaf audit

## Scope

This audit records the first executable Rust leaf for the pinned PyBERT
`sim` workflow. It consumes the upstream YAML `PyBertCfg` object form,
including `!!python/object:pybert.configuration.PyBertCfg` and
`!!python/tuple` tags, and maps one explicit profile to the existing Rust
native core:

- NRZ, PRBS-7, 1000 bits, 32 samples/UI;
- the analytic Howard-Johnson metallic-line channel;
- cursor-only TX and RX FFE;
- CTLE bypass, DFE bypass, and no noise;
- canonical impulse/step/pulse arrays written under `.pybert_data`.

The Rust binary executes this path without importing or starting Python. The
result is a Python-readable pickle dictionary with schema
`sipi.pybert_data.v1`, not a class-compatible `pybert.results.PyBertData`
pickle. The Python command is retained only as an oracle for the replay
runner. Pinned inert serialization/UI keys are explicitly allowlisted;
every other unclassified top-level key fails closed before simulation.

The YAML event stream is checked before typed projection. The root must carry
exactly `!!python/object:pybert.configuration.PyBertCfg`; nested tags may only
be `!!python/tuple`. Untagged roots, alternate object tags, and every other
tag fail closed. Configuration input is capped at 1 MiB before YAML parsing;
nesting is capped at 64, RX FFE at 256 taps, and DFE tuner input at 64 taps.
`nbits*nspui`, RX FFE samples, projected output vectors, and result bytes use
checked arithmetic before the native simulation allocates. Total samples are
capped at 50,000,000 and `.pybert_data` materialization at 512 MiB. Existing
result files are compared by file identity, so the output cannot overwrite
the configuration through an equal path, symlink, or hard link.

The artifact schema is closed over the pinned 23 canonical item names.
`item_names` preserves that exact order, while the `arrays` mapping contains
exactly the same key set. Earlier implementation-only `ctle_out` and
`dfe_out` waveform keys are not canonical `PyBertData` items and are no
longer serialized. The Rust integration test and evidence verifier both run
the real fixture, decode the generated pickle, and reject missing or extra
array keys.

## Predecessor relationship

`docs/baselines/pb-01-direct-port.v1.yaml` remains the authoritative frozen
inventory of the full upstream command, defaults, errors, artifacts, and open
branches. This executable record supersedes only that predecessor's
boundary-only implementation status for the scoped NRZ metallic-line leaf;
it does not supersede or close the predecessor's broader branch inventory.

## Local replay observation

The authored fixture
`crates/sipi-pybert-direct/fixtures/pb-01-legacy-nrz.yaml` was run through
the pinned upstream `pybert sim` command and the Rust `sipi-pybert-direct sim`
command with identical bytes. The selected 12 arrays had equal lengths
(640 samples each) and passed the bound comparator tolerance
`1e-7 + 1e-6 * max(|oracle|, |candidate|, 1)`. The largest observed absolute
residual was approximately `9.814112272854558e-9` on `chnl_s`.

The local report was generated in a temporary directory from the working tree
before an owner commit, so it is deliberately **not** bound as immutable
evidence. `tools/run_pb_01_legacy_leaf_replay.py` is prepared to materialize
the candidate and pinned upstream from immutable archives, run both processes,
extract only the selected arrays, and emit a path-free report. The required
next gate is two independent replay reports from the owner-committed
candidate, with report SHA-256 and nonce binding.

## Non-claims and license

This slice does not implement imported S2P, `.pybert_cfg` pickle input,
AMI/IBIS models, random or periodic noise, adaptive DFE/Viterbi, jitter/eye/
bathtub analysis, or exact `PyBertData` class serialization. It does not
claim that this slice itself promotes P0. The implementation agent did not
directly edit product routing or shared governance files; the coordinating
batch may mechanically rebind those records after review. Upstream PyBERT is
BSD-3-Clause; the existing copied native Rust core retains its separate
MIT/BSD quarantine and this audit is not a license decision or redistribution
authorization.
