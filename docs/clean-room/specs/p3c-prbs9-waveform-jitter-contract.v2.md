# P3C PRBS9 Waveform And Jitter Contract v2

This owner-authorized amendment supersedes the v1 contract only for the ADS
source transition semantics. The stimulus remains the same explicit Fibonacci
PRBS9 sequence, seed, period digest, differential plateau levels, 32 GT/s
timebase, OSR, window, sample indices, and waveform/eye/jitter metrics.

For the external ADS oracle lane, the waveform is finite-edge NRZ generated
by `ads_prbssrc`, with `EdgeShape=0`, equal 100 as rise and fall literals, a
zero transition reference, and transitions starting at each symbol boundary.
The edge-shape code is a component literal only; this specification does not
infer an interpolation family from it.

This amendment is not runtime evidence. It does not admit an external
reference until two fresh clean-archive ADS runs bind the source, topology,
netlist, waveform hashes, and the v2 contract. It cannot promote candidate
waveform/eye/jitter acceptance, receiver acceptance, AMI/P4B, product runtime,
statistical contour, or release capability.
