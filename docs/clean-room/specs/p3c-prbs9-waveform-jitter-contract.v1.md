# P3C PRBS9 Waveform And Jitter Contract v1

This contract records the owner-confirmed fixed PRBS9 stimulus and sampled
waveform metrics for a future local ADS same-bench comparison. It defines a
Fibonacci PRBS9 sequence, the nonzero seed and period digest, rectangular NRZ
levels in differential volts, a 32 GT/s timebase at 32 samples per UI, and a
three-period execution window whose third period is the only comparison range.

Waveforms must use the identical sample indices. The contract prohibits time
or phase alignment, resampling, gain/DC/polarity transforms, and zero-reference
normalization. It defines relative waveform RMS, fixed-phase sampled-eye
height/width, and raw NRZ crossing-time TIE RMS plus candidate/reference
crossing-time RMS error. It deliberately does not use CDR.

The ADS bench, reference waveform, and stage identities are still absent, as
is an accepted receiver stage. Therefore this contract is metric-semantics
ready but not acceptance-ready. It does not authorize ADS, AMI, DLL, PyBERT,
channel, receiver, or CDR execution, and cannot promote P4B or release gates.
