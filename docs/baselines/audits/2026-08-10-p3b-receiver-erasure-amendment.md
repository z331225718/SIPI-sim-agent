# P3B-03 Receiver Erasure Amendment Audit

- Candidate commit: `6d3c69b`
- Review request: `msg_3e6ba225cb1b`
- Reviewer conclusion: `msg_fb8354d0b3d6`, 0 P1 / 0 P2

The approved amendment fixes the previously unspecified measurement-feedback
case without changing the receiver scope: an exact-zero decision is an error,
feeds back `0.0`, and processing continues through the fixed 96-symbol BER
window. It remains a profile-specific semantic, not a general receiver policy.

The reviewer verified immutable anchors to the approved charter, strict
schema/status verification, and fail-closed rejection of anchor or amendment
drift. It also confirmed that no RFM, Python, engine, CLI, or capability route
was added. External required-profile comparison remains blocked on an
authorized same-source reference-bit vector.

This audit accepts the amendment as implementation input only. It does not
establish receiver implementation or RFM parity.
