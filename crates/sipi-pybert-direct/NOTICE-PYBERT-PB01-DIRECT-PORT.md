# PB-01 direct-port notice

This file covers the additive PB-01 legacy-simulation projection in
`src/legacy_runtime.rs`, the PB-01 fixture, and the bounded pickle/YAML
decoders.
It does not change the separate PB-02 native-core license boundary recorded in
`NOTICE-PYBERT-LICENSE-BOUNDARY.md`.

## Upstream reference

The reference behavior is read from the pinned PyBERT repository at commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe` (tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`). The repository root declares
BSD-3-Clause. The exact root `LICENSE` bytes have SHA-256
`4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1`.

The migrated module is a mechanical projection of the pinned `sim` command's
legacy YAML and `.pybert_cfg` state fields, default result suffix, native
metallic-line leaf, and canonical `PyBertData` item names. The pickle input
path is a bounded data-only decode of a `PyBertCfg` state mapping; it does not
restore Python globals or execute a Python runtime. The module is not a copy
of the upstream Python source, and it does not include the upstream pickle
payload or runtime assets.

## Dependency notices

The Rust YAML and pickle codecs are third-party crates with their own licenses:

- `serde_yaml 0.9.34+deprecated`: MIT OR Apache-2.0.
- `serde-pickle 1.2.0`: MIT OR Apache-2.0.
- `same-file 1.0.6`: MIT OR Unlicense.
- `yaml-rust2 0.10.x`: MIT OR Apache-2.0.

Their license texts remain the responsibility of the normal dependency
license inventory. This notice is not a redistribution authorization and does
not resolve the separate MIT/BSD metadata conflict for the copied native core.
The crate remains quarantined and `publish = false` until the owner resolves
all source and license boundaries.
