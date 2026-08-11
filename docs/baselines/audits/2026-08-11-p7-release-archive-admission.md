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
