# P3C Exact-Impulse Replay Identity Reconciliation v3

The preparation, blocked v1 evidence, and recovered v2 evidence remain
byte-for-byte unchanged. Their selected source inventory recorded Windows CRLF
checkout digests while declaring `git_archive_only` materialization.

This additive record reads the seven exact Git objects from commit `7f21b5fc`,
proves that none matches the recorded checkout digest, and separately proves
that LF-to-CRLF transformation explains all seven values. That diagnostic
equivalence is not accepted as canonical source identity.

The historical NRMSE remains a forensic observation, not a current exact
clean-archive replay. Candidate, receiver, policy, and release gates remain
blocked until a new canonical replay is executed.
