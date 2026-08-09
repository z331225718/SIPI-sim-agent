# M5B-04 Candidate Bundle And License Preflight

Status: an explicit Windows x64 candidate-artifact policy only. It does not
promote an executable, alter `engine.lock`, register a resolver, or authorize a
vendor AMI runtime.

`tools/build_m5b_ami_candidate_bundle.py` copies a caller-selected candidate
executable into a new, external artifact directory and writes a versioned
manifest. It requires a clean SIPI source commit, the candidate's `build-info`
declaration for `ami-host-candidate`, the `sipi-circuit` Cargo.lock hash, the
clean-room `sipi-ami` lineage, and Git-object-backed license evidence from
`agent-spice@2cc92316`. No user agent-spice worktree file is read as authority.

The candidate manifest can declare only a system-DLL closure. That declaration
is deliberately not a PE-import scan, an authorization result, or a release
attestation. Vendor DLL, AMI, IBIS, and vendor DLL dependency assets remain
caller-supplied `blocked_unknown` assets. The verifier rejects their presence
in the candidate directory, rejects third-party closure entries, and rejects a
candidate hash or command appearing in the production engine lock.

Example (all output paths are external to the Git worktree):

```text
python tools/build_m5b_ami_candidate_bundle.py --executable <candidate.exe> \
  --output-dir <external-dir> --agent-spice-root C:\Users\z3312\code\agent-spice \
  --system-dll kernel32.dll --system-dll vcruntime140.dll
python tools/verify_m5b_ami_candidate_bundle.py --bundle <external-dir>
```

The generated manifest records input pinning and explicitly labels executable
reproducibility as an observation still required from an independent clean
build. It is neither a substitute for the existing synthetic ABI transport
test nor evidence for a real DLL lifecycle, Python default routing, or AMI
numerical parity.
