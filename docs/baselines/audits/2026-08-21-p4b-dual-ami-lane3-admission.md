# P4B Dual AMI Lane 3 Admission Audit

- Date: 2026-08-21
- Scope: P4B only; ADS PCIe Gen5 TX/RX AMI admission sequence
- Result: additive blocker; no vendor DLL was loaded or invoked

## Serial Review

1. Custody and identity: the TX/RX `.ami` and DLL files were rehashed in their
   external ADS workspace. Their byte lengths and SHA-256 values match the
   existing authorized-material registry and asset-preflight record. The
   selected profile is the existing Windows x64 TX+RX pair, not either model
   in isolation.
2. Rights: the workspace contains no hash-bound vendor license or run grant
   for these exact assets. Owner choice `D5=A/E4=A` authorizes the proposed
   external-only procedure, but it does not establish third-party runtime
   rights. The sequence therefore stops before any DLL load.
3. Parameters: the production worker and host now expose a narrow
   `AmiForwardedParameterSubsetV1` adapter for the selected external TX/RX
   texts. Two fresh reads produce hash-only canonical tree/subset evidence
   (eight TX and thirty RX selected values). The adapter validates explicit
   type/format/range/usage identity and forwards unchanged raw text only after
   that check. A vendor `.ami` declaration or host-forwarded subset is not
   proof that a DLL consumes a parameter. The P4B-02 decision is therefore
   `external_asset_oracle`, not vendor-runtime acceptance.
4. Loader closure: the existing static PE record establishes AMD64, three AMI
   exports, and direct imports. It explicitly does not establish transitive
   dynamic dependency or sidecar closure.
5. Isolation and runtime: `sipi-ami-worker` provides bounded process and
   artifact mechanics, but its own contract says it is not a security sandbox.
   It is therefore not an admitted boundary for this vendor runtime. Neither
   `AMI_Init` nor `AMI_GetWave` was invoked in this review.

## Unblock Inputs

- A vendor or license-administrator grant bound to the exact TX/RX asset
  identities, explicitly allowing private Windows x64 execution and covering
  required sidecars and non-system dependencies.
- Vendor-runtime telemetry remains required before any DLL-consumption claim;
  the current hash-only subset evidence is intentionally not runtime evidence.
- A complete static/transitive dependency inventory and an approved external
  security isolation boundary with timeout, crash containment, output budget,
  and close-on-termination policy.
- Only after all earlier gates pass: fresh isolated `AMI_Init` and
  `AMI_GetWave` evidence retaining hashes and bounded aggregates, never raw
  vendor assets.

No vendor asset bytes, absolute paths, parameter values, or runtime output are
stored in the repository by this audit.
