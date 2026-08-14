# P3C External ADS Reference Metric Observation Audit

Scope: P3C-04aa external reference-binding and rejected metric-evaluation
evidence, including the ignored runner, hash-only baseline, verifier, and
mutation tests.

OpenCode read-only audit: 0 P1 / 0 P2 after two corrections. The runner now
uses the already-authorized eight-ULP ADS time-grid tolerance and records only
CLI exit 3 as an observed contract rejection. Other CLI failures remain
fail-closed. The final verifier binds the recorded clean commit to its actual
tree and rejects tree drift.

Verified evidence: two fresh external runs both produced the same 220-byte,
hash-only rejection report. No waveform bytes, paths, or diagnostic streams
were retained. The rejected result does not promote waveform, eye, TIE,
receiver, profile, or release acceptance.
