# P4B ADS PCIe Gen5 Dual AMI Asset Preflight v1

This observer-only boundary identifies exactly five user-provided local ADS
assets: one shared IBIS text, TX/RX AMI texts, and TX/RX Windows x64 DLLs.
It copies only that allowlist into a fresh private directory, rejects path
escape, reparse points, source changes during copying, non-text IBIS/AMI
content, wrong PE architecture, missing ABI exports, or unexpected static
imports. Its report retains only hashes, lengths, logical names, declared
IBIS binding names, AMI root/version labels, and PE import/export facts.

The report is external-only. It retains no asset bytes, parameter trees,
absolute paths, workspace identity, or runnable job. The asset set remains
`external_only_identity_observed_worker_blocked`; it is not admitted to the
worker, product, release, package, default route, or public CLI.

The preflight does not establish runtime loadability, dynamic dependency
closure, third-party rights, IBIS/AMI-version compatibility, TX-to-RX
composition, GetWave behavior, PRBS semantics, CDR/DFE behavior, numerical
parity, or any channel/eye/BER acceptance.
