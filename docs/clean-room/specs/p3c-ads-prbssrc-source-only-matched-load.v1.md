# P3C ADS PRBSsrc Source-Only Matched-Load Charter v1

This external-only charter isolates the ADS PRBSsrc strobe semantics from the
selected channel chain. It is intentionally blocked until the owner confirms
the two 50 ohm-to-ground loads, the fixed half-scale Thevenin mapping, and the
diagnostic-only UI boundary/interior partition.

The runner may materialize only two complementary explicit-bit PRBSsrc sources,
two 50 ohm loads, one transient controller, and `V(txp)-V(txm)`. It must reject
S4P/channel, RX, AMI, IBIS, DLL, GetWave, CDR, alignment, resampling, fitted
gain, delay/phase shifting, DC removal, and polarity changes. A successful
future observation is evidence about this source-only topology only; it cannot
change product source policy or establish channel/ADS parity, candidate
acceptance, receiver acceptance, or release readiness.
