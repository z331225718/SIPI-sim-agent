# P3B Required RFM Receiver Boundary v1

## Product Boundary

`sipi.receiver-input.v1` accepts only a product-owned, single-ended receive
voltage waveform. The waveform has a uniform timebase starting at zero, exactly
1024 finite voltage samples, a `1e-12 s` interval, and eight samples per UI.
It carries no RFM model, current vector, port, FFT, engine, fixture, source
path, or external provenance field.

The only v1 frontend is identity: CTLE and FFE are both explicitly `bypass`.
Bypass changes neither voltage sign, amplitude, time index, nor delay. Unknown
or non-bypass stages are rejected at the wire boundary.

## Explicitly Unsupported Stages

| Stage | v1 status | Missing semantic contract |
| --- | --- | --- |
| DFE | unsupported | tap vector, cursor, units, sign, initial state |
| CDR | unsupported | clock source, detector, phase state, lock/reset/cancel |
| BER | unsupported | reference bits, polarity, threshold, alignment, window, metric |

No stage may infer these values from external observations. The accepted RFM
profile supplies only oracle provenance: Windows, a fixed external engine,
current-drive ports 1 to 2, calibrated sign `-1`, 1024 samples, `dt=1e-12 s`,
and eight samples per UI. Those facts are not product input semantics.

## Non-Claims

This boundary does not run RFM, causalize a P3A periodic kernel, implement a
receiver algorithm, establish RFM/Link parity, or enable a default route.
