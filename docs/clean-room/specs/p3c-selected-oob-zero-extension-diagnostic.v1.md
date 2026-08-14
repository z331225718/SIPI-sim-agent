# P3C Selected OOB Zero-Extension Diagnostic v1

This fixed diagnostic consumes only the existing selected 25,601-bin, 20 MHz,
one-sided uniform spectrum. It preserves bins 0 through 2000 exactly, including
the 40 GHz bin, and replaces bins 2001 through 25600 with canonical positive
complex zero. There are no caller-selected cutoffs, tapers, windows, smoothing,
normalization, or best-variant selection.

The result may later be sent through the same bounded causality, truncation,
and fixed PRBS9 convolution path solely to observe sensitivity. It is not a
product interpolation-policy change, an ADS equivalence claim, a causality
bypass, or an accepted candidate. Any external observation must reproduce the
unmodified current baseline separately and retain only hash-only summaries.
