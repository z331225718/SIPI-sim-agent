# PB statistical-eye golden source map

This is a bounded, release-external verification of the existing reachable
Rust statistical-eye leaf. It does not import the upstream JSON corpus into
the SIPI package, expose another public API, or claim Web/GUI/AMI parity.

## Pinned source

The oracle is PyBERT commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`, under its BSD-3-Clause `LICENSE`.
The exact source objects are:

| Pinned path | Git object | Role |
| --- | --- | --- |
| `tests/golden/rust_migration/statistical_eye` | tree `4de363247ca45a399d4dd0e69e8d7e71c4f2654e` | Eight existing NRZ statistical-eye configuration/result cases. The test requires this exact tree and a clean source/corpus checkout. |
| `native/pybert-core/tests/statistical_eye.rs` | blob `ba2a241b0b7de9db676a22e6e4865fba5f537661` | Existing native-core behavioral test intent. |
| `native/pybert-core/src/statistical_eye.rs` | blob `e2f9dea5d8734903514720d93b1a0ce2079a61ee` | Existing direct-port lineage for `src/statistical_eye.rs`; this slice does not copy or alter it. |
| `LICENSE` | blob `64d198ba43675ede5fbdef1ec918a63954951640` | BSD-3-Clause, David Banas copyright notice. |

## Verification boundary

`tests/pb_statistical_eye_goldens.rs` parses each source-owned JSON at test
time, passes its complete typed input into `calculate_statistical_eye`, and
compares all six published scalar results with the pinned native integration
envelope: `3e-9 V` for voltage scalars and `1e-9 ps` for widths. The eight configurations cover cursor-only, pre/post-cursor ISI,
vertical noise, receiver horizontal jitter, combined RX jitter/noise, and a
slew-limited response.

This is only a direct reachable-leaf comparison. It excludes PAM4 and
DuoBinary statistical eyes, TX edge jitter, full Web result serialization,
S2P/AMI/IBIS/GetWave, external assets, product promotion, and release claims.
