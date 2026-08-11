# P4B-05b ADS PCIe Gen5 Dual AMI Asset Preflight

This slice records an observer-only, hash-and-structure preflight for exactly
five user-provided local ADS assets: one shared IBIS file, TX/RX AMI text, and
TX/RX Windows x64 DLLs. No external asset bytes, paths, parameter trees, or
runnable jobs are retained in the repository.

The observer makes one fresh private copy, rejects reparse/path escape and
source changes during materialization, locks the IBIS Executable bindings to
the five-file allowlist, and records only declared AMI root/version plus PE
architecture, required exports, and exact static imports. The manifest is
fixed at `external_only_identity_observed_worker_blocked`: packaging, product,
release, default-runtime, and worker admission all remain prohibited or
blocked. Dynamic closure, rights, runtime behavior, compatibility, TX-to-RX
composition, and numerical evidence are explicitly not claimed.

Verification passed:

```text
python -B tools/observe_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py \
  --external-root <user-provided-external-root> \
  --report <external-report-path> \
  --expected-report-sha256 2734418992a10865943b618e3786b01e578749d3709f4d75f6a812833a0c05b2
python -B tools/test_observe_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py
python -B tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py
python -B tools/test_verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
python -B tools/verify_p4b_external_ami_asset_set.py
python -B tools/test_verify_p4b_external_ami_asset_set.py
python -B tools/test_verify_release_capability_publication.py
```

One Orca OpenCode reviewer performed the required read-only audit. Its first
pass found 0 P1/0 P2 and four P3 hardening gaps. They were addressed before
acceptance: observer tests now cover exact binding, source-change, and report
boundary rejection; the external report digest is also leak-checked; IBIS
Executable names are exact-allowlisted; and the non-claims are exact. The
reviewer's second pass found 0 P1/0 P2 and no remaining blocking gap.

This is not an AMI runtime admission, ADS run, PyBERT composition, PRBS run,
channel/eye/BER acceptance, third-party rights clearance, or release evidence.
