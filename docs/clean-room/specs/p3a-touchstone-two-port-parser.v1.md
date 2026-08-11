# P3A Strict Touchstone Two-Port Parser v1

## Scope

This product-owned clean-room boundary accepts one in-memory ASCII subset of
public Touchstone two-port data and converts it into the existing matched
channel spectrum type. It has no file, URL, CLI, artifact, Link, or external
oracle behavior. It neither resolves a kernel nor changes selected-profile
acceptance.

## Accepted Syntax

The input bytes must be ASCII, contain no NUL, and be valid UTF-8. The parser
accepts LF and CRLF physical lines, blank lines, and `!` comments, including an
inline comment after a data row; every other carriage return is rejected. It
requires exactly one option line before all data:

```text
# Hz S RI R 50.0
```

Each data row is one physical line with exactly nine whitespace-separated
finite numbers:

```text
frequency_hz S11_re S11_im S21_re S21_im S12_re S12_im S22_re S22_im
```

This is the public Touchstone two-port ordering. No continuation records,
implicit defaults, alternate unit/parameter/format tokens, unit conversion, or
renormalization are admitted.

The three caller-provided parsing limits are inclusive maxima for input bytes,
physical-line bytes, and data rows respectively. A document with exactly the
configured number of rows is admitted; its next row is rejected.

## Matched Admission

Admission requires at least two rows, a bit-exact `0.0` Hz first row, a
positive second-row step, strictly increasing frequencies, and a bit-exact
uniform grid where row `k` equals the parsed `f64` expression `k * df`. The
reference impedance is fixed to finite real `50.0` Ohm. The output maps the
public order directly to `TwoPortS { s11, s12, s21, s22 }` without any numeric
transformation.

The existing matched-kernel resolver remains the sole FFT/IFFT implementation.
This boundary does not interpolate, pad, window, trim, fit, de-embed,
renormalize, solve reflections, or derive a Link waveform.

## Rejections and Nonclaims

The parser fail-closes on invalid encoding, non-ASCII input, NUL, malformed or
non-finite data, duplicate/missing/unsupported option lines, limits, missing
DC, reordered or nonuniform grids, and channel-type construction errors.

It is not full Touchstone support, a generic S2P/channel resolver, a CLI route,
selected-profile parity evidence, Link/eye/BER support, or release evidence.
External S2P assets remain observer-only and must not enter this crate or its
tests.
