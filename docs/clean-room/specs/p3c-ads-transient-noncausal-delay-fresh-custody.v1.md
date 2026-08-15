# P3C ADS Transient Noncausal-Delay Fresh Custody v1

This harness exists only to run the already-specified read-only policy-surface
observer twice from separately materialized clean Git archives. Each run has a
private temporary archive tree and a private report location. The harness reads
only the observer's hash-only JSON result, requires both canonical results to
be identical, and verifies that its complete temporary custody root no longer
exists before reporting success.

The harness does not launch ADS, create a waveform, retain a report, expose a
runtime option, or turn the documented policy surface into a selected-run delay
action or product algorithm. Cleanup failure rejects the entire observation and
returns no successful result.
