# P7 Evidence Anchor v1

This document defines a product-governance record that binds a bounded set of
external provisional evidence hashes to two immutable Git commits. It is not
a release candidate, release tag, package, signature, or promotion decision.

`record_commit` identifies the Git commit that recorded the external evidence.
`candidate_source_commit` identifies the separately measured source commit.
They are intentionally distinct. The anchor also records the candidate tree,
locked build inputs, executable identity, and report digests without storing
paths, payloads, assets, machine details, or measurement samples.

Validation requires both commits and the candidate tree to be reachable from
the local Git object database, all report identities to be exact SHA-256
strings, a safe relative audit reference, and nonempty release blockers. The
anchor always has `promotion_status=blocked` and `release_candidate=false`.
It must retain the current license/NOTICE, fresh-machine, and uncertified
profile blockers.

An optional external evaluation file can be checked against the anchor. This
does not copy the report into the repository: it only confirms the report's
digest and its candidate, policy, evidence, threshold, and blocked-promotion
fields. No filesystem path or external asset may become part of the record.
