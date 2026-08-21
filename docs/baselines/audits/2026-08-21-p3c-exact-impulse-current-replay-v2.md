# T08 P3C exact impulse replay v2 audit

This additive record supersedes neither the v1 blocked-input evidence nor any
product acceptance record. It records a two-fresh replay after the exact ADS
canonical payload was recovered from the retained external ADS run custody.

## Inputs and custody

- Clean archive: commit `7f21b5fc8f3290b3726d64c1858bd8f013816920`, tree
  `adc84f2ffbe4d755032c452e8181e56603cccf53`.
- Selected S4P: 1,834,156 bytes,
  `25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47`.
- Recovered ADS canonical payload: 1,177,344 bytes,
  `5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726`.
  Ref01 and ref02 are byte-identical.
- Locked/offline external release CLI: 3,975,168 bytes,
  `fd0a4b2115f6cfbe4d12a0ba507bc40e1577fda01a3a994f81b7581a5afc1c98`.
- Hash-only external report: 4,256 bytes,
  `b22366e33c7fd58f83103b7f9b97191f18ab62745632f41d1995084fe6fd58f4`.

Both recovered manifests are 2,479 bytes with SHA-256
`37930afa7f151cd6ca317f17ebb544dfb9c5a56a4a4c455b35f0114dc4fb94f9`.
Their source, dataset, and canonical payload identities match. The retained
netlist bytes are 5,254 bytes with SHA-256
`c6d3df30e2f23dd9181426b2d834bab4cb5990d19a1e48a2b968eb9e79369765`, while
the manifest declares 5,246 bytes with SHA-256
`2784e9e8d42c7ecdc3459b79a5f9cd79cc86131f839c86b1658e8d40b1d9aaf9`.
The bytes are equal after LF newline normalization, but not byte-identical;
the discrepancy is retained as a blocker rather than hidden.

## Replay result

The fixed route was sealed S4P admission, IEEE/BSD interpolation, bounded
causality, truncation, finite-edge v2 full linear convolution, and strict
waveform-only comparison. Two fresh artifact roots were used for each run;
source/reference/candidate manifests were distinct and canonical facts were
equal.

- Candidate payload: `3bc73cc7f1bc09ec03c1266b5a3faa3353e9307e6832a81f51a8c1d55efcec3d`.
- Reference RX payload: `2cf94baf436bd04ff86baeca7d03eab1e6d9a8ce019163d43987a0200eb1bfa5`.
- Candidate waveform digest: `a61375c6fd17edc484ca03697dedfa8f93d1376ed4571ea364f11df0c547baae`.
- Reference waveform digest: `2e0ecb1e37bf7593e6774faaa7d5808a7c4acbf1ae8793f7afbda1b20bbc6e37`.
- Strict third-period NRMSE: `0.02911956313297956` (`3f9dd184cd51df98`).
- Fixed limit: `0.01` (`3f847ae147ae147b`).
- Result: not accepted; the 1% gate is false.

No rational fitting, delay/alignment, gain/DC/polarity transform, parameter
scan, or tolerance relaxation was used. The result does not promote a causal
FIR, receiver, P4B/P5 runtime, or release ledger.
