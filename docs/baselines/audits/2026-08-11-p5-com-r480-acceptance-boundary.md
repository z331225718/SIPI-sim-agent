# P5 COM R480 Acceptance Boundary Audit

- Candidate commit: `85531c2`
- Reviewer: Orca independent read-only reviewer
- Review message: `msg_1ccb359f738a`
- Conclusion: **0 P1 / 0 P2**

## Accepted Scope

`com-r480-envelope-v1` is a user-selected required external-oracle profile.
The source is pinned to fresh-clone reproducible `agent-com@5272ffe` and the
R480 envelope Git object is checked by blob and SHA-256. MATLAB source,
workbooks, and fixture data remain external quarantine; they are prohibited
product material and cannot be a runtime fallback.

The product boundary lists only independently named Rust evidence families:
three input identities, selected-channel/equalizer/PDF-stage evidence, and
COM/ERL/TDILN scalar metrics in dB.

## Current Gate

The authoritative reference remains missing. Exact input, oracle runtime
identity, reference metric-bundle hash, and tolerance/alignment policy are
all required before a comparison can begin. The verifier rejects a relaxed
reference state, product self-comparison, and product use of MATLAB material.

## Non-Claims

This acceptance does not implement COM, provide a legacy wire API, reproduce
MATLAB semantics, establish a numerical result or parity, enable a CLI route,
or grant source/release promotion.
