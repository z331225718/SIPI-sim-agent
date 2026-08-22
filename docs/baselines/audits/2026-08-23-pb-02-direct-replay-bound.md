# PB-02 immutable direct-replay evidence

Date: 2026-08-23

This audit records the narrow PB-02 fresh replay observation for the pinned
PyBERT native numerical core. The candidate is the immutable SIPI commit
`ec94468772182e17cf7b935ab2d7c0437ea7692e` with tree
`5e0de1ac29f64f935339a4d5eed09fc1b43c6591`. The upstream oracle is the pinned
PyBERT commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe` with tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`.

The replay runner materialized both commits from immutable archives into
independent source, build, and output roots. It ran one upstream oracle and
one product replay per report, and the two reports were generated in separate
runs. The runner generates an independent 256-bit nonce for every run; the
nonce is not derived from the caller-supplied run id. The aggregate accepts
only distinct report paths, run ids, fresh nonces, and complete report hashes.

The two bound reports are:

* `docs/baselines/pb-02-direct-replay-bound-run-01.v1.json`
  (`pb-02-bound-20260823-01`), SHA-256
  `3899be3eec0c561fe0526d71dd7f0c78f1d9e872334595fef7ebcdfddc149096`.
* `docs/baselines/pb-02-direct-replay-bound-run-02.v1.json`
  (`pb-02-bound-20260823-02`), SHA-256
  `737b6a042f4251e380a3e66cf31089a3b28ba16e67c459ea7c4ab4915e8c3a6d`.

The aggregate is
`docs/baselines/pb-02-direct-replay-bound-aggregate.v1.json`, SHA-256
`ada25b3ea02cf98f7290cbea77192f46bd8f8043b4d3b7fa44cf8915d9197ab2`.
The fixture is
`crates/sipi-pybert-direct/fixtures/pb-02-nrz.json`, 1,245 bytes, SHA-256
`5bcd0b905f8a7f0ec5e2b7c3761a998e9553ac24a71b54f8b0d4e8e84261ea13`.

Both reports have status `passed`, zero oracle/product exits, and equal
logical float64 array members. The bound logical-array digest is
`5090a1478ea6e985342d8500c6220cdde5c7fa2c416abbdeb595dcdc380c275a`.
This is an exact numerical-core result for the one explicit PB-02 fixture,
not a claim over uncovered `SimulationInputV1` branches.

The runner is
`tools/run_pb_02_direct_replay.py`, SHA-256
`6c6a777a2e616e5778eaa7f396ba173791c67381d81cf00b473f87efb2553d0f`.
The aggregate verifier input is produced by
`tools/aggregate_pb_02_direct_replay.py`, SHA-256
`04a2d35fd7f1df1fc3728c0918fc752980b0e7c718eedf5a0285ff0bae24043a`.
The report toolchain identity is path-free and exact: cargo and rustc are
identified by executable basename, file SHA-256, successful version-output
SHA-256, and redacted path; uv is identified the same way. No host absolute
path is part of the report.

The following remain outside this parity claim: SIPI strict JSON admission,
artifact writing, uncompressed NPZ policy, output-directory symlink rejection,
and other wrapper policies. Those are SIPI-owned non-parity behavior and are
not asserted to be PyBERT sim-native semantics. This evidence is not a
license decision, release approval, or product-capability admission. The
PyBERT native-core MIT/BSD notice conflict remains quarantined and release
blocked.
