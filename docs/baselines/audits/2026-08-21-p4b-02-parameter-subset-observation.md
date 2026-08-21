# P4B-02 parameter subset observation

## Decision

The selected ADS TX/RX text profiles now support a narrow external-asset
oracle status for **host-forwarded typed parameter-subset identity**. This is
not a vendor-runtime oracle and does not change the P4B-08/P4B-09 rights,
dynamic-closure, or security-sandbox blockers.

## Fresh observation

The observer performed two bounded reads of each exact external `.ami` text,
required byte equality between the reads, parsed the retained bytes with the
existing structural parser, built a canonical typed declaration tree, and
validated the explicit forwarded subset. The hash-only evidence is recorded in
`docs/baselines/p4b-02-ads-pcie-gen5-parameter-subset-observation.v1.json`.

| profile | bytes | source SHA-256 | selected | tree digest | subset digest |
| --- | ---: | --- | ---: | --- | --- |
| TX | 3280 | `9272e241901d8fa749909e501c6625e508961f581e624c3f64d18a27a2408fb0` | 8 | `85421869e459942647f9767e570f41e5ffa5952cec8220b563f40b79e7836410` | `3aacacef9c2cccf217e33bba24578543f42e29be74f187e97554529a7f3b88bf` |
| RX | 7489 | `9e6206eddd32ab9d1a2ec8237d84608509131f7c3fc309c4f90f44a87f8905c1` | 30 | `c78ad0b4991b48d7b6ccd86b70da7658c1c79e0906085b636920e7d49850d8f9` | `22fa25e1d8c5c7290083f2c5be238fdb230fde62c2a01a000a36c14014820aae` |

The production adapter validates declaration usage, type, value/list format,
finite ranges, explicit selected values, source identity, and canonical tree
identity under fixed work limits. It never resolves a declaration default or
auto-tunes a missing value. The host adapter forwards the unchanged raw text
only after this typed subset verification.

## Boundary

The observation did not load a DLL or call `AMI_Init`/`AMI_GetWave`; the report
explicitly records all three as false. Consequently it establishes at most
that the selected values are represented in an exact external host-forwarded
subset. Vendor consumption, runtime acceptance, rights, transitive dependency
closure, and worker security isolation remain unproven or blocked.
