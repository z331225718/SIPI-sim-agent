# Upstream Integration Ledger v5 Audit

Schema: `sipi.upstream-integration-ledger.v5`; status:
`current_clean_candidate_open_no_release`.

This additive v5 snapshot preserves all fifteen rows (15 rows) and the v1-v4 ledgers.
It binds candidate commit `9aeb69173daefc59f77205280931896fed7bf9a8`, tree
`815eda3c7ed2e692588f4f0161b0ff82831e40a7`, and clean archive SHA-256
`e73ac6c8b7cfe816753c058620f7ce3d144b01f948c1be6942db3236f06788ee`.
The archive is 43,458,560 bytes and has no worktree overlay.

AS-05 now records attested external ngspice result consumption and immutable
double-replay evidence. The external solver itself is not verified, numeric
parity is false, the row remains open, and there is no release promotion. The
current observation is mechanically bound to
`docs/baselines/as-05-ngspice-scoped-observation-v2.manifest.json` with SHA-256
`47656c53fda3d39a29b3577945471dbfd21e68dc2f167ad43bfab72aeacb9a55`.

PyBERT now records Rust external-worker and typed-receipt consumption against
a real product-owned mock DLL. Vendor AMI/DLL assets remain external; no real
vendor numeric parity, row close, or promotion is claimed. V1 compatibility is
retained.

COM records the pinned package-case selector as a direct port consumed by the
real selected SNDR/ACCM search consumers, preserving source order and repeats.
Package VTF/S4P FD TwoPort cascade remains missing. The COM route remains
impulse-only and forbids S-parameter fitting. COM rows remain open.

All fifteen rows remain open and `release-ready=0`. No promotion is made from
external solver, vendor asset, mock DLL, scoped observation, selector port, or
source map to global parity or release. The v5 verifier rejects fake promotion, row deletion,
hash drift, AS external-parity promotion, PB vendor claims, and COM VTF/fit
claims.
