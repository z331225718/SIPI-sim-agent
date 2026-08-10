# P3B-04 RFM Reference-Bit Source Preflight Audit

- Candidate commit: `2942d6c`
- Review request: `msg_1160472ce7e2`
- Reviewer conclusion: `msg_1b078a9d196c`, 0 P1 / 0 P2

The user authorization is recorded as permission to use an external
observer-only source, not as a parity conclusion. The preflight pins the clean
PyBERT `199696a` stimulus generator, the `f6ba031` RFM Git object, origin,
tree/blob identities, and direct launch-current mapping. It emits only the
hash of a 128-byte `0|1` external sidecar after two fresh temporary replays.

The reviewer verified that the source is direct current generation and not a
waveform threshold, correlation, PRBS guess, or retained receiver decision.
No sidecar, waveform, RFM, Python source, or engine artifact is placed in the
product or Git tree. The profile now records `required_pending_receiver_compare`.

This accepts provenance readiness only. The next gate must independently
replay and hash the receive waveform, invoke the fixed receiver with the
attested bits, and retain its scope-limited non-parity claims until an
appropriate external comparison observable exists.
