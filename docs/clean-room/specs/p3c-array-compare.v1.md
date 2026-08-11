# P3C Strict Array Comparison v1

## Scope

`sipi-compare` compares two caller-aligned finite arrays. Each array carries
an exact shape, a canonical unit tag, and an opaque SHA-256 semantic-binding
digest. The binding digest is caller-owned and must cover the relevant axis and
interpretation. Both sides must match these identities exactly before any
numeric comparison occurs.

The comparison is directional: reference to candidate. Both tolerance terms
are explicit, finite, and non-negative. For every index, v1 accepts only:

```text
abs(candidate - reference) <= absolute_tolerance
                              + relative_tolerance * abs(reference)
```

No default tolerance, alignment, interpolation, resampling, window, FFT,
sign correction, unit conversion, or domain-specific interpretation exists.

## Identity And Failure

Array identity uses domain-separated SHA-256 over shape, unit, binding digest,
and ordered IEEE-754 `f64` bits. Consequently `-0.0` and `+0.0` compare
numerically equal under zero tolerance but intentionally have different input
identities. Reports expose only these digests and aggregate mismatch metadata,
never complete input arrays or paths.

Missing reference/candidate, malformed shape/unit/binding, non-finite input,
shape/unit/binding mismatch, and non-finite comparison arithmetic are distinct
fail-closed errors. They are not ordinary numeric mismatches.

## Exclusions

This crate has no CLI, filesystem, artifact, oracle, external data, resolver,
metric, or simulation dependency. It does not implement eye, jitter, bathtub,
channel execution, profile comparison, or a `sipi compare` route.
