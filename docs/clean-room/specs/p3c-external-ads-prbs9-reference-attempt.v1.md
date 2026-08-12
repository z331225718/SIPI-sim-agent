# P3C External ADS PRBS9 Reference Attempt v1

This observer-only tool creates a fresh external ADS run directory containing
only the allowed `channel_gen5_highloss.s4p` source copy and a generated,
explicit PRBS9 bit sequence. It uses the ADS documented Python circuit
simulator path, two complementary `PRBSsrc` sources with their internal
50-ohm output resistance, a four-port Touchstone channel, and two 50-ohm
loads to global ground. No IBIS, AMI, DLL, CDR, equalizer, noise, or
statistical-eye component is accepted or referenced.

The tool records hashes and structural facts externally. It requires a fixed
32 GT/s, OSR-32 output grid, rejects non-finite or off-grid data, retains the
ADS inclusive endpoint only long enough to prove it, then canonicalizes the
contract's half-open 49056-sample payload without resampling or alignment.
Two fresh runs must yield identical canonical payload hashes.

ADS clamps a requested zero PRBS source rise/fall time to 100 as. Therefore
this attempt is a rejected external runtime observation, not an external
reference or any waveform, eye, jitter, receiver, product, AMI, or release
acceptance. The rectangular-NRZ contract remains unchanged until the owner
explicitly disposes of this source-edge mismatch.
