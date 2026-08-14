# Selected High-Loss PRBS9 Waveform-Only v3

Scope is one immutable selected high-loss raw post-channel profile. This does
not alter the v2 waveform/eye/TIE profile and is not a generic closed-eye
fallback.

Inputs are two sealed, finite, differential-voltage waveforms. Each contains
three 511-UI PRBS9 periods at 32 samples/UI. The consumer validates 49,056
binary64 samples per waveform and compares only `[32704, 49056)` by original
sample index.

The only result is
`sqrt(sum((candidate-reference)^2)/sum(reference^2)) <= 0.01`. A zero
reference norm, non-finite value, malformed artifact, identity drift, extra
file, or resource violation rejects. No alignment, resampling, gain fit, DC
removal, polarity flip, phase/fold adjustment, CDR, eye metric, or crossing
metric is permitted.

The public route accepts opaque reference/candidate artifact IDs plus their
manifest digests. Its v3 request and waveform metadata schemas are distinct
from v2 and cannot select a metric mode. Results may state only waveform NRMSE
and whether this selected waveform-only profile is within its fixed limit.

This slice neither binds external provenance nor accepts a receiver, physical
causality/FIR, 100-as ADS parity, eye/TIE/statistical-eye behavior, P4B/P5, or
release promotion.
