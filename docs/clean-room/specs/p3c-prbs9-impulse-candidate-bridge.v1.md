# P3C PRBS9 Impulse Candidate Bridge v1

The only source projection is the owner-confirmed OSR32 right-continuous
mapping: each PRBS9 symbol holds one differential level for its 32 samples,
with a changed level beginning at the UI-boundary sample. The first symbol is
effective at `t=0`; there is no predecessor, sub-strobe interpolation, or ADS
`EdgeShape` parity claim. Three explicit periods are launched with zero
prehistory; the first two are warmup.

The bridge consumes only `SelectedP3cTruncatedResponseV1` with the frozen
10,871-sample selected response and the PRBS9 sample interval. It constructs a
fixed internal LinkPlan and reuses P3B's deterministic direct full linear
convolution. The 59,926-sample tail is calculated before the strict-grid
49,056-sample prefix is exposed; its third-period metric window is
`[32704, 49056)`. No `dt` scale is applied to the discrete taps.

This bridge derives only from the selected P3C truncation leaf, the P1 typed
Link contracts, and the P3B Link-plan/direct-convolution contracts. It does
not alter or broaden P3B's public generic route.

This is neither physical causal-FIR admission nor ADS/COM parity. It does not
perform passivity repair, delay extraction, alignment, resampling, FFT,
circular wrapping, CLI/artifact I/O, receiver processing, reference binding,
metric acceptance, or release promotion.
