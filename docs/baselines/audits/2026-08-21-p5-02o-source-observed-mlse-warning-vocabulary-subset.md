# P5-02o source-observed MLSE warning vocabulary subset

This evidence-only slice binds three `warning(...)` call-sites in the pinned
Agent-COM MLSE region. It adds no Rust API and does not implement runtime
warning detection. The source identity is inherited from the existing 25-call
warning observation and the pinned external MATLAB candidate record; both
records are hash-bound without rewriting them.

The subset rule is exact: include `warning(...)` at lines 2109, 2228, and 2238.
Line 2230 is a `msgbox(...)` UI warning dialog and is recorded as an explicit
exclusion rather than silently omitted. The vocabulary is not a complete COM
warning contract and does not define MLSE, DER, CDR, checkpoint, tolerance,
oracle, acceptance, or release semantics.

Validation is document-only unless a separate future observation reopens the
pinned Git object. The verifier checks inherited record hashes, source identity,
entry order, message digests, the excluded call-site, and all non-claims.
