# P3C Selected S4P Uniform-Spectrum Observation Evidence v1

## Purpose

This document records one immutable, hash-only external observation of the
already frozen selected-S4P admission and IEEE BSD interpolation leaf. It is
evidence of a successful input admission, not an implementation specification
for an impulse or waveform route.

## Required Facts

The evidence binds the clean-archive commit and source inventory, exact S4P
identity, two distinct sealed-artifact manifests, source before/stage/after
identity checks, report identity, record count, and the admitted uniform-grid
summary. The summary is limited to bin count, frequency step bit pattern,
DC/Nyquist complex bit patterns, and a canonical spectrum digest.

The detailed report, temporary roots, source path and bytes, and spectrum
values remain external. Any future source or runner drift must historicalize
this record rather than rewrite it.

## Gates

Only selected static admission and interpolation observation may be true. IFFT,
causality, delay, passivity repair, truncation, convolution, candidate waveform
generation, oracle binding, receiver acceptance, AMI runtime, P5, and release
promotion remain false.

## Non-Claims

Uniform-spectrum interpolation is not an IFFT, a causal impulse, an ADS or COM
equivalence result, or a candidate/release acceptance result. The historical
exact-grid raw-impulse diagnostic and its non-admission stay unchanged.
