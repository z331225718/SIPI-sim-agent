# P3C External ADS Reference Metric Rejection-Reason Evidence v1

This observer-only evidence records the fixed reason token returned by the
already implemented strict-grid metric core for two fresh external runs. It
supersedes only the *cause-unobserved* aspect of the historical CLI-only
rejection record; it does not rewrite that record, alter its source-drift
state, or amend the PRBS9 metric contract.

The report may retain only fixed stage tokens, hashes, byte lengths, clean
archive identity, counts, and product inventory. It must not retain paths,
waveforms, samples, sample indices, metric values, or diagnostic text.

`zero_reference_eye_width` means that the reference eye-width denominator is
structurally zero under the current fixed-fold definition. It is neither a
candidate mismatch nor evidence for an implicit delay correction. Any
delay-aware fold-origin change requires a new owner contract and fresh ADS and
candidate observations.

The observer requires two distinct fresh custody roots and manifests. It
calls the direct core before the sealed-artifact CLI, then requires the CLI's
fixed generic rejection envelope. Any custody, direct-core, CLI-envelope, or
cleanup failure yields no observation. No gate beyond direct reason observation
and reference-input binding may be promoted.
