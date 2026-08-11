# P7-03a Release Archive Admission

P7-03a adds a provisional, no-extract ZIP admission scanner. Its policy is
closed to an exact two-entry capsule: `sipi.exe`, byte-bound to P7-02a stage
evidence, and the root MIT `LICENSE`, byte-bound to the source commit.

The scanner rejects unknown files before classifying them by filename token,
so Python, vendor DLLs, IBIS/AMI assets, fixtures, source trees, and blocked
materials cannot enter by an omitted deny-list spelling. It also rejects ZIP
path bypasses, links, encryption, data descriptors, unsupported archive
features, and configured resource excesses.

The scanner emits only external, digest-based evidence with
`promotion_status: blocked`. It neither creates nor approves a release
archive. A current external observation is intentionally deferred until the
new P7-03a commit has its own P7-01a/P7-02a evidence chain.

An independent Orca review reported no P1 or P2 findings. It noted the
intentional producer-format restriction (no data descriptors or ZIP64) and
the fail-closed private verifier coupling; neither changes the blocked
promotion state.

The external observation was then replayed for commit
`c7c97b27e5cfb508b938cb4f325937f3cdab4b98`. Two fresh locked builds produced
the same `sipi.exe` digest
`cf36303e8997124c8bc1f9d53ea410eb09a6b17431453ef1dd2fb0cca73adfd8`.
The composition evidence remained `incomplete` and blocked. A 318907-byte
external ZIP with that executable and the exact `git archive` bytes of
`LICENSE` passed structural admission. The archive scanner report remains
blocked and records no release approval.
