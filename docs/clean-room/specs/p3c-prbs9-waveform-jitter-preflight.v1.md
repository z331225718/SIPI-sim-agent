# P3C PRBS9 Waveform And Jitter Preflight v1

This policy records only the user's supplied metric constraints for a future
same-bench ADS reference comparison. It freezes PRBS9 polynomial `x9+x5+1`,
symbols `-1` and `+1`, 32 samples per UI, a shared reference/candidate seed,
strict same-index waveform comparison, no waveform alignment, and a 1 percent
relative RMS limit. NRZ jitter is limited to a crossing-time TIE RMS observable;
SNR is excluded and statistical-eye contour comparison remains blocked.

It deliberately does not choose an LFSR convention, seed, symbol mapping,
sequence hash, UI duration, sample origin, window, reference identity, stage,
RMS normalization formula, crossing rule, interpolation, TIE tolerance, or
statistical-eye source/contour semantics. These omissions are gates, not
defaults. A future implementation must reject execution and acceptance until
the owner supplies them as immutable, machine-verifiable inputs.

The policy cannot load ADS, AMI, IBIS, DLL, PyBERT, or a receiver. It cannot
change release publication, external asset admission, worker admission, or
product capability status.
