# P3A Matched Channel Comparator v1

This observer-side gate compares only the selected external `channel_16ghz_3db`
two-port response against the product's matched-S21 discrete V/V kernel. It is
not a product parser, artifact, CLI input, or Link-stage contract.

The observer materializes the exact external Git blob in a temporary directory
and parses only its documented two-port `Hz S RI R 50.0` rows. It creates the
product helper's binary spectrum record by structural field ordering only:
Touchstone `S11, S21, S12, S22` becomes row-major `S11, S12, S21, S22`. It does
not resample, renormalize, fit, window, trim, repair causality, solve
terminations, convolve, or run Python/PyBERT.

The observer independently computes the policy's Hermitian-completed standard
inverse DFT twice and requires exact f64le kernel hashes before starting the
product process. The comparator then requires `N=400`, `dt=25 ps`, finite
index-aligned arrays, and each value to satisfy
`abs(product - observer) <= 1e-9 + 1e-5 * max(abs(product), abs(observer))`.
Any identity, grid, finite-value, determinism, build, record, output, or
comparison failure is rejected.

For source provenance, the product runner is built from a fresh Git archive of
the declared SIPI commit with `--locked`, external target output, and offline
dependency resolution. The report retains only commit/tree/lock/runner hashes,
external source identity, binary-record and kernel hashes, metrics, and
non-claims. It retains no external asset, configuration, or waveform/kernel
array.

Passing this gate establishes only the frozen matched-S21 discrete-kernel
response comparison. It does not establish public Touchstone support,
reflection or multiport behavior, Link/eye/BER parity, default routing, or a
release claim.
