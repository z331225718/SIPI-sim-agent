# P3B Approved Fixed Receiver Erasure Amendment v1

This owner-approved amendment completes the measurement-feedback branch of
`p3b-approved-fixed-receiver.v1`. When a measurement value is exactly zero,
the receiver records an erasure and an error, appends `0.0` as that symbol's
DFE feedback value, and continues processing the remaining measurement UI.
Consecutive erasures use the same feedback rule. The BER denominator remains
96; no erasure is converted into a positive or negative hard decision.

This is a profile-scoped receiver semantic. It does not introduce RFM,
Python, external-engine, or oracle inputs to product code.
