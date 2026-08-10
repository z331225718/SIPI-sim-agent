# P4B-05 External AMI Asset Set Acceptance

Implementation commit: `c5de38d`.

The asset-set manifest records only external identities for the pinned
`example_rx` IBIS, AMI text, and DLL. It is Windows x64, external custody only,
and packaging/default/release use are prohibited. The known declared-DLL versus
authorized-asset-name mismatch and the incomplete non-system closure remain
blocked.

The verifier cross-checks the three prior M5B/P4A evidence documents by hash
and asset identity, rejects asset-byte leaks into tracked files, absolute or
drive-qualified paths, unknown fields, duplicate hashes, fake rights states,
and any attempt to mark the current set worker-admitted.

Verification passed:

```text
python -B tools/verify_p4b_external_ami_asset_set.py
python -B tools/test_verify_p4b_external_ami_asset_set.py
python -B tools/verify_product_boundary.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_release_license_preflight.py
python -B tools/verify_rust_candidate_source_map.py
python -B tools/verify_acceptance_profiles.py
```

One Orca reviewer audited the slice in `msg_8ebc476b4e8a`: 0 P1 and 0 P2.
Its two P3 hardening notes were addressed before this acceptance commit: logical
asset names reject path syntax and source references reject drive-qualified
paths.

This accepts only machine-verifiable external asset-set admission policy. It
does not accept vendor runtime interoperability, a complete DLL closure,
third-party rights clearance, AMI/IBIS parity, a sandbox, or release readiness.
